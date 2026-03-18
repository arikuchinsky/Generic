"""Application configuration via pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Legal Document Polisher"
    debug: bool = False

    # Paths
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"
    jobs_dir: Path = data_dir / "jobs"
    rules_config_path: Path = base_dir / "rules_config" / "default_rules.yaml"
    db_path: Path = data_dir / "examples.db"

    # API
    anthropic_api_key: str = ""
    vision_model: str = "claude-opus-4-20250918"

    # Processing
    vision_enabled: bool = True
    max_pages_for_vision: int = 100

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_prefix": "LDP_", "env_file": ".env"}


settings = Settings()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.jobs_dir.mkdir(parents=True, exist_ok=True)
