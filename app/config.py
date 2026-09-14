from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    ai_provider: Literal["ollama", "openai"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    app_access_key: str = ""
    app_env: str = "development"
    database_path: str = "data/reviewlens.db"
    job_timeout_seconds: int = Field(default=600, ge=10, le=1800)
    max_pending_jobs: int = Field(default=8, ge=1, le=50)
    live_jobs_per_hour: int = Field(default=10, ge=1, le=1000)
    retention_days: int = Field(default=7, ge=1, le=90)

    @property
    def live_enabled(self) -> bool:
        provider_configured = self.ai_provider == "ollama" or bool(self.openai_api_key)
        return provider_configured and (
            self.app_env != "production" or len(self.app_access_key) >= 24
        )
