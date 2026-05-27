from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

LlmProvider = Literal["huggingface", "openai_compatible", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: LlmProvider = "huggingface"
    hf_model_id: str = "tencent/Hy-MT2-1.8B"
    hf_max_new_tokens: int = 256
    hf_preload_on_startup: bool = True
    hf_attn_implementation: str = "eager"

    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "local-model"
    llm_api_key: str = "not-needed"
    llm_timeout_seconds: float = 180.0

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

    tts_voice: str = "ja-JP-NanamiNeural"
    tts_prefer_gtts: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ankiconnect_url: str = "http://127.0.0.1:8765"
    anki_deck_name: str = "日本語の文"
    anki_model_name: str = "Lapis"


settings = Settings()
