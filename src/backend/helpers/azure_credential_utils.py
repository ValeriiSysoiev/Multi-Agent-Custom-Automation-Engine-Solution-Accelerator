import os
from typing import Optional

try:
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.identity.aio import (
        DefaultAzureCredential as AioDefaultAzureCredential,
        ManagedIdentityCredential as AioManagedIdentityCredential,
    )
except ModuleNotFoundError:  # pragma: no cover - test fallback
    class _DummyCredential:
        def __init__(self, *args, **kwargs):
            pass

        def get_token(self, *args, **kwargs):
            class _Token:
                token = 'test-token'
            return _Token()

        async def close(self):
            return None

    DefaultAzureCredential = ManagedIdentityCredential = _DummyCredential
    AioDefaultAzureCredential = AioManagedIdentityCredential = _DummyCredential


def resolve_managed_identity_client_id(preferred: Optional[str] = None) -> Optional[str]:
    """Return the first non-empty managed-identity client ID candidate."""

    for candidate in (
        preferred,
        os.getenv("AZURE_MANAGED_IDENTITY_CLIENT_ID"),
        os.getenv("AZURE_CLIENT_ID"),
    ):
        if candidate:
            stripped = candidate.strip()
            if stripped:
                return stripped
    return None


def _use_default_credential() -> bool:
    return os.getenv("APP_ENV", "prod").lower() == "dev"


async def get_azure_credential_async(client_id: Optional[str] = None):
    """Return an async Azure credential suitable for the current environment."""

    return _create_aio_credential(client_id)


def get_async_azure_credential(client_id: Optional[str] = None):
    """Return an aio-compatible Azure credential without requiring await."""

    return _create_aio_credential(client_id)


def _create_aio_credential(client_id: Optional[str]):
    resolved_client_id = resolve_managed_identity_client_id(client_id)
    if _use_default_credential():
        return AioDefaultAzureCredential(managed_identity_client_id=resolved_client_id)  # CodeQL [SM05139] Okay use of DefaultAzureCredential as it is only used in development
    return AioManagedIdentityCredential(client_id=resolved_client_id)


def get_azure_credential(client_id: Optional[str] = None):
    """Return a synchronous Azure credential for the current environment."""

    resolved_client_id = resolve_managed_identity_client_id(client_id)
    if _use_default_credential():
        return DefaultAzureCredential(managed_identity_client_id=resolved_client_id)  # CodeQL [SM05139]
    return ManagedIdentityCredential(client_id=resolved_client_id)


__all__ = [
    "get_azure_credential",
    "get_azure_credential_async",
    "get_async_azure_credential",
    "resolve_managed_identity_client_id",
]
