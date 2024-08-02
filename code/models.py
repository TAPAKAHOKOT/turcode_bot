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
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    # @classmethod
    # def add_row(cls, session, action, operation_id, user_id, amount):
    #     new_row = cls(action=action, operation_id=operation_id, user_id=user_id, amount=amount)
    #     session.add(new_row)
    #     session.commit()
    #     return new_row

    @classmethod
    def get_count_by_operation_id(cls, session, operation_id: str) -> int:
        return session.query(func.count(cls.id)).filter(and_(
            cls.operation_id == operation_id,
            cls.action == PayoutActionEnum.SUCCESS.code,
        )).scalar()

    @classmethod
    def get_count_by_date_and_action(cls, session, date_str, action) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        return session.query(func.count(cls.id)).filter(
            and_(
                cls.created_at >= start_date,
                cls.created_at <= end_date,
                cls.action == action
            )
        ).scalar()

    @classmethod
    def get_amount_sum_by_date_and_action(cls, session, date_str, action) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        return session.query(func.sum(cls.amount)).filter(
            and_(
                cls.created_at >= start_date,
                cls.created_at <= end_date,
                cls.action == action
            )
        ).scalar()
