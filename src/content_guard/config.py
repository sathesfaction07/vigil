from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CG_")

    redis_url: str = "redis://localhost:6379"
    bedrock_model: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_region: str = "us-east-1"
    catalog_api_url: str = "http://localhost:8001"
    max_marketplaces: int = 10
    classification_timeout: int = 30
    worker_concurrency: int = 5
    result_ttl_seconds: int = 3600
    log_level: str = "INFO"

    enricher: str = "none"  # "none" | "comprehend" | "local"
    multimodal: bool = False


settings = Settings()
