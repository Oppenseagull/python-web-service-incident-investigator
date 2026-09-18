from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "lab"
    postgres_password: SecretStr
    postgres_db: str = "fault_lab"
    fault_lab_enabled: bool = False
    # Intentionally tiny, unrealistic defaults for a deterministic local lab.
    db_pool_size: int = Field(default=2, ge=1)
    db_max_overflow: int = Field(default=0, ge=0)
    db_pool_timeout: float = Field(default=1, gt=0, allow_inf_nan=False)

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
