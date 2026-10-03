import os
import unittest
from unittest.mock import patch

from translator.config import ANTHROPIC_BASE_URL, ANTHROPIC_DEFAULT_MODEL, resolve_provider_settings


class ProviderSettingsTests(unittest.TestCase):
    def test_auto_provider_prefers_epub_tsuyaku_environment(self):
        with patch.dict(
            os.environ,
            {
                "EPUB_TSUYAKU_API_KEY": "new-key",
                "EPUB_TSUYAKU_BASE_URL": "https://example.com/v1",
                "EPUB_TSUYAKU_MODEL": "new-model",
                "EPUB_TRANSLATOR_API_KEY": "legacy-key",
                "EPUB_TRANSLATOR_BASE_URL": "https://legacy.example.com/v1",
                "EPUB_TRANSLATOR_MODEL": "legacy-model",
            },
            clear=True,
        ):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="auto",
                api_key_env=None,
                explicit_base_url=None,
                explicit_model=None,
            )

        self.assertEqual(provider, "openai-compatible")
        self.assertEqual(api_key, "new-key")
        self.assertEqual(base_url, "https://example.com/v1")
        self.assertEqual(model, "new-model")

    def test_auto_provider_keeps_legacy_epub_translator_environment(self):
        with patch.dict(
            os.environ,
            {
                "EPUB_TRANSLATOR_API_KEY": "legacy-key",
                "EPUB_TRANSLATOR_BASE_URL": "https://legacy.example.com/v1",
                "EPUB_TRANSLATOR_MODEL": "legacy-model",
            },
            clear=True,
        ):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="auto",
                api_key_env=None,
                explicit_base_url=None,
                explicit_model=None,
            )

        self.assertEqual(provider, "openai-compatible")
        self.assertEqual(api_key, "legacy-key")
        self.assertEqual(base_url, "https://legacy.example.com/v1")
        self.assertEqual(model, "legacy-model")

class AnthropicProviderSettingsTests(unittest.TestCase):
    def test_anthropic_provider_uses_dedicated_env(self):
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-ant",
                "ANTHROPIC_MODEL": "claude-custom",
                "ANTHROPIC_BASE_URL": "https://gateway.example.com",
            },
            clear=True,
        ):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="anthropic",
                api_key_env=None,
                explicit_base_url=None,
                explicit_model=None,
            )

        self.assertEqual(provider, "anthropic")
        self.assertEqual(api_key, "sk-ant")
        self.assertEqual(base_url, "https://gateway.example.com")
        self.assertEqual(model, "claude-custom")

    def test_anthropic_provider_falls_back_to_official_defaults(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant"}, clear=True):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="anthropic",
                api_key_env=None,
                explicit_base_url=None,
                explicit_model=None,
            )

        self.assertEqual(provider, "anthropic")
        self.assertEqual(api_key, "sk-ant")
        self.assertEqual(base_url, ANTHROPIC_BASE_URL)
        self.assertEqual(model, ANTHROPIC_DEFAULT_MODEL)

    def test_anthropic_provider_honors_explicit_overrides(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant"}, clear=True):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="anthropic",
                api_key_env=None,
                explicit_base_url="https://relay.example.com/v1",
                explicit_model="claude-x",
            )

        self.assertEqual(base_url, "https://relay.example.com/v1")
        self.assertEqual(model, "claude-x")

    def test_anthropic_provider_without_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
                resolve_provider_settings(
                    provider="anthropic",
                    api_key_env=None,
                    explicit_base_url=None,
                    explicit_model=None,
                )

    def test_auto_provider_detects_anthropic_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant"}, clear=True):
            provider, api_key, base_url, model = resolve_provider_settings(
                provider="auto",
                api_key_env=None,
                explicit_base_url=None,
                explicit_model=None,
            )

        self.assertEqual(provider, "anthropic")
        self.assertEqual(api_key, "sk-ant")
        self.assertEqual(model, ANTHROPIC_DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()
