"""
Secure API key storage utilities for backend-only use.
- Primary: OS keychain via `keyring`
- Fallback: Encrypted file at a per-user application data directory

Notes:
- The fallback is best-effort and intended to avoid accidental plaintext exposure.
- The encryption key is stored next to the encrypted blob with 0600 permissions.
- Secrets are never logged.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import stat
from typing import Optional

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None  # type: ignore

try:
    from cryptography.fernet import Fernet  # type: ignore
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore

logger = logging.getLogger(__name__)


def _get_app_data_dir() -> str:
    # Prefer Electron app path if provided by the launcher
    electron_app_path = os.environ.get("ELECTRON_APP_PATH")
    if electron_app_path:
        return electron_app_path
    # Otherwise use ~/.typecomplex
    home = pathlib.Path.home()
    base = home / ".typecomplex"
    base.mkdir(mode=0o700, exist_ok=True)
    return str(base)


class ApiKeyStore:
    """Simple API key storage with keyring primary and encrypted-file fallback."""

    def __init__(self, service_name: str = "typecomplex.deepseek") -> None:
        self.service_name = service_name
        self._fallback_dir = os.path.join(_get_app_data_dir(), "secrets")
        os.makedirs(self._fallback_dir, exist_ok=True)
        # Ensure directory permissions are strict
        try:
            os.chmod(self._fallback_dir, 0o700)
        except Exception:
            pass
        self._key_file = os.path.join(self._fallback_dir, "deepseek.key")
        self._blob_file = os.path.join(self._fallback_dir, "deepseek.blob")

    def is_set(self) -> bool:
        # Prefer keyring
        if keyring is not None:
            try:
                value = keyring.get_password(self.service_name, "api_key")
                if value:
                    return True
            except Exception:
                pass
        # Fallback file exists?
        return os.path.exists(self._blob_file)

    def set_key(self, key: str) -> None:
        if not key or not isinstance(key, str):
            raise ValueError("Invalid API key")
        # Attempt keyring first
        if keyring is not None:
            try:
                keyring.set_password(self.service_name, "api_key", key)
                return
            except Exception as e:
                logger.warning("Keyring set_password failed; using fallback storage: %s", type(e).__name__)
        # Fallback to encrypted file
        self._fallback_store(key)

    def get_key(self) -> Optional[str]:
        # Try keyring
        if keyring is not None:
            try:
                value = keyring.get_password(self.service_name, "api_key")
                if value:
                    return value
            except Exception:
                pass
        # Fallback
        return self._fallback_load()

    def delete_key(self) -> None:
        # Try keyring
        deleted_any = False
        if keyring is not None:
            try:
                # keyring throws if not found, ignore
                keyring.delete_password(self.service_name, "api_key")
                deleted_any = True
            except Exception:
                pass
        # Fallback files
        for p in (self._key_file, self._blob_file):
            try:
                if os.path.exists(p):
                    os.remove(p)
                    deleted_any = True
            except Exception:
                pass
        if not deleted_any:
            logger.info("No stored DeepSeek key material to delete")

    # --- Fallback helpers ---

    def _fallback_store(self, secret: str) -> None:
        if Fernet is None:
            # As last resort, still store as plain but protect permissions strongly
            with open(self._blob_file, "w", encoding="utf-8") as f:
                f.write(secret)
            self._secure_path(self._blob_file)
            return
        key = self._load_or_create_fernet_key()
        fernet = Fernet(key)
        token = fernet.encrypt(secret.encode("utf-8"))
        with open(self._blob_file, "wb") as f:
            f.write(token)
        self._secure_path(self._blob_file)

    def _fallback_load(self) -> Optional[str]:
        if not os.path.exists(self._blob_file):
            return None
        if Fernet is None:
            try:
                with open(self._blob_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None
        key = self._load_or_create_fernet_key()
        try:
            with open(self._blob_file, "rb") as f:
                token = f.read()
            fernet = Fernet(key)
            return fernet.decrypt(token).decode("utf-8")
        except Exception:
            return None

    def _load_or_create_fernet_key(self) -> bytes:
        if os.path.exists(self._key_file):
            try:
                with open(self._key_file, "rb") as f:
                    key = f.read().strip()
                return key
            except Exception:
                pass
        key = Fernet.generate_key() if Fernet else b""
        with open(self._key_file, "wb") as f:
            f.write(key)
        self._secure_path(self._key_file)
        return key

    def _secure_path(self, path: str) -> None:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
