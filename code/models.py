import enum
from datetime import datetime
from typing import Sequence

from sqlalchemy import Column, Integer, Boolean, String, TIMESTAMP, and_, Table, ForeignKey, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

user_bot_association = Table(
    'user_bot_association', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('bot_id', Integer, ForeignKey('bots.id'), primary_key=True)
)


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    chat_id = Column(String, nullable=False, unique=True)
    is_admin = Column(Boolean, nullable=False, default=False)

    # Many-to-many relationship with Bot
    bots = relationship('Bot', secondary=user_bot_association, back_populates='users')

    @classmethod
    async def get_all(cls, session: AsyncSession) -> Sequence['User']:
        result = await session.execute(select(User))
        return result.scalars().all()

    @classmethod
    async def get_by_id(cls, session: AsyncSession, user_id: int) -> 'User':
        result = await session.execute(select(User).filter(cls.id == user_id))
        return result.scalars().first()

    @classmethod
    async def get_by_bot_id(cls, session, bot_id: int) -> Sequence['User']:
        result = await session.execute(select(User).filter(User.bots.any(Bot.id.in_([bot_id]))))
        return result.scalars().all()


class Bot(Base):
    __tablename__ = 'bots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_name = Column(String, nullable=False)

    is_running = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    min_amount = Column(Integer, nullable=False)
    max_amount = Column(Integer, nullable=False)

    tg_bot_token = Column(String, nullable=True)

    turcode_login = Column(String, nullable=True)
    turcode_pass = Column(String, nullable=True)
    auth_cookie = Column(String, nullable=True)

    claimed_payouts_limit = Column(Integer, nullable=False)
    claimed_payouts_count = Column(Integer, nullable=False, default=0)

    users = relationship('User', secondary=user_bot_association, back_populates='bots', lazy='subquery')

    @classmethod
    async def get_active(cls, session: AsyncSession) -> Sequence['Bot']:
        result = await session.execute(select(Bot).filter(cls.is_active))
        return result.scalars().all()

    @classmethod
    async def get_by_id(cls, session: AsyncSession, bot_id: int) -> 'Bot':
        result = await session.execute(select(Bot).filter(cls.id == bot_id))
        return result.scalars().first()

    async def add_user(self, session: AsyncSession, user: User):
        """Add user to bot's user list"""
        if user not in self.users:
            self.users.append(user)
            await session.commit()

    async def remove_user(self, session: AsyncSession, user: User):
        """Remove user from bot's user list"""
        if user in self.users:
            self.users.remove(user)
            await session.commit()

    async def set_is_running(self, session: AsyncSession, is_running: bool):
        await session.execute(update(Bot).where(Bot.id == self.id).values(is_running=is_running))

    async def set_min_amount(self, session: AsyncSession, min_amount: int):
        await session.execute(update(Bot).where(Bot.id == self.id).values(min_amount=min_amount))

    async def set_max_amount(self, session: AsyncSession, max_amount: int):
        await session.execute(update(Bot).where(Bot.id == self.id).values(max_amount=max_amount))

    async def set_claimed_payouts_count(self, session: AsyncSession, claimed_payouts_count: int):
        await session.execute(update(Bot).where(Bot.id == self.id).values(claimed_payouts_count=claimed_payouts_count))

    async def set_claimed_payouts_limit(self, session: AsyncSession, claimed_payouts_limit: int):
        await session.execute(update(Bot).where(Bot.id == self.id).values(claimed_payouts_limit=claimed_payouts_limit))

    async def set_auth_cookie(self, session: AsyncSession, auth_cookie: str | None):
        await session.execute(update(Bot).where(Bot.id == self.id).values(auth_cookie=auth_cookie))


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
    bank_name = Column(String, nullable=True)
    card = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    payout_id = Column(String, nullable=True)

    is_gained_and_notified = Column(Boolean, nullable=False, default=False)

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    async def set_is_gained_and_notified(self, session: AsyncSession, is_gained_and_notified: bool):
        await session.execute(update(Payout).where(Payout.id == self.id).values(is_gained_and_notified=is_gained_and_notified))

    @classmethod
    async def get_not_gained_by_operation_id(cls, session: AsyncSession, operation_id: str) -> Sequence['Payout']:
        result = await session.execute(select(Payout).where(and_(
            cls.operation_id == operation_id,
            cls.action == PayoutActionEnum.SUCCESS.code,
            cls.is_gained_and_notified.is_(False),
        )).order_by(Payout.id.desc()))
        return result.scalars().all()

    # @classmethod
    # def get_count_by_operation_id(cls, session, operation_id: str) -> int:
    #     return session.query(Payout).filter(and_(
    #         cls.operation_id == operation_id,
    #         cls.action == PayoutActionEnum.SUCCESS.code,
    #     )).count()

    # @classmethod
    # def get_count_by_operation_id_and_bot_name(cls, session, bot_name: str, operation_id: str) -> int:
    #     return session.query(Payout).filter(and_(
    #         cls.bot_name == bot_name,
    #         cls.operation_id == operation_id,
    #         cls.action == PayoutActionEnum.SUCCESS.code,
    #     )).count()

    @classmethod
    async def get_count_by_date_and_action(cls, session: AsyncSession, bot_name: str, date_str: str,
                                           action: int) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        result = await session.execute(select(func.count(cls.id)).where(and_(
            cls.bot_name == bot_name,
            cls.created_at >= start_date,
            cls.created_at <= end_date,
            cls.action == action
        )))
        return result.scalar()

    @classmethod
    async def get_amount_sum_by_date_and_action(cls, session: AsyncSession, bot_name: str, date_str, action) -> int:
        start_date = datetime.strptime(date_str, "%d.%m.%Y")
        end_date = start_date.replace(hour=23, minute=59, second=59)

        result = await session.execute(select(func.sum(cls.amount)).where(and_(
            cls.bot_name == bot_name,
            cls.created_at >= start_date,
            cls.created_at <= end_date,
            cls.action == action
        )))
        return result.scalar()

    @classmethod
    async def search_payouts(cls, session: AsyncSession, value: str) -> Sequence['Payout']:
        result = await session.execute(select(cls).where(or_(
            cls.operation_id == value,
            cls.card == value,
            cls.phone == value,

        )).order_by(cls.created_at.desc()))
        return result.scalars().all()
