from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/ecommerce_tracker"
    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 20
    ECHO_SQL: bool = False

    class Config:
        env_file = ".env"


settings = Settings()