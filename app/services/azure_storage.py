"""
Azure Blob Storage Service
==========================

Service for uploading, downloading, and managing voice recordings
in Azure Blob Storage.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

from app.config import settings


class AzureStorageService:
    """
    Service for Azure Blob Storage operations.
    
    Container structure:
        dopamine-detox-{env}/
        ├── voice-recordings/
        │   └── {user_id}/
        │       ├── journals/{entry_id}.mp3
        │       ├── plans/{plan_id}.mp3
        │       └── onboarding/{step_name}.mp3
        └── profile-pictures/
            └── {user_id}/avatar.jpg
    """
    
    def __init__(self):
        self.connection_string = settings.AZURE_STORAGE_CONNECTION_STRING
        self.account_name = settings.AZURE_STORAGE_ACCOUNT_NAME
        self.account_key = settings.AZURE_STORAGE_ACCOUNT_KEY
        self.container_name = settings.AZURE_STORAGE_CONTAINER
        
        self._client: Optional[BlobServiceClient] = None
    
    @property
    def client(self) -> BlobServiceClient:
        """Get or create blob service client."""
        if self._client is None:
            if not self.connection_string:
                raise ValueError(
                    "Azure Storage not configured. "
                    "Set AZURE_STORAGE_CONNECTION_STRING environment variable."
                )
            self._client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
        return self._client
    
    def _get_blob_path(
        self,
        user_id: str,
        recording_type: str,
        filename: str,
    ) -> str:
        """Generate blob path."""
        return f"voice-recordings/{user_id}/{recording_type}/{filename}"
    
    async def upload_voice_recording(
        self,
        user_id: str,
        file_content: bytes,
        recording_type: str,
        file_format: str = "mp3",
        reference_id: Optional[str] = None,
    ) -> dict:
        """
        Upload voice recording to Azure Blob Storage.
        
        Args:
            user_id: User's UUID
            file_content: Binary audio content
            recording_type: Type of recording (journal, plan, onboarding)
            file_format: Audio format (mp3, wav, m4a)
            reference_id: Optional reference ID (entry_id, plan_id, step_name)
            
        Returns:
            Dict with blob_url, sas_url, and metadata
        """
        # Generate filename
        filename = reference_id or str(uuid.uuid4())
        filename = f"{filename}.{file_format}"
        
        blob_path = self._get_blob_path(user_id, recording_type, filename)
        
        # Get blob client
        blob_client = self.client.get_blob_client(
            container=self.container_name,
            blob=blob_path,
        )
        
        # Set content type
        content_type_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "ogg": "audio/ogg",
        }
        content_type = content_type_map.get(file_format, "audio/mpeg")
        
        # Upload blob
        blob_client.upload_blob(
            file_content,
            overwrite=True,
            metadata={
                "user_id": user_id,
                "recording_type": recording_type,
                "upload_timestamp": datetime.now(timezone.utc).isoformat(),
                "file_format": file_format,
            },
            content_settings=ContentSettings(content_type=content_type),
        )
        
        # Generate SAS URL (valid for 1 year)
        sas_url = self._generate_sas_url(blob_path)
        
        # Get blob URL
        blob_url = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}"
        
        return {
            "blob_path": blob_path,
            "blob_url": blob_url,
            "sas_url": sas_url,
            "file_size_bytes": len(file_content),
            "content_type": content_type,
        }
    
    def _generate_sas_url(
        self,
        blob_path: str,
        expiry_days: int = 365,
    ) -> str:
        """Generate SAS URL for blob access."""
        if not self.account_name or not self.account_key:
            # Return blob URL without SAS if keys not configured
            return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}"
        
        sas_token = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_path,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(days=expiry_days),
        )
        
        return f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{blob_path}?{sas_token}"
    
    async def delete_voice_recording(self, blob_path: str) -> bool:
        """
        Delete voice recording from storage.
        
        Args:
            blob_path: Full blob path or URL
            
        Returns:
            True if deleted successfully
        """
        try:
            # Extract path from URL if necessary
            if blob_path.startswith("https://"):
                # Parse URL to get blob path
                parts = blob_path.split(f"{self.container_name}/")
                if len(parts) > 1:
                    blob_path = parts[1].split("?")[0]  # Remove SAS token
            
            blob_client = self.client.get_blob_client(
                container=self.container_name,
                blob=blob_path,
            )
            
            blob_client.delete_blob()
            return True
            
        except Exception as e:
            print(f"Error deleting blob {blob_path}: {e}")
            return False
    
    async def get_blob_metadata(self, blob_path: str) -> Optional[dict]:
        """Get metadata for a blob."""
        try:
            if blob_path.startswith("https://"):
                parts = blob_path.split(f"{self.container_name}/")
                if len(parts) > 1:
                    blob_path = parts[1].split("?")[0]
            
            blob_client = self.client.get_blob_client(
                container=self.container_name,
                blob=blob_path,
            )
            
            properties = blob_client.get_blob_properties()
            
            return {
                "size": properties.size,
                "content_type": properties.content_settings.content_type,
                "created_on": properties.creation_time,
                "metadata": properties.metadata,
            }
            
        except Exception as e:
            print(f"Error getting blob metadata: {e}")
            return None
    
    async def download_blob(self, blob_path: str) -> Optional[bytes]:
        """Download blob content."""
        try:
            if blob_path.startswith("https://"):
                parts = blob_path.split(f"{self.container_name}/")
                if len(parts) > 1:
                    blob_path = parts[1].split("?")[0]
            
            blob_client = self.client.get_blob_client(
                container=self.container_name,
                blob=blob_path,
            )
            
            download_stream = blob_client.download_blob()
            return download_stream.readall()
            
        except Exception as e:
            print(f"Error downloading blob: {e}")
            return None
    
    def refresh_sas_url(self, blob_url: str) -> str:
        """Refresh SAS URL for an existing blob."""
        # Extract blob path from URL
        if "?" in blob_url:
            blob_url = blob_url.split("?")[0]
        
        parts = blob_url.split(f"{self.container_name}/")
        if len(parts) > 1:
            blob_path = parts[1]
            return self._generate_sas_url(blob_path)
        
        return blob_url


# Singleton instance
_storage_service: Optional[AzureStorageService] = None


def get_storage_service() -> AzureStorageService:
    """Get or create storage service instance."""
    global _storage_service
    
    if _storage_service is None:
        _storage_service = AzureStorageService()
    
    return _storage_service
