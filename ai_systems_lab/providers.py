import os
from dataclasses import dataclass
from typing import Optional


SUPPORTED_PROVIDER_TYPES = {"llama_cpp", "openai_compatible"}


class ProviderConfigError(Exception):
    pass


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
    providers = cfg.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ProviderConfigError("providers must be a non-empty object")
    for name, provider in providers.items():
        provider_type = provider.get("type")
        if provider_type not in SUPPORTED_PROVIDER_TYPES:
            raise ProviderConfigError(
                f"provider '{name}' has unsupported type {provider_type!r}"
            )
        if provider_type == "openai_compatible":
            if not provider.get("base_url"):
                raise ProviderConfigError(f"provider '{name}' requires base_url")
            if not provider.get("api_key_env"):
                raise ProviderConfigError(f"provider '{name}' requires api_key_env")
    for alias, model in cfg.get("models", {}).items():
        provider_name = model.get("provider")
        if not provider_name:
            raise ProviderConfigError(f"model '{alias}' requires provider")
        if provider_name not in providers:
            raise ProviderConfigError(
                f"model '{alias}' references unknown provider '{provider_name}'"
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
