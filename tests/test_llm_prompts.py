"""Tests for LLM prompt management."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.storage import Storage
from utils.config import Config
from utils.crypto import CryptoManager


class InMemoryKeyring:
    """Simple in-memory keyring for tests to avoid DBus issues."""

    def __init__(self):
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def mock_keyring():
    """Use in-memory keyring for all tests to avoid DBus race conditions."""
    mock = InMemoryKeyring()
    with patch("utils.crypto.keyring", mock):
        yield mock


@pytest.fixture
def storage(temp_db, mock_keyring):
    """Create storage with temporary database."""
    # Initialize encryption key first
    crypto = CryptoManager(temp_db)
    if not crypto.key_exists():
        crypto.initialize_database_key()

    config = Config(temp_db)
    return Storage(temp_db, config=config)


class TestLLMPrompts:
    """Test LLM prompt database operations."""

    def test_llm_prompts_table_exists(self, storage):
        """Test that llm_prompts table is created."""
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_prompts'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "llm_prompts"

    def test_initialize_default_prompts(self, storage):
        """Test default prompts are initialized."""
        storage.reset_default_prompts()

        prompts = storage.get_all_prompts()
        assert len(prompts) == 3

        names = [p["name"] for p in prompts]
        assert "Professional Technical" in names
        assert "Casual Narrative" in names
        assert "Minimal Simple" in names

    def test_create_custom_prompt(self, storage):
        """Test creating custom prompt."""
        prompt_id = storage.create_prompt(
            "My Custom Prompt",
            "Generate text with {word_count}",
            is_default=False,
        )

        prompt = storage.get_prompt(prompt_id)
        assert prompt is not None
        assert prompt["name"] == "My Custom Prompt"
        assert prompt["is_default"] == False

    def test_update_prompt(self, storage):
        """Test updating prompt."""
        prompt_id = storage.create_prompt("Test", "Content")

        result = storage.update_prompt(prompt_id, "Updated", "New content")
        assert result is True

        prompt = storage.get_prompt(prompt_id)
        assert prompt["name"] == "Updated"
        assert prompt["content"] == "New content"

    def test_delete_custom_prompt(self, storage):
        """Test deleting custom prompt."""
        prompt_id = storage.create_prompt("Test", "Content")

        result = storage.delete_prompt(prompt_id)
        assert result is True

        prompt = storage.get_prompt(prompt_id)
        assert prompt is None

    def test_cannot_delete_default_prompt(self, storage):
        """Test default prompts cannot be deleted."""
        storage.reset_default_prompts()
        prompts = storage.get_all_prompts()

        for prompt in prompts:
            if prompt["is_default"]:
                result = storage.delete_prompt(prompt["id"])
                assert result is False

    def test_get_active_prompt(self, storage):
        """Test getting active prompt."""
        storage.reset_default_prompts()

        prompt = storage.get_active_prompt()
        assert prompt is not None
        assert "content" in prompt

    def test_initialize_default_prompts_only_if_empty(self, storage):
        """Test that initialize_default_prompts only creates prompts if none exist."""
        # First call should create prompts
        storage.initialize_default_prompts()
        prompts = storage.get_all_prompts()
        assert len(prompts) == 3

        # Create a custom prompt
        storage.create_prompt("Custom", "Custom content")

        # Second call should not delete the custom prompt
        storage.initialize_default_prompts()
        prompts = storage.get_all_prompts()
        assert len(prompts) == 4

        # Verify custom prompt still exists
        names = [p["name"] for p in prompts]
        assert "Custom" in names

    def test_prompt_has_placeholders(self, storage):
        """Test that default prompts contain required placeholders."""
        storage.reset_default_prompts()
        prompts = storage.get_all_prompts()

        for prompt in prompts:
            content = prompt["content"]
            assert "{word_count}" in content
            assert "{hardest_words}" in content
