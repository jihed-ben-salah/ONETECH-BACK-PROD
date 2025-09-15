"""PDF processing utilities for splitting and converting PDFs to images."""

import io
import os
import tempfile
from typing import List, Tuple, BinaryIO
from PIL import Image
import logging

try:
    import fitz  # PyMuPDF
    PDF_LIBS_AVAILABLE = True
except ImportError:
    PDF_LIBS_AVAILABLE = False

logger = logging.getLogger(__name__)

def is_pdf_file(file_content: bytes) -> bool:
    """Check if the file content is a PDF."""
    return file_content.startswith(b'%PDF-')

def split_pdf_to_images(file_content: bytes, dpi: int = 150, format: str = 'JPEG') -> List[Tuple[int, bytes]]:
    """
    Split a PDF into individual page images using PyMuPDF (cloud-ready, no system dependencies).
    
    Args:
        file_content: PDF file content as bytes
        dpi: Resolution for the converted images (default: 150)
        format: Output image format (default: 'JPEG')
    
    Returns:
        List of tuples (page_number, image_bytes)
    """
    if not PDF_LIBS_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) library not available")
    
    pages = []
    
    try:
        # Open PDF from bytes using PyMuPDF
        pdf_document = fitz.open(stream=file_content, filetype="pdf")
        
        logger.info(f"PDF has {pdf_document.page_count} pages")
        
        for page_num in range(pdf_document.page_count):
            # Get the page
            page = pdf_document[page_num]
            
            # Create transformation matrix for DPI scaling
            # PyMuPDF default is 72 DPI, so we scale accordingly
            scale_factor = dpi / 72.0
            mat = fitz.Matrix(scale_factor, scale_factor)
            
            # Render page to pixmap (image)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            
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
            
        # Close the PDF document
        pdf_document.close()
            
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
    Get the number of pages in a PDF using PyMuPDF (cloud-ready).
    
    Args:
        file_content: PDF file content as bytes
    
    Returns:
        Number of pages in the PDF
    """
    if not PDF_LIBS_AVAILABLE:
        raise ImportError("PyMuPDF (fitz) library not available")
    
    try:
        # Use PyMuPDF to get page count (very fast and lightweight)
        pdf_document = fitz.open(stream=file_content, filetype="pdf")
        page_count = pdf_document.page_count
        pdf_document.close()
        return page_count
    except Exception as e:
        logger.error(f"Error getting PDF page count: {str(e)}")
        raise Exception(f"Failed to get PDF page count: {str(e)}")

def cleanup_temp_file(file_path: str) -> bool:
    """
    Safely delete a temporary file.
    
    Args:
        file_path: Path to the temporary file to delete
    
    Returns:
        True if file was deleted successfully, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"Deleted temporary file: {file_path}")
            return True
        else:
            logger.warning(f"Temporary file not found: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error deleting temporary file {file_path}: {str(e)}")
        return False
