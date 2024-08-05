import copy
import json

from sqlalchemy import Engine

from logger import Logger


class Settings:
    bot_name: str
    default_settings: dict = {
        "min_amount": 50_000,
        "max_amount": 80_000,
        "auth_cookie": "",
        "is_running": False,
        "update_offset": None,
        "payouts_limit": 10,
    }
    settings: dict = None
    notifications: dict = None
    file_path: str = 'settings.json'

    def __init__(self, bot_name: str, engine: Engine, logger: Logger):
        self.bot_name = bot_name
        self.engine = engine
        self.logger = logger
        self.clear_notifications()

    def __setitem__(self, key, value):
        self.settings[key] = value
        self.save()

    def __getitem__(self, key):
        return self.settings[key]

    def __repr__(self):
        return repr(self.settings)

    def __str__(self):
        return str(self.settings)

    def get(self, *args, **kwargs):
        if self.settings is None:
            return None
        return self.settings.get(*args, **kwargs)

    def save(self):
        """
        Сохраняет настройки в JSON файл.

        :param file_path: Путь к файлу, в который будут сохранены настройки.
        :param settings: Словарь с настройками.
        """
        try:
            with open(self.file_path, 'w', encoding='utf-8') as file:
                json.dump(self.settings, file, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении настроек: {e}")

    def load(self):
        """
        Загружает настройки из JSON файла.

        :param file_path: Путь к файлу, из которого будут загружены настройки.
        :return: Словарь с настройками.
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                self.settings = json.load(file)

            # Выставляем новые настройки, если они добавлялись в default_settings,
            # но еще не появились в файле настроек (FILE_PATH)
            for key, value in self.default_settings.items():
                if key not in self.settings:
                    self.settings[key] = value
            self.logger.info("Настройки успешно загружены.")
        except Exception as e:
            self.settings = copy.deepcopy(self.default_settings)
            self.logger.error(f"Ошибка при загрузке настроек: {e}")

    def clear_notifications(self):
        self.notifications = {'admins': [], 'only_taken': []}
