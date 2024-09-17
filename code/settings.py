import copy
import dataclasses
import json
import os

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from code.logger import Logger


@dataclasses.dataclass
class Notifications:
    admins: list = dataclasses.field(default_factory=list)
    watchers: list = dataclasses.field(default_factory=list)

    def add_to_admins(self, value):
        """Add a value to the admins list."""
        self.admins.append(value)

    def add_to_watchers(self, value):
        """Add a value to the only_taken list."""
        self.watchers.append(value)

    def add_to_all(self, value):
        """Add a value to both admins and only_taken lists."""
        self.admins.append(value)
        self.watchers.append(value)


class Settings:
    bot_name: str
    bot: Bot = None
    dp: Dispatcher = None
    db_pool: None = None
    default_settings: dict = {
        "min_amount": 50_000,
        "max_amount": 80_000,
        "auth_cookie": "",
        "is_running": False,
        "update_offset": None,
        "payouts_limit": 10,
    }
    settings: dict = None
    notifications: Notifications = Notifications()
    file_path: str = 'settings.json'

    def __init__(self, bot_name: str, logger: Logger):
        self.bot_name = bot_name
        self.logger = logger

        self.engine = create_async_engine(
            '{DB}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'.format(
                DB=os.getenv("DB"),
                DB_USER=os.getenv("DB_USER"),
                DB_PASS=os.getenv("DB_PASS"),
                DB_HOST=os.getenv("DB_HOST"),
                DB_PORT=os.getenv("DB_PORT"),
                DB_NAME=os.getenv("DB_NAME")
            )
        )

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
            self.logger.error(f"Settings save error: {e}")

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
            self.logger.info("Settings loaded.")
        except Exception as e:
            self.settings = copy.deepcopy(self.default_settings)
            self.logger.error(f"Settings load error: {e}")

    def clear_notifications(self):
        self.notifications = Notifications()

    @property
    def db_session(self):
        return sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
