import os
import re
import time

import requests as r
from sqlalchemy.orm import Session

from logger import Logger
from models import Payout, PayoutActionEnum
from settings import Settings
from tg import Tg


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
    is_auth: bool = False

    def __init__(self, session: r.Session, settings: Settings, tg: Tg, logger: Logger):
        self.session = session
        self.settings = settings
        self.tg = tg
        self.tg.api = self
        self.logger = logger

        self.turcode_login = os.getenv('TURCODE_LOGIN', None)
        self.turcode_password = os.getenv('TURCODE_PASSWORD', None)

        logger.info(f'<{settings.bot_name}> API initialized')

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

    def auth(self):
        # Предотвращаем бесконечную авторизацию
        if self.turcode_login is None or self.turcode_password is None:
            return

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
            auth_cookie = request.headers.get('Set-Cookie')
            if auth_cookie is not None:
                auth_cookie = auth_cookie.replace('auth=', '').strip().replace('auth=', '')
                self.settings['auth_cookie'] = auth_cookie
        except r.exceptions.RequestException as e:
            self.logger.error('Ошибка запроса:', e)
            return

        self.is_auth = True

    def get_payouts(self):
        if not self.is_auth:
            self.auth()

        if not self.is_auth:
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
            auth_cookie = request.headers.get('Set-Cookie')
            if auth_cookie is not None:
                auth_cookie = auth_cookie.replace('auth=', '').strip().replace('auth=', '')
                self.settings['auth_cookie'] = auth_cookie
        except r.exceptions.RequestException as e:
            self.logger.error('Ошибка запроса:', e)
            return []

        try:
            request_data = request.json()
            self.auth_error_count = 0
        except r.exceptions.JSONDecodeError:
            self.is_auth = False

            self.auth_error_count += 1
            if self.auth_error_count >= 3:
                self.auth_error_count = 0
                return []
            else:
                return self.get_payouts()

        self.is_auth = True
        self.auth_error_count = 0
        return request_data['data']

    # Забираем платеж
    def claim_payout(self, payout) -> bool:
        if not self.is_auth:
            self.auth()

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
            self.logger.error('Ошибка запроса:', e)
            return False

        self.logger.info(request.status_code, request.text)

        try:
            request_data = request.json()
        except r.exceptions.JSONDecodeError as e:
            self.logger.error(f'Ошибка запроса  {request.status_code} {request.text}:', e)
            return False

        with Session(self.settings.engine) as session, session.begin():
            payout_row = Payout(
                operation_id=payout.get('operation_id', ''),
                user_id=payout.get('user_id', ''),
                amount=self.str_to_int(payout.get('amount', 0)),
                bot_name=self.settings.bot_name,
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

    # Получаем обработанные платежи
    def load_payouts(self):
        payouts_count_limit = self.settings.get('payouts_limit', 10)
        if self.claimed_payouts_count is None or self.claimed_payouts_count >= payouts_count_limit:
            self.claimed_payouts_count = 0
            all_payouts = self.get_payouts()
            for row in all_payouts:
                self.claimed_payouts_count += 0 if not row[2] else 1

        if self.claimed_payouts_count >= payouts_count_limit:
            return []

        payouts = []
        self.claimed_payouts_count = 0
        for row in self.get_payouts():
            is_able = not row[2]
            if not is_able:
                self.claimed_payouts_count += 1
                continue

            claim_btn = row[3]
            payout_id = claim_btn.split('data-id=')[1].split("'")[1]

            card = row[8]
            card_match = re.search(r'\d+', card)
            if card_match:
                card = card_match.group(0)

            payout = {
                'time': row[0],
                'status': row[1],
                'id': payout_id,
                'amount': row[5],
                'card': card,
                'operation_id': row[15],
                'user_id': row[16],
            }

            self.logger.info(f'Найден платеж: {payout}')
            self.settings.notifications['admins'].append(f'Найден платеж ({time.time()})\n\n{self.dict_to_str(payout)}')
            payouts.append(payout)

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
                self.logger.error(f'Ошибка при опросе {ip} method webstats: {e}')
                host_data = None

            result.append(host_data)

        return result
