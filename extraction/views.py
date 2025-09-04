import io
import os
import tempfile
from typing import Any, Dict
import google.generativeai as genai

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

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

class ExtractView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        serializer = ExtractionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize document_type (case-insensitive, accept variants like defauts)
        raw_type = serializer.validated_data['document_type'].strip()
        lowered = raw_type.lower()
        doc_type_map = {
            'rebut': 'Rebut',
            'kosu': 'Kosu',
            'npt': 'NPT',
            'défauts': 'Défauts',
            'defauts': 'Défauts',
            'defauts_ascii': 'Défauts'
        }
        document_type = doc_type_map.get(lowered, raw_type)
        up_file = serializer.validated_data['file']

        # Save to temp file for existing extraction function
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            for chunk in up_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            # Configure API key each call (idempotent) if available
            api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                except Exception:
                    pass

            # Call underlying extraction
            wrapper: Dict[str, Any] = extract_data_from_image(tmp_path, doc_type=document_type)
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
            return Response(resp_payload)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
