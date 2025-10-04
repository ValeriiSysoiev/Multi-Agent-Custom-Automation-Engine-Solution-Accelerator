# Import AppConfig from app_config
from app_config import config
from helpers.azure_credential_utils import get_azure_credential


class _ConfigMeta(type):
    """Metaclass that proxies attribute lookups to the AppConfig instance."""

    def __getattr__(cls, item):
        return getattr(config, item)


class Config(metaclass=_ConfigMeta):
    """Legacy compatibility wrapper over AppConfig."""

    @staticmethod
    def GetAzureCredentials():
        """Get Azure credentials using the AppConfig implementation."""
        return get_azure_credential(
            getattr(config, "AZURE_MANAGED_IDENTITY_CLIENT_ID", None)
            or getattr(config, "AZURE_CLIENT_ID", None)
        )

    @staticmethod
    def GetCosmosDatabaseClient():
        """Get a Cosmos DB client using the AppConfig implementation."""
        return getattr(config, "get_cosmos_database_client")()

    @staticmethod
    def CreateKernel():
        """Creates a new Semantic Kernel instance using the AppConfig implementation."""
        return getattr(config, "create_kernel")()

    @staticmethod
    def GetAIProjectClient():
        """Get an AIProjectClient using the AppConfig implementation."""
        return getattr(config, "get_ai_project_client")()
