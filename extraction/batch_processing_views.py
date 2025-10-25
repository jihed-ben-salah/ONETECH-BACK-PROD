"""
Comprehensive backend batch processing system for PDF documents.
Handles: PDF upload → Split → Extract → Real-time tracking → Database storage
"""
import os
import uuid
import json
import time
import threading
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, List, Optional
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from PIL import Image, UnidentifiedImageError

from .pdf_utils import (
    is_pdf_file, 
    split_pdf_to_images, 
    convert_single_page_pdf_to_image,
    get_pdf_page_count
)
from .document_models import get_model_by_type
from .document_views import serialize_document
from .image_storage import save_image_from_bytes

# Import extraction function
try:
    from process_forms import extract_data_from_image
except Exception:
    from ..process_forms import extract_data_from_image

# MongoDB connection for session storage (production-ready)
from .mongodb import get_database

# In-memory session storage DEPRECATED - keeping for backward compatibility only
BATCH_SESSIONS = {}

def get_sessions_collection():
    """Get MongoDB collection for batch sessions"""
    try:
        db = get_database()
        return db['batch_sessions']
    except Exception as e:
        print(f"[ERROR] Failed to connect to MongoDB for sessions: {e}")
        return None


class BatchProcessingSession:
    """Enhanced processing session with real-time tracking"""
    
    def __init__(self, session_id: str, total_pages: int, document_type: str, filename: str):
        self.session_id = session_id
        self.total_pages = total_pages
        self.document_type = document_type
        self.filename = filename
        self.completed_pages = 0
        self.failed_pages = 0
        self.processing_page = None  # Currently processing page number
        self.documents = []
        self.errors = []
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.status = 'initializing'  # initializing, processing, completed, failed
        self.pages_info = {}  # Detailed info about each page
        self.processing_thread = None
        
    def update_status(self, status: str):
        """Update session status"""
        self.status = status
        self.updated_at = datetime.utcnow()
        
    def set_processing_page(self, page_num: int):
        """Set currently processing page - now supports multiple concurrent pages"""
        # Don't update self.processing_page anymore since we have multiple pages
        # Instead, track individual page status
        self.updated_at = datetime.utcnow()
        if page_num not in self.pages_info:
            self.pages_info[page_num] = {
                'page_number': page_num,
                'status': 'processing',
                'started_at': datetime.utcnow().isoformat(),
                'document_id': None,
                'error': None,
                'image_url': None
            }
        else:
            # Update existing page info
            self.pages_info[page_num].update({
                'status': 'processing',
                'started_at': datetime.utcnow().isoformat()
            })
        
    def add_success(self, page_num: int, document_id: str, extraction_data: Dict[str, Any], document_data: Dict[str, Any] = None):
        """Add successful page processing"""
        self.completed_pages += 1
        self.processing_page = None
        
        # Store comprehensive document info for frontend
        doc_info = {
            'page': page_num,
            'id': document_id,
            'extraction_confidence': extraction_data.get('extraction_confidence'),
            'final_confidence': extraction_data.get('final_confidence')
        }
        
        # Include full document data if provided
        if document_data:
            doc_info.update({
                'data': extraction_data,
                'metadata': document_data.get('metadata', {}),
                'remark': document_data.get('remark', ''),
                'imageUrl': document_data.get('imageUrl', ''),
                'json_url': document_data.get('json_url', ''),
                'excel_url': document_data.get('excel_url', ''),
                'filename': document_data.get('metadata', {}).get('filename', ''),
                'document_type': self.document_type,
                'created_at': document_data.get('metadata', {}).get('processed_at', ''),
            })
        
        self.documents.append(doc_info)
        
        # Update page info
        if page_num in self.pages_info:
            self.pages_info[page_num].update({
                'status': 'completed',
                'completed_at': datetime.utcnow().isoformat(),
                'document_id': document_id,
                'extraction_confidence': extraction_data.get('extraction_confidence'),
                'final_confidence': extraction_data.get('final_confidence')
            })
        
        self.updated_at = datetime.utcnow()
        
        # Update overall status
        if (self.completed_pages + self.failed_pages) >= self.total_pages:
            self.status = 'completed' if self.completed_pages > 0 else 'failed'
            print(f"[DEBUG] Session {self.session_id} marked as {self.status}: {self.completed_pages}/{self.total_pages} completed")
        
        # Save to MongoDB after each update
        self.save_to_db()
        
    def add_error(self, page_num: int, error: str):
        """Add failed page processing"""
        self.failed_pages += 1
        self.processing_page = None
        self.errors.append({
            'page': page_num,
            'error': str(error),
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Update page info
        if page_num in self.pages_info:
            self.pages_info[page_num].update({
                'status': 'failed',
                'completed_at': datetime.utcnow().isoformat(),
                'error': str(error)
            })
        
        self.updated_at = datetime.utcnow()
        
        # Update overall status
        if (self.completed_pages + self.failed_pages) >= self.total_pages:
            self.status = 'completed' if self.completed_pages > 0 else 'failed'
        
        # Save to MongoDB after each update
        self.save_to_db()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for JSON response"""
        progress_percentage = ((self.completed_pages + self.failed_pages) / self.total_pages * 100) if self.total_pages > 0 else 0
        
        # Get currently processing pages (multiple pages can be processing in parallel)
        processing_pages = [
            page_num for page_num, info in self.pages_info.items() 
            if info.get('status') == 'processing'
        ]
        
        return {
            'session_id': self.session_id,
            'status': self.status,
            'total_pages': self.total_pages,
            'completed_pages': self.completed_pages,
            'failed_pages': self.failed_pages,
            'processing_page': self.processing_page,  # Keep for backward compatibility
            'processing_pages': processing_pages,  # New: list of currently processing pages
            'progress_percentage': round(progress_percentage, 1),
            'document_type': self.document_type,
            'filename': self.filename,
            'documents': self.documents,
            'errors': self.errors,
            'pages_info': self.pages_info,
            'started_at': self.started_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'elapsed_seconds': (datetime.utcnow() - self.started_at).total_seconds(),
        }
    
    def save_to_db(self):
        """Save session to MongoDB"""
        try:
            collection = get_sessions_collection()
            if collection is None:
                print(f"[WARNING] MongoDB not available, session {self.session_id} only in memory")
                return
            
            session_data = self.to_dict()
            session_data['_id'] = self.session_id  # Use session_id as MongoDB _id
            
            # MongoDB requires string keys - convert pages_info integer keys to strings
            if 'pages_info' in session_data and session_data['pages_info']:
                session_data['pages_info'] = {
                    str(k): v for k, v in session_data['pages_info'].items()
                }
            
            # Upsert (update or insert)
            collection.replace_one(
                {'_id': self.session_id},
                session_data,
                upsert=True
            )
            print(f"[DEBUG] Session {self.session_id} saved to MongoDB")
        except Exception as e:
            print(f"[ERROR] Failed to save session to MongoDB: {e}")
    
    @classmethod
    def load_from_db(cls, session_id: str):
        """Load session from MongoDB"""
        try:
            collection = get_sessions_collection()
            if collection is None:
                return None
            
            session_data = collection.find_one({'_id': session_id})
            if not session_data:
                return None
            
            # Reconstruct session object
            session = cls(
                session_id=session_data['session_id'],
                total_pages=session_data['total_pages'],
                document_type=session_data['document_type'],
                filename=session_data['filename']
            )
            
            # Restore state
            session.status = session_data.get('status', 'processing')
            session.completed_pages = session_data.get('completed_pages', 0)
            session.failed_pages = session_data.get('failed_pages', 0)
            session.processing_page = session_data.get('processing_page')
            session.documents = session_data.get('documents', [])
            session.errors = session_data.get('errors', [])
            
            # Convert string keys back to integers for pages_info
            pages_info = session_data.get('pages_info', {})
            if pages_info:
                session.pages_info = {
                    int(k) if k.isdigit() else k: v 
                    for k, v in pages_info.items()
                }
            else:
                session.pages_info = {}
            
            session.started_at = datetime.fromisoformat(session_data['started_at'])
            session.updated_at = datetime.fromisoformat(session_data['updated_at'])
            
            print(f"[DEBUG] Session {session_id} loaded from MongoDB")
            return session
            
        except Exception as e:
            print(f"[ERROR] Failed to load session from MongoDB: {e}")
            return None


def process_pdf_pages_background(session_id: str):
    """Background thread function to process PDF pages in parallel"""
    session = BATCH_SESSIONS.get(session_id)
    if not session:
        print(f"[ERROR] Session {session_id} not found in background processing")
        return
    
    print(f"[DEBUG] Starting parallel background processing for session {session_id}")
    session.update_status('processing')
    
    # Configure Google AI
    import google.generativeai as genai
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        session.add_error(0, "Google API key not configured")
        session.update_status('failed')
        return
    
    try:
        genai.configure(api_key=api_key)
        print(f"[DEBUG] Google AI configured for session {session_id}")
    except Exception as e:
        session.add_error(0, f"Failed to configure Google AI: {str(e)}")
        session.update_status('failed')
        return
    
    # Get page images from session metadata
    pages_data = session.__dict__.get('pages_data', [])
    if not pages_data:
        session.add_error(0, "No page data available for processing")
        session.update_status('failed')
        return
    
    # Process pages in parallel using ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    
    # Use a reasonable number of workers (e.g., 3-5 to avoid API rate limits)
    max_workers = min(5, len(pages_data))
    print(f"[DEBUG] Processing {len(pages_data)} pages with {max_workers} parallel workers")
    
    def process_single_page(page_data):
        """Process a single page - this will run in parallel"""
        page_num, image_bytes, image_url = page_data
        thread_id = threading.current_thread().ident
        
        try:
            print(f"[DEBUG] Thread {thread_id}: Processing page {page_num}/{session.total_pages}")
            session.set_processing_page(page_num)
            
            # Save image to temporary file for extraction
            import tempfile
            tmp_path = None
            
            try:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp.write(image_bytes)
                    tmp_path = tmp.name
                
                # Perform AI extraction
                print(f"[DEBUG] Thread {thread_id}: Starting extraction for page {page_num}, doc type: {session.document_type}")
                wrapper = extract_data_from_image(tmp_path, doc_type=session.document_type)
                
                if not wrapper:
                    raise Exception("Empty extraction result from AI")
                
                # Process extraction result
                inner = wrapper.get('data') if isinstance(wrapper, dict) else wrapper
                remark = wrapper.get('remark') if isinstance(wrapper, dict) else None
                
                # Create document in database
                Model = get_model_by_type(session.document_type)
                doc_id = str(uuid.uuid4())
                
                document_data = {
                    'id': doc_id,
                    'data': inner,
                    'metadata': {
                        'filename': f'{session.filename}_page_{page_num}',
                        'document_type': session.document_type,
                        'processed_at': datetime.utcnow().isoformat(),
                        'page_number': page_num,
                        'total_pages': session.total_pages,
                        'session_id': session_id,
                        'is_multi_page': session.total_pages > 1,
                        'original_filename': session.filename
                    },
                    'remark': remark or f'{session.document_type} extraction complete - Page {page_num}',
                    'imageUrl': image_url,
                    'json_url': f'/api/documents/{doc_id}/export?format=json',
                    'excel_url': f'/api/documents/{doc_id}/export?format=excel',
                    'retry_used': 'no',
                }
                
                document = Model.create(document_data)
                session.add_success(page_num, doc_id, inner, document_data)
                
                print(f"[DEBUG] Thread {thread_id}: Successfully processed page {page_num}")
                return {'success': True, 'page': page_num, 'doc_id': doc_id}
                
            finally:
                # Cleanup temp file
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                        
        except Exception as e:
            print(f"[ERROR] Thread {thread_id}: Failed to process page {page_num}: {str(e)}")
            session.add_error(page_num, str(e))
            return {'success': False, 'page': page_num, 'error': str(e)}
    
    # Execute pages in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all pages for processing
        future_to_page = {executor.submit(process_single_page, page_data): page_data[0] 
                         for page_data in pages_data}
        
        # Process completed futures as they finish
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                result = future.result()
                if result['success']:
                    print(f"[DEBUG] Page {result['page']} completed successfully")
                else:
                    print(f"[ERROR] Page {result['page']} failed: {result['error']}")
            except Exception as e:
                print(f"[ERROR] Exception getting result for page {page_num}: {str(e)}")
                session.add_error(page_num, f"Future exception: {str(e)}")
    
    # Final status update
    if session.completed_pages > 0:
        session.update_status('completed')
        print(f"[DEBUG] Session {session_id} completed: {session.completed_pages}/{session.total_pages} pages processed in parallel")
    else:
        session.update_status('failed')
        print(f"[ERROR] Session {session_id} failed: no pages processed successfully")





@csrf_exempt
@require_http_methods(["POST"])
def start_batch_processing(request):
    """
    Start batch processing of PDF document.
    This endpoint handles the entire pipeline in the background.
    """
    try:
        print(f"[DEBUG] Batch processing request received")
        print(f"[DEBUG] Request FILES keys: {list(request.FILES.keys())}")
        print(f"[DEBUG] Request POST keys: {list(request.POST.keys())}")
        
        # Validate request
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
        
        document_type = request.POST.get('document_type')
        if not document_type:
            return JsonResponse({'error': 'document_type is required'}, status=400)
        
        if document_type not in ['Rebut', 'NPT', 'Kosu']:
            return JsonResponse({'error': 'Invalid document_type. Must be Rebut, NPT, or Kosu'}, status=400)
        
        uploaded_file = request.FILES['file']
        
        print(f"[DEBUG] Processing file: {uploaded_file.name}, size: {uploaded_file.size}, type: {uploaded_file.content_type}")
        
        # Read uploaded content once
        file_content = uploaded_file.read()
        
        pages_data: List[Any] = []
        page_count = 0
        original_filename = uploaded_file.name or 'uploaded_file'
        
        if is_pdf_file(file_content):
            # Handle PDF uploads
            try:
                page_count = get_pdf_page_count(file_content)
                print(f"[DEBUG] PDF has {page_count} pages")
                
                if page_count == 1:
                    image_bytes = convert_single_page_pdf_to_image(file_content)
                    pages_data = [(1, image_bytes)]
                else:
                    pages_data = split_pdf_to_images(file_content)
                    
            except Exception as e:
                print(f"[ERROR] PDF processing failed: {str(e)}")
                return JsonResponse({'error': f'Failed to process PDF: {str(e)}'}, status=400)
        else:
            # Attempt to treat the upload as an image
            try:
                with Image.open(BytesIO(file_content)) as img:
                    # Normalize to RGB JPEG to align with downstream expectations
                    converted = img.convert('RGB')
                    buffer = BytesIO()
                    converted.save(buffer, format='JPEG', quality=95)
                    image_bytes = buffer.getvalue()
            except UnidentifiedImageError:
                print("[ERROR] Uploaded file is neither a valid PDF nor an image")
                return JsonResponse({'error': 'File must be a valid PDF or image'}, status=400)
            except Exception as e:
                print(f"[ERROR] Image normalization failed: {str(e)}")
                return JsonResponse({'error': f'Failed to process image: {str(e)}'}, status=400)
            
            page_count = 1
            pages_data = [(1, image_bytes)]
            print(f"[DEBUG] Image upload detected, normalized to single page batch")
        
        # Create session
        session_id = str(uuid.uuid4())
        session = BatchProcessingSession(
            session_id=session_id,
            total_pages=len(pages_data),
            document_type=document_type,
            filename=original_filename
        )
        
        # Save images and prepare data for background processing
        pages_with_urls = []
        filename_root = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        for page_num, image_bytes in pages_data:
            # Save image to media storage
            image_url = save_image_from_bytes(
                image_bytes, 
                f"{filename_root}_page_{page_num}"
            )
            
            if not image_url:
                print(f"[WARNING] Failed to save image for page {page_num}")
                image_url = f"/media/images/page_{page_num}.jpg"  # fallback
            
            pages_with_urls.append((page_num, image_bytes, image_url))
            print(f"[DEBUG] Saved page {page_num} to {image_url}")
            
            # Initialize page info with image URL
            session.pages_info[page_num] = {
                'page_number': page_num,
                'status': 'pending',
                'image_url': image_url,
                'document_id': None,
                'error': None
            }
        
        # Store page data in session for background processing
        session.__dict__['pages_data'] = pages_with_urls
        BATCH_SESSIONS[session_id] = session
        
        # Save session to MongoDB for multi-worker access
        session.save_to_db()
        print(f"[DEBUG] Session {session_id} saved to MongoDB and in-memory cache")
        
        # Start background processing
        processing_thread = threading.Thread(
            target=process_pdf_pages_background,
            args=(session_id,),
            daemon=True
        )
        processing_thread.start()
        session.processing_thread = processing_thread
        
        print(f"[DEBUG] Started background processing for session {session_id}")
        
        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'message': f'Started processing {page_count} pages in background',
            'status': session.to_dict()
        })
        
    except Exception as e:
        print(f"[ERROR] Batch processing start failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to start batch processing: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_batch_status(request, session_id):
    """
    Get real-time status of batch processing session.
    Frontend polls this endpoint for progress updates.
    """
    try:
        # First check in-memory cache (fastest)
        session = BATCH_SESSIONS.get(session_id)
        
        # If not in memory, try loading from MongoDB (handles multiple workers)
        if not session:
            session = BatchProcessingSession.load_from_db(session_id)
            if session:
                # Cache in memory for faster subsequent access
                BATCH_SESSIONS[session_id] = session
                print(f"[DEBUG] Session {session_id} loaded from MongoDB and cached")
            else:
                return JsonResponse({'error': 'Session not found'}, status=404)
        
        status_data = session.to_dict()
        
        # Add some helpful computed fields
        status_data['is_processing'] = session.status == 'processing'
        status_data['is_completed'] = session.status == 'completed'
        status_data['is_failed'] = session.status == 'failed'
        
        # Calculate estimated time remaining
        if session.status == 'processing' and session.completed_pages > 0:
            elapsed = (datetime.utcnow() - session.started_at).total_seconds()
            avg_time_per_page = elapsed / (session.completed_pages + session.failed_pages)
            remaining_pages = session.total_pages - session.completed_pages - session.failed_pages
            estimated_remaining = avg_time_per_page * remaining_pages
            status_data['estimated_remaining_seconds'] = round(estimated_remaining)
        else:
            status_data['estimated_remaining_seconds'] = None
        
        return JsonResponse(status_data)
        
    except Exception as e:
        print(f"[ERROR] Failed to get batch status: {str(e)}")
        return JsonResponse({
            'error': f'Failed to get status: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def cancel_batch_processing(request, session_id):
    """
    Cancel an active batch processing session.
    """
    try:
        if session_id not in BATCH_SESSIONS:
            return JsonResponse({'error': 'Session not found'}, status=404)
        
        session = BATCH_SESSIONS[session_id]
        
        if session.status in ['completed', 'failed']:
            return JsonResponse({
                'message': f'Session already {session.status}',
                'status': session.to_dict()
            })
        
        # Update status to cancelled
        session.update_status('cancelled')
        
        # Note: We can't easily stop the background thread, but we can mark it as cancelled
        # The thread will continue but results won't be used
        
        return JsonResponse({
            'success': True,
            'message': 'Batch processing cancelled',
            'status': session.to_dict()
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to cancel batch processing: {str(e)}")
        return JsonResponse({
            'error': f'Failed to cancel: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def list_batch_sessions(request):
    """
    List all batch processing sessions (for debugging/monitoring).
    """
    try:
        sessions_data = []
        for session_id, session in BATCH_SESSIONS.items():
            sessions_data.append(session.to_dict())
        
        # Sort by most recent first
        sessions_data.sort(key=lambda x: x['started_at'], reverse=True)
        
        return JsonResponse({
            'sessions': sessions_data,
            'total': len(sessions_data)
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to list sessions: {str(e)}")
        return JsonResponse({
            'error': f'Failed to list sessions: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def cleanup_batch_sessions(request):
    """
    Clean up old completed/failed sessions (for memory management).
    """
    try:
        # Keep only sessions from last 24 hours or still processing
        cutoff_time = datetime.utcnow().timestamp() - 24 * 3600  # 24 hours ago
        
        sessions_to_remove = []
        for session_id, session in BATCH_SESSIONS.items():
            if (session.status in ['completed', 'failed', 'cancelled'] and 
                session.updated_at.timestamp() < cutoff_time):
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del BATCH_SESSIONS[session_id]
        
        return JsonResponse({
            'success': True,
            'cleaned_up': len(sessions_to_remove),
            'remaining': len(BATCH_SESSIONS)
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to cleanup sessions: {str(e)}")
        return JsonResponse({
            'error': f'Failed to cleanup: {str(e)}'
        }, status=500)
