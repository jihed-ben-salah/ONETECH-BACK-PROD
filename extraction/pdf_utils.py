"""PDF processing utilities for splitting and converting PDFs to images."""

import io
import os
import tempfile
from typing import List, Tuple, BinaryIO
from PIL import Image
import logging

try:
    from pdf2image import convert_from_bytes
    import PyPDF2
    PDF_LIBS_AVAILABLE = True
except ImportError:
    PDF_LIBS_AVAILABLE = False

logger = logging.getLogger(__name__)

def is_pdf_file(file_content: bytes) -> bool:
    """Check if the file content is a PDF."""
    return file_content.startswith(b'%PDF-')

def split_pdf_to_images(file_content: bytes, dpi: int = 150, format: str = 'JPEG') -> List[Tuple[int, bytes]]:
    """
    Split a PDF into individual page images.
    
    Args:
        file_content: PDF file content as bytes
        dpi: Resolution for the converted images (default: 150)
        format: Output image format (default: 'JPEG')
    
    Returns:
        List of tuples (page_number, image_bytes)
    """
    if not PDF_LIBS_AVAILABLE:
        raise ImportError("PDF processing libraries not available")
    
    pages = []
    
    try:
        # Convert PDF to images using pdf2image
        images = convert_from_bytes(file_content, dpi=dpi)
        
        logger.info(f"PDF has {len(images)} pages")
        
        for page_num, img in enumerate(images):
            # Convert to target format
            output_buffer = io.BytesIO()
            
            if format.upper() == 'JPEG':
                # Convert to RGB if necessary (remove alpha channel)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(output_buffer, format='JPEG', quality=85, optimize=True)
            else:
                img.save(output_buffer, format=format)
            
            image_bytes = output_buffer.getvalue()
            pages.append((page_num + 1, image_bytes))  # 1-indexed page numbers
            
            logger.info(f"Converted page {page_num + 1} to {format}, size: {len(image_bytes)} bytes")
            
    except Exception as e:
        logger.error(f"Error splitting PDF to images: {str(e)}")
        raise Exception(f"Failed to split PDF: {str(e)}")
        
    return pages

def convert_single_page_pdf_to_image(file_content: bytes, dpi: int = 150) -> bytes:
    """
    Convert a single-page PDF to an image.
    
    Args:
        file_content: PDF file content as bytes
        dpi: Resolution for the converted image
    
    Returns:
        Image bytes in JPEG format
    """
    try:
        pages = split_pdf_to_images(file_content, dpi=dpi)
        if not pages:
            raise Exception("No pages found in PDF")
        
        if len(pages) > 1:
            logger.warning(f"PDF has {len(pages)} pages, returning only the first page")
        
        return pages[0][1]  # Return the image bytes of the first page
        
    except Exception as e:
        logger.error(f"Error converting PDF to image: {str(e)}")
        raise Exception(f"Failed to convert PDF to image: {str(e)}")

def save_image_to_temp_file(image_bytes: bytes, suffix: str = '.jpg') -> str:
    """
    Save image bytes to a temporary file.
    
    Args:
        image_bytes: Image content as bytes
        suffix: File suffix (default: '.jpg')
    
    Returns:
        Path to the temporary file
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            return tmp.name
    except Exception as e:
        logger.error(f"Error saving image to temp file: {str(e)}")
        raise Exception(f"Failed to save image to temp file: {str(e)}")

def get_pdf_page_count(file_content: bytes) -> int:
    """
    Get the number of pages in a PDF.
    
    Args:
        file_content: PDF file content as bytes
    
    Returns:
        Number of pages in the PDF
    """
    if not PDF_LIBS_AVAILABLE:
        raise ImportError("PDF processing libraries not available")
    
    try:
        # Use PyPDF2 to get page count (lighter than converting to images)
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        page_count = len(pdf_reader.pages)
        return page_count
    except Exception as e:
        logger.error(f"Error getting PDF page count: {str(e)}")
        # Fallback: convert to images and count
        try:
            images = convert_from_bytes(file_content, dpi=72)  # Low DPI for speed
            return len(images)
        except Exception as fallback_e:
            logger.error(f"Fallback method also failed: {str(fallback_e)}")
            raise Exception(f"Failed to get PDF page count: {str(e)}")
