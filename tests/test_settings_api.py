from __future__ import annotations

import os
import sys
import tempfile
import shutil
import types
import unittest
from typing import Optional


class _MemoryKeyring:
    def __init__(self):
        self._store = {}

    def get_password(self, service_name: str, username: str) -> Optional[str]:
        return self._store.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self._store[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self._store.pop((service_name, username), None)


class _FakeOpenAIModels:
    def list(self):
        # Simulate OK connectivity
        return []


class _FakeOpenAIClient:
    def __init__(self, api_key=None, base_url=None):
        self._api_key = api_key
        self._base_url = base_url
        self.models = _FakeOpenAIModels()

    class _ChoicesMsg:
        def __init__(self, content: str):
            self.message = types.SimpleNamespace(content=content)

    class _Resp:
        def __init__(self, content: str):
            self.choices = [_FakeOpenAIClient._ChoicesMsg(content)]

    class _Chat:
        def __init__(self, outer: "_FakeOpenAIClient"):
            self._outer = outer
            self.completions = types.SimpleNamespace(create=self._create)

        def _create(self, model=None, messages=None, temperature=None, response_format=None):
            return _FakeOpenAIClient._Resp('{"ok": true}')

    @property
    def chat(self):
        return _FakeOpenAIClient._Chat(self)


class SettingsApiIntegrationTest(unittest.TestCase):
    def setUp(self):
        # Electron mode and isolated app path
        self._tmpdir = tempfile.mkdtemp(prefix="tc_settings_")
        self._prev_app_path = os.environ.get("ELECTRON_APP_PATH")
        os.environ["ELECTRON_APP_PATH"] = self._tmpdir
        self._prev_electron = os.environ.get("ELECTRON_RUN_AS_NODE")
        os.environ["ELECTRON_RUN_AS_NODE"] = "1"
        # Avoid picking up project .env by changing CWD for duration of import
        self._prev_cwd = os.getcwd()
        os.chdir(self._tmpdir)

        # Ensure env var migration does not auto-set key
        self._prev_env_key = os.environ.get('DEEPSEEK_API_KEY')
        if 'DEEPSEEK_API_KEY' in os.environ:
            del os.environ['DEEPSEEK_API_KEY']

        # Stub dotenv.load_dotenv to prevent loading project .env
        self._prev_dotenv = sys.modules.get('dotenv')
        sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda *a, **k: False, __spec__=types.SimpleNamespace())

        # Install fake 'openai' to avoid network/deps
        self._prev_openai = sys.modules.get('openai')
        sys.modules['openai'] = types.SimpleNamespace(OpenAI=_FakeOpenAIClient, __spec__=types.SimpleNamespace())

        # Patch keyring to in-memory before importing the app
        import app.api_keys as api_keys_mod
        self._prev_keyring = getattr(api_keys_mod, 'keyring', None)
        api_keys_mod.keyring = _MemoryKeyring()

        # Import the Flask app (Electron variant)
        from app.__init___electron import app as flask_app  # noqa
        self.app = flask_app
        self.client = self.app.test_client()

        # Ensure DeepSeekClient uses our fake openai even if module imported earlier
        import app.ai.deepseek_client as dsc
        self._prev_module_openai = getattr(dsc, 'openai', None)
        dsc.openai = sys.modules['openai']

    def tearDown(self):
        # Restore deepseek_client.openai
        try:
            import app.ai.deepseek_client as dsc
            dsc.openai = self._prev_module_openai
        except Exception:
            pass

        # Restore stubbed modules
        if self._prev_openai is None:
            sys.modules.pop('openai', None)
        else:
            sys.modules['openai'] = self._prev_openai
        if self._prev_dotenv is None:
            sys.modules.pop('dotenv', None)
        else:
            sys.modules['dotenv'] = self._prev_dotenv

        # Restore env
        if self._prev_env_key is None:
            os.environ.pop('DEEPSEEK_API_KEY', None)
        else:
            os.environ['DEEPSEEK_API_KEY'] = self._prev_env_key
        if self._prev_app_path is None:
            os.environ.pop("ELECTRON_APP_PATH", None)
        else:
            os.environ["ELECTRON_APP_PATH"] = self._prev_app_path
        if self._prev_electron is None:
            os.environ.pop("ELECTRON_RUN_AS_NODE", None)
        else:
            os.environ["ELECTRON_RUN_AS_NODE"] = self._prev_electron
        try:
            shutil.rmtree(self._tmpdir)
        except Exception:
            pass
        # Restore CWD
        try:
            os.chdir(self._prev_cwd)
        except Exception:
            pass

    def test_settings_api_flow(self):
        # Initial status should be unset
        r = self.client.get('/settings/api-key/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn('status', data)
        self.assertEqual(data['status'], 'unset')

        # Set a key
        secret = 'sk-unit-test-123456'
        r = self.client.post('/settings/api-key', json={'api_key': secret})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body.get('status'), 'set')

        # Status reflects set, does not echo secret
        r = self.client.get('/settings/api-key/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data.get('status'), 'set')
        self.assertTrue('lastTest' in data)
        self.assertNotIn(secret, str(data))

        # Test connectivity (uses fake openai -> ok)
        r = self.client.post('/settings/api-key/test')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get('ok'))
        self.assertIsNone(data.get('error'))

        # Delete key
        r = self.client.delete('/settings/api-key')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        # Endpoint returns {status:"removed"}; accept either 'removed' or 'unset'
        self.assertIn(data.get('status'), ('removed', 'unset'))

        # Status back to unset
        r = self.client.get('/settings/api-key/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data.get('status'), 'unset')
        self.assertNotIn(secret, str(data))


if __name__ == '__main__':
    unittest.main()
