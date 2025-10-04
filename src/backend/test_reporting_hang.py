#!/usr/bin/env python3
"""Test script to identify where reporting export hangs."""

import asyncio
import sys
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_reporting_export():
    """Test the reporting export to find where it hangs."""
    
    logger.info("Starting test...")
    
    # Test 1: Check Cosmos DB connection
    logger.info("Testing Cosmos DB connection...")
    try:
        from azure.cosmos.aio import CosmosClient
        from azure.identity.aio import DefaultAzureCredential
        
        credential = DefaultAzureCredential()
        cosmos_client = CosmosClient(
            os.environ.get('COSMOSDB_ENDPOINT'),
            credential=credential
        )
        
        database = cosmos_client.get_database_client(os.environ.get('COSMOSDB_DATABASE'))
        logger.info("✓ Cosmos DB client created")
        
        # Try to list containers
        logger.info("Listing containers...")
        containers = []
        async for container in database.list_containers():
            containers.append(container['id'])
            logger.info(f"  Found container: {container['id']}")
        
        if not containers:
            logger.warning("No containers found in database!")
            
        await cosmos_client.close()
        await credential.close()
        
    except Exception as e:
        logger.error(f"✗ Cosmos DB error: {e}")
        return 1
    
    # Test 2: Check Storage connection
    logger.info("Testing Storage connection...")
    try:
        from azure.storage.blob.aio import BlobServiceClient
        from azure.identity.aio import DefaultAzureCredential
        
        credential = DefaultAzureCredential()
        storage_account = os.environ.get('STORAGE_ACCOUNT_NAME')
        blob_service = BlobServiceClient(
            account_url=f"https://{storage_account}.blob.core.windows.net",
            credential=credential
        )
        
        container_name = os.environ.get('STORAGE_CONTAINER_NAME')
        container_client = blob_service.get_container_client(container_name)
        
        logger.info(f"✓ Storage client created for {storage_account}/{container_name}")
        
        # Check if container exists
        try:
            props = await container_client.get_container_properties()
            logger.info(f"✓ Container exists: {container_name}")
        except Exception as e:
            logger.warning(f"Container may not exist: {e}")
        
        await blob_service.close()
        await credential.close()
        
    except Exception as e:
        logger.error(f"✗ Storage error: {e}")
        return 1
    
    logger.info("Basic connectivity tests passed!")
    
    # Test 3: Try to import and run the actual service
    logger.info("Testing ReportingExportService...")
    try:
        # Mock the config to avoid all the environment variable requirements
        import sys
        sys.path.insert(0, '.')
        
        # Create minimal mock config
        class MockConfig:
            COSMOSDB_ENDPOINT = os.environ.get('COSMOSDB_ENDPOINT')
            COSMOSDB_DATABASE = os.environ.get('COSMOSDB_DATABASE')
            AZURE_CLIENT_ID = os.environ.get('AZURE_CLIENT_ID')
            KEYVAULT_URI = os.environ.get('KEYVAULT_URI')
            
        import app_config
        app_config.config = MockConfig()
        
        logger.info("Importing ReportingExportService...")
        from services.reporting_export_service import ReportingExportService
        
        logger.info("Creating service instance...")
        service = ReportingExportService()
        
        logger.info("Starting export with 10-second timeout...")
        try:
            result = await asyncio.wait_for(
                service.export(date_key=None, refresh_powerbi=False),
                timeout=10.0
            )
            logger.info(f"✓ Export completed: {result}")
        except asyncio.TimeoutError:
            logger.error("✗ Export timed out after 10 seconds - THIS IS THE HANG!")
        finally:
            await service.close()
            
    except Exception as e:
        logger.error(f"✗ Service error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(test_reporting_export()))
