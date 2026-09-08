"""
Сервис для работы с TON блокчейном
"""
import asyncio
import json
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal

from pytoniq import WalletV4, Address, LiteBalancer, begin_cell
from pytoniq_core import Cell

from app.core.config import settings


class TONClient:
    """Клиент для работы с TON блокчейном"""
    
    def __init__(self):
        self.provider = None
        self.is_connected = False
        self.config = self._get_config()
    
    def _get_config(self) -> Dict:
        """Получить конфигурацию для LiteBalancer"""
        return {
            "liteservers": [
                {
                    "ip": settings.TON_LITESERVER_IP,
                    "port": settings.TON_LITESERVER_PORT,
                    "id": {
                        "@type": "pub.ed25519",
                        "key": settings.TON_LITESERVER_KEY
                    }
                }
            ],
            "@type": "config.config"
        }
    
    async def connect(self):
        """Подключиться к TON сети"""
        if not self.is_connected:
            self.provider = LiteBalancer.from_config(self.config)
            await self.provider.start_up()
            self.is_connected = True
            print("✅ Подключение к TON установлено")
    
    async def close(self):
        """Закрыть соединение"""
        if self.is_connected and self.provider:
            await self.provider.close()
            self.is_connected = False
    
    async def create_wallet(self) -> Tuple[str, List[str]]:
        """
        Создать новый TON кошелек
        
        Returns:
            Tuple[str, List[str]]: (адрес, мнемоническая фраза)
        """
        try:
            # Генерируем мнемонику
            mnemonics = WalletV4.generate_mnemonics()
            
            # Создаем кошелек
            wallet = await WalletV4.from_mnemonics(
                mnemonics=mnemonics,
                workchain=0
            )
            
            address = wallet.address.to_str(True, True, True)
            
            print(f"✅ Создан кошелек: {address}")
            return address, mnemonics
        except Exception as e:
            print(f"❌ Ошибка создания кошелька: {e}")
            raise
    
    async def get_wallet_from_seed(self, seed_phrase: str) -> WalletV4:
        """
        Восстановить кошелек из сид-фразы
        
        Args:
            seed_phrase: Сид-фраза в формате JSON строки
            
        Returns:
            WalletV4: Объект кошелька
        """
        try:
            mnemonics = json.loads(seed_phrase)
            wallet = await WalletV4.from_mnemonics(
                mnemonics=mnemonics,
                workchain=0
            )
            return wallet
        except Exception as e:
            print(f"❌ Ошибка восстановления кошелька: {e}")
            raise
    
    async def get_balance(self, address: str) -> int:
        """
        Получить баланс TON в нанотоннах
        
        Args:
            address: Адрес кошелька
            
        Returns:
            int: Баланс в нанотоннах
        """
        await self.connect()
        try:
            addr = Address(address)
            balance = await self.provider.get_balance(addr)
            return balance
        except Exception as e:
            print(f"❌ Ошибка получения баланса: {e}")
            return 0
    
    async def send_transaction(
        self,
        from_seed: str,
        to_address: str,
        amount_nano: int,
        comment: str = ""
    ) -> str:
        """
        Отправить TON транзакцию
        
        Args:
            from_seed: Сид-фраза отправителя (JSON строка)
            to_address: Адрес получателя
            amount_nano: Сумма в нанотоннах
            comment: Комментарий к транзакции
            
        Returns:
            str: Хэш транзакции
        """
        await self.connect()
        
        try:
            # Восстанавливаем кошелек отправителя
            wallet = await self.get_wallet_from_seed(from_seed)
            
            # Создаем получателя
            to_addr = Address(to_address)
            
            # Создаем тело транзакции
            body = begin_cell()
            if comment:
                body.store_uint(0, 32)  # op
                body.store_string(comment)
            else:
                body.store_uint(0, 32)
            
            # Отправляем транзакцию
            tx_hash = await wallet.transfer(
                provider=self.provider,
                destination=to_addr,
                amount=amount_nano,
                body=body.end_cell()
            )
            
            print(f"✅ Транзакция отправлена: {tx_hash}")
            return str(tx_hash)
            
        except Exception as e:
            print(f"❌ Ошибка отправки транзакции: {e}")
            raise
    
    async def get_transaction_status(self, tx_hash: str) -> Dict:
        """
        Получить статус транзакции
        
        Args:
            tx_hash: Хэш транзакции
            
        Returns:
            Dict: Информация о транзакции
        """
        await self.connect()
        try:
            # TODO: Реализовать проверку статуса транзакции
            # В pytoniq это может быть не реализовано напрямую
            return {
                "hash": tx_hash,
                "status": "pending",
                "message": "Status check not fully implemented"
            }
        except Exception as e:
            print(f"❌ Ошибка получения статуса: {e}")
            return {"error": str(e)}


# Создаем глобальный экземпляр клиента
ton_client = TONClient()
