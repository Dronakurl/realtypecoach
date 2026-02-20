"""Ollama API client for text generation."""

import logging

import ollama
from PySide6.QtCore import QObject, Signal

log = logging.getLogger("realtypecoach")

# Default model to use for text generation
MODEL = "gemma2:2b"


class OllamaClient(QObject):
    """Client for Ollama text generation API."""

    signal_generation_complete = Signal(str)  # Generated text
    signal_generation_failed = Signal(str)  # Error message

    def __init__(
        self, host: str = "localhost", port: int = 11434, model: str = "gemma2:2b"
    ) -> None:
        """Initialize Ollama client.

        Args:
            host: Ollama server host
            port: Ollama server port
            model: Model to use for generation
        """
        super().__init__()
        self.host = host
        self.port = port
        self.model = model  # Store as instance variable
        self.client = ollama.Client(host=f"{host}:{port}")

    def check_server_available(self) -> bool:
        """Check if Ollama server is running.

        Returns:
            True if server is available
        """
        try:
            self.client.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models from Ollama.

        Returns:
            List of model names
        """
        try:
            response = self.client.list()
            models = response.get("models", [])
            return [model.get("model", model.get("name", "")) for model in models]
        except Exception:
            return []

    def generate_text(self, prompt: str, words: list[str]) -> None:
        """Generate text using Ollama.

        Args:
            prompt: Prompt template with word placeholders
            words: List of hardest words to include
        """
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            )

            generated_text = response.get("response", "").strip()

            if not generated_text:
                self.signal_generation_failed.emit("Ollama returned empty text")
                return

            self.signal_generation_complete.emit(generated_text)

        except ollama.ResponseError as e:
            error_msg = str(e.error).lower()

            # Check if error is about model not found
            if "not found" in error_msg or "model" in error_msg:
                log.warning(f"Model '{self.model}' not found, trying fallback")

                # Try to get list of available models and use first one
                try:
                    models = self.list_models()
                    if models:
                        fallback_model = models[0]
                        log.info(f"Retrying with fallback model: {fallback_model}")

                        response = self.client.generate(
                            model=fallback_model,
                            prompt=prompt,
                            stream=False,
                            options={
                                "temperature": 0.7,
                                "top_p": 0.9,
                            },
                        )

                        generated_text = response.get("response", "").strip()

                        if not generated_text:
                            self.signal_generation_failed.emit("Ollama returned empty text")
                            return

                        # Emit a note that we used a fallback model
                        self.signal_generation_complete.emit(
                            f"[Using model: {fallback_model}]\n\n{generated_text}"
                        )
                        return
                except Exception as fallback_error:
                    log.error(f"Fallback model also failed: {fallback_error}")

            # If we get here, either error wasn't about model or fallback failed
            self.signal_generation_failed.emit(f"Ollama error: {e.error}")

        except Exception as e:
            log.error(f"Error generating text: {e}")
            self.signal_generation_failed.emit(str(e))

    def stop_model(self, model: str | None = None) -> None:
        """Stop a running model in Ollama.

        Args:
            model: Model name to stop. If None, stops the current model.
        """
        model_to_stop = model or self.model
        if not model_to_stop:
            return

        try:
            # Try using the ollama Python library's stop method if available
            if hasattr(self.client, "stop"):
                self.client.stop(model_to_stop)
                log.info(f"Stopped model: {model_to_stop}")
        except Exception as e:
            # Method might not exist or stop failed - log but don't crash
            log.debug(f"Could not stop model {model_to_stop}: {e}")

    def generate_text_sync(self, prompt: str, words: list[str]) -> str | None:
        """Generate text using Ollama synchronously.

        Args:
            prompt: Prompt template with word placeholders
            words: List of hardest words to include

        Returns:
            Generated text, or None if generation failed
        """
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            )

            generated_text = response.get("response", "").strip()

            if not generated_text:
                log.error("Ollama returned empty text")
                return None

            return generated_text

        except ollama.ResponseError as e:
            error_msg = str(e.error).lower()

            # Check if error is about model not found
            if "not found" in error_msg or "model" in error_msg:
                log.warning(f"Model '{self.model}' not found, trying fallback")

                # Try to get list of available models and use first one
                try:
                    models = self.list_models()
                    if models:
                        fallback_model = models[0]
                        log.info(f"Retrying with fallback model: {fallback_model}")

                        response = self.client.generate(
                            model=fallback_model,
                            prompt=prompt,
                            stream=False,
                            options={
                                "temperature": 0.7,
                                "top_p": 0.9,
                            },
                        )

                        generated_text = response.get("response", "").strip()

                        if not generated_text:
                            log.error("Ollama returned empty text")
                            return None

                        return generated_text
                except Exception as fallback_error:
                    log.error(f"Fallback model also failed: {fallback_error}")

            # If we get here, either error wasn't about model or fallback failed
            log.error(f"Ollama error: {e.error}")
            return None

        except Exception as e:
            log.error(f"Error generating text: {e}")
            return None
