"""Application configuration via environment variables with pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Pipeline configuration loaded from environment variables.

    All settings can be overridden via environment variables or a .env file.
    Example: OPENAI_API_KEY=sk-... sets openai_api_key.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI Image Generation
    openai_api_key: str = Field(
        default="", description="OpenAI API key for image generation and chat completion"
    )
    image_model: str = Field(default="gpt-image-1.5", description="Image generation model")
    dalle_quality: str = Field(default="standard", description="Image quality: 'standard' or 'hd'")
    image_style: str = Field(default="vivid", description="Image style: 'vivid' or 'natural'")

    # Paths
    data_dir: str = Field(default="data", description="Base data directory")
    output_dir: str = Field(default="data/output", description="Base output directory")
    input_assets_dir: str = Field(
        default="data/input_assets", description="Directory containing existing assets"
    )
    brand_config_path: str = Field(
        default="data/brand/brand_config.yaml", description="Path to brand config file"
    )
    fonts_dir: str = Field(
        default="src/assets/fonts", description="Directory containing font files"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Console log level")

    # Storage
    storage_backend: str = Field(default="local", description="Storage backend: 'local' or 's3'")
    s3_bucket: str = Field(default="", description="S3 bucket name for asset storage")
    s3_prefix: str = Field(default="campaigns/", description="S3 key prefix for assets")
    s3_region: str = Field(default="us-east-1", description="AWS region for S3")
    aws_access_key_id: str = Field(default="", description="AWS access key ID for S3")
    aws_secret_access_key: str = Field(default="", description="AWS secret access key for S3")

    # Web UI
    web_host: str = Field(default="0.0.0.0", description="Web server bind host")
    web_port: int = Field(default=8080, description="Web server port")
    cors_origins: str = Field(default="*", description="Comma-separated CORS allowed origins")
    upload_dir: str = Field(default="data/uploads", description="Temp directory for uploaded files")

    # Resilience
    max_retries: int = Field(default=3, description="Max retries for API calls")
    api_timeout_seconds: int = Field(default=60, description="API call timeout in seconds")
    fallback_to_placeholder: bool = Field(
        default=True, description="Generate placeholder if all GenAI calls fail"
    )


def get_settings() -> Settings:
    """Create and return a Settings instance.

    Returns:
        Validated Settings loaded from environment.
    """
    return Settings()
