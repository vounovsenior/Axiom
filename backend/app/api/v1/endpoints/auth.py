"""
Эндпоинты для аутентификации и регистрации
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.core.db import get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user_from_token
)
from app.models.user import User
from app.models.wallet import Wallet
from app.services.ton_client import ton_client

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()


# Схемы для валидации
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: Optional[str] = Field(None, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    wallet_address: Optional[str]
    created_at: datetime


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db)
):
    """
    Регистрация нового пользователя
    
    - Создает аккаунт
    - Генерирует TON кошелек
    - Возвращает JWT токен
    """
    # Проверяем, существует ли пользователь
    existing_user = await session.execute(
        select(User).where(User.username == user_data.username)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким именем уже существует"
        )
    
    # Проверяем email
    if user_data.email:
        existing_email = await session.execute(
            select(User).where(User.email == user_data.email)
        )
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже существует"
            )
    
    # Создаем пользователя
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hashed_password
    )
    session.add(new_user)
    await session.flush()  # Получаем ID
    
    # Создаем TON кошелек
    try:
        address, mnemonics = await ton_client.create_wallet()
        
        # Сохраняем кошелек
        wallet = Wallet(
            user_id=new_user.id,
            address=address,
            seed_phrase=json.dumps(mnemonics),
            is_default=True
        )
        session.add(wallet)
        await session.commit()
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка создания TON кошелька: {str(e)}"
        )
    
    # Создаем JWT токен
    access_token = create_access_token(
        data={"sub": new_user.username, "user_id": new_user.id}
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=24 * 60 * 60  # 24 часа
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    user_data: UserLogin,
    session: AsyncSession = Depends(get_db)
):
    """Вход в систему"""
    # Ищем пользователя
    result = await session.execute(
        select(User).where(User.username == user_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль"
        )
    
    # Обновляем время последнего входа
    user.last_login = datetime.utcnow()
    await session.commit()
    
    # Создаем токен
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=24 * 60 * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user_from_token),
    session: AsyncSession = Depends(get_db)
):
    """Получить информацию о текущем пользователе"""
    result = await session.execute(
        select(User).where(User.id == current_user.id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    # Получаем кошелек
    wallet_result = await session.execute(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.is_default == True)
    )
    wallet = wallet_result.scalar_one_or_none()
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        wallet_address=wallet.address if wallet else None,
        created_at=user.created_at
    )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Выход из системы
    В реальном проекте здесь можно добавить токен в черный список
    """
    return {"message": "Успешный выход из системы"}


# Импортируем json для создания кошелька
import json
