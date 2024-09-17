import datetime
import os
import re
import time

import requests as r
from sqlalchemy.orm import Session

from code.db import DB
from code.logger import Logger
from code.models import Payout, PayoutActionEnum
from code.settings import Settings
from code.tg import Tg


class API:
    session: r.Session
    settings: Settings
    db: DB
    tg: Tg
    logger: Logger

    claimed_payouts = set()

    auth_error_count: int = 0
    claimed_payouts_count: int | None = None

    base_url = 'https://api.turcode.app'
    headers = {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    }
    auth_cookie: str = None

    turcode_login: str
    turcode_password: str
    is_auth: bool = True

    def __init__(self, session: r.Session, settings: Settings, db: DB, tg: Tg, logger: Logger):
        self.session = session
        self.settings = settings
        self.db = db
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

    async def check_claimed_payouts(self):
        async with self.settings.db_session() as session:
            claimed_payouts = self.claimed_payouts.copy()
            self.claimed_payouts = set()
            for operation_id in claimed_payouts:
                payouts = await Payout.get_not_gained_by_operation_id(session, operation_id)
                if not payouts:
                    continue

                for payout in payouts:
                    payout.is_claimed = True
                    session.add(payout)

                payout = payouts[0]
                success_msg = (
                    f'Платеж забран\n'
                    f'Сумма - 💰{payout.amount}💰\n'
                    f'Карта - 💸{payout.card}💸'
                )

                if len(payouts) > 1:
                    success_msg += '\n\n‼️Кажется, этот платеж уже забирался‼️'

                self.settings.notifications.add_to_all(success_msg)
            await session.commit()

    async def update_bot_claimed_payouts_count(self):
        async with self.settings.db_session() as session:
            claimed_payouts_count = self.claimed_payouts_count
            if claimed_payouts_count is None:
                claimed_payouts_count = 0
            await self.db.cur_bot.set_claimed_payouts_count(session, claimed_payouts_count)

    async def auth(self):
        # Предотвращаем бесконечную авторизацию
        if self.turcode_login is None or self.turcode_password is None:
            return

        await self.tg.notify_admins('Авторизовался')

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
                self.auth_cookie = auth_cookie

                async with self.settings.db_session() as session:
                    await self.db.cur_bot.set_auth_cookie(session, auth_cookie)
                    await session.commit()

                self.session.cookies.set('auth', auth_cookie)
        except r.exceptions.RequestException as e:
            self.logger.error('Request error:', e)
            return

        self.is_auth = True

    async def get_payouts(self):
        if not self.is_auth:
            await self.auth()

        if not self.is_auth:
            self.logger.info(f'{self.is_auth=}')

            async with self.settings.db_session() as session:
                await self.db.cur_bot.set_is_running(session, False)
                await session.commit()
            await self.db.load_bots()

            await self.tg.notify_admins('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            await self.tg.notify_watchers('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            return []

        form_data = {
            'length': 100,
            'pfrom': self.db.all_active_bots_min_amount,
            'pto': self.db.all_active_bots_max_amount,
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
                async with self.settings.db_session() as session:
                    await self.db.cur_bot.set_is_running(session, False)
                    await session.commit()
                await self.db.load_bots()

                await self.tg.notify_admins('Меня блокнуло\nВыключаю штуку')
                await self.tg.notify_watchers('Меня блокнуло\nВыключаю штуку')
                return []

            auth_cookie = self._extract_auth_cookie(request.headers.get('Set-Cookie'))
            if auth_cookie is not None:
                self.auth_cookie = auth_cookie
                self.session.cookies.set('auth', auth_cookie)
        except r.exceptions.RequestException as e:
            self.logger.error('Request error:', e)
            return []

        if request.status_code == 429:
            await self.tg.notify_admins('Код 429')
            time.sleep(4)
            return []

        try:
            request_data = request.json()
            self.auth_error_count = 0
        except r.exceptions.JSONDecodeError:
            self.auth_error_count += 1

            if self.auth_error_count > 5:
                self.is_auth = False

                async with self.settings.db_session() as session:
                    await self.db.cur_bot.set_auth_cookie(session, auth_cookie)
                    await session.commit()
                await self.db.load_bots()

                await self.tg.notify_admins('Выкинуло\nВыключаю штуку')
                await self.tg.notify_watchers('Выкинуло\nВыключаю штуку')

            return []

        self.is_auth = True
        self.auth_error_count = 0
        return request_data['data']

    # Забираем платеж
    async def claim_payout(self, payout) -> bool:
        # if not self.is_auth:
        #     self.auth()

        bot_to_claim = await self.db.get_bot_by_amount(self.str_to_int(payout.get('amount', 0)))
        if bot_to_claim is None:
            return False

        if bot_to_claim.claimed_payouts_count >= bot_to_claim.claimed_payouts_limit:
            return False

        # # Чекаем забирался ли платеж другим ботом
        # with Session(self.settings.engine) as session, session.begin():
        #     all_bots_operation_payouts_count = Payout.get_count_by_operation_id(
        #         session=session,
        #         operation_id=payout['operation_id'],
        #     )
        #     if all_bots_operation_payouts_count > 0:
        #         return False

        # self.settings.notifications.admins.append(f'Пробую забрать платеж ({time.time()})')
        form_data = {
            'id': payout['id'],
            'mode': 'claim',
        }

        if bot_to_claim.id != self.db.cur_bot.id:
            session = r.Session()
            session.cookies.set('auth', bot_to_claim.auth_cookie)
        else:
            session = self.session

        try:
            request = session.post(
                f'{self.base_url}/prtProcessPayoutsOwnership.php',
                data=form_data,
                headers=self.headers,
            )
            # self.settings.notifications.admins.append(
            #     f'Ответ системы ({time.time()})\n\n'
            #     f'status - {request.status_code}\n'
            #     f'text - {request.text}'
            # )
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
                bot_name=bot_to_claim.bot_name,
                # bank_name=erow(payout.get('bank', None)),
                card=erow(payout.get('card', None)),
                phone=erow(payout.get('phone', None)),
                payout_id=erow(payout.get('id', None)),
            )
            if request_data['status']:
                # success_msg = (
                #     f'Платеж забран\n'
                #     f'Сумма - 💰{payout['amount']}💰\n'
                #     f'Карта - 💸{payout['card']}💸'
                # )

                # Чекаем забирал ли текущий бот этот платеж
                # cur_bot_operation_payouts_count = Payout.get_count_by_operation_id_and_bot_name(
                #     session=session,
                #     bot_name=self.settings.bot_name,
                #     operation_id=payout['operation_id'],
                # )
                # if cur_bot_operation_payouts_count > 0:
                #     success_msg += '\n\n‼️Кажется, этот платеж уже забирался‼️'
                #
                # self.settings.notifications.admins.append(success_msg)
                # self.settings.notifications.watchers.append(success_msg)

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
    async def load_payouts(self):
        payouts_count_limit = self.db.cur_bot.claimed_payouts_limit
        if self.claimed_payouts_count is None or self.claimed_payouts_count >= payouts_count_limit:
            self.claimed_payouts_count = 0
            await self.tg.notify_admins('Обновляю claimed_payouts_count')
            all_payouts = await self.get_payouts()
            for row in all_payouts:
                if row[3]:
                    self.claimed_payouts.add(row[16])
                    self.claimed_payouts_count += 1

            time.sleep(2)

        if self.claimed_payouts_count >= payouts_count_limit:
            return []

        _time_ending_notified_payouts = []
        payouts = []
        self.claimed_payouts_count = 0
        for row in await self.get_payouts():
            claim_btn = row[2]
            payout_id = claim_btn.split('data-id=')[1].split("'")[1]

            is_able = not row[3]
            if not is_able:
                self.claimed_payouts.add(row[16])
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
                                               f'Operation ID: {row[16]} Сумма: {row[6]}')
                            self.settings.notifications.add_to_all(remind_msg_text)

                continue
            card = row[9]
            card_match = re.search(r'\d+', card)
            if card_match:
                card = card_match.group(0)

            payout = {
                'time': row[0],
                'status': row[1],
                'id': payout_id,
                'amount': row[6],
                'bank': row[8],
                'card': card,
                'phone': row[15],
                'operation_id': row[16],
                'user_id': row[17],
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
            # self.settings.notifications.admins.append(f'Найден платеж ({time.time()})\n\n{self.dict_to_str(payout)}')
            payouts.append(payout)

        self.time_ending_notified_payouts = _time_ending_notified_payouts
        return payouts

    async def get_stats(self) -> list:
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
