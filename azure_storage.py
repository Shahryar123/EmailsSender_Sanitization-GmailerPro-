# azure_storage.py
import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Load env vars
load_dotenv()

# Initialize Azure blob service client
blob_service_client = BlobServiceClient.from_connection_string(
    os.getenv("AZURE_STORAGE_CONNECTION_STRING")
)
container_client = blob_service_client.get_container_client(os.getenv("CONTAINER_NAME"))

# Ensure container exists
try:
    container_client.create_container()
except Exception:
    pass  # Already exists
