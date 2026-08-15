import os
import unittest
from unittest import mock

from ai_systems_lab.providers import (
    ProviderConfigError,
    authorization_headers,
    chat_completions_request,
    responses_json_request,
    resolve_model_target,
    validate_provider_config,
)


class ProviderConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "providers": {
                "local-llama": {"type": "llama_cpp"},
                "cloud-openai": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.test/v1/",
                    "api_key_env": "EXAMPLE_AI_API_KEY",
                },
            },
            "models": {
                "fast": {"provider": "local-llama"},
                "cloud-coder": {
                    "provider": "cloud-openai",
                    "provider_model": "vendor/coder-v1",
                },
            },
        }

    def test_validate_rejects_model_with_unknown_provider(self):
        self.config["models"]["fast"]["provider"] = "missing"
        with self.assertRaisesRegex(ProviderConfigError, "unknown provider 'missing'"):
            validate_provider_config(self.config)

    def test_resolve_local_target_uses_gateway_and_alias(self):
        target = resolve_model_target(self.config, "fast", "http://127.0.0.1:8080/v1")
        self.assertEqual(target.provider_type, "llama_cpp")
        self.assertEqual(target.base_url, "http://127.0.0.1:8080/v1")
        self.assertEqual(target.model_id, "fast")
        self.assertTrue(target.is_local)

    def test_resolve_cloud_target_uses_provider_model_and_trimmed_url(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        self.assertEqual(target.provider_type, "openai_compatible")
        self.assertEqual(target.base_url, "https://api.example.test/v1")
        self.assertEqual(target.model_id, "vendor/coder-v1")
        self.assertFalse(target.is_local)

    def test_cloud_credentials_are_loaded_from_configured_environment_name(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            self.assertEqual(authorization_headers(target), {"Authorization": "Bearer secret-value"})

    def test_missing_cloud_credentials_fail_without_disclosing_a_value(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ProviderConfigError, "EXAMPLE_AI_API_KEY"):
                authorization_headers(target)

    def test_chat_request_contains_resolved_provider_model(self):
        target = resolve_model_target(self.config, "cloud-coder", "http://127.0.0.1:8080/v1")
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            url, payload, headers = chat_completions_request(
                target,
                [{"role": "user", "content": "hello"}],
                max_tokens=64,
                temperature=0.2,
            )
        self.assertEqual(url, "https://api.example.test/v1/chat/completions")
        self.assertEqual(payload["model"], "vendor/coder-v1")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(headers, {"Authorization": "Bearer secret-value"})

    def test_responses_request_uses_provider_capability_and_credentials(self):
        self.config["providers"]["cloud-openai"]["responses_api"] = True
        target = resolve_model_target(
            self.config, "cloud-coder", "http://127.0.0.1:8080/v1"
        )
        schema = {
            "type": "object",
            "properties": {"pass": {"type": "boolean"}},
            "required": ["pass"],
            "additionalProperties": False,
        }
        with mock.patch.dict(os.environ, {"EXAMPLE_AI_API_KEY": "secret-value"}, clear=False):
            url, payload, headers = responses_json_request(
                target,
                "Score the response.",
                "evaluation input",
                schema,
                "low",
            )
        self.assertEqual(url, "https://api.example.test/v1/responses")
        self.assertEqual(payload["model"], "vendor/coder-v1")
        self.assertEqual(payload["text"]["format"]["schema"], schema)
        self.assertEqual(headers, {"Authorization": "Bearer secret-value"})

    def test_responses_request_rejects_unsupported_provider_before_credentials(self):
        target = resolve_model_target(
            self.config, "cloud-coder", "http://127.0.0.1:8080/v1"
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                ProviderConfigError, "does not support the Responses API judge"
            ):
                responses_json_request(target, "Score.", "input", {}, "low")


if __name__ == "__main__":
    unittest.main()
