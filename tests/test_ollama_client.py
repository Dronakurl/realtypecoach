"""Tests for Ollama client."""

import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, ".")
from core.ollama_client import OllamaClient


class TestOllamaClient:
    """Test suite for OllamaClient."""

    def test_initialization(self):
        """Test client initialization with default parameters."""
        client = OllamaClient()
        assert client.host == "localhost"
        assert client.port == 11434
        assert client.client is not None  # ollama.Client instance created

    def test_initialization_custom_host_port(self):
        """Test client initialization with custom host and port."""
        client = OllamaClient(host="example.com", port=8080)
        assert client.host == "example.com"
        assert client.port == 8080

    @patch("core.ollama_client.ollama.Client")
    def test_check_server_available_success(self, mock_ollama_client_class):
        """Test successful server availability check."""
        mock_client = Mock()
        mock_client.list.return_value = {"models": []}
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()
        result = client.check_server_available()

        assert result is True
        mock_client.list.assert_called_once()

    @patch("core.ollama_client.ollama.Client")
    def test_check_server_available_failure(self, mock_ollama_client_class):
        """Test server availability check when server is down."""
        mock_client = Mock()
        mock_client.list.side_effect = Exception("Connection refused")
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()
        result = client.check_server_available()

        assert result is False

    @patch("core.ollama_client.ollama.Client")
    def test_generate_text_success(self, mock_ollama_client_class):
        """Test successful text generation."""
        mock_client = Mock()
        mock_client.generate.return_value = {
            "response": "This is a generated text about typing practice."
        }
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()

        # Track signals
        success_signals = []
        failure_signals = []

        client.signal_generation_complete.connect(success_signals.append)
        client.signal_generation_failed.connect(failure_signals.append)

        client.generate_text("Write about typing", ["word1", "word2"])

        # Check that generate was called with correct parameters
        mock_client.generate.assert_called_once()
        call_args = mock_client.generate.call_args

        assert call_args[1]["model"] == "gemma2:2b"
        assert call_args[1]["stream"] is False
        assert "temperature" in call_args[1]["options"]

        # Check success signal was emitted
        assert len(success_signals) == 1
        assert success_signals[0] == "This is a generated text about typing practice."
        assert len(failure_signals) == 0

    @patch("core.ollama_client.ollama.Client")
    def test_generate_text_empty_response(self, mock_ollama_client_class):
        """Test text generation when response is empty."""
        mock_client = Mock()
        mock_client.generate.return_value = {"response": ""}
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()

        success_signals = []
        failure_signals = []

        client.signal_generation_complete.connect(success_signals.append)
        client.signal_generation_failed.connect(failure_signals.append)

        client.generate_text("Write about typing", ["word1"])

        assert len(success_signals) == 0
        assert len(failure_signals) == 1
        assert "empty text" in failure_signals[0]

    @patch("core.ollama_client.ollama.Client")
    def test_generate_text_response_error(self, mock_ollama_client_class):
        """Test text generation when Ollama returns an error."""
        from ollama import ResponseError

        mock_client = Mock()
        mock_client.generate.side_effect = ResponseError("Model not found")
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()

        success_signals = []
        failure_signals = []

        client.signal_generation_complete.connect(success_signals.append)
        client.signal_generation_failed.connect(failure_signals.append)

        client.generate_text("Write about typing", ["word1"])

        assert len(success_signals) == 0
        assert len(failure_signals) == 1
        assert "Model not found" in failure_signals[0]

    @patch("core.ollama_client.ollama.Client")
    def test_generate_text_connection_error(self, mock_ollama_client_class):
        """Test text generation when connection fails."""
        mock_client = Mock()
        mock_client.generate.side_effect = Exception("Connection refused")
        mock_ollama_client_class.return_value = mock_client

        client = OllamaClient()

        success_signals = []
        failure_signals = []

        client.signal_generation_complete.connect(success_signals.append)
        client.signal_generation_failed.connect(failure_signals.append)

        client.generate_text("Write about typing", ["word1"])

        assert len(success_signals) == 0
        assert len(failure_signals) == 1

    def test_model_constant(self):
        """Test that model constant is set correctly."""
        from core.ollama_client import MODEL

        assert MODEL == "gemma2:2b"


class TestOllamaIntegration:
    """Integration tests for Ollama functionality."""

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="Requires Python 3.12+")
    def test_ollama_import(self):
        """Test that ollama package can be imported."""
        try:
            import ollama

            assert hasattr(ollama, "Client")
            assert hasattr(ollama, "generate")
        except ImportError:
            pytest.skip("ollama package not installed")

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="Requires Python 3.12+")
    @pytest.mark.slow
    def test_ollama_server_connection(self):
        """Test actual connection to Ollama server (if available)."""
        try:
            import ollama

            client = ollama.Client()
            models = client.list()

            assert isinstance(models, dict)
            assert "models" in models
        except Exception as e:
            pytest.skip(f"Ollama server not available: {e}")

    @pytest.mark.skipif(sys.version_info < (3, 12), reason="Requires Python 3.12+")
    @pytest.mark.slow
    def test_ollama_text_generation(self):
        """Test actual text generation (if Ollama available)."""
        try:
            import ollama

            client = ollama.Client()
            response = client.generate(
                model="gemma2:2b",
                prompt="Say hello",
                stream=False,
            )

            assert "response" in response
            assert isinstance(response["response"], str)
            assert len(response["response"]) > 0
        except Exception as e:
            pytest.skip(f"Ollama generation failed: {e}")
