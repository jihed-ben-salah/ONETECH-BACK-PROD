"""
Document management views - REST API for document CRUD operations.
All database operations happen here in the backend.
"""
import csv
import io
import json
from datetime import datetime
from bson import ObjectId
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .document_models import get_model_by_type


def serialize_document(doc):
    """Convert datetime and ObjectId objects to JSON serializable formats."""
    if not doc:
        return doc
    
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = serialize_document(value)
        elif isinstance(value, list):
            serialized[key] = [serialize_document(item) if isinstance(item, dict) else item for item in value]
        else:
            serialized[key] = value
    return serialized


@method_decorator(csrf_exempt, name='dispatch')
class DocumentListCreateView(APIView):
    """
    GET: List all documents of a specific type
    POST: Create a new document
    """
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        """Get list of documents filtered by type."""
        doc_type = request.query_params.get('type')
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type. Must be one of: Rebut, NPT, Kosu'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            documents = Model.find_all()
            # Serialize datetime objects to strings
            serialized_docs = [serialize_document(doc) for doc in documents]
            return Response(serialized_docs, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"[ERROR] Failed to fetch documents: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to fetch documents: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Create a new document."""
        data = request.data
        
        # Extract document type from metadata or data
        doc_type = None
        if 'metadata' in data and 'document_type' in data['metadata']:
            doc_type = data['metadata']['document_type']
        elif 'data' in data and 'document_type' in data['data']:
            doc_type = data['data']['document_type']
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type in metadata or data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            document = Model.create(data)
            # Serialize datetime objects to strings
            serialized_doc = serialize_document(document)
            return Response(serialized_doc, status=status.HTTP_201_CREATED)
        except Exception as e:
            print(f"[ERROR] Failed to create document: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to create document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class DocumentDetailView(APIView):
    """
    GET: Retrieve a single document by ID
    PUT: Update a document
    DELETE: Delete a document
    """
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, doc_id):
        """Get a single document by ID."""
        doc_type = request.query_params.get('type')
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            document = Model.find_by_id(doc_id)
            
            if not document:
                return Response(
                    {'error': 'Document not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Serialize datetime objects to strings
            serialized_doc = serialize_document(document)
            return Response(serialized_doc, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"[ERROR] Failed to fetch document: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to fetch document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, doc_id):
        """Update a document."""
        doc_type = request.data.get('type')
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            
            # Check if this is a verification update or field update
            if 'verification_status' in request.data:
                # Verification update
                updates = {
                    'verification_status': request.data['verification_status'],
                    'verified_by': request.data.get('verified_by'),
                    'verified_at': request.data.get('verified_at'),
                    'verification_notes': request.data.get('verification_notes'),
                    'data': request.data.get('data'),
                    'metadata': request.data.get('metadata')
                }
                document = Model.update_verification(doc_id, updates)
            else:
                # Field update
                field = request.data.get('field')
                old_value = request.data.get('oldValue')
                new_value = request.data.get('newValue')
                
                if not field:
                    return Response(
                        {'error': 'Field name is required for field updates'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                document = Model.update_field(doc_id, field, old_value, new_value)
            
            if not document:
                return Response(
                    {'error': 'Document not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Serialize datetime objects to strings
            serialized_doc = serialize_document(document)
            return Response(serialized_doc, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"[ERROR] Failed to update document: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to update document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, doc_id):
        """Delete a document."""
        doc_type = request.query_params.get('type')
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            deleted_count = Model.delete(doc_id)
            
            if deleted_count == 0:
                return Response(
                    {'error': 'Document not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response(
                {'message': 'Document deleted successfully'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            print(f"[ERROR] Failed to delete document: {str(e)}")
            return Response(
                {'error': f'Failed to delete document: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class DocumentExportView(APIView):
    """Export documents to CSV or JSON format."""
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        """Export documents in CSV or JSON format."""
        doc_type_param = request.query_params.get('type')
        export_format = (request.query_params.get('format') or 'csv').lower()

        allowed_types = {'rebut': 'Rebut', 'npt': 'NPT', 'kosu': 'Kosu'}

        if not doc_type_param:
            return Response(
                {'error': 'Document type is required. Allowed values: Rebut, NPT, Kosu'},
                status=status.HTTP_400_BAD_REQUEST
            )

        doc_type_key = doc_type_param.strip().lower()
        if doc_type_key not in allowed_types:
            return Response(
                {'error': f'Invalid document type "{doc_type_param}". Allowed values: Rebut, NPT, Kosu'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if export_format not in ['csv', 'json']:
            return Response(
                {'error': f'Invalid export format "{export_format}". Allowed values: csv, json'},
                status=status.HTTP_400_BAD_REQUEST
            )

        canonical_doc_type = allowed_types[doc_type_key]

        try:
            Model = get_model_by_type(canonical_doc_type)
            documents = Model.find_all()
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"[ERROR] Failed to fetch documents for export: {str(e)}")
            return Response(
                {'error': f'Failed to fetch documents for export: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        if export_format == 'json':
            serialized_docs = [serialize_document(doc) for doc in documents]
            response = HttpResponse(
                json.dumps(serialized_docs, indent=2),
                content_type='application/json'
            )
            response['Content-Disposition'] = (
                f'attachment; filename="{canonical_doc_type.lower()}_export_{timestamp}.json"'
            )
            response['X-Export-Count'] = str(len(serialized_docs))
            return response

        csv_content = self._generate_csv(documents, canonical_doc_type)
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="{canonical_doc_type.lower()}_export_{timestamp}.csv"'
        )
        response['X-Export-Count'] = str(len(documents))
        return response

    def _generate_csv(self, documents, doc_type):
        """Generate CSV content from documents."""
        documents = documents or []
        doc_type_key = (doc_type or '').lower()
        output = io.StringIO()
        writer = csv.writer(output)

        # Generate CSV based on document type
        if doc_type_key == 'rebut':
            writer.writerow([
                'Document ID', 'Date', 'Ligne', 'OF Number', 'Item Index',
                'Reference', 'Designation', 'Quantity', 'Unit', 'Type', 'Total Scrapped'
            ])
            
            for doc in documents:
                data = doc.get('data', {})
                header = data.get('header', {})
                items = data.get('items', [])
                
                for idx, item in enumerate(items):
                    writer.writerow([
                        doc.get('id', ''),
                        header.get('date', ''),
                        header.get('ligne', ''),
                        header.get('of_number', ''),
                        idx,
                        item.get('reference', ''),
                        item.get('designation', ''),
                        item.get('quantity', ''),
                        item.get('unit', ''),
                        item.get('type', ''),
                        item.get('total_scrapped', '')
                    ])
        
        elif doc_type_key == 'npt':
            writer.writerow([
                'Document ID', 'Date', 'UAP', 'Equipe', 'Event Index',
                'Codes Ligne', 'Ref PF', 'Designation', 'NPT Minutes',
                'Heure Debut', 'Heure Fin', 'Cause NPT'
            ])
            
            for doc in documents:
                data = doc.get('data', {})
                header = data.get('header', {})
                events = data.get('downtime_events', [])
                
                for idx, event in enumerate(events):
                    writer.writerow([
                        doc.get('id', ''),
                        header.get('date', ''),
                        header.get('uap', ''),
                        header.get('equipe', ''),
                        idx,
                        event.get('codes_ligne', ''),
                        event.get('ref_pf', ''),
                        event.get('designation', ''),
                        event.get('npt_minutes', ''),
                        event.get('heure_debut_d_arret', ''),
                        event.get('heure_fin_d_arret', ''),
                        event.get('cause_npt', '')
                    ])
        
        elif doc_type_key == 'kosu':
            writer.writerow([
                'Document ID', 'Date', 'Nom Ligne', 'Code Ligne', 'Numero OF',
                'Ref PF', 'Heures Deposees', 'Objectif Qte EQ', 'Qte Realisee'
            ])
            
            for doc in documents:
                data = doc.get('data', {})
                header = data.get('header', {})
                team_summary = data.get('team_summary', {})
                
                writer.writerow([
                    doc.get('id', ''),
                    header.get('date', ''),
                    header.get('nom_ligne', ''),
                    header.get('code_ligne', ''),
                    header.get('numero_of', ''),
                    header.get('ref_pf', ''),
                    team_summary.get('heures_deposees', ''),
                    team_summary.get('objectif_qte_eq', ''),
                    team_summary.get('qte_realisee', '')
                ])
        else:
            writer.writerow(['Document ID'])
            for doc in documents:
                writer.writerow([doc.get('id', '')])

        return output.getvalue()


@method_decorator(csrf_exempt, name='dispatch')
class BulkDocumentExportView(APIView):
    """Export multiple documents by IDs."""
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        """Export multiple documents."""
        doc_type = request.data.get('type')
        doc_ids = request.data.get('ids', [])
        export_format = (request.data.get('format') or 'csv').lower()
        
        if not doc_type or doc_type not in ['Rebut', 'NPT', 'Kosu']:
            return Response(
                {'error': 'Invalid or missing document type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not doc_ids or not isinstance(doc_ids, list):
            return Response(
                {'error': 'Invalid or missing document IDs'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            Model = get_model_by_type(doc_type)
            documents = [Model.find_by_id(doc_id) for doc_id in doc_ids]
            documents = [doc for doc in documents if doc is not None]
            
            if export_format == 'json':
                serialized_docs = [serialize_document(doc) for doc in documents]
                response = HttpResponse(
                    json.dumps(serialized_docs, indent=2),
                    content_type='application/json'
                )
                response['Content-Disposition'] = f'attachment; filename="{doc_type.lower()}_bulk_export.json"'
                response['X-Export-Count'] = str(len(serialized_docs))
                return response

            # Use the same CSV generation as single export
            export_view = DocumentExportView()
            csv_content = export_view._generate_csv(documents, doc_type)
            response = HttpResponse(csv_content, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{doc_type.lower()}_bulk_export.csv"'
            response['X-Export-Count'] = str(len(documents))
            return response
                
        except Exception as e:
            print(f"[ERROR] Failed to export documents: {str(e)}")
            return Response(
                {'error': f'Failed to export documents: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
