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


async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    logger = Logger()
    logger.info('Starting app')

    async def cancel_tasks():
        if runner.tasks:
            logger.info(f'Cancelling {len(runner.tasks)} tasks')
            tasks = [task.cancel() for task in runner.tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info('All tasks cancelled')

    # Настраиваем сигналы закрытия программы
    def onexit(*args, **kwargs):
        try:
            settings.save()
            logger.info(f'Program stopped')

            if runner.tasks:
                logger.info(f'{len(runner.tasks)} tasks found, cancelling...')
                loop = asyncio.get_event_loop()
                loop.run_until_complete(cancel_tasks())

        except Exception as e:
            logger.error(f'Error during shutdown: {e}')

        finally:
            logger.info('Exiting program...')
            sys.exit(0)

    loop = asyncio.get_running_loop()

    # Используем loop.add_signal_handler для регистрации сигналов
    loop.add_signal_handler(signal.SIGINT, onexit)
    loop.add_signal_handler(signal.SIGTERM, onexit)

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

    asyncio.run(await runner.start())


if __name__ == '__main__':
    asyncio.run(main())
