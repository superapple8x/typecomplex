from __future__ import annotations

from typing import Optional, Protocol, Dict

from app.api_keys import ApiKeyStore


class KeyProvider(Protocol):
    def get_key(self) -> Optional[str]:
        ...

    def has_key(self) -> bool:
        ...

    def mask_status(self) -> Dict[str, str]:
        ...


class ApiKeyStoreKeyProvider:
    """KeyProvider backed by existing ApiKeyStore (OS keychain + fallback)."""

    def __init__(self, store: Optional[ApiKeyStore] = None) -> None:
        self._store = store or ApiKeyStore()

    def get_key(self) -> Optional[str]:
        return self._store.get_key()

    def has_key(self) -> bool:
        return self._store.is_set()

    def mask_status(self) -> Dict[str, str]:
        return {"status": "set" if self.has_key() else "unset"}
