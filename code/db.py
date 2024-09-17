from typing import Sequence

from code.models import Bot, User
from code.settings import Settings


class DB:
    settings: Settings

    cur_bot: Bot | None = None
    bots: Sequence[Bot] | None = None

    is_any_bot_active: bool = False
    all_active_bots_min_amount: int | None = None
    all_active_bots_max_amount: int | None = None

    users: Sequence[User] | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _find_cur_bot(self) -> Bot | None:
        if not self.bots:
            return None

        for bot in self.bots:
            if bot.bot_name == self.settings.bot_name:
                return bot

        return None

    async def load_bots(self):
        async with self.settings.db_session() as session:
            self.bots = await Bot.get_active(session=session)
            self.cur_bot = await self._find_cur_bot()

        await self._update_bots_info()

    async def get_bot_by_amount(self, amount: int) -> Bot | None:
        for bot in self.bots:
            if bot.is_running and bot.min_amount <= amount <= bot.max_amount:
                return bot

    async def _update_bots_info(self):
        self.is_any_bot_active = False
        self.all_active_bots_min_amount = None
        self.all_active_bots_max_amount = None
        for bot in self.bots:
            if not bot.is_running:
                continue

            if self.all_active_bots_min_amount is None or self.all_active_bots_min_amount > bot.min_amount:
                self.all_active_bots_min_amount = bot.min_amount

            if self.all_active_bots_max_amount is None or self.all_active_bots_max_amount < bot.max_amount:
                self.all_active_bots_max_amount = bot.max_amount

            self.is_any_bot_active = True

    async def load_users(self):
        async with self.settings.db_session() as session:
            self.users = await User.get_all(session=session)
