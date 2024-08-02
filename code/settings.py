import copy
import json

from logger import Logger


class Settings:
    default_settings = {
        "min_amount": 50_000,
        "max_amount": 80_000,
        "auth_cookie": "",
        "is_running": False,
        "update_offset": None,
        "payouts_limit": 10,
    }
    settings = None
    file_path = None

    def __init__(self, file_path: str, logger: Logger):
        self.file_path = file_path
        self.logger = logger

    def save(self):
        """
        Сохраняет настройки в JSON файл.

        :param file_path: Путь к файлу, в который будут сохранены настройки.
        :param settings: Словарь с настройками.
        """
        try:
            with open(self.file_path, 'w', encoding='utf-8') as file:
                json.dump(self.settings, file, ensure_ascii=False, indent=4)
            self.logger.info("Настройки успешно сохранены.")
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

    def __setitem__(self, key, value):
        self.settings[key] = value
        self.save()

    def __getitem__(self, key):
        return self.settings[key]

    def __repr__(self):
        return repr(self.settings)

    def get(self, *args, **kwargs):
        if self.settings is None:
            return None
        return self.settings.get(*args, **kwargs)

    def __str__(self):
        return str(self.settings)
