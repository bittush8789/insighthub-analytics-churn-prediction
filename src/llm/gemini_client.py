"""Official Google GenAI SDK client initialization and wrapper."""

import logging
from typing import Optional
from google import genai
from google.genai import types

from src.config.settings import get_settings
from src.utils.exceptions import ConfigurationError, GeminiAssistantError

logger = logging.getLogger(__name__)


class GeminiClientManager:
    """Manages the official Google GenAI SDK client lifecycle."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self._client: Optional[genai.Client] = None

    def get_client(self) -> genai.Client:
        """Initialize or return the cached genai.Client instance."""
        if self._client is not None:
            return self._client

        if not self.api_key or self.api_key.strip() in ("", "your_gemini_api_key_here"):
            raise ConfigurationError(
                "GEMINI_API_KEY is not configured. Please supply a valid Google Gemini API key "
                "in your environment variables or .env file."
            )

        try:
            self._client = genai.Client(api_key=self.api_key)
            logger.info("Initialized Google GenAI client with model '%s'", self.model_name)
            return self._client
        except Exception as exc:
            logger.error("Failed to initialize Google GenAI Client: %s", exc)
            raise GeminiAssistantError(f"Client initialization failed: {exc}") from exc
