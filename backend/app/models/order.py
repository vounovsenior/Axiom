"""
Модель ордера
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, BigInteger, Float, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.db import Base


class OrderSide(str, enum.Enum):
    """Сторона ордера"""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    """Тип ордера"""
    LIMIT = "limit"
    MARKET = "market"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, enum.Enum):
    """Статус ордера"""
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Order(Base):
    """Модель ордера"""
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    
    # Параметры ордера
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # buy/sell
    order_type: Mapped[str] = mapped_column(String(20), default="limit")  # limit/market
    
    # Цена и количество
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # Изначальное количество
    filled: Mapped[float] = mapped_column(Float, default=0.0)  # Заполненное количество
    
    # Статус
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    
    # Дополнительные параметры для стоп-лоссов
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Время
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Связи
    user: Mapped["User"] = relationship("User", back_populates="orders")
    trades: Mapped[list["Trade"]] = relationship(
        "Trade",
        foreign_keys="Trade.buy_order_id",
        back_populates="buy_order"
    )
    
    @property
    def remaining(self) -> float:
        """Оставшееся количество"""
        return self.amount - self.filled
    
    @property
    def is_open(self) -> bool:
        """Проверка, открыт ли ордер"""
        return self.status in [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]
    
    def __repr__(self) -> str:
        return f"<Order(id={self.id}, side={self.side}, price={self.price}, amount={self.amount})>"
