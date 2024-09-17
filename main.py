import asyncio
import os
import signal
import sys

import requests as r

from code.api import API
from code.db import DB
from code.logger import Logger
from code.runner import Runner
from code.settings import Settings
from code.tg import Tg


def handle_sigint():
    print("Received SIGINT, shutting down...")
    for task in asyncio.all_tasks():
        task.cancel()


async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    logger = Logger()
    logger.info('Starting app')

    # Загрузка настроек
    settings = Settings(os.getenv('BOT_NAME', 'unknown'), logger)
    settings.load()

    db = DB(settings)
    await db.load_bots()
    await db.load_users()

    # Base.metadata.create_all(settings.engine)

    logger.info('Settings:', settings)

    # Приступаем к запуску
    session = r.Session()
    session.cookies.set('auth', db.cur_bot.auth_cookie)

    tg = Tg(session, settings, db)
    logger.tg = tg
    api = API(session, settings, db, tg, logger)

    runner = Runner(settings, db, api, tg)
    tg.setup()

    await runner.start()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint)
    loop.add_signal_handler(signal.SIGTERM, handle_sigint)

    try:
        loop.run_until_complete(main())
    except asyncio.CancelledError:
        print("All tasks have been cancelled")
    finally:
        loop.close()
