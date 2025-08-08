"""AI support package: DeepSeek client, errors, and key provider."""

from .deepseek_client import DeepSeekClient  # noqa: F401
from .errors import DeepSeekError, normalize_exception  # noqa: F401
from .key_provider import KeyProvider, ApiKeyStoreKeyProvider  # noqa: F401
