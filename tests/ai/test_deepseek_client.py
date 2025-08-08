from __future__ import annotations

import types
import sys
import unittest
from typing import Optional, Dict

from app.ai.deepseek_client import DeepSeekClient


class NullKeyProvider:
    def get_key(self) -> Optional[str]:
        return None

    def has_key(self) -> bool:
        return False

    def mask_status(self):
        return {"status": "unset"}


class FixedKeyProvider:
    def __init__(self, key: str) -> None:
        self._key = key

    def get_key(self) -> Optional[str]:
        return self._key

    def has_key(self) -> bool:
        return True

    def mask_status(self):
        return {"status": "set"}


class _FakeOpenAIModels:
    def list(self):
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
            # Just echo a simple JSON string for tests
            return _FakeOpenAIClient._Resp('{"ok": true}')

    @property
    def chat(self):
        return _FakeOpenAIClient._Chat(self)


class DeepSeekClientTest(unittest.TestCase):
    def setUp(self):
        # Install a fake minimal 'openai' to avoid real dependency
        fake_mod = types.SimpleNamespace(OpenAI=_FakeOpenAIClient)
        fake_mod.__spec__ = types.SimpleNamespace()
        self._prev_openai = sys.modules.get('openai')
        sys.modules['openai'] = fake_mod

    def tearDown(self):
        if self._prev_openai is None:
            sys.modules.pop('openai', None)
        else:
            sys.modules['openai'] = self._prev_openai

    def test_test_key_missing(self):
        client = DeepSeekClient(key_provider=NullKeyProvider())
        res = client.test_key()
        self.assertFalse(res["ok"]) 
        self.assertEqual(res["error"], "api_key_missing")

    def test_test_key_ok(self):
        client = DeepSeekClient(key_provider=FixedKeyProvider("sk-test"))
        res = client.test_key()
        self.assertTrue(res["ok"]) 
        self.assertIsNone(res["error"]) 

    def test_chat_json_parses(self):
        client = DeepSeekClient(key_provider=FixedKeyProvider("sk-test"))
        out = client.chat_json(system_prompt="sys", user_content="user")
        self.assertEqual(out, {"ok": True})


if __name__ == '__main__':
    unittest.main()
