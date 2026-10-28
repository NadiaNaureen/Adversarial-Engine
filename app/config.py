from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    # Set RAG_MODE=local for an offline synthetic demo.
    rag_mode: str = "gemini"
    # Bound cloud requests to keep the dashboard responsive.
    gemini_request_timeout_seconds: float = 120.0
    gemini_chat_timeout_seconds: float = 20.0
    gemini_fallback_to_local: bool = True
    chroma_path: Path = Path("chroma_data")
    reports_path: Path = Path("reports")
    top_k: int = 4
    max_attack_budget_tokens: int = 500


settings = Settings()
