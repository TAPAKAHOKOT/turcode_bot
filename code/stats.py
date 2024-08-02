import json
import os
from datetime import datetime, timedelta, UTC


def get_stats(stat_date=None):
    # Определяем сегодняшнюю дату и даты за последние 5 дней
    if stat_date is not None:
        dates = [stat_date.strftime('%d.%m.%y')]
    else:
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)).strftime('%d.%m.%y') for i in
                 range(7)]

    stats = {}
    for date in dates:
        filename = f'stats/{date}.json'
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                data = json.load(file)

            daily_stats = {}
            for entry in data:
                metric = entry['metric']
                value = float(entry['value'].replace(',', ''))
                if metric in daily_stats:
                    daily_stats[metric]['total'] += value
                    daily_stats[metric]['count'] += 1
                else:
                    daily_stats[metric] = {'total': value, 'count': 1}

            # Вычисляем среднее значение для каждой метрики
            for metric in daily_stats:
                total = daily_stats[metric]['total']
                _count = daily_stats[metric]['count']
                average = total / _count
                daily_stats[metric] = {'total': total, 'average': average,
                                       'count': _count}

            stats[date] = daily_stats

    return stats


def write_stat(metric, value):
    # Создаем папку "stats", если она не существует
    if not os.path.exists('stats'):
        os.makedirs('stats')

    # Определяем имя файла с сегодняшней датой
    today = datetime.now().strftime('%d.%m.%y')
    filename = f'stats/{today}.json'

    # Загружаем данные из файла, если он существует, или создаем новый словарь
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            data = json.load(file)
    else:
        data = []

    # Добавляем новую метрику с текущим временем
    stat = {
        'metric': metric,
        'value': value,
        'timestamp': int(datetime.now(UTC).timestamp())
    }
    data.append(stat)

    # Сохраняем данные обратно в файл
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)
