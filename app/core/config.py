from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Base Config
    HOST: str = "0.0.0.0"
    PORT: int = 5555
    DEBUG: bool = False

    # Secrets
    APP_SECRET_KEY: str = "some_super_secret_key"
    KODIK_TOKEN: Optional[str] = None

    # Optional Third-Party Services
    SHIKIMORI_MIRROR: Optional[str] = None
    USE_KODIK_SEARCH: bool = False

    # Infrastructure
    REDIS_URL: str = "redis://localhost:6379/0"
    # If None, the frontend will try to detect the origin dynamically
    WS_URL: Optional[str] = None
    API_URL: Optional[str] = None

    # Cache and Storage Config
    SAVE_DATA: bool = True
    USE_SAVED_DATA: bool = True
    SAVED_DATA_FILE: str = "cache.json"
    SAVING_PERIOD: int = 5
    CACHE_LIFE_TIME: int = 3

    # App Features Config
    ALLOW_WATCH_TOGETHER: bool = True
    REMOVE_TIME: int = 5
    ALLOW_NSFW: bool = False
    IMAGE_NOT_FOUND: str = "/resources/no-image.png"
    IMAGE_AGE_RESTRICTED: str = "/resources/age-restricted.png"
    FAVICON_PATH: str = "resources/A.ico"
    USE_LXML: bool = True

    # Security
    ADMIN_USERNAME: str = "user"
    # Default is the bcrypt hash of 'user'. MUST be changed in production.
    ADMIN_PASSWORD_HASH: str = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjIQqi.wvy"  # noqa: E501
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow"
    )


settings = Settings()
