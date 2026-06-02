from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "travel-experiences-backend"
    APP_ENV: str = "local"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./app.db"

    SECRET_KEY: str = "dev-secret-key-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    MOCK_PAYMENT_WEBHOOK_SECRET: str = "dev-mock-secret"
    MOCK_PAYMENT_BASE_URL: str = "https://mock-payments.local/pay"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
