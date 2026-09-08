"""
Конфигурация приложения
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Базовые настройки
    APP_NAME: str = "TON Crypto Exchange"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # JWT настройки
    JWT_SECRET_KEY: str = Field(default="your-secret-key-change-in-production-12345")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа
    
    # База данных
    DATABASE_URL: str = "sqlite+aiosqlite:///./crypto_exchange.db"
    DATABASE_ECHO: bool = False
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # TON Testnet конфигурация
    TON_LITESERVER_IP: int = 92
    TON_LITESERVER_PORT: int = 30001
    TON_LITESERVER_KEY: str = "Ef87SoL0pnAjY_LhjsXqHZ0PNwD6S9ktyDnhKZNHZ9C6f8D0"
    
    # TON Mainnet (закомментировано для безопасности)
    # TON_MAINNET_LITESERVER_IP: int = ...
    
    # Комиссия для вывода
    WITHDRAW_FEE: float = 0.001  # TON
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
