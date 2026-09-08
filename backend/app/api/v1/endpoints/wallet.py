"""
Эндпоинты для работы с кошельком
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import get_current_user_from_token
from app.models.user import User
from app.models.wallet import Wallet
from app.models.order import Order, OrderStatus
from app.services.ton_client import ton_client
from pydantic import BaseModel, Field

router = APIRouter(prefix="/wallet", tags=["wallet"])


class BalanceResponse(BaseModel):
    """Ответ с балансом"""
    address: str
    balance_ton: float = Field(..., description="Баланс в TON")
    balance_nano: int = Field(..., description="Баланс в нанотоннах")
    cached_balance: float = Field(..., description="Кешированный баланс")
    is_cached: bool = Field(..., description="Использован ли кеш")


class WithdrawRequest(BaseModel):
    """Запрос на вывод"""
    address: str = Field(..., description="Адрес получателя")
    amount: float = Field(..., gt=0, description="Сумма в TON")
    comment: Optional[str] = Field(None, description="Комментарий")


class WithdrawResponse(BaseModel):
    """Ответ на вывод"""
    tx_hash: str
    amount: float
    fee: float
    to_address: str
    status: str


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    current_user: User = Depends(get_current_user_from_token),
    session: AsyncSession = Depends(get_db),
    use_cache: bool = True
):
    """
    Получить баланс TON кошелька
    
    - Возвращает баланс в TON и нанотоннах
    - Поддерживает кеширование
    """
    # Получаем кошелек пользователя
    result = await session.execute(
        select
