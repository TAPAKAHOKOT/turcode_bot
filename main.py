import os
import signal
import sys
import time

import requests as r

from code.api import API
from code.logger import Logger
from code.models import Base
from code.settings import Settings
from code.tg import Tg

sys.stdout.reconfigure(encoding='utf-8')
logger = Logger()


# Настраиваем сигналы закрытия программы
def onexit(*args, **kwargs):
    settings.save()
    logger.info(f'Program stopped')
    sys.exit(0)


signal.signal(signal.SIGINT, onexit)
signal.signal(signal.SIGTERM, onexit)

# Загрузка настроек
settings = Settings(os.getenv('BOT_NAME', 'unknown'), logger)
settings.load()

Base.metadata.create_all(settings.engine)

logger.info('Settings:', settings)


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
        time.sleep(1)
        continue

    claimed_payouts_count = 0
    for payout in api.load_payouts():
        if api.claim_payout(payout):
            claimed_payouts_count += 1

        if claimed_payouts_count >= settings.get('payouts_limit', 10):
            break

    # time.sleep(2)
