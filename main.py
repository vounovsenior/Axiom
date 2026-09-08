import asyncio
import hashlib
import json
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from pytoniq import WalletV4, Address, LiteBalancer, begin_cell
import aiosqlite

# ----- Конфигурация -----
SECRET_KEY = "your-secret-key-change-in-production-12345"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа

# TON testnet конфигурация
TON_TESTNET_CONFIG = {
    "liteservers": [
        {"ip": 92, "port": 30001, "id": {"@type": "pub.ed25519", "key": "Ef87SoL0pnAjY_LhjsXqHZ0PNwD6S9ktyDnhKZNHZ9C6f8D0"}}
    ],
    "@type": "config.config"
}

# В реальном проекте используйте переменные окружения
JWT_SECRET = "your-secret-key-change-in-production-12345"
REDIS_URL = "redis://localhost:6379/0"

# ----- Модели данных -----
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class OrderCreate(BaseModel):
    side: str  # "buy" или "sell"
    price: float = Field(..., gt=0)
    amount: float = Field(..., gt=0)

class WithdrawRequest(BaseModel):
    address: str
    amount: float = Field(..., gt=0)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    username: str
    wallet_address: Optional[str] = None

class BalanceResponse(BaseModel):
    address: str
    balance: float
    balance_nano: int

class OrderResponse(BaseModel):
    id: int
    user_id: int
    side: str
    price: float
    amount: float
    filled: float
    status: str
    created_at: str

# ----- JWT функции -----
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str) -> Dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return {"username": username, "user_id": payload.get("user_id")}
    except JWTError:
        raise credentials_exception

# ----- База данных (SQLite с async) -----
DB_PATH = "crypto_exchange.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                wallet_address TEXT UNIQUE,
                wallet_seed TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
                price REAL NOT NULL,
                amount REAL NOT NULL,
                filled REAL DEFAULT 0,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'filled', 'cancelled')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buy_order_id INTEGER,
                sell_order_id INTEGER,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(buy_order_id) REFERENCES orders(id),
                FOREIGN KEY(sell_order_id) REFERENCES orders(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                tx_hash TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        await db.commit()

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

# ----- TON кошелек (pytoniq) -----
async def create_ton_wallet():
    """Создает новый TON кошелек в testnet"""
    mnemonics = WalletV4.generate_mnemonics()
    wallet = await WalletV4.from_mnemonics(
        mnemonics=mnemonics,
        workchain=0
    )
    address = wallet.address.to_str(True, True, True)
    return {
        "address": address,
        "mnemonics": mnemonics,
        "wallet": wallet
    }

async def get_wallet_from_seed(seed: List[str]):
    """Восстанавливает кошелек из сид-фразы"""
    wallet = await WalletV4.from_mnemonics(mnemonics=seed, workchain=0)
    return wallet

async def get_ton_balance(address: str) -> int:
    """Получает баланс TON в нанотоннах"""
    try:
        provider = LiteBalancer.from_config(TON_TESTNET_CONFIG)
        await provider.start_up()
        try:
            addr = Address(address)
            balance = await provider.get_balance(addr)
            return balance
        finally:
            await provider.close()
    except Exception as e:
        print(f"Error getting balance: {e}")
        return 0

async def send_ton(from_wallet: WalletV4, to_address: str, amount_nano: int):
    """Отправляет TON"""
    try:
        provider = LiteBalancer.from_config(TON_TESTNET_CONFIG)
        await provider.start_up()
        try:
            to_addr = Address(to_address)
            # Создаем транзакцию
            tx = await from_wallet.transfer(
                provider=provider,
                destination=to_addr,
                amount=amount_nano,
                body=begin_cell().store_uint(0, 32).store_string("Withdraw from exchange").end_cell(),
            )
            return tx
        finally:
            await provider.close()
    except Exception as e:
        print(f"Error sending TON: {e}")
        raise

# ----- Redis кеш -----
class RedisCache:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    
    async def close(self):
        if self.redis:
            await self.redis.close()
    
    async def get(self, key: str):
        return await self.redis.get(key)
    
    async def set(self, key: str, value: str, expire: int = 60):
        await self.redis.set(key, value, ex=expire)
    
    async def delete(self, key: str):
        await self.redis.delete(key)

cache = RedisCache()

# ----- Матчинг ордеров -----
async def match_orders():
    """Простой матчинг ордеров - buy и sell по цене"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Получаем открытые buy ордера (сортировка по цене убывания)
        buy_orders = await db.execute("""
            SELECT * FROM orders 
            WHERE side = 'buy' AND status = 'open' AND amount > filled
            ORDER BY price DESC, created_at ASC
        """)
        buys = await buy_orders.fetchall()
        
        # Получаем открытые sell ордера (сортировка по цене возрастания)
        sell_orders = await db.execute("""
            SELECT * FROM orders 
            WHERE side = 'sell' AND status = 'open' AND amount > filled
            ORDER BY price ASC, created_at ASC
        """)
        sells = await sell_orders.fetchall()
        
        matched = False
        for buy in buys:
            for sell in sells:
                if sell['id'] == buy['id']:
                    continue
                if buy['price'] >= sell['price']:
                    # Нашли совпадение
                    buy_remaining = buy['amount'] - buy['filled']
                    sell_remaining = sell['amount'] - sell['filled']
                    trade_amount = min(buy_remaining, sell_remaining)
                    trade_price = sell['price']  # Цена продавца
                    
                    # Обновляем ордера
                    new_buy_filled = buy['filled'] + trade_amount
                    new_sell_filled = sell['filled'] + trade_amount
                    
                    buy_status = 'filled' if new_buy_filled >= buy['amount'] else 'open'
                    sell_status = 'filled' if new_sell_filled >= sell['amount'] else 'open'
                    
                    await db.execute("""
                        UPDATE orders SET filled = ?, status = ? WHERE id = ?
                    """, (new_buy_filled, buy_status, buy['id']))
                    
                    await db.execute("""
                        UPDATE orders SET filled = ?, status = ? WHERE id = ?
                    """, (new_sell_filled, sell_status, sell['id']))
                    
                    # Записываем сделку
                    await db.execute("""
                        INSERT INTO trades (buy_order_id, sell_order_id, price, amount)
                        VALUES (?, ?, ?, ?)
                    """, (buy['id'], sell['id'], trade_price, trade_amount))
                    
                    await db.commit()
                    matched = True
                    
                    # Кешируем последнюю цену
                    await cache.set("last_price", str(trade_price), 3600)
                    
                    # Если один из ордеров заполнен, выходим из цикла
                    if buy_status == 'filled' or sell_status == 'filled':
                        break
            
            if matched:
                break
    
    return matched

# ----- FastAPI приложение -----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация БД
    await init_db()
    # Подключение к Redis
    await cache.connect()
    yield
    # Очистка
    await cache.close()

app = FastAPI(title="TON Crypto Exchange API", lifespan=lifespan)
security = HTTPBearer()

# ----- Аутентификация -----
async def get_current_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    return await get_current_user(token)

# ----- Эндпоинты -----
@app.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserRegister, background_tasks: BackgroundTasks):
    """Регистрация нового пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверка существующего пользователя
        existing = await db.execute(
            "SELECT id FROM users WHERE username = ?", (user_data.username,)
        )
        if await existing.fetchone():
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Хеширование пароля
        password_hash = pwd_context.hash(user_data.password)
        
        # Создание TON кошелька
        wallet_data = await create_ton_wallet()
        
        # Сохранение пользователя
        await db.execute(
            """INSERT INTO users (username, password_hash, wallet_address, wallet_seed) 
               VALUES (?, ?, ?, ?)""",
            (user_data.username, password_hash, wallet_data['address'], 
             json.dumps(wallet_data['mnemonics']))
        )
        await db.commit()
        
        # Получаем ID пользователя
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (user_data.username,)
        )
        user = await cursor.fetchone()
        
        # Создаем JWT
        access_token = create_access_token(
            data={"sub": user_data.username, "user_id": user['id']}
        )
        
        # Фоновая задача: добавить тестовые TON для нового пользователя (testnet)
        background_tasks.add_task(fund_testnet_wallet, wallet_data['address'])
        
        return {"access_token": access_token, "token_type": "bearer"}

async def fund_testnet_wallet(address: str):
    """Фоновая задача для отправки тестовых TON (testnet faucet)"""
    # В testnet можно использовать бесплатный faucet
    # Здесь мы просто логируем, что кошелек создан
    print(f"New wallet created on testnet: {address}")
    # В реальном проекте можно интегрировать API faucet

@app.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    """Вход в систему"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await db.execute(
            "SELECT * FROM users WHERE username = ?", (user_data.username,)
        )
        user_row = await user.fetchone()
        
        if not user_row:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not pwd_context.verify(user_data.password, user_row['password_hash']):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        access_token = create_access_token(
            data={"sub": user_row['username'], "user_id": user_row['id']}
        )
        return {"access_token": access_token, "token_type": "bearer"}

@app.get("/user/profile", response_model=UserResponse)
async def get_profile(current_user: Dict = Depends(get_current_user_from_token)):
    """Получить профиль текущего пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await db.execute(
            "SELECT id, username, wallet_address FROM users WHERE id = ?",
            (current_user['user_id'],)
        )
        user_row = await user.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(
            id=user_row['id'],
            username=user_row['username'],
            wallet_address=user_row['wallet_address']
        )

@app.get("/wallet/balance", response_model=BalanceResponse)
async def get_balance(current_user: Dict = Depends(get_current_user_from_token)):
    """Получить баланс TON кошелька"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await db.execute(
            "SELECT wallet_address FROM users WHERE id = ?",
            (current_user['user_id'],)
        )
        user_row = await user.fetchone()
        if not user_row or not user_row['wallet_address']:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        address = user_row['wallet_address']
        balance_nano = await get_ton_balance(address)
        balance_ton = balance_nano / 1_000_000_000
        
        return BalanceResponse(
            address=address,
            balance=balance_ton,
            balance_nano=balance_nano
        )

@app.post("/wallet/withdraw")
async def withdraw(
    request: WithdrawRequest,
    current_user: Dict = Depends(get_current_user_from_token)
):
    """Вывод TON на внешний адрес"""
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await db.execute(
            "SELECT wallet_address, wallet_seed FROM users WHERE id = ?",
            (current_user['user_id'],)
        )
        user_row = await user.fetchone()
        if not user_row or not user_row['wallet_address']:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        # Проверяем баланс
        balance_nano = await get_ton_balance(user_row['wallet_address'])
        amount_nano = int(request.amount * 1_000_000_000)
        
        if amount_nano > balance_nano:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        
        try:
            # Восстанавливаем кошелек
            seed = json.loads(user_row['wallet_seed'])
            wallet = await get_wallet_from_seed(seed)
            
            # Отправляем транзакцию
            tx_hash = await send_ton(wallet, request.address, amount_nano)
            
            # Записываем транзакцию
            await db.execute("""
                INSERT INTO transactions (user_id, type, amount, status, tx_hash, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                current_user['user_id'],
                'withdraw',
                request.amount,
                'completed',
                str(tx_hash),
                json.dumps({"to": request.address})
            ))
            await db.commit()
            
            return {
                "status": "success",
                "tx_hash": str(tx_hash),
                "amount": request.amount,
                "to": request.address
            }
        except Exception as e:
            # Записываем неудачную транзакцию
            await db.execute("""
                INSERT INTO transactions (user_id, type, amount, status, details)
                VALUES (?, ?, ?, ?, ?)
            """, (
                current_user['user_id'],
                'withdraw',
                request.amount,
                'failed',
                json.dumps({"error": str(e), "to": request.address})
            ))
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Withdraw failed: {str(e)}")

@app.post("/orders/create", response_model=OrderResponse)
async def create_order(
    order: OrderCreate,
    current_user: Dict = Depends(get_current_user_from_token)
):
    """Создать новый ордер"""
    if order.side not in ['buy', 'sell']:
        raise HTTPException(status_code=400, detail="Side must be 'buy' or 'sell'")
    
    if order.price <= 0 or order.amount <= 0:
        raise HTTPException(status_code=400, detail="Price and amount must be positive")
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Проверяем наличие кошелька
        user = await db.execute(
            "SELECT wallet_address, wallet_seed FROM users WHERE id = ?",
            (current_user['user_id'],)
        )
        user_row = await user.fetchone()
        if not user_row or not user_row['wallet_address']:
            raise HTTPException(status_code=404, detail="Wallet not found")
        
        # Для sell проверяем баланс
        if order.side == 'sell':
            balance_nano = await get_ton_balance(user_row['wallet_address'])
            required_nano = int(order.amount * 1_000_000_000)
            if required_nano > balance_nano:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient balance. Required: {order.amount}, Available: {balance_nano / 1_000_000_000}"
                )
        
        # Создаем ордер
        cursor = await db.execute("""
            INSERT INTO orders (user_id, side, price, amount, filled, status)
            VALUES (?, ?, ?, ?, 0, 'open')
            RETURNING id, created_at
        """, (current_user['user_id'], order.side, order.price, order.amount))
        order_row = await cursor.fetchone()
        await db.commit()
        
        # Запускаем матчинг в фоне
        asyncio.create_task(match_orders())
        
        return OrderResponse(
            id=order_row['id'],
            user_id=current_user['user_id'],
            side=order.side,
            price=order.price,
            amount=order.amount,
            filled=0.0,
            status='open',
            created_at=order_row['created_at']
        )

@app.get("/orders", response_model=List[OrderResponse])
async def get_orders(current_user: Dict = Depends(get_current_user_from_token)):
    """Получить все ордера пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        orders = await db.execute("""
            SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC
        """, (current_user['user_id'],))
        rows = await orders.fetchall()
        return [
            OrderResponse(
                id=row['id'],
                user_id=row['user_id'],
                side=row['side'],
                price=row['price'],
                amount=row['amount'],
                filled=row['filled'],
                status=row['status'],
                created_at=row['created_at']
            )
            for row in rows
        ]

@app.get("/orders/open", response_model=List[OrderResponse])
async def get_open_orders(current_user: Dict = Depends(get_current_user_from_token)):
    """Получить открытые ордера пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        orders = await db.execute("""
            SELECT * FROM orders 
            WHERE user_id = ? AND status = 'open' AND amount > filled
            ORDER BY created_at DESC
        """, (current_user['user_id'],))
        rows = await orders.fetchall()
        return [
            OrderResponse(
                id=row['id'],
                user_id=row['user_id'],
                side=row['side'],
                price=row['price'],
                amount=row['amount'],
                filled=row['filled'],
                status=row['status'],
                created_at=row['created_at']
            )
            for row in rows
        ]

@app.delete("/orders/{order_id}")
async def cancel_order(
    order_id: int,
    current_user: Dict = Depends(get_current_user_from_token)
):
    """Отменить ордер"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        order = await db.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?",
            (order_id, current_user['user_id'])
        )
        order_row = await order.fetchone()
        
        if not order_row:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order_row['status'] != 'open':
            raise HTTPException(status_code=400, detail="Order is not open")
        
        await db.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ?",
            (order_id,)
        )
        await db.commit()
        
        return {"status": "cancelled", "order_id": order_id}

@app.get("/market/orderbook")
async def get_orderbook():
    """Получить книгу ордеров (все открытые ордера)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Buy ордера (цена убывание)
        buys = await db.execute("""
            SELECT price, SUM(amount - filled) as total_amount
            FROM orders
            WHERE side = 'buy' AND status = 'open' AND amount > filled
            GROUP BY price
            ORDER BY price DESC
            LIMIT 20
        """)
        buy_rows = await buys.fetchall()
        
        # Sell ордера (цена возрастание)
        sells = await db.execute("""
            SELECT price, SUM(amount - filled) as total_amount
            FROM orders
            WHERE side = 'sell' AND status = 'open' AND amount > filled
            GROUP BY price
            ORDER BY price ASC
            LIMIT 20
        """)
        sell_rows = await sells.fetchall()
        
        return {
            "bids": [{"price": row['price'], "amount": row['total_amount']} for row in buy_rows],
            "asks": [{"price": row['price'], "amount": row['total_amount']} for row in sell_rows]
        }

@app.get("/market/trades")
async def get_recent_trades(limit: int = 50):
    """Получить последние сделки"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        trades = await db.execute("""
            SELECT * FROM trades ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        rows = await trades.fetchall()
        return [
            {
                "id": row['id'],
                "price": row['price'],
                "amount": row['amount'],
                "time": row['created_at']
            }
            for row in rows
        ]

@app.get("/market/price")
async def get_current_price():
    """Получить текущую цену TON (последняя сделка или средняя)"""
    # Пробуем получить из кеша
    cached_price = await cache.get("last_price")
    if cached_price:
        return {"price": float(cached_price), "source": "cache"}
    
    # Ищем последнюю сделку
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        trade = await db.execute(
            "SELECT price FROM trades ORDER BY created_at DESC LIMIT 1"
        )
        row = await trade.fetchone()
        
        if row:
            await cache.set("last_price", str(row['price']), 60)
            return {"price": row['price'], "source": "trade"}
        
        # Если нет сделок, берем среднюю из ордеров
        orderbook = await get_orderbook()
        if orderbook['bids'] and orderbook['asks']:
            mid_price = (orderbook['bids'][0]['price'] + orderbook['asks'][0]['price']) / 2
            return {"price": mid_price, "source": "mid_price"}
        
        return {"price": 0.0, "source": "none"}

@app.get("/admin/run_matching")
async def run_matching():
    """Запустить матчинг вручную (для тестирования)"""
    result = await match_orders()
    return {"matched": result}

# ----- Запуск -----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
