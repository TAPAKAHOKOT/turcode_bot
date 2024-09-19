import asyncio
import time
from typing import Sequence

from code.api import API
from code.db import DB
from code.models import Bot, User
from code.settings import Settings
from code.tg import Tg


class Runner:
    settings: Settings
    db: DB
    api: API
    tg: Tg
    cur_bot: Bot | None = None
    bots: Sequence[Bot] | None = None
    users: Sequence[User] | None = None
    tasks: list[asyncio.Task] | None = None

    def __init__(self, settings: Settings, db: DB, api: API, tg: Tg):
        self.settings = settings
        self.db = db
        self.api = api
        self.tg = tg
        self.extra_update_last_fast_run = int(time.time())
        self.extra_update_last_slow_run = int(time.time())

    async def fetch_turcode_api(self):
        try:
            while True:
                if not self.db.is_any_bot_active:
                    await asyncio.sleep(10)
                    continue

                for payout in await self.api.load_payouts():
                    await self.api.claim_payout(payout)

                await asyncio.sleep(0.005)
        except asyncio.CancelledError:
            print('fetch_turcode_api cancelled')

    async def _extra_update_fast(self):
        await self.api.check_claimed_payouts()
        await self.api.update_bot_claimed_payouts_count()
        await self.db.load_bots()

        # Отправка уведомлений
        await self.tg.notify_bulk_admins(self.settings.notifications.admins)
        await self.tg.notify_bulk_watchers(self.settings.notifications.watchers)
        self.settings.clear_notifications()

    async def _extra_update_slow(self):
        await self.db.load_users()

    async def extra_update(self):
        try:
            while True:
                if self.db.is_any_bot_active:
                    cur_time = int(time.time())

                    if cur_time - self.extra_update_last_fast_run >= 10:
                        await self._extra_update_fast()
                        self.extra_update_last_fast_run = cur_time
                    if cur_time - self.extra_update_last_slow_run >= 30:
                        await self._extra_update_slow()
                        self.extra_update_last_slow_run = cur_time
                else:
                    await self._extra_update_fast()
                    await self._extra_update_slow()
                    await asyncio.sleep(5)
                    continue

                await asyncio.sleep(0.005)
        except asyncio.CancelledError:
            print('extra_update cancelled')

    async def start(self):
        # Run both tasks in parallel
        task1 = asyncio.Task(self.fetch_turcode_api())
        task2 = asyncio.Task(self.extra_update())

        polling_task = asyncio.Task(self.settings.dp.start_polling(self.settings.bot, handle_signals=False))

        self.tasks = [task1, task2, polling_task]

        # Wait for tasks to complete (which won't happen due to infinite loops)
        await asyncio.gather(*self.tasks)
