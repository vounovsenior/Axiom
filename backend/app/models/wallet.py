"""
Модель кошелька
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, Integer, BigInteger, Text, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Wallet(Base):
    """Модель TON кошелька"""
    __tablename__ = "wallets"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    
    # Адрес кошелька в TON (человекочитаемый)
    address: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    # Сид-фраза (хранится в зашифрованном виде в реальном проекте)
    # ВНИМАНИЕ: В production используйте шифрование!
    seed_phrase: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Информация о кошельке
    wallet_type: Mapped[str] = mapped_column(String(50), default="v4r2")  # v4r2, v3, etc.
    workchain: Mapped[int] = mapped_column(Integer, default=0)
    
    # Баланс (кешируется)
    cached_balance: Mapped[float] = mapped_column(Float, default=0.0)
    balance_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Статус
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Связи
    user: Mapped["User"] = relationship("User", back_populates="wallets")
    
    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, address={self.address[:10]}...)>"
