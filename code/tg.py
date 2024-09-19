import os
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot as TgBot
from aiogram import Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from code.db import DB
from code.models import Payout, PayoutActionEnum, User, Bot
from code.settings import Settings
from code.stats import get_stats

load_dotenv()


@dataclass
class Routers:
    base: Router
    admin: Router


class UserCallback(CallbackData, prefix='user'):
    bot_id: int
    user_id: int
    page: int


class BotCallback(CallbackData, prefix='bot'):
    bot_id: int
    page: int


class Tg:
    api: None
    routers: Routers

    def __init__(self, session: Session, settings: Settings, db: DB):
        self.session = session
        self.settings = settings
        self.db = db

    def _is_user_exists(self, chat: types.Chat) -> bool:
        if not (self.db and self.db.cur_bot):
            return False

        for user in self.db.cur_bot.users:
            if user.chat_id == str(chat.id):
                return True
        return False

    def _is_admin(self, chat: types.Chat) -> bool:
        if not (self.db and self.db.cur_bot):
            return False

        for user in self.db.cur_bot.users:
            if user.chat_id == str(chat.id) and user.is_admin:
                return True
        return False

    def setup(self):
        self.settings.bot = TgBot(token=self.db.cur_bot.tg_bot_token)
        self.settings.dp = Dispatcher()

        self.routers = Routers(
            base=Router(),
            admin=Router(),
        )

        self.routers.base.message.filter(F.chat.func(self._is_user_exists))
        self.routers.base.callback_query.filter(F.from_user.id.in_(
            [int(u.chat_id) for u in self.db.cur_bot.users]
        ))

        self.routers.admin.message.filter(F.chat.func(self._is_admin))
        self.routers.admin.callback_query.filter(F.from_user.id.in_(
            [int(u.chat_id) for u in self.db.cur_bot.users if u.is_admin]
        ))

        self.routers.base.include_router(self.routers.admin)
        self.settings.dp.include_router(self.routers.base)

        self.routers.base.message.register(self._help_command, Command('help'))
        self.routers.base.message.register(self._run_command, Command('run'))
        self.routers.base.message.register(self._stop_command, Command('stop'))
        self.routers.base.message.register(self._status_command, Command('status'))
        self.routers.base.message.register(self._stats_command, Command('stats'))

        # self.routers.admin.message.register(self._webstats_command, Command('webstats'))
        self.routers.admin.message.register(self._payout_command, Command('payout'))
        self.routers.admin.message.register(self._set_min_amount_command, Command('set_min_amount'))
        self.routers.admin.message.register(self._set_max_amount_command, Command('set_max_amount'))
        self.routers.admin.message.register(self._set_payouts_limit_command, Command('set_payouts_limit'))
        self.routers.admin.message.register(self._add_user_command, Command('add_user'))

        self.routers.admin.message.register(self._list_bots, Command('bots_users'))
        self.routers.admin.callback_query.register(self._show_users_in_bot, BotCallback.filter())
        self.routers.admin.callback_query.register(self._back_to_list_bots, F.data == 'to_list_bots')
        self.routers.admin.callback_query.register(self._toggle_user_in_bot, UserCallback.filter())

    def format_number(self, num):
        if num is None:
            return '-'

        num = round(num, 2)
        return '{:,}'.format(num).replace(',', ' ')

    def split_list(self, lst, step: int = 2):
        return [lst[i:i + step] for i in range(0, len(lst), step)]

    async def send_msg(self, chat_id: int, text: str):
        await self.settings.bot.send_message(chat_id, text)

    async def notify_admins(self, *args):
        if not (self.db and self.db.cur_bot):
            return

        text = ' '.join([str(s) for s in args])
        for admin in self.db.cur_bot.users:
            if not admin.is_admin:
                continue

            await self.send_msg(admin.chat_id, text)

    async def notify_watchers(self, *args):
        if not (self.db and self.db.cur_bot):
            return

        text = ' '.join([str(s) for s in args])
        for watcher in self.db.cur_bot.users:
            if watcher.is_admin:
                continue

            await self.send_msg(watcher.chat_id, text)

    async def notify_bulk_admins(self, notifications):
        for notification in notifications:
            if isinstance(notification, str):
                notification = [notification]
            await self.notify_admins(*notification)

    async def notify_bulk_watchers(self, notifications):
        for notification in notifications:
            if isinstance(notification, str):
                notification = [notification]
            await self.notify_watchers(*notification)

    async def _help_command(self, message: types.Message):
        await message.answer(
            'Хелпанем немножечко :)\n\n'
            '/help - список команд\n\n'
            + f'{'Штука':=^20}' + '\n' +
            '/run - включить штуку\n'
            '/stop - остановить штуку\n'
            '/status - статусы, настройки, тут всякое\n\n'
            + f'{'Статистика':=^20}' + '\n' +
            '/webstats - получить статистику с turcode\n'
            '/stats - получить статистику\n'
            '/payout <operation_id> - найти платеж среди всех платежей забранных всеми ботами\n\n'
            + f'{'Настройки':=^20}' + '\n' +
            '/set_min_amount <number> - установить минимальную сумму резервирования платежа, '
            '<number> - любое целое число, можно использовать пробел как разделитель\n'
            '/set_max_amount <number> - установить максимальную сумму резервирования платежа, '
            '<number> - любое целое число, можно использовать пробел как разделитель\n'
            '/set_payouts_limit <number> - установить лимит кол-ва платежей, '
            '<number> - любое целое число, можно использовать пробел как разделитель\n',
        )

    async def _run_command(self, message: types.Message):
        async with self.settings.db_session() as session:
            await self.db.cur_bot.set_is_running(session, True)
            await session.commit()

        await message.answer('Запустил штуку')

    async def _stop_command(self, message: types.Message):
        async with self.settings.db_session() as session:
            await self.db.cur_bot.set_is_running(session, False)
            await session.commit()

        await message.answer('Остановил штуку')

    async def _status_command(self, message: types.Message):
        await message.answer(
            f'Штука запущена: {'да' if self.db.cur_bot.is_running else 'нет'}\n'
            f'Мин. сумма резервирования: {self.format_number(self.db.cur_bot.min_amount)}\n'
            f'Макс. сумма резервирования: {self.format_number(self.db.cur_bot.min_amount)}\n'
            f'Лимит кол-ва платежей: {self.format_number(self.db.cur_bot.claimed_payouts_limit)}'
        )

    async def _webstats_command(self, message: types.Message):
        if not self.api:
            await message.answer('Апи не подключено')
            return

        # TODO: переписать без использования апи
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
            await message.answer(stats_msg)

    async def _stats_command(self, message: types.Message):
        stats_date = message.text.replace('/stats', '').strip() or None

        if stats_date:
            try:
                stats_date = datetime.strptime(stats_date, '%d.%m.%Y').date()
            except ValueError:
                await message.answer('Неверный формат даты')
                return

        stats_dict = await get_stats(self.settings, stats_date)
        for date, metrics in stats_dict.items():
            await message.answer(
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
            await message.answer('Статистики нет')

    async def _payout_command(self, message: types.Message):
        search_value = message.text.replace('/payout', '').strip()

        if not search_value:
            await message.answer(
                'Неверный формат ввода,\n'
                'пример: /payout W153944573'
            )

        async with self.settings.db_session() as session:
            payouts = await Payout.search_payouts(session, search_value)

            if payouts:
                for payout in payouts:
                    action = (PayoutActionEnum.SUCCESS.text
                              if payout.action == PayoutActionEnum.SUCCESS.code else
                              PayoutActionEnum.FAIL.text)

                    await message.answer(
                        f'Событие: {action}\n'
                        f'Дата события: {payout.created_at.strftime("%d.%m.%Y %H:%M:%S")}\n'
                        f'Бот: {payout.bot_name}\n'
                        f'Operation id: {payout.operation_id}\n'
                        f'Сумма: {self.format_number(payout.amount)}\n'
                        f'Банк: {payout.bank_name}\n'
                        f'Карта: {payout.card}\n'
                        f'Телефон: {payout.phone}\n'
                    )
                return

        await message.answer(
            'Платеж не найден :('
        )

    async def _set_min_amount_command(self, message: types.Message):
        new_min_amount = message.text.replace('/set_min_amount ', '')
        try:
            new_min_amount = int(new_min_amount.replace(' ', ''))
        except ValueError:
            await message.answer(
                'Неверный формат ввода, пример: /set_min_amount 50 000'
            )
        else:
            async with self.settings.db_session() as session:
                await self.db.cur_bot.set_min_amount(session, new_min_amount)
                await session.commit()

            await message.answer(
                f'Мин. сумма резервирования: {self.format_number(new_min_amount)}'
            )

    async def _set_max_amount_command(self, message: types.Message):
        new_max_amount = message.text.replace('/set_max_amount ', '')
        try:
            new_max_amount = int(new_max_amount.replace(' ', ''))
        except ValueError:
            await message.answer('Неверный формат ввода, пример: /set_max_amount 80 000')
        else:
            async with self.settings.db_session() as session:
                await self.db.cur_bot.set_max_amount(session, new_max_amount)
                await session.commit()

            await message.answer(f'Макс. сумма резервирования: {self.format_number(new_max_amount)}')

    async def _set_payouts_limit_command(self, message: types.Message):
        new_payouts_limits = message.text.replace('/set_payouts_limit ', '')
        try:
            new_payouts_limits = int(
                new_payouts_limits.replace(' ', ''))
        except ValueError:
            await message.answer('Неверный формат ввода, пример: /set_payouts_limit 10')
        else:
            async with self.settings.db_session() as session:
                await self.db.cur_bot.set_claimed_payouts_limit(session, new_payouts_limits)
                await session.commit()

            await message.answer(f'Лимит кол-ва платежей: {self.format_number(new_payouts_limits)}')

    async def _add_user_command(self, message: types.Message):
        data = message.text.replace('/add_user', '').strip().split()

        if len(data) != 2:
            await message.answer('Неверный формат, пример: /add_user Петя 123321')

        name, chat_id = data
        async with self.settings.db_session() as session:
            session.add(User(name=name, chat_id=chat_id))

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                await message.answer('Пользователь с таким chat_id уже добавлен')
                return

        await message.answer('Пользователь успешно добавлен')
        await self.db.load_users()

    async def _list_bots(self, message: types.Message, is_edit: bool = False):
        bots_btns = []
        for bot in self.db.bots:
            bots_btns.append(InlineKeyboardButton(
                text=bot.bot_name,
                callback_data=BotCallback(bot_id=bot.id, page=1).pack()
            ))

        markup = InlineKeyboardMarkup(inline_keyboard=self.split_list(bots_btns))

        method = message.edit_text if is_edit else message.answer
        await method("Список ботов", reply_markup=markup)

    async def _show_users_in_bot(self, callback_query: types.CallbackQuery, callback_data: BotCallback = None,
                                 bot_id: int = None, page: int = None):
        page_size = 10

        if bot_id is None:
            bot_id = callback_data.bot_id
        if page is None:
            page = callback_data.page

        async with self.settings.db_session() as session:
            all_users = await User.get_all(session)
            bot_users = await User.get_by_bot_id(session, bot_id)

        has_next = len(all_users) >= page * page_size
        cur_page_users = all_users[(page - 1) * page_size: page * page_size]

        users_btns = []
        for user in cur_page_users:
            is_added_to_bot = user in bot_users
            users_btns.append(InlineKeyboardButton(
                text=f'{'🟩' if is_added_to_bot else '🟥'} {user.name}',
                callback_data=UserCallback(bot_id=bot_id, user_id=user.id, page=page).pack()
            ))

        keyboard = self.split_list(users_btns)

        # Add pagination buttons
        pagination_row = []
        if page > 1:
            pagination_row.append(InlineKeyboardButton(
                text="⬅️",
                callback_data=BotCallback(bot_id=bot_id, page=page - 1).pack()
            ))
        if has_next:
            pagination_row.append(InlineKeyboardButton(
                text="➡️",
                callback_data=BotCallback(bot_id=bot_id, page=page + 1).pack()
            ))

        keyboard.append(pagination_row)
        keyboard.append([InlineKeyboardButton(text="Назад", callback_data="to_list_bots")])

        markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        return await callback_query.message.edit_text(f"Список пользователей бота", reply_markup=markup)

    async def _back_to_list_bots(self, callback_query: types.CallbackQuery):
        await self._list_bots(callback_query.message, True)

    async def _toggle_user_in_bot(self, callback_query: types.CallbackQuery, callback_data: UserCallback):
        bot_id = callback_data.bot_id
        user_id = callback_data.user_id
        page = callback_data.page

        async with self.settings.db_session() as session:
            bot = await Bot.get_by_id(session, bot_id)
            user = await User.get_by_id(session, user_id)

            if user in bot.users:
                await bot.remove_user(session, user)
            else:
                await bot.add_user(session, user)

            await session.commit()

        await self.db.load_bots()
        await self.db.load_users()

        return await self._show_users_in_bot(callback_query, bot_id=bot_id, page=page)
