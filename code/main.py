import signal
import sys
import time

import requests as r
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from settings import Settings
from logger import Logger
from stats import write_stat
from tg import Tg

logger = Logger()


# Настраиваем сигналы закрытия программы
def onexit(*args, **kwargs):
    settings.save()
    logger.info(f'Программа остановлена')
    sys.exit(0)


signal.signal(signal.SIGINT, onexit)
signal.signal(signal.SIGTERM, onexit)


# Словарь переводим в читаемую строку
def dict_to_str(dict_item):
    res = ''
    for key, value in dict_item.items():
        res += f'{key} - {value}\n'
    return res


# Дефолтные настройки
FILE_PATH = 'settings.json'
BASE_URL = 'https://api.turcode.app'
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
}

# Загрузка настроек
settings = Settings(FILE_PATH, logger)
settings.load()

logger.info('Настройки:', settings)

# API
# Получаем платежи по апи
auth_error_count = 0


def get_payouts(session):
    global auth_error_count

    form_data = {
        'length': 100,
        'pfrom': settings.get('min_amount', None),
        'pto': settings.get('max_amount', None),
        'fstatus': 'Pending',
        'ftime': 'All',
    }

    try:
        request = session.post(
            f'{BASE_URL}/datatables/payouts.php',
            data=form_data,
            headers=HEADERS,
        )
        auth_cookie = request.headers.get('Set-Cookie')
        if auth_cookie is not None:
            auth_cookie = auth_cookie.replace('auth=', '').strip().replace(
                'auth=', '')
            settings['auth_cookie'] = auth_cookie
    except r.exceptions.RequestException as e:
        logger.error('Ошибка запроса:', e)
        return []

    logger.info(request.status_code, request.text)

    try:
        request_data = request.json()
    except r.exceptions.JSONDecodeError as e:
        # logger.error(f'Ошибка запроса {request.status_code} {request.text}:', e)

        auth_error_count += 1
        if auth_error_count >= 10:
            settings['is_running'] = False
            auth_error_count = 0
            tg.notify_admins('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            tg.notify_watchers('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')

        return []

    auth_error_count = 0
    return request_data['data']


# Забираем платеж
def claim_payout(payout) -> bool:
    global notifications, metrics

    # same_payouts_count = get_same_payouts_count(payout['operation_id'], payout['user_id'])

    notifications['admins'].append(f'Пробую забрать платеж ({time.time()})')
    form_data = {
        'id': payout['id'],
        'mode': 'claim',
    }

    try:
        request = session.post(
            f'{BASE_URL}/prtProcessPayoutsOwnership.php',
            data=form_data,
            headers=HEADERS,
        )
        notifications['admins'].append(
            f'Ответ системы ({time.time()})\n\n'
            f'status - {request.status_code}\n'
            f'text - {request.text}'
        )
    except r.exceptions.RequestException as e:
        logger.error('Ошибка запроса:', e)
        return False

    logger.info(request.status_code, request.text)

    try:
        request_data = request.json()
    except r.exceptions.JSONDecodeError as e:
        logger.error(f'Ошибка запроса  {request.status_code} {request.text}:', e)
        return False

    if request_data['status']:
        metrics.append(
            {'metric': 'payout_successed', 'value': payout['amount']})
        success_msg = (
            f'Платеж забран\n'
            f'Сумма - 💰{payout['amount']}💰\n'
            f'Карта - 💸{payout['card']}💸'
        )
        # if same_payouts_count > 0:
        #     success_msg += f'\n\n‼️Кажется, этот платеж уже забирался‼️'

        notifications['admins'].append(success_msg)
        notifications['only_taken'].append(success_msg)

        return True
    else:
        metrics.append({'metric': 'payout_failed', 'value': payout['amount']})

    return False


# Получаем обработанные платежи
def load_payouts():
    global notifications

    claimed_count = 0
    all_payouts = get_payouts(session)
    for row in all_payouts:
        claimed_count += 0 if not row[2] else 1

    if claimed_count >= settings.get('payouts_limit', 10):
        return []

    payouts = []
    for row in get_payouts(session):
        is_able = not row[2]
        if not is_able:
            continue

        claim_btn = row[3]
        payout_id = claim_btn.split('data-id=')[1].split("'")[1]

        payout = {
            'time': row[0],
            'status': row[1],
            'id': payout_id,
            'amount': row[4],
            'card': row[7],
            'requests': row[8],
            'operation_id': row[14],
            'user_id': row[15],
        }

        logger.info(f'Найден платеж: {payout}')
        notifications['admins'].append(
            f'Найден платеж ({time.time()})\n\n{dict_to_str(payout)}')
        payouts.append(payout)

    return payouts


# Доп. функции
def get_clear_notifications():
    return {'admins': [], 'only_taken': []}


def run_extra_actions():
    global notifications, metrics
    tg.get_updates()

    # notify
    tg.notify_bulk_admins(notifications['admins'])
    tg.notify_bulk_watchers(notifications['only_taken'])
    notifications = get_clear_notifications()

    for metric in metrics:
        write_stat(**metric)
    metrics = []


# Приступаем к запуску
session = r.Session()
session.cookies.set('auth', settings['auth_cookie'])

tg = Tg(session, settings)

notifications = get_clear_notifications()
metrics = []
while True:
    is_running = settings.get('is_running', False)
    if is_running:
        cur_time = int(time.time())
        if cur_time % 10 == 0:
            run_extra_actions()
    else:
        run_extra_actions()
        time.sleep(5)
        continue

    calimed_payouts_count = 0
    for payout in load_payouts():
        if claim_payout(payout):
            calimed_payouts_count += 1

        if calimed_payouts_count >= settings.get('payouts_limit', 10):
            break
