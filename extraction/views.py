import io
import os
import tempfile
from typing import Any, Dict
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

        # Save to temp file for existing extraction function
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                for chunk in up_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            
            # Verify the file was written correctly
            if not os.path.exists(tmp_path):
                return Response({
                    'status': 'error', 
                    'message': 'Failed to create temporary file'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            if os.path.getsize(tmp_path) == 0:
                return Response({
                    'status': 'error', 
                    'message': 'Temporary file is empty'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as file_error:
            return Response({
                'status': 'error', 
                'message': f'Failed to process uploaded file: {str(file_error)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # Configure API key each call (idempotent) if available
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

            # Call underlying extraction
            print(f"[DEBUG] Starting extraction for {document_type} with file {tmp_path}")
            wrapper: Dict[str, Any] = extract_data_from_image(tmp_path, doc_type=document_type)
            print(f"[DEBUG] Extraction completed. Result: {wrapper}")
            
            if not wrapper:
                return Response({'status': 'error', 'message': 'Empty extraction result (model returned nothing or parsing failed).'}, status=status.HTTP_502_BAD_GATEWAY)

            # Unwrap if nested {"data": {...}, "remark": "..."}
            inner = wrapper.get('data') if isinstance(wrapper, dict) else None
            remark = wrapper.get('remark') if isinstance(wrapper, dict) else None
            if inner is None:
                inner = wrapper  # fall back to raw

            processed = post_process_payload(inner)
            resp_payload = {'status': 'success', 'data': processed}
            if remark:
                resp_payload['remark'] = remark
            print(f"[DEBUG] Returning response: {resp_payload}")
            return Response(resp_payload)
        except Exception as e:
            print(f"[ERROR] Exception in extraction: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
