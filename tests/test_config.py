"""Tests for utils.config module."""

import pytest
import tempfile
from pathlib import Path

from utils.config import Config, AppSettings
from utils.crypto import CryptoManager


@pytest.fixture
def temp_db():
    """Create temporary database for config."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def config(temp_db):
    """Create Config instance with temporary database."""
    # Initialize encryption key first
    crypto = CryptoManager(temp_db)
    if not crypto.key_exists():
        crypto.initialize_database_key()
    return Config(temp_db)


class TestConfigInit:
    """Tests for Config initialization."""

    def test_config_initialization_creates_settings_table(self, config):
        """Test that settings table is created on initialization."""
        with config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
            )
            result = cursor.fetchone()
            assert result is not None

    def test_config_initialization_inserts_default_settings(self, config):
        """Test that all default settings are inserted."""
        with config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM settings")
            count = cursor.fetchone()[0]
            # Count fields in AppSettings model (exclude private fields)
            expected_count = len(AppSettings.model_fields)
            assert count == expected_count

    def test_config_initialization_all_default_keys_present(self, config):
        """Test that all AppSettings keys are in database."""
        all_settings = config.get_all()
        for key in AppSettings.model_fields:
            assert key in all_settings

    def test_config_db_path_stored(self, temp_db):
        """Test that db_path is stored correctly."""
        # Initialize encryption key first
        crypto = CryptoManager(temp_db)
        if not crypto.key_exists():
            crypto.initialize_database_key()
        config = Config(temp_db)
        assert config.db_path == temp_db


class TestConfigGet:
    """Tests for Config.get method."""

    def test_get_existing_key_returns_value(self, config):
        """Test getting an existing key returns its value."""
        value = config.get("burst_timeout_ms")
        expected = AppSettings.model_fields["burst_timeout_ms"].default
        assert value == expected  # Should be parsed as int

    def test_get_existing_key_string_value(self, config):
        """Test getting a key with string value."""
        value = config.get("keyboard_layout")
        expected = AppSettings.model_fields["keyboard_layout"].default
        assert value == expected

    def test_get_existing_key_bool_value(self, config):
        """Test getting a key with boolean value."""
        value = config.get("worst_letter_notifications_enabled")
        assert value is True

    def test_get_nonexistent_key_returns_default_from_defaults(self, config):
        """Test that nonexistent key returns value from AppSettings."""
        # Delete a key
        with config._get_connection() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'min_burst_key_count'")

        # get() returns from AppSettings default (typed as int)
        value = config.get("min_burst_key_count")
        expected = AppSettings.model_fields["min_burst_key_count"].default
        assert value == expected
        assert isinstance(value, int)

    def test_get_nonexistent_key_with_custom_default(self, config):
        """Test that custom default overrides DEFAULT_SETTINGS."""
        value = config.get("nonexistent_key", default="custom_value")
        assert value == "custom_value"

    def test_get_nonexistent_key_no_default_returns_none(self, config):
        """Test that missing key with no default returns None."""
        value = config.get("totally_fake_key_that_does_not_exist")
        assert value is None


class TestConfigTypeGetters:
    """Tests for typed getter methods."""

    def test_get_int_returns_integer(self, config):
        """Test get_int returns integer value."""
        value = config.get_int("burst_timeout_ms")
        expected = AppSettings.model_fields["burst_timeout_ms"].default
        assert isinstance(value, int)
        assert value == expected

    def test_get_int_converts_string(self, config):
        """Test get_int converts string to int."""
        config.set("test_int", "500")
        value = config.get_int("test_int")
        assert value == 500

    def test_get_int_invalid_string_returns_zero(self, config):
        """Test get_int with invalid string returns 0."""
        config.set("test_invalid", "not_a_number")
        value = config.get_int("test_invalid")
        assert value == 0

    def test_get_int_with_default(self, config):
        """Test get_int with custom default."""
        value = config.get_int("nonexistent_int", default=999)
        assert value == 999

    def test_get_int_uses_default_setting_fallback(self, config):
        """Test get_int falls back to AppSettings defaults."""
        # Remove from database
        with config._get_connection() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'burst_timeout_ms'")

        value = config.get_int("burst_timeout_ms")
        expected = AppSettings.model_fields["burst_timeout_ms"].default
        assert value == expected
        assert isinstance(value, int)

    def test_get_float_returns_float(self, config):
        """Test get_float returns float value."""
        value = config.get_float("burst_timeout_ms")
        expected = AppSettings.model_fields["burst_timeout_ms"].default
        assert isinstance(value, float)
        assert value == expected

    def test_get_float_converts_string(self, config):
        """Test get_float converts string to float."""
        config.set("test_float", "98.6")
        value = config.get_float("test_float")
        assert value == 98.6

    def test_get_float_integer_converts_to_float(self, config):
        """Test get_float converts integer string to float."""
        config.set("test_float_int", "100")
        value = config.get_float("test_float_int")
        assert value == 100.0

    def test_get_float_invalid_string_returns_zero(self, config):
        """Test get_float with invalid string returns 0.0."""
        config.set("test_invalid_float", "not_a_float")
        value = config.get_float("test_invalid_float")
        assert value == 0.0

    def test_get_float_with_default(self, config):
        """Test get_float with custom default."""
        value = config.get_float("nonexistent_float", default=3.14)
        assert value == 3.14

    def test_get_bool_true_values(self, config):
        """Test get_bool with various true representations."""
        # String true values
        for true_val in ["True", "true", "yes", "on"]:
            config.set("test_bool_true", true_val)
            value = config.get_bool("test_bool_true")
            assert value is True

        # Integer 1 should now be treated as True
        config.set("test_bool_int", "1")  # Stored as string '1', parsed to int 1
        assert config.get("test_bool_int") == 1  # get() returns int
        assert (
            config.get_bool("test_bool_int") is True
        )  # get_bool() handles int 1 as True

    def test_get_bool_false_values(self, config):
        """Test get_bool with various false representations."""
        for false_val in ["False", "false", "no", "off"]:
            config.set("test_bool_false", false_val)
            value = config.get_bool("test_bool_false")
            assert value is False

        # Integer 0 should be treated as False
        config.set("test_bool_int", 0)  # Set as int 0
        assert config.get("test_bool_int") == 0  # get() returns int 0
        assert (
            config.get_bool("test_bool_int") is False
        )  # get_bool() handles int 0 as False

    def test_get_bool_actual_boolean(self, config):
        """Test get_bool with actual boolean values."""
        config.set("test_bool_actual", True)
        value = config.get_bool("test_bool_actual")
        assert value is True

    def test_get_bool_with_default(self, config):
        """Test get_bool with custom default."""
        value = config.get_bool("nonexistent_bool", default=True)
        assert value is True

    def test_get_bool_fallback_to_default_settings(self, config):
        """Test get_bool falls back to DEFAULT_SETTINGS."""
        value = config.get_bool("worst_letter_notifications_enabled")
        assert value is True


class TestConfigSet:
    """Tests for Config.set method."""

    def test_set_creates_new_key(self, config):
        """Test that set() creates a new key-value pair."""
        config.set("new_key", "new_value")
        value = config.get("new_key")
        assert value == "new_value"

    def test_set_updates_existing_key(self, config):
        """Test that set() updates an existing key."""
        original = config.get("burst_timeout_ms")
        config.set("burst_timeout_ms", 2000)
        updated = config.get("burst_timeout_ms")
        assert updated == 2000
        assert updated != original

    def test_set_converts_int_to_string(self, config):
        """Test that set() converts int to string."""
        config.set("test_int", 12345)
        with config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'test_int'")
            result = cursor.fetchone()
            assert result[0] == "12345"

    def test_set_converts_bool_to_string(self, config):
        """Test that set() converts bool to string."""
        config.set("test_bool", True)
        with config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'test_bool'")
            result = cursor.fetchone()
            assert result[0] == "True"

    def test_set_converts_float_to_string(self, config):
        """Test that set() converts float to string."""
        config.set("test_float", 3.14159)
        with config._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'test_float'")
            result = cursor.fetchone()
            assert result[0] == "3.14159"

    def test_set_preserves_string_value(self, config):
        """Test that set() preserves string values."""
        config.set("test_string", "hello world")
        value = config.get("test_string")
        assert value == "hello world"


class TestConfigGetAll:
    """Tests for Config.get_all method."""

    def test_get_all_returns_dict(self, config):
        """Test that get_all() returns a dictionary."""
        all_settings = config.get_all()
        assert isinstance(all_settings, dict)

    def test_get_all_contains_all_defaults(self, config):
        """Test that get_all() contains all default keys."""
        all_settings = config.get_all()
        for key in AppSettings.model_fields:
            assert key in all_settings

    def test_get_all_includes_custom_values(self, config):
        """Test that get_all() includes custom set values."""
        config.set("custom_key", "custom_value")
        all_settings = config.get_all()
        assert "custom_key" in all_settings
        assert all_settings["custom_key"] == "custom_value"

    def test_get_all_reflects_updated_values(self, config):
        """Test that get_all() reflects updated values."""
        config.set("burst_timeout_ms", 5000)
        all_settings = config.get_all()
        assert all_settings["burst_timeout_ms"] == 5000

    def test_get_all_values_are_parsed(self, config):
        """Test that get_all() returns parsed values, not strings."""
        all_settings = config.get_all()
        # Check that numeric values are parsed
        assert isinstance(all_settings["burst_timeout_ms"], int)
        assert isinstance(all_settings["notification_threshold_days"], int)
        # Check that boolean values are parsed
        assert isinstance(all_settings["worst_letter_notifications_enabled"], bool)


class TestConfigValueParsing:
    """Tests for Config._parse_value method."""

    def test_parse_value_integer(self, config):
        """Test that '123' parses to int 123."""
        config.set("test_int_str", "123")
        value = config.get("test_int_str")
        assert isinstance(value, int)
        assert value == 123

    def test_parse_value_negative_integer(self, config):
        """Test that negative integers are parsed."""
        config.set("test_neg_int", "-1")
        value = config.get("test_neg_int")
        assert value == -1

    def test_parse_value_zero(self, config):
        """Test that '0' parses to int 0."""
        config.set("test_zero", "0")
        value = config.get("test_zero")
        assert value == 0

    def test_parse_value_float(self, config):
        """Test that '123.45' parses to float 123.45."""
        config.set("test_float_str", "123.45")
        value = config.get("test_float_str")
        assert isinstance(value, float)
        assert value == 123.45

    def test_parse_value_float_zero(self, config):
        """Test that '0.0' parses to float 0.0."""
        config.set("test_float_zero", "0.0")
        value = config.get("test_float_zero")
        assert value == 0.0

    def test_parse_value_true_boolean(self, config):
        """Test that 'True' parses to boolean True."""
        config.set("test_true", "True")
        value = config.get("test_true")
        assert value is True

    def test_parse_value_false_boolean(self, config):
        """Test that 'False' parses to boolean False."""
        config.set("test_false", "False")
        value = config.get("test_false")
        assert value is False

    def test_parse_value_string_stays_string(self, config):
        """Test that non-numeric strings stay as strings."""
        config.set("test_string", "hello")
        value = config.get("test_string")
        assert isinstance(value, str)
        assert value == "hello"

    def test_parse_value_empty_string(self, config):
        """Test that empty string stays as empty string."""
        config.set("test_empty", "")
        value = config.get("test_empty")
        assert value == ""

    def test_parse_value_one_as_bool(self, config):
        """Test that '1' parses to integer 1, and get_bool converts to True."""
        config.set("test_one", "1")
        value = config.get("test_one")
        # _parse_value() tries int before bool, so '1' becomes int 1
        assert value == 1
        assert isinstance(value, int)
        # get_bool() now properly handles int 1 as True
        assert config.get_bool("test_one") is True

    def test_parse_value_zero_as_bool(self, config):
        """Test that '0' parses to integer 0, and get_bool converts to False."""
        config.set("test_zero_str", "0")
        value = config.get("test_zero_str")
        # _parse_value() tries int before bool, so '0' becomes int 0
        assert value == 0
        assert isinstance(value, int)
        # get_bool() now properly handles int 0 as False
        assert config.get_bool("test_zero_str") is False

    def test_parse_value_yes_no(self, config):
        """Test that 'yes'/'no' parse to booleans."""
        config.set("test_yes", "yes")
        config.set("test_no", "no")
        assert config.get("test_yes") is True
        assert config.get("test_no") is False

    def test_parse_value_on_off(self, config):
        """Test that 'on'/'off' parse to booleans."""
        config.set("test_on", "on")
        config.set("test_off", "off")
        assert config.get("test_on") is True
        assert config.get("test_off") is False


class TestConfigValidation:
    """Tests for pydantic validation in Config."""

    def test_set_rejects_invalid_positive_int(self, config):
        """Test that set() rejects invalid positive integers."""
        with pytest.raises(ValueError, match="Invalid value for burst_timeout_ms"):
            config.set("burst_timeout_ms", -1)

    def test_set_rejects_invalid_retention_days(self, config):
        """Test that set() rejects invalid retention days (< -1)."""
        with pytest.raises(ValueError, match="Invalid value for data_retention_days"):
            config.set("data_retention_days", -2)

    def test_set_accepts_magic_minus_one_for_retention(self, config):
        """Test that -1 is accepted for data_retention_days (keep forever)."""
        config.set("data_retention_days", -1)
        value = config.get_int("data_retention_days")
        assert value == -1

    def test_set_rejects_invalid_hour(self, config):
        """Test that set() rejects invalid hour values."""
        with pytest.raises(
            ValueError, match="Invalid value for notification_time_hour"
        ):
            config.set("notification_time_hour", 24)

    def test_cross_field_validation_active_threshold_too_high(self, config):
        """Test that active_time_threshold_ms < burst_timeout_ms is enforced."""
        # First set burst_timeout_ms
        config.set("burst_timeout_ms", 1000)
        # Then try to set active_time_threshold_ms >= burst_timeout_ms
        with pytest.raises(ValueError, match="must be less than"):
            config.set("active_time_threshold_ms", 1000)

    def test_cross_field_validation_active_threshold_ok(self, config):
        """Test that valid active_time_threshold_ms is accepted."""
        config.set("burst_timeout_ms", 1000)
        config.set("active_time_threshold_ms", 500)
        assert config.get_int("active_time_threshold_ms") == 500


class TestDefaultSettings:
    """Tests for AppSettings model."""

    def test_app_settings_is_model(self):
        """Test that AppSettings is a pydantic BaseModel."""
        from pydantic import BaseModel

        assert isinstance(AppSettings(), BaseModel)

    def test_app_settings_has_expected_defaults(self):
        """Test that AppSettings has expected default values."""
        settings = AppSettings()
        # Check that key fields have expected default values
        assert settings.burst_timeout_ms > 0
        assert isinstance(settings.keyboard_layout, str)

    def test_app_settings_expected_keys_present(self):
        """Test that expected keys are accessible on AppSettings."""
        expected_keys = [
            "burst_timeout_ms",
            "keyboard_layout",
        ]
        settings = AppSettings()
        for key in expected_keys:
            # Test that the attribute is accessible (hasattr on public interface)
            assert hasattr(settings, key)

    def test_app_settings_has_proper_types(self):
        """Test that AppSettings fields have proper types."""
        # Check that fields exist and have proper types
        settings = AppSettings()
        assert isinstance(settings.burst_timeout_ms, int)
        assert isinstance(settings.keyboard_layout, str)
