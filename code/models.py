import enum
from datetime import datetime

from sqlalchemy import Column, Integer, String, TIMESTAMP, and_
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class PayoutActionEnum(enum.Enum):
    SUCCESS = (10, "Забран")
    FAIL = (20, "Не забран")

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def text(self) -> str:
        return self.value[1]


class Payout(Base):
    __tablename__ = 'payouts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(Integer, nullable=False)
    operation_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    bot_name = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    @classmethod
    def get_count_by_operation_id(cls, session, operation_id: str) -> int:
        return session.query(Payout).filter(and_(
            cls.operation_id == operation_id,
            cls.action == PayoutActionEnum.SUCCESS.code,
        )).count()

    @classmethod
    def get_count_by_operation_id_and_bot_name(cls, session, bot_name: str, operation_id: str) -> int:
        return session.query(Payout).filter(and_(
            cls.bot_name == bot_name,
            cls.operation_id == operation_id,
            cls.action == PayoutActionEnum.SUCCESS.code,
        )).count()

    @classmethod
    def get_count_by_date_and_action(cls, session, bot_name: str, date_str: str, action: int) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        return session.query(Payout).filter(
            and_(
                cls.bot_name == bot_name,
                cls.created_at >= start_date,
                cls.created_at <= end_date,
                cls.action == action
            )
        ).count()

    @classmethod
    def get_amount_sum_by_date_and_action(cls, session, date_str, action) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        return session.query(Payout).filter(
            and_(
                cls.created_at >= start_date,
                cls.created_at <= end_date,
                cls.action == action
            )
        ).count()
