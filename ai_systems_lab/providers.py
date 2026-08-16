import os
from dataclasses import dataclass
from typing import Optional


SUPPORTED_PROVIDER_TYPES = {"llama_cpp", "openai_compatible"}


class ProviderConfigError(Exception):
    pass


def _is_non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class ModelTarget:
    alias: str
    provider: str
    provider_type: str
    model_id: str
    base_url: str
    api_key_env: Optional[str]
    responses_api: bool

    @property
    def is_local(self):
        return self.provider_type == "llama_cpp"


def validate_provider_config(cfg):
    if not isinstance(cfg, dict):
        raise ProviderConfigError("configuration must be an object")
    providers = cfg.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ProviderConfigError("providers must be a non-empty object")
    for name, provider in providers.items():
        if not _is_non_empty_string(name):
            raise ProviderConfigError("provider names must be non-empty strings")
        if not isinstance(provider, dict):
            raise ProviderConfigError(f"provider '{name}' must be an object")
        provider_type = provider.get("type")
        if not _is_non_empty_string(provider_type):
            raise ProviderConfigError(
                f"provider '{name}' type must be a non-empty string"
            )
        if provider_type not in SUPPORTED_PROVIDER_TYPES:
            raise ProviderConfigError(
                f"provider '{name}' has unsupported type {provider_type!r}"
            )
        if provider_type == "openai_compatible":
            if not _is_non_empty_string(provider.get("base_url")):
                raise ProviderConfigError(
                    f"provider '{name}' base_url must be a non-empty string"
                )
            if not _is_non_empty_string(provider.get("api_key_env")):
                raise ProviderConfigError(
                    f"provider '{name}' api_key_env must be a non-empty string"
                )
        if "responses_api" in provider and not isinstance(
            provider["responses_api"], bool
        ):
            raise ProviderConfigError(
                f"provider '{name}' responses_api must be a boolean"
            )
    models = cfg.get("models", {})
    if not isinstance(models, dict):
        raise ProviderConfigError("models must be an object")
    for alias, model in models.items():
        if not _is_non_empty_string(alias):
            raise ProviderConfigError("model aliases must be non-empty strings")
        if not isinstance(model, dict):
            raise ProviderConfigError(f"model '{alias}' must be an object")
        provider_name = model.get("provider")
        if not _is_non_empty_string(provider_name):
            raise ProviderConfigError(
                f"model '{alias}' provider must be a non-empty string"
            )
        if provider_name not in providers:
            raise ProviderConfigError(
                f"model '{alias}' references unknown provider '{provider_name}'"
            )
        if "provider_model" in model and (
            not _is_non_empty_string(model["provider_model"])
        ):
            raise ProviderConfigError(
                f"model '{alias}' provider_model must be a non-empty string"
            )


def resolve_model_target(cfg, alias, local_base_url):
    validate_provider_config(cfg)
    try:
        model = cfg["models"][alias]
    except KeyError as exc:
        raise ProviderConfigError(f"unknown model alias '{alias}'") from exc
    provider_name = model["provider"]
    provider = cfg["providers"][provider_name]
    provider_type = provider["type"]
    base_url = local_base_url if provider_type == "llama_cpp" else provider["base_url"]
    return ModelTarget(
        alias=alias,
        provider=provider_name,
        provider_type=provider_type,
        model_id=model.get("provider_model", alias),
        base_url=base_url.rstrip("/"),
        api_key_env=provider.get("api_key_env"),
        responses_api=provider.get("responses_api") is True,
    )


def authorization_headers(target, environ=None):
    if not target.api_key_env:
        return {}
    environment = os.environ if environ is None else environ
    api_key = environment.get(target.api_key_env)
    if not api_key:
        raise ProviderConfigError(
            f"{target.api_key_env} is required for provider '{target.provider}'"
        )
    return {"Authorization": f"Bearer {api_key}"}


def chat_completions_request(target, messages, max_tokens, temperature):
    payload = {
        "model": target.model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    return (
        f"{target.base_url}/chat/completions",
        payload,
        authorization_headers(target),
    )


def responses_json_request(
    target,
    instructions,
    input_value,
    schema,
    reasoning_effort,
):
    if not target.responses_api:
        raise ProviderConfigError(
            f"provider '{target.provider}' does not support the Responses API judge"
        )
    payload = {
        "model": target.model_id,
        "instructions": instructions,
        "input": input_value,
        "store": False,
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "quality_score",
                "strict": True,
                "schema": schema,
            },
        },
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return (
        f"{target.base_url}/responses",
        payload,
        authorization_headers(target),
    )
