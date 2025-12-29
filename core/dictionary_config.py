"""Dictionary configuration with Pydantic validation."""

from pydantic import BaseModel, Field


class DictionaryConfig(BaseModel):
    """Configuration for Dictionary with validation."""

    enabled_languages: list[str] = Field(
        default_factory=lambda: ["en", "de"], description="Language codes to load"
    )
    custom_paths: dict[str, str] = Field(
        default_factory=dict, description="Custom dictionary paths per language"
    )
    accept_all_mode: bool = Field(
        default=False, description="Skip validation, accept all 3+ letter words"
    )
    auto_fallback: bool = Field(
        default=True, description="Auto-enable accept_all if no dictionaries found"
    )

    class Config:
        """Pydantic model configuration."""

        extra = "ignore"


__all__ = ["DictionaryConfig"]
