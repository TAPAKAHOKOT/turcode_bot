import json
import os
import re

import requests as r
from dotenv import load_dotenv
from flask import Flask, jsonify, request, abort

load_dotenv()

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


def str_to_int(num: str) -> int:
    try:
        num = int(float(str(num).replace(',', '')))
    except:
        num = 0
    return num


def get_auth_cookie() -> str:
    with open('settings.json', 'r', encoding='utf-8') as file:
        return (json.load(file) or {}).get('auth_cookie', '')


@app.route('/webstats', methods=['GET'])
def webstats():
    base_url = 'https://api.turcode.app'

    try:
        form_data = {
            'draw': 100,
            'start': 0,
            'length': 100,
        }
        session = r.Session()
        session.cookies.set('auth', get_auth_cookie())

        request = session.post(
            f'{base_url}/datatables/tstats.php',
            data=form_data,
        )
    except r.exceptions.RequestException as e:
        print(e)
        return []

    try:
        request_data = request.json()
    except r.exceptions.JSONDecodeError as e:
        print(e)
        return []

    result = []
    for row in request_data.get('data', []):
        result.append({
            'username': re.sub(r'<.*?>', '', row[1]),
            'balance': str_to_int(row[2]),
            'payouts_sum_for_24h': str_to_int(row[6]),
            'payouts_count_for_24h': row[7],
        })
    return jsonify(result)


if __name__ == '__main__':
    app.run()
