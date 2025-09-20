import os
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from typing import Optional
import hashlib

def save_uploaded_image(file_content: bytes, original_filename: str) -> str:
    """
    Save uploaded image to media directory and return the URL path.
    
    Args:
        file_content: The raw file content as bytes
        original_filename: Original filename for extension detection
        
    Returns:
        String path to the saved image that can be used as imageUrl
    """
    try:
        # Generate unique filename to avoid conflicts
        file_hash = hashlib.md5(file_content).hexdigest()[:8]
        file_extension = os.path.splitext(original_filename)[1].lower()
        
        # Fallback to .jpg if no extension
        if not file_extension:
            file_extension = '.jpg'
            
        unique_filename = f"{uuid.uuid4().hex}_{file_hash}{file_extension}"
        
        # Create relative path for storage
        relative_path = os.path.join('images', unique_filename)
        
        # Save file using Django's storage system
        content_file = ContentFile(file_content)
        saved_path = default_storage.save(relative_path, content_file)
        
        # Return URL path that can be accessed via /media/
        # Ensure no double slash by using settings.MEDIA_URL
        return f"{settings.MEDIA_URL}{saved_path}".replace('//', '/')
        
    except Exception as e:
        print(f"[ERROR] Failed to save image: {str(e)}")
        return None

def save_image_from_bytes(image_bytes: bytes, filename_prefix: str = "extracted") -> Optional[str]:
    """
    Save image bytes to media directory.
    
    Args:
        image_bytes: The image data as bytes
        filename_prefix: Prefix for the generated filename
        
    Returns:
        String path to the saved image or None if failed
    """
    try:
        # Generate unique filename
        file_hash = hashlib.md5(image_bytes).hexdigest()[:8]
        unique_filename = f"{filename_prefix}_{uuid.uuid4().hex}_{file_hash}.jpg"
        
        # Create relative path for storage
        relative_path = os.path.join('images', unique_filename)
        
        # Save file
        content_file = ContentFile(image_bytes)
        saved_path = default_storage.save(relative_path, content_file)
        
        # Return URL path
        return f"{settings.MEDIA_URL}{saved_path}".replace('//', '/')
        
    except Exception as e:
        print(f"[ERROR] Failed to save image bytes: {str(e)}")
        return None