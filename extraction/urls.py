from django.urls import path
from django.http import JsonResponse
from .views import HealthView, ExtractView, SplitPDFView, MediaServeView

def test_export_view(request):
    return JsonResponse({'message': 'Test export endpoint working!', 'params': dict(request.GET)})
from .document_views import (
    DocumentListCreateView,
    DocumentDetailView,
    DocumentExportView,
    BulkDocumentExportView
)
print("[DEBUG] DocumentExportView imported successfully in extraction/urls.py")
from .processing_views import (
    split_pdf,
    process_page,
    get_processing_session,
    process_full_pdf
)
from .batch_processing_views import (
    start_batch_processing,
    get_batch_status,
    cancel_batch_processing,
    list_batch_sessions,
    cleanup_batch_sessions
)

urlpatterns = [
    path('', HealthView.as_view()),
    path('health/', HealthView.as_view()),
    path('extract/', ExtractView.as_view()),
    path('split-pdf/', SplitPDFView.as_view()),
    path('media/<path:path>', MediaServeView.as_view(), name='media-serve'),
    
    # Document management endpoints
    path('documents/', DocumentListCreateView.as_view(), name='document-list-create'),
        path('export-documents/', DocumentExportView.as_view(), name='export-documents'),
    path('test-export/', test_export_view, name='test-export'),
    path('documents/export-bulk/', BulkDocumentExportView.as_view(), name='document-export-bulk'),
    path('documents/<str:doc_id>/', DocumentDetailView.as_view(), name='document-detail'),
    
    # Complete PDF processing pipeline endpoints
    path('processing/split-pdf/', split_pdf, name='processing-split-pdf'),
    path('processing/process-page/', process_page, name='processing-process-page'),
    path('processing/session/<str:session_id>/', get_processing_session, name='processing-session'),
    path('processing/full-pdf/', process_full_pdf, name='processing-full-pdf'),
    
    # Batch processing endpoints (recommended)
    path('batch/start/', start_batch_processing, name='batch-start'),
    path('batch/status/<str:session_id>/', get_batch_status, name='batch-status'),
    path('batch/cancel/<str:session_id>/', cancel_batch_processing, name='batch-cancel'),
    path('batch/sessions/', list_batch_sessions, name='batch-sessions'),
    path('batch/cleanup/', cleanup_batch_sessions, name='batch-cleanup'),
]
