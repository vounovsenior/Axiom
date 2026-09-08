"""
Модель сделки
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, BigInteger, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Trade(Base):
    """Модель сделки (матчинг ордеров)"""
    __tablename__ = "trades"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    
    # Ордера
    buy_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    sell_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    
    # Участники
    buyer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    
    # Параметры сделки
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)  # price * amount
    
    # Время
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    
    # Связи
    buy_order: Mapped["Order"] = relationship(
        "Order",
        foreign_keys=[buy_order_id],
        back_populates="trades"
    )
    sell_order: Mapped["Order"] = relationship(
        "Order",
        foreign_keys=[sell_order_id],
        backref="sell_trades"
    )
    buyer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[buyer_id],
        back_populates="trades"
    )
    seller: Mapped["User"] = relationship(
        "User",
        foreign_keys=[seller_id],
        backref="sell_trades"
    )
    
    def __repr__(self) -> str:
        return f"<Trade(id={self.id}, price={self.price}, amount={self.amount})>"
