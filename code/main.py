import requests as r
from dotenv import load_dotenv

import json
import time
from random import choices
import signal
import sys
import os
from datetime import datetime, timedelta, UTC

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()


# Настраиваем сигналы закрытия программы
def onexit(*args, **kwargs):
    save_settings(FILE_PATH, settings)
    log_info(f'Программа остановлена')
    sys.exit(0)

signal.signal(signal.SIGINT, onexit)
signal.signal(signal.SIGTERM, onexit)


# Функции работы со статистикой
def write_stat(metric, value):
    # Создаем папку "stats", если она не существует
    if not os.path.exists('stats'):
        os.makedirs('stats')

    # Определяем имя файла с сегодняшней датой
    today = datetime.now().strftime('%d.%m.%y')
    filename = f'stats/{today}.json'

    # Загружаем данные из файла, если он существует, или создаем новый словарь
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            data = json.load(file)
    else:
        data = []

    # Добавляем новую метрику с текущим временем
    stat = {
        'metric': metric,
        'value': value,
        'timestamp': int(datetime.now(UTC).timestamp())
    }
    data.append(stat)

    # Сохраняем данные обратно в файл
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)

def get_stats(stat_date=None):
    # Определяем сегодняшнюю дату и даты за последние 5 дней
    if stat_date is not None:
        dates = [stat_date.strftime('%d.%m.%y')]
    else:
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)).strftime('%d.%m.%y') for i in range(7)]


    stats = {}
    for date in dates:
        filename = f'stats/{date}.json'
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                data = json.load(file)
            
            daily_stats = {}
            for entry in data:
                metric = entry['metric']
                value = float(entry['value'].replace(',', ''))
                if metric in daily_stats:
                    daily_stats[metric]['total'] += value
                    daily_stats[metric]['count'] += 1
                else:
                    daily_stats[metric] = {'total': value, 'count': 1}
            
            # Вычисляем среднее значение для каждой метрики
            for metric in daily_stats:
                total = daily_stats[metric]['total']
                _count = daily_stats[metric]['count']
                average = total / _count
                daily_stats[metric] = {'total': total, 'average': average, 'count': _count}
            
            stats[date] = daily_stats

    return stats


# Словарь переводим в читаемую строку
def dict_to_str(dict_item):
    res = ''
    for key, value in dict_item.items():
        res += f'{key} - {value}\n'
    return res


# TG
watchers = list(map(int, os.getenv('WATCHERS').split(',')))
admins = list(map(int, os.getenv('ADMINS').split(',')))

bot_token = os.getenv('BOT_TOKEN')

in_work_phrases = ["Явись-я работаю-вызвали!", "Всё ещё тут", "Работаю, не валяясь", "Не сплю, шишки не беру", "Продолжаю мучиться", "Трудится, как пчёлка", "Всё по расписанию", "Пашу, как осёл", "На лошади работаю", "Не останавливаюсь", "Делаю всё и даже больше", "Ходить еще не устал", "Ноги еще целые", "Мозги на месте", "Клаву грызу", "Делаю, что могу", "Ещё в деле", "Твердо на земле", "Горю желанием", "Не сдаюсь", "Работаю до отказа", "Только начал", "В процессе", "Не жалуюсь", "Продолжаю мучиться", "Жив-здоров", "Не сплю, не вяну", "На плаву", "Сияю здесь", "Тактичен",]

def format_number(num):
    num = round(num, 2)
    return '{:,}'.format(num).replace(',', ' ')

def send_msg(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={text}&reply_markup=%7B%22remove_keyboard%22%3A%20true%7D"
    response = r.get(url)

def notify_admins(*args):
    text = ' '.join([str(s) for s in args])
    for admin in admins:
        send_msg(admin, text)

def notify_watchers(*args):
    text = ' '.join([str(s) for s in args])
    for watcher in watchers:
        send_msg(watcher, text)

def notify_bulk_admins(notifications):
    for notification in notifications:
        if isinstance(notification, str):
            notification = [notification]
        notify_admins(*notification)

def notify_bulk_watchers(notifications):
    for notification in notifications:
        if isinstance(notification, str):
            notification = [notification]
        notify_watchers(*notification)

def tg_get_updates():
    update_offset = settings.get('update_offset', None)
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    if update_offset is not None:
        url += f'?offset={update_offset}'

    uppdates = r.get(url)

    if uppdates.status_code == 200:
        uppdates = uppdates.json()
        for msg in uppdates['result']:
            if 'message' not in msg or 'text' not in msg['message']:
                continue

            chat_id = msg['message']['from']['id']
            if chat_id not in watchers and chat_id not in admins:
                continue

            text = msg['message']['text']
            if text.startswith('/help'):
                send_msg(
                    chat_id,
                    'Хелпанем немножечко :))\n\n'
                    '/help - список команд\n'
                    '/run - включить штуку\n'
                    '/stop - остановить штуку\n'
                    '/status - статусы, настройки, тут всякое\n'
                    '/stats - получить статистику\n'
                    '/set_min_amount <number> - установить минимальную сумму резервирования платежа, <number> - любое целое число, можно использовать пробел как разделитель\n'
                    '/set_max_amount <number> - установить максимальную сумму резервирования платежа, <number> - любое целое число, можно использовать пробел как разделитель\n'
                    '/set_payouts_limit <number> - установить лимит кол-ва платежей, <number> - любое целое число, можно использовать пробел как разделитель\n'
                    '/auth <text> - установить куки авторизации'
                )
            elif text.startswith('/run'):
                settings['is_running'] = True
                save_settings(FILE_PATH, settings)
                send_msg(chat_id, 'Запустил штуку')
            elif text.startswith('/stop'):
                settings['is_running'] = False
                save_settings(FILE_PATH, settings)
                send_msg(chat_id, 'Остановил штуку')
            elif text.startswith('/status'):
                send_msg(
                    chat_id, 
                    f'Штука запущена: {'да' if settings['is_running'] else 'нет'}\n'
                    f'Мин. сумма резервирования: {format_number(settings.get('min_amount', 0))}\n'
                    f'Макс. сумма резервирования: {format_number(settings.get('max_amount', 0))}\n'
                    f'Лимит кол-ва платежей: {format_number(settings['payouts_limit'])}'
                )
            elif text.startswith('/stats'):
                metric_mapping = {
                    'payout_successed': 'Платеж забран успешно',
                    'payout_failed': 'Платеж не забран',
                }

                send_stats = True       
                stats_date = text.replace('/stats', '').strip()
                if stats_date:
                    try:
                        stats_date = datetime.strptime(stats_date, '%d.%m.%Y').date()
                    except ValueError:
                        send_stats = False
                        send_msg(chat_id, 'Неверный формат даты')
                else:
                    stats_date = None

                if send_stats:
                    stats_dict = get_stats(stats_date)
                    for date, metrics in stats_dict.items():
                        send_msg(chat_id, f"Дата: {date}")
                        for metric, values in metrics.items():
                            metric = metric_mapping[metric] if metric in metric_mapping else metric
                            send_msg(
                                chat_id, 
                                f"Метрика: {metric}\n\n"
                                f"Сумма: {format_number(values['total'])}\n"
                                f"Среднее: {format_number(values['average'])}\n"
                                f"Кол-во: {format_number(values['count'])}"
                            )
                    if not stats_dict:
                        send_msg(chat_id, 'Статистики нет')
            elif text.startswith('/set_min_amount'):
                new_min_amount = text.replace('/set_min_amount ', '')
                try:
                    new_min_amount = int(new_min_amount.replace(' ', ''))
                except ValueError:
                    send_msg(chat_id, 'Неверный формат ввода, пример: /set_min_amount 50 000')
                else:
                    settings['min_amount'] = new_min_amount
                    save_settings(FILE_PATH, settings)
                    send_msg(chat_id, f'Мин. сумма резервирования: {format_number(settings['min_amount'])}')
            elif text.startswith('/set_max_amount'):
                new_max_amount = text.replace('/set_max_amount ', '')
                try:
                    new_max_amount = int(new_max_amount.replace(' ', ''))
                except ValueError:
                    send_msg(chat_id, 'Неверный формат ввода, пример: /set_max_amount 80 000')
                else:
                    settings['max_amount'] = new_max_amount
                    save_settings(FILE_PATH, settings)
                    send_msg(chat_id, f'Макс. сумма резервирования: {format_number(settings['max_amount'])}')
            elif text.startswith('/set_payouts_limit'):
                new_payouts_limits = text.replace('/set_payouts_limit ', '')
                try:
                    new_payouts_limits = int(new_payouts_limits.replace(' ', ''))
                except ValueError:
                    send_msg(chat_id, 'Неверный формат ввода, пример: /set_payouts_limit 10')
                else:
                    settings['payouts_limit'] = new_payouts_limits
                    save_settings(FILE_PATH, settings)
                    send_msg(chat_id, f'Лимит кол-ва платежей: {format_number(settings['payouts_limit'])}')
            elif text.startswith('/auth'):
                auth_cookie = text.replace('/auth', '').strip().replace('auth=', '')
                settings['auth_cookie'] = auth_cookie

                save_settings(FILE_PATH, settings)
                session.cookies.set('auth', settings['auth_cookie'])

                send_msg(chat_id, f'Обновил куки: {auth_cookie}')
            else:
                send_msg(chat_id, choices(in_work_phrases)[0])

            update_offset = msg['update_id'] + 1
            settings['update_offset'] = update_offset
            save_settings(FILE_PATH, settings)


# LOGGING
def log(type, *args):
    print(f'{type} {int(time.time())}:', *args)

def log_info(*args):
    log('INFO', *args)

def log_error(*args):
    log('ERROR', *args)
    notify_admins('ERROR', *args)


# SETTINGS
def save_settings(file_path, settings):
    """
    Сохраняет настройки в JSON файл.

    :param file_path: Путь к файлу, в который будут сохранены настройки.
    :param settings: Словарь с настройками.
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(settings, file, ensure_ascii=False, indent=4)
        log_info("Настройки успешно сохранены.")
    except Exception as e:
        log_error(f"Ошибка при сохранении настроек: {e}")

def load_settings(file_path):
    """
    Загружает настройки из JSON файла.

    :param file_path: Путь к файлу, из которого будут загружены настройки.
    :return: Словарь с настройками.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            settings = json.load(file)
        log_info("Настройки успешно загружены.")
        return settings
    except Exception as e:
        log_error(f"Ошибка при загрузке настроек: {e}")
        return default_settings


# Дефолтные настройки
default_settings = {
    "min_amount": 50_000,
    "max_amount": 80_000,
    "auth_cookie": "",
    "is_running": False,
    "update_offset": None,
    "payouts_limit": 10,
}
FILE_PATH = 'settings.json'
BASE_URL = 'https://api.turcode.app'
HEADERS = {
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
}


# Загрузка настроек
settings = load_settings(FILE_PATH)

# Выставляем новые настройки, если они добавлялись в default_settings, но еще не появились в файле настроек (FILE_PATH)
for key, value in default_settings.items():
    if key not in settings:
        settings[key] = value

log_info('Настройки:', settings)


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
            auth_cookie = auth_cookie.replace('auth=', '').strip().replace('auth=', '')
            settings['auth_cookie'] = auth_cookie
    except r.exceptions.RequestException as e:
        log_error('Ошибка запроса:', e)
        return []

    log_info(request.status_code, request.text)

    try:
        request_data = request.json()
    except r.exceptions.JSONDecodeError as e:
        # log_error(f'Ошибка запроса {request.status_code} {request.text}:', e)

        auth_error_count += 1
        if auth_error_count >= 10:
            settings['is_running'] = False
            save_settings(FILE_PATH, settings)
            auth_error_count = 0
            notify_admins('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')
            notify_watchers('Меня выкинуло из системы, нужна авторизация\nВыключаю штуку')

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
        log_error('Ошибка запроса:', e)
        return False

    log_info(request.status_code, request.text)

    try:
        request_data = request.json()
    except r.exceptions.JSONDecodeError as e:
        log_error(f'Ошибка запроса  {request.status_code} {request.text}:', e)
        return False

    if request_data['status']:
        metrics.append({'metric': 'payout_successed', 'value': payout['amount']})
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

        log_info(f'Найден платеж: {payout}')
        notifications['admins'].append(f'Найден платеж ({time.time()})\n\n{dict_to_str(payout)}')
        payouts.append(payout)

    return payouts


# Доп. функции
def get_clear_notifications():
    return {'admins': [], 'only_taken': []}

def run_extra_actions():
    global notifications, metrics
    tg_get_updates()

    # notify
    notify_bulk_admins(notifications['admins'])
    notify_bulk_watchers(notifications['only_taken'])
    notifications = get_clear_notifications()

    for metric in metrics:
        write_stat(**metric)
    metrics = []


# Приступаем к запуску
session = r.Session() 
session.cookies.set('auth', settings['auth_cookie'])

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








