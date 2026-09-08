"""
Движок матчинга ордеров
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderSide, OrderStatus
from app.models.trade import Trade
from app.core.db import AsyncSessionLocal
from app.services.ton_client import ton_client

logger = logging.getLogger(__name__)


class MatchingEngine:
    """Движок для сопоставления ордеров"""
    
    def __init__(self):
        self.is_running = False
        self.last_price = None
    
    async def match_orders(self):
        """
        Основной метод матчинга ордеров
        Сопоставляет buy и sell ордера
        """
        async with AsyncSessionLocal() as session:
            try:
                # Получаем открытые ордера на покупку (самые высокие цены)
                buy_orders = await self._get_open_buy_orders(session)
                
                # Получаем открытые ордера на продажу (самые низкие цены)
                sell_orders = await self._get_open_sell_orders(session)
                
                matched = False
                
                # Проходим по ордерам
                for buy in buy_orders:
                    if not buy.is_open:
                        continue
                    
                    for sell in sell_orders:
                        if not sell.is_open:
                            continue
                        
                        # Проверяем, совпадают ли цены
                        if buy.price >= sell.price:
                            # Вычисляем количество для сделки
                            buy_remaining = buy.remaining
                            sell_remaining = sell.remaining
                            
                            trade_amount = min(buy_remaining, sell_remaining)
                            trade_price = sell.price  # Используем цену продавца
                            
                            # Создаем сделку
                            await self._execute_trade(
                                session=session,
                                buy_order=buy,
                                sell_order=sell,
                                price=trade_price,
                                amount=trade_amount
                            )
                            
                            matched = True
                            
                            # Сохраняем последнюю цену
                            self.last_price = trade_price
                            
                            # Если ордер полностью заполнен, выходим
                            if not buy.is_open or not sell.is_open:
                                break
                    
                    if not buy.is_open:
                        continue
                
                if matched:
                    await session.commit()
                    logger.info("✅ Матчинг выполнен успешно")
                    return True
                
                return False
                
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Ошибка матчинга: {e}")
                raise
    
    async def _get_open_buy_orders(self, session: AsyncSession) -> List[Order]:
        """Получить открытые ордера на покупку"""
        result = await session.execute(
            select(Order)
            .where(
                and_(
                    Order.side == OrderSide.BUY.value,
                    Order.status.in_([OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]),
                    Order.amount > Order.filled
                )
            )
            .order_by(Order.price.desc(), Order.created_at.asc())
            .limit(100)
        )
        return list(result.scalars().all())
    
    async def _get_open_sell_orders(self, session: AsyncSession) -> List[Order]:
        """Получить открытые ордера на продажу"""
        result = await session.execute(
            select(Order)
            .where(
                and_(
                    Order.side == OrderSide.SELL.value,
                    Order.status.in_([OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]),
                    Order.amount > Order.filled
                )
            )
            .order_by(Order.price.asc(), Order.created_at.asc())
            .limit(100)
        )
        return list(result.scalars().all())
    
    async def _execute_trade(
        self,
        session: AsyncSession,
        buy_order: Order,
        sell_order: Order,
        price: float,
        amount: float
    ):
        """
        Выполнить сделку между двумя ордерами
        
        Args:
            session: Сессия БД
            buy_order: Ордер на покупку
            sell_order: Ордер на продажу
            price: Цена сделки
            amount: Количество
        """
        try:
            # Обновляем количество заполненных ордеров
            buy_order.filled += amount
            sell_order.filled += amount
            
            # Обновляем статусы
            if buy_order.filled >= buy_order.amount:
                buy_order.status = OrderStatus.FILLED.value
                buy_order.executed_at = datetime.utcnow()
            else:
                buy_order.status = OrderStatus.PARTIALLY_FILLED.value
            
            if sell_order.filled >= sell_order.amount:
                sell_order.status = OrderStatus.FILLED.value
                sell_order.executed_at = datetime.utcnow()
            else:
                sell_order.status = OrderStatus.PARTIALLY_FILLED.value
            
            # Создаем запись о сделке
            trade = Trade(
                buy_order_id=buy_order.id,
                sell_order_id=sell_order.id,
                buyer_id=buy_order.user_id,
                seller_id=sell_order.user_id,
                price=price,
                amount=amount,
                total=price * amount
            )
            
            session.add(trade)
            
            logger.info(
                f"💰 Сделка: {amount} TON по цене {price} "
                f"(Buy {buy_order.id} / Sell {sell_order.id})"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения сделки: {e}")
            raise


# Глобальный экземпляр движка матчинга
matching_engine = MatchingEngine()


async def run_matching_background():
    """Фоновая задача для матчинга"""
    while True:
        try:
            await matching_engine.match_orders()
            await asyncio.sleep(1)  # Пауза 1 секунда
        except Exception as e:
            logger.error(f"❌ Ошибка в фоновом матчинге: {e}")
            await asyncio.sleep(5)
