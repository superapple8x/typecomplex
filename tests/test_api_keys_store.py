from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional

import unittest

from app.api_keys import ApiKeyStore as _ApiKeyStore
import app.api_keys as api_keys_mod


class _FailingKeyring:
    def get_password(self, service_name: str, username: str) -> Optional[str]:
        raise RuntimeError("keyring unavailable")

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise RuntimeError("keyring unavailable")

    def delete_password(self, service_name: str, username: str) -> None:
        raise RuntimeError("keyring unavailable")


class _MemoryKeyring:
    def __init__(self):
        self._store = {}

    def get_password(self, service_name: str, username: str) -> Optional[str]:
        return self._store.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self._store[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self._store.pop((service_name, username), None)


class ApiKeyStoreFallbackTest(unittest.TestCase):
    def setUp(self):
        # Isolate to a temp app path so tests do not touch real home
        self._tmpdir = tempfile.mkdtemp(prefix="tc_keys_")
        self._prev_app_path = os.environ.get("ELECTRON_APP_PATH")
        os.environ["ELECTRON_APP_PATH"] = self._tmpdir
        # Monkeypatch keyring to a failing implementation to force fallback
        self._prev_keyring = getattr(api_keys_mod, "keyring", None)
        api_keys_mod.keyring = _FailingKeyring()

    def tearDown(self):
        # Restore keyring and env
        api_keys_mod.keyring = self._prev_keyring
        if self._prev_app_path is None:
            os.environ.pop("ELECTRON_APP_PATH", None)
        else:
            os.environ["ELECTRON_APP_PATH"] = self._prev_app_path
        try:
            shutil.rmtree(self._tmpdir)
        except Exception:
            pass

    def test_fallback_store_load_delete(self):
        store = _ApiKeyStore(service_name="unittest.deepseek")
        self.assertFalse(store.is_set())

        secret = "sk-test-1234567890"
        store.set_key(secret)
        self.assertTrue(store.is_set())
        self.assertEqual(store.get_key(), secret)

        # Files should exist in fallback dir
        blob_path = os.path.join(self._tmpdir, "secrets", "deepseek.blob")
        key_path = os.path.join(self._tmpdir, "secrets", "deepseek.key")
        self.assertTrue(os.path.exists(blob_path))
        # key file may or may not exist depending on cryptography availability; tolerate both

        # Delete and confirm removal
        store.delete_key()
        self.assertFalse(store.is_set())


class ApiKeyStoreKeyringTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="tc_keys_")
        self._prev_app_path = os.environ.get("ELECTRON_APP_PATH")
        os.environ["ELECTRON_APP_PATH"] = self._tmpdir
        # Monkeypatch keyring to an in-memory implementation
        self._prev_keyring = getattr(api_keys_mod, "keyring", None)
        api_keys_mod.keyring = _MemoryKeyring()

    def tearDown(self):
        api_keys_mod.keyring = self._prev_keyring
        if self._prev_app_path is None:
            os.environ.pop("ELECTRON_APP_PATH", None)
        else:
            os.environ["ELECTRON_APP_PATH"] = self._prev_app_path
        try:
            shutil.rmtree(self._tmpdir)
        except Exception:
            pass

    def test_keyring_path(self):
        store = _ApiKeyStore(service_name="unittest.deepseek")
        secret = "sk-live-abcdef-0123456789"
        store.set_key(secret)
        self.assertTrue(store.is_set())
        self.assertEqual(store.get_key(), secret)
        # No blob file should have been created in keyring success path
        blob_path = os.path.join(self._tmpdir, "secrets", "deepseek.blob")
        self.assertFalse(os.path.exists(blob_path))
        store.delete_key()
        self.assertFalse(store.is_set())


if __name__ == "__main__":
    unittest.main()
