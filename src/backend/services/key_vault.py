"""Key Vault secret retrieval utilities."""

from __future__ import annotations

import re
from typing import Optional

from azure.core.exceptions import ResourceNotFoundError

from app_config import config


class KeyVaultService:
    """Provides cached access to secrets stored in Azure Key Vault."""

    def __init__(self) -> None:
        self._client = config.get_secret_client()
        self._cache: dict[str, str] = {}

    async def get_secret(self, name: str) -> str:
        """Retrieve a secret value, caching it locally."""

        if name in self._cache:
            return self._cache[name]

        candidates: list[str] = []
        variations = {
            name,
            name.replace("_", "-"),
            name.replace("-", "_"),
        }
        # include lowercase variants because Key Vault normalises names to lowercase
        variations |= {variant.lower() for variant in list(variations)}

        for candidate in variations:
            # Key Vault secret names allow alphanumerics and hyphen only
            if not candidate or not re.fullmatch(r"[0-9A-Za-z-]+", candidate):
                continue
            if candidate not in candidates:
                candidates.append(candidate)

        last_exc: ResourceNotFoundError | None = None
        for candidate in candidates:
            try:
                secret = await self._client.get_secret(candidate)
            except ResourceNotFoundError as exc:
                last_exc = exc
                continue

            value = secret.value
            if value is None:
                raise RuntimeError(f"Secret '{candidate}' has no value")

            self._cache[name] = value
            if candidate != name:
                self._cache[candidate] = value
            return value

        if last_exc is not None:
            raise ResourceNotFoundError(
                f"Secret '{name}' not found in Key Vault (tried: {', '.join(candidates)})"
            ) from last_exc

        raise ResourceNotFoundError(f"Secret '{name}' not found in Key Vault")

    async def close(self) -> None:
        await config.close_secret_client()
