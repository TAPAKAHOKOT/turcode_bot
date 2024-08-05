import os
import signal
import sys
import time

import requests as r
from sqlalchemy import create_engine

from api import API
from logger import Logger
from models import Base
from settings import Settings
from tg import Tg

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
engine = create_engine(
    '{DB}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'.format(
        DB=os.getenv("DB"),
        DB_USER=os.getenv("DB_USER"),
        DB_PASS=os.getenv("DB_PASS"),
        DB_HOST=os.getenv("DB_HOST"),
        DB_PORT=os.getenv("DB_PORT"),
        DB_NAME=os.getenv("DB_NAME")
    )
)
Base.metadata.create_all(engine)

sys.stdout.reconfigure(encoding='utf-8')
logger = Logger()


# Настраиваем сигналы закрытия программы
def onexit(*args, **kwargs):
    settings.save()
    logger.info(f'Программа остановлена')
    sys.exit(0)


signal.signal(signal.SIGINT, onexit)
signal.signal(signal.SIGTERM, onexit)

# Загрузка настроек
settings = Settings(os.getenv('BOT_NAME', 'unknown'), engine, logger)
settings.load()

logger.info('Настройки:', settings)


def run_extra_actions():
    # Обновляем бота тг
    tg.get_updates()

    # Jnghfdkztv edtljvktybz
    tg.notify_bulk_admins(settings.notifications['admins'])
    tg.notify_bulk_watchers(settings.notifications['only_taken'])
    settings.clear_notifications()


# Приступаем к запуску
session = r.Session()
session.cookies.set('auth', settings['auth_cookie'])

tg = Tg(session, settings)
logger.tg = tg
api = API(session, settings, tg, logger)

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

    claimed_payouts_count = 0
    for payout in api.load_payouts():
        if api.claim_payout(payout):
            claimed_payouts_count += 1

        if claimed_payouts_count >= settings.get('payouts_limit', 10):
            break
