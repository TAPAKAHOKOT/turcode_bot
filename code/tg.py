import os
from datetime import datetime
from random import choices

import requests as r
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from code.models import Payout, PayoutActionEnum
from code.stats import get_stats

load_dotenv()

# TG
watchers = list(map(int, os.getenv('WATCHERS').split(',')))
admins = list(map(int, os.getenv('ADMINS').split(',')))

bot_token = os.getenv('BOT_TOKEN')

in_work_phrases = ["Явись-я работаю-вызвали!", "Всё ещё тут",
                   "Работаю, не валяясь", "Не сплю, шишки не беру",
                   "Продолжаю мучиться", "Трудится, как пчёлка",
                   "Всё по расписанию", "Пашу, как осёл", "На лошади работаю",
                   "Не останавливаюсь", "Делаю всё и даже больше",
                   "Ходить еще не устал", "Ноги еще целые", "Мозги на месте",
                   "Клаву грызу", "Делаю, что могу", "Ещё в деле",
                   "Твердо на земле", "Горю желанием", "Не сдаюсь",
                   "Работаю до отказа", "Только начал", "В процессе",
                   "Не жалуюсь", "Продолжаю мучиться", "Жив-здоров",
                   "Не сплю, не вяну", "На плаву", "Сияю здесь", "Тактичен", ]


class Tg:
    api: None

    def __init__(self, session, settings):
        self.session = session
        self.settings = settings

    def format_number(self, num):
        if num is None:
            return '-'

        num = round(num, 2)
        return '{:,}'.format(num).replace(',', ' ')

    def send_msg(self, chat_id: int, text: str):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={text}&reply_markup=%7B%22remove_keyboard%22%3A%20true%7D"
        response = r.get(url)

        if response.status_code != 200:
            print(response.text)

    def notify_admins(self, *args):
        text = ' '.join([str(s) for s in args])
        for admin in admins:
            self.send_msg(admin, text)

    def notify_watchers(self, *args):
        text = ' '.join([str(s) for s in args])
        for watcher in watchers:
            self.send_msg(watcher, text)

    def notify_bulk_admins(self, notifications):
        for notification in notifications:
            if isinstance(notification, str):
                notification = [notification]
            self.notify_admins(*notification)

    def notify_bulk_watchers(self, notifications):
        for notification in notifications:
            if isinstance(notification, str):
                notification = [notification]
            self.notify_watchers(*notification)

    def get_updates(self):
        update_offset = self.settings.get('update_offset', None)
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        if update_offset is not None:
            url += f'?offset={update_offset}'

        updates = r.get(url)

        if updates.status_code == 200:
            updates = updates.json()
            for msg in updates['result']:
                if 'message' not in msg or 'text' not in msg['message']:
                    continue

                chat_id = msg['message']['from']['id']
                if chat_id not in watchers and chat_id not in admins:
                    continue

                text = msg['message']['text']
                if text.startswith('/help'):
                    self.send_msg(
                        chat_id,
                        'Хелпанем немножечко :))\n\n'
                        '/help - список команд\n\n'
                        + f'{'Штука':=^20}' + '\n'
                                              '/run - включить штуку\n'
                                              '/stop - остановить штуку\n'
                                              '/status - статусы, настройки, тут всякое\n\n'
                        + f'{'Статистика':=^20}' + '\n'
                                                   '/webstats - получить статистику с turcode\n'
                                                   '/stats - получить статистику\n'
                                                   '/payout <operation_id> - найти платеж среди всех платежей забранных всеми ботами\n\n'
                        + f'{'Настройки':=^20}' + '\n'
                                                  '/set_min_amount <number> - установить минимальную сумму резервирования платежа, <number> - любое целое число, можно использовать пробел как разделитель\n'
                                                  '/set_max_amount <number> - установить максимальную сумму резервирования платежа, <number> - любое целое число, можно использовать пробел как разделитель\n'
                                                  '/set_payouts_limit <number> - установить лимит кол-ва платежей, <number> - любое целое число, можно использовать пробел как разделитель\n'
                                                  '/auth <text> - установить куки авторизации'
                    )
                elif text.startswith('/run'):
                    self.settings['is_running'] = True
                    self.send_msg(chat_id, 'Запустил штуку')
                elif text.startswith('/stop'):
                    self.settings['is_running'] = False
                    self.send_msg(chat_id, 'Остановил штуку')
                elif text.startswith('/status'):
                    self.send_msg(
                        chat_id,
                        f'Штука запущена: {'да' if self.settings['is_running'] else 'нет'}\n'
                        f'Мин. сумма резервирования: {self.format_number(self.settings.get('min_amount', 0))}\n'
                        f'Макс. сумма резервирования: {self.format_number(self.settings.get('max_amount', 0))}\n'
                        f'Лимит кол-ва платежей: {self.format_number(self.settings['payouts_limit'])}'
                    )
                elif text.startswith('/webstats'):
                    if self.api:
                        for k, profiles in enumerate(self.api.get_stats()):
                            stats_msg = ''
                            k_msg = f' Бот {k + 1} '
                            stats_msg += f'{k_msg:=^20}' + '\n'

                            if profiles is None:
                                stats_msg += 'Нет данных'
                            else:
                                for stat in profiles:
                                    if stat is None:
                                        stats_msg += 'Не достучался :('
                                    else:
                                        stats_msg += (f'Акк: {stat['username']}\n'
                                                      f'Баланс: {self.format_number(stat['balance'])}\n'
                                                      f'Сумма платежей за 24 часа: {self.format_number(stat['payouts_sum_for_24h'])}\n'
                                                      f'Кол-во платежей за 24 часа: {stat['payouts_count_for_24h']}\n\n\n')
                            self.send_msg(chat_id, stats_msg)
                    else:
                        self.send_msg(chat_id, 'Апи не подключено')
                elif text.startswith('/stats'):
                    send_stats = True
                    stats_date = text.replace('/stats', '').strip()
                    if stats_date:
                        try:
                            stats_date = datetime.strptime(stats_date, '%d.%m.%Y').date()
                        except ValueError:
                            send_stats = False
                            self.send_msg(chat_id, 'Неверный формат даты')
                    else:
                        stats_date = None

                    if send_stats:
                        stats_dict = get_stats(self.settings, stats_date)
                        for date, metrics in stats_dict.items():
                            self.send_msg(
                                chat_id,
                                f"Дата: {date}\n\n" + "-" * 30 +
                                f"\n\nПлатеж забран успешно ✅\n\n"
                                f"Сумма: {self.format_number(metrics['success_payouts_amount_sum'])}\n"
                                f"Среднее: {self.format_number(metrics['success_payouts_avg'])}\n"
                                f"Кол-во: {self.format_number(metrics['success_payouts_count'])}\n\n"
                                + "-" * 30 +
                                f"\n\nПлатеж не забран ❌\n\n"
                                f"Сумма: {self.format_number(metrics['fail_payouts_amount_sum'])}\n"
                                f"Среднее: {self.format_number(metrics['fail_payouts_avg'])}\n"
                                f"Кол-во: {self.format_number(metrics['fail_payouts_count'])}\n\n"
                            )
                        if not stats_dict:
                            self.send_msg(chat_id, 'Статистики нет')
                elif text.startswith('/payout'):
                    operation_id = text.replace('/payout', '').strip()
                    if operation_id:
                        with Session(self.settings.engine) as session, session.begin():
                            payouts = Payout.get_all_by_operation_id(session, operation_id=operation_id)

                            if payouts:
                                for payout in payouts:
                                    action = (PayoutActionEnum.SUCCESS.text
                                              if payout.action == PayoutActionEnum.SUCCESS.code else
                                              PayoutActionEnum.FAIL.text)

                                    self.send_msg(
                                        chat_id,
                                        f'Событие: {action}\n'
                                        f'Дата события: {payout.created_at.strftime("%d.%m.%Y %H:%M:%S")}\n'
                                        f'Бот: {payout.bot_name}\n'
                                        f'Operation id: {payout.operation_id}\n'
                                        f'Сумма: {self.format_number(payout.amount)}\n'
                                    )
                            else:
                                self.send_msg(
                                    chat_id,
                                    'Платеж не найден :('
                                )
                    else:
                        self.send_msg(
                            chat_id,
                            'Неверный формат ввода, пример: /payout W153944573'
                        )
                elif text.startswith('/set_min_amount'):
                    new_min_amount = text.replace('/set_min_amount ', '')
                    try:
                        new_min_amount = int(new_min_amount.replace(' ', ''))
                    except ValueError:
                        self.send_msg(
                            chat_id,
                            'Неверный формат ввода, пример: /set_min_amount 50 000'
                        )
                    else:
                        self.settings['min_amount'] = new_min_amount
                        self.send_msg(
                            chat_id,
                            f'Мин. сумма резервирования: {self.format_number(self.settings['min_amount'])}'
                        )
                elif text.startswith('/set_max_amount'):
                    new_max_amount = text.replace('/set_max_amount ', '')
                    try:
                        new_max_amount = int(new_max_amount.replace(' ', ''))
                    except ValueError:
                        self.send_msg(chat_id,
                                      'Неверный формат ввода, пример: /set_max_amount 80 000')
                    else:
                        self.settings['max_amount'] = new_max_amount
                        self.send_msg(
                            chat_id,
                            f'Макс. сумма резервирования: {self.format_number(self.settings['max_amount'])}'
                        )
                elif text.startswith('/set_payouts_limit'):
                    new_payouts_limits = text.replace('/set_payouts_limit ', '')
                    try:
                        new_payouts_limits = int(
                            new_payouts_limits.replace(' ', ''))
                    except ValueError:
                        self.send_msg(chat_id,
                                      'Неверный формат ввода, пример: /set_payouts_limit 10')
                    else:
                        self.settings['payouts_limit'] = new_payouts_limits
                        self.send_msg(
                            chat_id,
                            f'Лимит кол-ва платежей: {self.format_number(self.settings['payouts_limit'])}'
                        )
                elif text.startswith('/auth'):
                    auth_cookie = text.replace('/auth', '').strip().replace(
                        'auth=', '').encode('latin-1', 'ignore').decode('utf-8', 'ignore')
                    self.settings['auth_cookie'] = auth_cookie
                    self.session.cookies.set('auth', self.settings['auth_cookie'])

                    self.send_msg(chat_id, f'Обновил куки: {auth_cookie}')
                else:
                    self.send_msg(chat_id, choices(in_work_phrases)[0])

                update_offset = msg['update_id'] + 1
                self.settings['update_offset'] = update_offset
