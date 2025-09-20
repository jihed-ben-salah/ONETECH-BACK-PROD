import io
import os
import tempfile
import base64
from typing import Any, Dict, List
import google.generativeai as genai

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

# Reuse existing extraction logic from parent project
try:
    from process_forms import extract_data_from_image
except Exception:
    from ..process_forms import extract_data_from_image  # type: ignore

from .serializers import ExtractionRequestSerializer
from .utils import post_process_payload
from .image_storage import save_uploaded_image, save_image_from_bytes
from .pdf_utils import (
    is_pdf_file, 
    split_pdf_to_images, 
    convert_single_page_pdf_to_image, 
    save_image_to_temp_file,
    get_pdf_page_count,
    cleanup_temp_file
)

MODEL_NAME = os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')

class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({'status': 'ok', 'model': MODEL_NAME})

@method_decorator(csrf_exempt, name='dispatch')
class ExtractView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        print(f"[DEBUG] Received request with data keys: {list(request.data.keys())}")
        
        serializer = ExtractionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            print(f"[ERROR] Serializer validation failed: {serializer.errors}")
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize document_type (case-insensitive, accept variants like defauts)
        raw_type = serializer.validated_data['document_type'].strip()
        lowered = raw_type.lower()
        print(f"[DEBUG] Document type: '{raw_type}' -> '{lowered}'")
        
        doc_type_map = {
            'rebut': 'Rebut',
            'kosu': 'Kosu', 
            'npt': 'NPT',
            'défauts': 'Défauts',
            'defauts': 'Défauts',
            'defauts_ascii': 'Défauts'
        }
        document_type = doc_type_map.get(lowered, raw_type)
        print(f"[DEBUG] Final document type: '{document_type}'")
        
        up_file = serializer.validated_data['file']
        print(f"[DEBUG] File info: name='{up_file.name}', size={up_file.size}, content_type='{up_file.content_type}'")

        # Read file content
        try:
            file_content = up_file.read()
            up_file.seek(0)  # Reset file pointer
        except Exception as e:
            return Response({
                'status': 'error', 
                'message': f'Failed to read uploaded file: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check if it's a PDF file
        is_pdf = is_pdf_file(file_content)
        print(f"[DEBUG] Is PDF file: {is_pdf}")

        # Configure API key
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
        print(f"[DEBUG] API key status: {'found' if api_key else 'missing'}")
        if not api_key:
            print("[ERROR] Google API key not configured")
            return Response({
                'status': 'error', 
                'message': 'Google API key not configured'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        try:
            genai.configure(api_key=api_key)
            print("[DEBUG] Google AI configured successfully")
        except Exception as config_error:
            print(f"[ERROR] Failed to configure Google AI: {config_error}")
            return Response({
                'status': 'error', 
                'message': f'Failed to configure Google AI: {str(config_error)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if is_pdf:
            return self._handle_pdf_extraction(file_content, document_type, up_file.name)
        else:
            return self._handle_image_extraction(file_content, document_type, up_file.name)

    def _handle_image_extraction(self, file_content: bytes, document_type: str, filename: str):
        """Handle extraction from a single image file."""
        tmp_path = None
        try:
            # Save the uploaded image to media directory
            image_url = save_uploaded_image(file_content, filename)
            if not image_url:
                print("[WARNING] Failed to save uploaded image")
            
            # Save to temp file for existing extraction function
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            
            # Verify the file was written correctly
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                return Response({
                    'status': 'error', 
                    'message': 'Failed to create temporary file'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Call extraction
            print(f"[DEBUG] Starting extraction for {document_type} with file {tmp_path}")
            wrapper: Dict[str, Any] = extract_data_from_image(tmp_path, doc_type=document_type)
            print(f"[DEBUG] Extraction completed. Result: {wrapper}")
            
            if not wrapper:
                return Response({'status': 'error', 'message': 'Empty extraction result'}, status=status.HTTP_502_BAD_GATEWAY)

            # Process result
            inner = wrapper.get('data') if isinstance(wrapper, dict) else wrapper
            remark = wrapper.get('remark') if isinstance(wrapper, dict) else None
            
            processed = post_process_payload(inner)
            resp_payload = {'status': 'success', 'data': processed}
            if remark:
                resp_payload['remark'] = remark
            
            # Add image URL to response if successfully saved
            if image_url:
                resp_payload['imageUrl'] = image_url
            
            print(f"[DEBUG] Returning response: {resp_payload}")
            return Response(resp_payload)
            
        except Exception as e:
            print(f"[ERROR] Exception in extraction: {type(e).__name__}: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            print(f"[ERROR] Exception in extraction: {type(e).__name__}: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _handle_pdf_extraction(self, file_content: bytes, document_type: str, filename: str):
        """Handle extraction from PDF file (single or multi-page)."""
        try:
            # Get page count first
            page_count = get_pdf_page_count(file_content)
            print(f"[DEBUG] PDF has {page_count} pages")
            
            if page_count == 1:
                # Single page PDF - convert to image and process normally
                print("[DEBUG] Processing single-page PDF")
                image_bytes = convert_single_page_pdf_to_image(file_content)
                return self._handle_image_extraction(image_bytes, document_type, filename)
            else:
                # Multi-page PDF - split and process each page
                print(f"[DEBUG] Processing multi-page PDF with {page_count} pages")
                return self._handle_multipage_pdf_extraction(file_content, document_type, filename, page_count)
                
        except Exception as e:
            print(f"[ERROR] Exception in PDF processing: {type(e).__name__}: {str(e)}")
            return Response({
                'status': 'error', 
                'message': f'Failed to process PDF: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_multipage_pdf_extraction(self, file_content: bytes, document_type: str, filename: str, page_count: int):
        """Handle extraction from multi-page PDF."""
        try:
            # Split PDF into individual page images
            pages = split_pdf_to_images(file_content)
            
            results = []
            errors = []
            
            for page_num, image_bytes in pages:
                print(f"[DEBUG] Processing page {page_num}/{page_count}")
                
                tmp_path = None
                try:
                    # Save the page image to media directory
                    page_image_url = save_image_from_bytes(image_bytes, f"{filename}_page_{page_num}")
                    if not page_image_url:
                        print(f"[WARNING] Failed to save image for page {page_num}")
                    
                    # Save page image to temp file
                    tmp_path = save_image_to_temp_file(image_bytes, suffix='.jpg')
                    
                    # Extract data from this page
                    wrapper: Dict[str, Any] = extract_data_from_image(tmp_path, doc_type=document_type)
                    
                    if wrapper:
                        # Process result
                        inner = wrapper.get('data') if isinstance(wrapper, dict) else wrapper
                        remark = wrapper.get('remark') if isinstance(wrapper, dict) else None
                        
                        processed = post_process_payload(inner)
                        
                        # Create page-specific document
                        page_result = {
                            'page_number': page_num,
                            'data': processed,
                            'remark': remark or f'{document_type} extraction complete - Page {page_num}',
                            'metadata': {
                                'filename': f"{filename}_page_{page_num}",
                                'document_type': document_type,
                                'original_filename': filename,
                                'page_number': page_num,
                                'total_pages': page_count,
                                'is_multi_page': True
                            }
                        }
                        
                        # Add image URL if successfully saved
                        if page_image_url:
                            page_result['imageUrl'] = page_image_url
                        
                        results.append(page_result)
                        print(f"[DEBUG] Successfully processed page {page_num}")
                    else:
                        error = {
                            'page_number': page_num,
                            'error': 'Empty extraction result',
                            'filename': f"{filename}_page_{page_num}"
                        }
                        errors.append(error)
                        print(f"[ERROR] Failed to process page {page_num}: Empty result")
                        
                except Exception as e:
                    error = {
                        'page_number': page_num,
                        'error': str(e),
                        'filename': f"{filename}_page_{page_num}"
                    }
                    errors.append(error)
                    print(f"[ERROR] Failed to process page {page_num}: {str(e)}")
                finally:
                    if tmp_path:
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass

            # Return comprehensive results
            response = {
                'status': 'success',
                'totalPages': page_count,
                'processedSuccessfully': len(results),
                'errors': len(errors),
                'results': results,
                'failedPages': errors,
                'originalFileName': filename,
                'message': f'Processed {len(results)} out of {page_count} pages successfully'
            }
            
            if len(results) == 0:
                response['status'] = 'error'
                response['message'] = 'Failed to process any pages'
                return Response(response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response(response)
            
        except Exception as e:
            print(f"[ERROR] Exception in multi-page PDF processing: {type(e).__name__}: {str(e)}")
            return Response({
                'status': 'error', 
                'message': f'Failed to process multi-page PDF: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class SplitPDFView(APIView):
    """Split PDF into pages and return images with base64 encoding for visualization.
    Updated: 2025-09-13 - Using PyMuPDF for cloud-ready PDF processing."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        print(f"[DEBUG] PDF Split request received with data keys: {list(request.data.keys())}")
        
        # Get the uploaded file
        if 'file' not in request.FILES:
            return Response({
                'error': 'No file uploaded'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        uploaded_file = request.FILES['file']
        print(f"[DEBUG] File info: name='{uploaded_file.name}', size={uploaded_file.size}, content_type='{uploaded_file.content_type}'")

        try:
            # Read file content
            file_content = uploaded_file.read()
            uploaded_file.seek(0)  # Reset file pointer
            
            # Check if it's a PDF file
            if not is_pdf_file(file_content):
                return Response({
                    'error': 'File is not a PDF'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get page count
            page_count = get_pdf_page_count(file_content)
            print(f"[DEBUG] PDF has {page_count} pages")
            
            if page_count == 1:
                # Single page PDF - convert to image
                image_bytes = convert_single_page_pdf_to_image(file_content)
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                
                page_data = [{
                    'pageNumber': 1,
                    'fileName': f"{uploaded_file.name.rsplit('.', 1)[0]}-page-1.jpg",
                    'mimeType': 'image/jpeg',
                    'imageDataUrl': f"data:image/jpeg;base64,{base64_image}",
                    'bufferSize': len(image_bytes),
                    'status': 'pending',
                    'extractedData': None,
                    'error': None
                }]
            else:
                # Multi-page PDF - split into images
                pages = split_pdf_to_images(file_content)
                page_data = []
                
                for page_num, image_bytes in pages:
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    page_info = {
                        'pageNumber': page_num,
                        'fileName': f"{uploaded_file.name.rsplit('.', 1)[0]}-page-{page_num}.jpg",
                        'mimeType': 'image/jpeg',
                        'imageDataUrl': f"data:image/jpeg;base64,{base64_image}",
                        'bufferSize': len(image_bytes),
                        'status': 'pending',
                        'extractedData': None,
                        'error': None
                    }
                    page_data.append(page_info)
                    print(f"[DEBUG] Processed page {page_num}, image size: {len(image_bytes)} bytes")
            
            response = {
                'success': True,
                'originalFileName': uploaded_file.name,
                'totalPages': page_count,
                'pages': page_data
            }
            
            print(f"[DEBUG] Returning {len(page_data)} pages for visualization")
            return Response(response)
            
        except Exception as e:
            print(f"[ERROR] Exception in PDF splitting: {type(e).__name__}: {str(e)}")
            return Response({
                'error': f'Failed to process PDF: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
