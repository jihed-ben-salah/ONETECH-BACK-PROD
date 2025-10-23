"""
PDF Processing views - Complete PDF processing pipeline in backend.
Handles: PDF upload → Split → Extract → Save to database
Frontend just uploads PDF and gets results.
"""
import os
import uuid
import tempfile
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from .document_models import get_model_by_type
from .document_views import serialize_document


# In-memory session storage (use Redis/database in production)
PROCESSING_SESSIONS = {}


class ProcessingSession:
    """Track processing session state"""
    def __init__(self, session_id, total_pages, document_type, filename):
        self.session_id = session_id
        self.total_pages = total_pages
        self.document_type = document_type
        self.filename = filename
        self.completed_pages = 0
        self.failed_pages = 0
        self.documents = []
        self.errors = []
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
    def add_success(self, page_num, document_id):
        self.completed_pages += 1
        self.documents.append({'page': page_num, 'id': document_id})
        self.updated_at = datetime.utcnow()
        
    def add_error(self, page_num, error):
        self.failed_pages += 1
        self.errors.append({'page': page_num, 'error': str(error)})
        self.updated_at = datetime.utcnow()
        
    def to_dict(self):
        return {
            'session_id': self.session_id,
            'total_pages': self.total_pages,
            'completed_pages': self.completed_pages,
            'failed_pages': self.failed_pages,
            'document_type': self.document_type,
            'filename': self.filename,
            'documents': self.documents,
            'errors': self.errors,
            'status': 'completed' if (self.completed_pages + self.failed_pages) >= self.total_pages else 'processing',
            'started_at': self.started_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


@csrf_exempt
@require_http_methods(["POST"])
def split_pdf(request):
    """
    Split PDF into individual page images and save them to media folder.
    Returns URLs to the saved images instead of base64 data.
    """
    try:
        print(f"[DEBUG] Processing split_pdf request")
        print(f"[DEBUG] Request method: {request.method}")
        print(f"[DEBUG] Request FILES keys: {list(request.FILES.keys())}")
        print(f"[DEBUG] Request POST keys: {list(request.POST.keys())}")
        print(f"[DEBUG] Content type: {request.content_type}")
        
        if 'file' not in request.FILES:
            print(f"[ERROR] No 'file' in request.FILES")
            return JsonResponse({'error': 'No file uploaded'}, status=400)
            
        pdf_file = request.FILES['file']
        
        print(f"[DEBUG] PDF Split request received with data keys: {list(request.FILES.keys())}")
        print(f"[DEBUG] File info: name='{pdf_file.name}', size={pdf_file.size}, content_type='{pdf_file.content_type}'")
        
        # Use the same PDF processing logic as the working SplitPDFView
        try:
            from .pdf_utils import split_pdf_to_images, get_pdf_page_count, is_pdf_file
        except ImportError:
            return JsonResponse({
                'error': 'PDF processing utilities not available.'
            }, status=500)
        
        # Read PDF content
        pdf_content = pdf_file.read()
        
        # Check if it's actually a PDF
        if not is_pdf_file(pdf_content):
            return JsonResponse({'error': 'File is not a valid PDF'}, status=400)
        
        # Convert PDF to images using the working method
        try:
            page_count = get_pdf_page_count(pdf_content)
            print(f"[DEBUG] PDF has {page_count} pages")
            
            if page_count == 1:
                from .pdf_utils import convert_single_page_pdf_to_image
                image_bytes = convert_single_page_pdf_to_image(pdf_content)
                pages_data = [(1, image_bytes)]
            else:
                pages_data = split_pdf_to_images(pdf_content)
                
        except Exception as e:
            print(f"[ERROR] PDF processing failed: {str(e)}")
            return JsonResponse({
                'error': f'Failed to process PDF: {str(e)}'
            }, status=400)
        
        # Save each page as an image and return URLs
        pages = []
        session_id = str(uuid.uuid4())
        
        for page_num, image_bytes in pages_data:
            # Save image to media directory
            filename = f"pdf_pages/{session_id}/page_{page_num}.jpg"
            
            # Save to Django storage
            path = default_storage.save(filename, ContentFile(image_bytes))
            url = default_storage.url(path)
            
            pages.append({
                'pageNumber': page_num,
                'imageUrl': url,
                'filename': filename,
            })
            print(f"[DEBUG] Processed page {page_num}, image size: {len(image_bytes)} bytes")
        
        print(f"[DEBUG] Returning {len(pages)} pages for visualization")
        return JsonResponse({
            'success': True,
            'sessionId': session_id,
            'totalPages': len(pages),
            'pages': pages,
            'originalFilename': pdf_file.name,
        })
        
    except Exception as e:
        print(f"[ERROR] PDF split failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to split PDF: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_page(request):
    """
    Process a single page: extract data and save to database.
    This handles the AI extraction and document saving.
    """
    try:
        import json
        
        # Parse request data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            print(f"[DEBUG] Received data keys: {list(data.keys())}")
            print(f"[DEBUG] Request data: {data}")
            
            # Handle all field name variations from frontend
            image_url = data.get('imageUrl') or data.get('imageDataUrl')
            document_type = data.get('documentType') 
            page_number = data.get('pageNumber')
            session_id = data.get('sessionId')
            # Handle all filename variations
            original_filename = (data.get('originalFilename') or 
                               data.get('originalFileName') or 
                               data.get('fileName') or 
                               'unknown.pdf')
        else:
            return JsonResponse({'error': 'Invalid content type'}, status=400)
        
        # Validate required fields
        if not image_url:
            return JsonResponse({'error': 'Missing imageUrl field'}, status=400)
        if not document_type:
            return JsonResponse({'error': 'Missing documentType field'}, status=400)  
        if not page_number:
            return JsonResponse({'error': 'Missing pageNumber field'}, status=400)
            
        print(f"[DEBUG] Processed fields: imageUrl='{image_url}', documentType='{document_type}', pageNumber={page_number}, originalFilename='{original_filename}'")
        
        # Get or create processing session
        if session_id and session_id in PROCESSING_SESSIONS:
            session = PROCESSING_SESSIONS[session_id]
        else:
            # Create new session if not exists
            session = ProcessingSession(
                session_id=session_id or str(uuid.uuid4()),
                total_pages=1,
                document_type=document_type,
                filename=original_filename or 'unknown.pdf'
            )
            PROCESSING_SESSIONS[session.session_id] = session
        
        # TODO: Call AI extraction service here
        # For now, return success to test the flow
        # This is where you'd call your AI model/service
        
        # Mock document data (replace with actual AI extraction)
        doc_id = str(uuid.uuid4())
        
        # Create document in database
        Model = get_model_by_type(document_type)
        document_data = {
            'id': doc_id,
            'data': {
                'document_type': document_type,
                'header': {},
                'items': [] if document_type == 'Rebut' else None,
                'downtime_events': [] if document_type == 'NPT' else None,
                'team_summary': {} if document_type == 'Kosu' else None,
            },
            'metadata': {
                'filename': f'{original_filename}_page_{page_number}',
                'document_type': document_type,
                'processed_at': datetime.utcnow().isoformat(),
                'file_size': 0,
                'page_number': page_number,
                'session_id': session.session_id,
            },
            'remark': f'{document_type} extraction pending',
            'imageUrl': image_url,
            'json_url': f'/api/documents/{doc_id}/export?format=json',
            'excel_url': f'/api/documents/{doc_id}/export?format=excel',
            'retry_used': 'no',
        }
        
        try:
            document = Model.create(document_data)
            serialized = serialize_document(document)
            session.add_success(page_number, doc_id)
            
            return JsonResponse({
                'success': True,
                'document': serialized,
                'session': session.to_dict(),
            })
        except Exception as e:
            session.add_error(page_number, str(e))
            raise
            
    except Exception as e:
        print(f"[ERROR] Page processing failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to process page: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_processing_session(request, session_id):
    """Get status of a processing session"""
    try:
        if session_id not in PROCESSING_SESSIONS:
            return JsonResponse({'error': 'Session not found'}, status=404)
        
        session = PROCESSING_SESSIONS[session_id]
        return JsonResponse(session.to_dict())
        
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to get session: {str(e)}'
        }, status=500)


@csrf_exempt  
@require_http_methods(["POST"])
def process_full_pdf(request):
    """
    Complete PDF processing pipeline: Upload → Split → Extract → Save
    This is the all-in-one endpoint that does everything in backend.
    """
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
        
        document_type = request.POST.get('document_type')
        if not document_type or document_type not in ['Rebut', 'NPT', 'Kosu']:
            return JsonResponse({'error': 'Invalid document type'}, status=400)
        
        pdf_file = request.FILES['file']
        session_id = str(uuid.uuid4())
        
        # Step 1: Split PDF
        try:
            from pdf2image import convert_from_bytes
            pdf_content = pdf_file.read()
            images = convert_from_bytes(pdf_content, dpi=200)
        except Exception as e:
            return JsonResponse({
                'error': f'Failed to split PDF: {str(e)}'
            }, status=400)
        
        # Create session
        session = ProcessingSession(
            session_id=session_id,
            total_pages=len(images),
            document_type=document_type,
            filename=pdf_file.name
        )
        PROCESSING_SESSIONS[session_id] = session
        
        # Step 2: Process each page
        documents = []
        for i, image in enumerate(images):
            page_num = i + 1
            
            try:
                # Save image
                filename = f"pdf_pages/{session_id}/page_{page_num}.jpg"
                import io
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG', quality=95)
                img_byte_arr.seek(0)
                path = default_storage.save(filename, ContentFile(img_byte_arr.read()))
                image_url = default_storage.url(path)
                
                # TODO: Extract data using AI here
                # For now, create placeholder document
                
                doc_id = str(uuid.uuid4())
                Model = get_model_by_type(document_type)
                document_data = {
                    'id': doc_id,
                    'data': {
                        'document_type': document_type,
                        'header': {},
                    },
                    'metadata': {
                        'filename': f'{pdf_file.name}_page_{page_num}',
                        'document_type': document_type,
                        'processed_at': datetime.utcnow().isoformat(),
                        'file_size': len(img_byte_arr.getvalue()),
                        'page_number': page_num,
                        'session_id': session_id,
                    },
                    'remark': f'{document_type} extraction pending',
                    'imageUrl': image_url,
                    'json_url': f'/api/documents/{doc_id}/export?format=json',
                    'excel_url': f'/api/documents/{doc_id}/export?format=excel',
                    'retry_used': 'no',
                }
                
                document = Model.create(document_data)
                serialized = serialize_document(document)
                documents.append(serialized)
                session.add_success(page_num, doc_id)
                
            except Exception as e:
                session.add_error(page_num, str(e))
                print(f"[ERROR] Failed to process page {page_num}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'session': session.to_dict(),
            'documents': documents,
        })
        
    except Exception as e:
        print(f"[ERROR] Full PDF processing failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to process PDF: {str(e)}'
        }, status=500)
