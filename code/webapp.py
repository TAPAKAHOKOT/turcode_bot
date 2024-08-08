import os, sys

import requests as r
from dotenv import load_dotenv
from flask import Flask, jsonify, request, abort

from code.api import API
from code.logger import Logger
from code.settings import Settings
from code.tg import Tg

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

WEBAPP_PASS = os.getenv('WEBAPP_PASS')


def check_auth(password):
    """Проверка аутентификационных данных."""
    return password == WEBAPP_PASS


def authenticate():
    """Отправка ответа с требованием аутентификации."""
    abort(401, description="Unauthorized")


@app.before_request
def before_request():
    """Проверка аутентификации перед обработкой запроса."""
    auth = request.headers.get('Authorization')
    if not auth:
        authenticate()
    token_type, password = auth.split()
    if token_type.lower() != 'bearer' or not check_auth(password):
        authenticate()


@app.route('/webstats', methods=['GET'])
def webstats():
    logger = Logger()
    settings = Settings(os.getenv('BOT_NAME', 'unknown'), logger)
    settings.load()

    session = r.Session()
    session.cookies.set('auth', settings['auth_cookie'])

    tg = Tg(session, settings)
    logger.tg = tg
    api = API(session, settings, tg, logger)

    result = api.get_webstats()
    if not result:
        api.auth()
        session.cookies.set('auth', settings['auth_cookie'])
        result = api.get_webstats()

    return jsonify(result)


if __name__ == '__main__':
    app.run()
