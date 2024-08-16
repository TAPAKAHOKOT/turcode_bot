import datetime
import os
import re
import time

import requests as r
from sqlalchemy.orm import Session

from code.logger import Logger
from code.models import Payout, PayoutActionEnum
from code.settings import Settings
from code.tg import Tg


class API:
    session: r.Session
    settings: Settings
    tg: Tg
    logger: Logger

    auth_error_count = 0
    claimed_payouts_count = None

    base_url = 'https://api.turcode.app'
    headers = {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    }

    turcode_login: str
    turcode_password: str
    is_auth: bool = True

    def __init__(self, session: r.Session, settings: Settings, tg: Tg, logger: Logger):
        self.session = session
        self.settings = settings
        self.tg = tg
        self.tg.api = self
        self.logger = logger

        self.turcode_login = os.getenv('TURCODE_LOGIN', None)
        self.turcode_password = os.getenv('TURCODE_PASSWORD', None)

        logger.info(f'<{settings.bot_name}> API initialized')

        self.time_ending_notified_payouts = []

    # Словарь переводим в читаемую строку
    def dict_to_str(self, dict_item):
        res = ''
        for key, value in dict_item.items():
            res += f'{key} - {value}\n'
        return res

    def str_to_int(self, num: str) -> int:
        try:
            num = int(float(str(num).replace(',', '')))
        except:
            num = 0
        return num

    def _extract_auth_cookie(self, cookies):
        try:
            return cookies.split('auth=')[1].split(';')[0]
        except:
            self.tg.notify_admins(f'Что-то не так с куками... {cookies}')

            return None

    def auth(self):
        # Предотвращаем бесконечную авторизацию
        if self.turcode_login is None or self.turcode_password is None:
            return

        self.tg.notify_admins('Авторизовался')

        form_data = {
            'login': self.turcode_login,
            'password': self.turcode_password,
            'authenticator': '',
        }
        try:
            request = self.session.post(
                f'{self.base_url}/authUser.php',
                data=form_data,
                headers=self.headers,
            )
            auth_cookie = self._extract_auth_cookie(request.headers.get('Set-Cookie'))
            if auth_cookie is not None:
                self.settings['auth_cookie'] = auth_cookie
                self.session.cookies.set('auth', self.settings['auth_cookie'])
        except r.exceptions.RequestException as e:
            self.logger.error('Request error:', e)
            return

        self.is_auth = True

    def get_payouts(self):
        if not self.is_auth:
            self.auth()

        if not self.is_auth:
            self.logger.info(f'{self.is_auth=}')
            self.settings['is_running'] = False
            self.tg.notify_admins('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            self.tg.notify_watchers('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            return []

        form_data = {
            'length': 100,
            'pfrom': self.settings.get('min_amount', None),
            'pto': self.settings.get('max_amount', None),
            'fstatus': 'Pending',
            'ftime': 'All',
        }

        try:
            request = self.session.post(
                f'{self.base_url}/datatables/payouts.php',
                data=form_data,
                headers=self.headers,
            )

            if 'blocked' in request.text:
                self.settings['is_running'] = False
                self.tg.notify_admins('Меня блокнуло\nВыключаю штуку')
                self.tg.notify_watchers('Меня блокнуло\nВыключаю штуку')
                return []

            auth_cookie = self._extract_auth_cookie(request.headers.get('Set-Cookie'))
            if auth_cookie is not None:
                self.settings['auth_cookie'] = auth_cookie
                self.session.cookies.set('auth', self.settings['auth_cookie'])
        except r.exceptions.RequestException as e:
            self.logger.error('Request error:', e)
            return []

        if request.status_code == 429:
            self.tg.notify_admins('Код 429')
            time.sleep(4)
            return []

        try:
            request_data = request.json()
            self.auth_error_count = 0
        except r.exceptions.JSONDecodeError:
            self.auth_error_count += 1

            if self.auth_error_count > 5:
                self.is_auth = False
                self.settings['is_running'] = False
                self.tg.notify_admins('Выкинуло\nВыключаю штуку')
                self.tg.notify_watchers('Выкинуло\nВыключаю штуку')

            return []

        self.is_auth = True
        self.auth_error_count = 0
        return request_data['data']

    # Забираем платеж
    def claim_payout(self, payout) -> bool:
        # if not self.is_auth:
        #     self.auth()

        payouts_count_limit = self.settings.get('payouts_limit', 10)
        if self.claimed_payouts_count >= payouts_count_limit:
            return False

        # Чекаем забирался ли платеж другим ботом
        with Session(self.settings.engine) as session, session.begin():
            all_bots_operation_payouts_count = Payout.get_count_by_operation_id(
                session=session,
                operation_id=payout['operation_id'],
            )
            if all_bots_operation_payouts_count > 0:
                return False

        self.settings.notifications['admins'].append(f'Пробую забрать платеж ({time.time()})')
        form_data = {
            'id': payout['id'],
            'mode': 'claim',
        }

        try:
            request = self.session.post(
                f'{self.base_url}/prtProcessPayoutsOwnership.php',
                data=form_data,
                headers=self.headers,
            )
            self.settings.notifications['admins'].append(
                f'Ответ системы ({time.time()})\n\n'
                f'status - {request.status_code}\n'
                f'text - {request.text}'
            )
        except r.exceptions.RequestException as e:
            self.logger.error('Request error:', e)
            return False

        self.logger.info(request.status_code, request.text)

        try:
            request_data = request.json()
        except r.exceptions.JSONDecodeError as e:
            self.logger.error(f'Request error  {request.status_code} {request.text}:', e)
            return False

        def erow(row: str):
            if row is None:
                return None
            return row.encode('latin-1', 'ignore').decode('utf-8', 'ignore')

        with Session(self.settings.engine) as session, session.begin():
            payout_row = Payout(
                operation_id=payout.get('operation_id', ''),
                user_id=payout.get('user_id', ''),
                amount=self.str_to_int(payout.get('amount', 0)),
                bot_name=self.settings.bot_name,
                # bank_name=erow(payout.get('bank', None)),
                card=erow(payout.get('card', None)),
                phone=erow(payout.get('phone', None)),
                payout_id=erow(payout.get('id', None)),
            )
            if request_data['status']:
                success_msg = (
                    f'Платеж забран\n'
                    f'Сумма - 💰{payout['amount']}💰\n'
                    f'Карта - 💸{payout['card']}💸'
                )

                # Чекаем забирал ли текущий бот этот платеж
                cur_bot_operation_payouts_count = Payout.get_count_by_operation_id_and_bot_name(
                    session=session,
                    bot_name=self.settings.bot_name,
                    operation_id=payout['operation_id'],
                )
                if cur_bot_operation_payouts_count > 0:
                    success_msg += '\n\n‼️Кажется, этот платеж уже забирался‼️'

                self.settings.notifications['admins'].append(success_msg)
                self.settings.notifications['only_taken'].append(success_msg)

                payout_row.action = PayoutActionEnum.SUCCESS.code
                session.add(payout_row)
                session.flush()

                self.claimed_payouts_count += 1
                return True
            else:
                payout_row.action = PayoutActionEnum.FAIL.code
                session.add(payout_row)
                session.flush()

        return False

    def get_webstats(self) -> list:
        try:
            form_data = {
                'draw': 100,
                'start': 0,
                'length': 100,
            }

            request = self.session.post(
                f'{self.base_url}/datatables/tstats.php',
                data=form_data,
            )
        except r.exceptions.RequestException as e:
            return []

        try:
            request_data = request.json()
        except r.exceptions.JSONDecodeError as e:
            return []

        result = []
        for row in request_data.get('data', []):
            result.append({
                'username': re.sub(r'<.*?>', '', row[1]),
                'balance': self.str_to_int(row[2]),
                'payouts_sum_for_24h': self.str_to_int(row[6]),
                'payouts_count_for_24h': row[7],
            })
        return result

    # Получаем обработанные платежи
    def load_payouts(self):
        payouts_count_limit = self.settings.get('payouts_limit', 10)
        if self.claimed_payouts_count is None or self.claimed_payouts_count >= payouts_count_limit:
            self.claimed_payouts_count = 0
            all_payouts = self.get_payouts()
            for row in all_payouts:
                self.claimed_payouts_count += 0 if not row[2] else 1

            time.sleep(2)

        if self.claimed_payouts_count >= payouts_count_limit:
            return []

        _time_ending_notified_payouts = []
        payouts = []
        self.claimed_payouts_count = 0
        for row in self.get_payouts():
            claim_btn = row[3]
            payout_id = claim_btn.split('data-id=')[1].split("'")[1]

            is_able = not row[2]
            if not is_able:
                self.claimed_payouts_count += 1
                end_time = row[4].split('data-end-time=')[1].split("'")[1]
                try:
                    end_time = int(end_time) // 1000
                    end_time -= 6 * 60 * 60
                except ValueError:
                    continue

                now_time = datetime.datetime.utcnow().timestamp()
                time_diff = end_time - now_time

                for _msg_text, check_fun in [
                    ['Осталось 15 минут', lambda _time_diff: 14 * 60 < time_diff < 15 * 60],
                    ['Осталось 5 минут', lambda _time_diff: 4 * 60 < time_diff < 5 * 60],
                ]:
                    if check_fun(time_diff):
                        _time_ending_notified_payouts.append(payout_id)
                        if payout_id not in self.time_ending_notified_payouts:
                            remind_msg_text = (f'❗️У платежа заканчивается время для оплаты\n'
                                               f'{_msg_text}\n'
                                               f'Operation ID: {row[15]} Сумма: {row[5]}')
                            self.settings.notifications['admins'].append(remind_msg_text)
                            self.settings.notifications['only_taken'].append(remind_msg_text)

                continue
            card = row[8]
            card_match = re.search(r'\d+', card)
            if card_match:
                card = card_match.group(0)

            payout = {
                'time': row[0],
                'status': row[1],
                'id': payout_id,
                'amount': row[5],
                'bank': row[7],
                'card': card,
                'phone': row[14],
                'operation_id': row[15],
                'user_id': row[16],
            }

            bank_is_correct = False
            lower_payout_bank = payout['bank'].lower()
            for bank_name in [
                'Тинькофф',
                'Tinkoff',
                'T-Bank',
                'Сбербанк',
                'Sberbank',
                # 'Райффайзен',
                # 'Raiffeisen',
            ]:
                if bank_name.lower() in lower_payout_bank:
                    bank_is_correct = True
                    break

            if not bank_is_correct and not (len(payout['card']) == 11 or len(payout['phone']) == 11):
                continue

            self.logger.info(f'Payout found: {payout}')
            self.settings.notifications['admins'].append(f'Найден платеж ({time.time()})\n\n{self.dict_to_str(payout)}')
            payouts.append(payout)

        self.time_ending_notified_payouts = _time_ending_notified_payouts
        return payouts

    def get_stats(self) -> list:
        webapp_list = os.getenv('WEBAPP_LIST', default=None)
        if webapp_list is None:
            return []

        webapp_list = list(map(lambda l: l.split('::'), webapp_list.split(';')))

        result = []
        for ip, password in webapp_list:
            try:
                host_data = r.get(f'{ip}/webstats', headers={'Authorization': f'Bearer {password}'}).json()
            except r.exceptions.RequestException as e:
                self.logger.error(f'Ping {ip} error method webstats: {e}')
                host_data = None

            result.append(host_data)

        return result
