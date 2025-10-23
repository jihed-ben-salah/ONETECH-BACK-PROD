"""
Document models for MongoDB operations.
These replace the frontend Mongoose models.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from .mongodb import get_collection


class DocumentModel:
    """Base class for document operations with MongoDB."""
    
    collection_name: str = None  # Override in subclasses
    
    @classmethod
    def get_collection(cls):
        """Get the MongoDB collection for this model."""
        if not cls.collection_name:
            raise NotImplementedError("collection_name must be defined")
        return get_collection(cls.collection_name)
    
    @classmethod
    def create(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new document."""
        collection = cls.get_collection()
        
        # Generate ID if not provided
        if 'id' not in data:
            data['id'] = str(uuid.uuid4())
        
        # Set timestamps
        now = datetime.utcnow()
        data['created_at'] = now
        data['updated_at'] = now
        
        # Initialize tracking fields
        if 'updated_by_user' not in data:
            data['updated_by_user'] = False
        if 'history' not in data:
            data['history'] = []
        if 'verification_status' not in data:
            data['verification_status'] = 'original'
        if 'verification_history' not in data:
            data['verification_history'] = []
        
        # Insert the document
        collection.insert_one(data)
        
        # Remove MongoDB's _id before returning
        if '_id' in data:
            del data['_id']
        
        return data
    
    @classmethod
    def find_by_id(cls, doc_id: str) -> Optional[Dict[str, Any]]:
        """Find a document by its ID."""
        collection = cls.get_collection()
        doc = collection.find_one({'id': doc_id})
        if doc and '_id' in doc:
            del doc['_id']
        return doc
    
    @classmethod
    def find_all(cls, limit: Optional[int] = None, sort_field: str = 'created_at', sort_order: int = -1) -> List[Dict[str, Any]]:
        """Find all documents with optional limit and sorting."""
        collection = cls.get_collection()
        cursor = collection.find().sort(sort_field, sort_order)
        
        if limit:
            cursor = cursor.limit(limit)
        
        docs = list(cursor)
        # Remove MongoDB's _id from all documents
        for doc in docs:
            if '_id' in doc:
                del doc['_id']
        
        return docs
    
    @classmethod
    def update_field(cls, doc_id: str, field: str, old_value: Any, new_value: Any) -> Optional[Dict[str, Any]]:
        """Update a specific field and track the change in history."""
        collection = cls.get_collection()
        
        # Handle nested field paths (e.g., "data.header.ligne" -> {"data.header.ligne": new_value})
        # Convert dot notation to nested dictionary structure
        field_parts = field.split('.')
        if len(field_parts) > 1:
            # Create nested update structure
            nested_update = {}
            current = nested_update
            for part in field_parts[:-1]:
                current[part] = {}
                current = current[part]
            current[field_parts[-1]] = new_value
            
            # Use dot notation for MongoDB update
            update_data = {
                '$set': {
                    field: new_value,
                    'updated_at': datetime.utcnow(),
                    'updated_by_user': True
                },
                '$push': {
                    'history': {
                        'field': field,
                        'old_value': old_value,
                        'new_value': new_value,
                        'updated_at': datetime.utcnow(),
                        'updated_by': 'user'
                    }
                }
            }
        else:
            # Simple field update
            update_data = {
                '$set': {
                    field: new_value,
                    'updated_at': datetime.utcnow(),
                    'updated_by_user': True
                },
                '$push': {
                    'history': {
                        'field': field,
                        'old_value': old_value,
                        'new_value': new_value,
                        'updated_at': datetime.utcnow(),
                        'updated_by': 'user'
                    }
                }
            }
        
        result = collection.find_one_and_update(
            {'id': doc_id},
            update_data,
            return_document=True
        )
        
        if result and '_id' in result:
            del result['_id']
        
        return result
    
    @classmethod
    def update_verification(cls, doc_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update verification status and related fields."""
        collection = cls.get_collection()
        
        update_data = {
            '$set': {
                'updated_at': datetime.utcnow(),
                'verification_status': updates['verification_status']
            },
            '$push': {
                'verification_history': {
                    'status': updates['verification_status'],
                    'timestamp': datetime.utcnow(),
                    'user': updates.get('verified_by', 'user'),
                    'notes': updates.get('verification_notes')
                }
            }
        }
        
        # Add optional fields to $set
        if 'data' in updates:
            update_data['$set']['data'] = updates['data']
            update_data['$set']['updated_by_user'] = True
        
        if 'metadata' in updates:
            update_data['$set']['metadata'] = updates['metadata']
        
        if 'verified_by' in updates:
            update_data['$set']['verified_by'] = updates['verified_by']
        
        if 'verified_at' in updates:
            update_data['$set']['verified_at'] = updates['verified_at']
        
        result = collection.find_one_and_update(
            {'id': doc_id},
            update_data,
            return_document=True
        )
        
        if result and '_id' in result:
            del result['_id']
        
        return result
    
    @classmethod
    def delete(cls, doc_id: str) -> int:
        """Delete a document by ID. Returns count of deleted documents."""
        collection = cls.get_collection()
        result = collection.delete_one({'id': doc_id})
        return result.deleted_count


class RebutModel(DocumentModel):
    """Model for Rebut documents."""
    collection_name = 'rebuts'


class NPTModel(DocumentModel):
    """Model for NPT documents."""
    collection_name = 'npts'


class KosuModel(DocumentModel):
    """Model for Kosu documents."""
    collection_name = 'kosus'


def get_model_by_type(doc_type: str) -> type[DocumentModel]:
    """Get the appropriate model class based on document type."""
    doc_type_lower = doc_type.lower()
    if doc_type_lower == 'rebut':
        return RebutModel
    elif doc_type_lower == 'npt':
        return NPTModel
    elif doc_type_lower == 'kosu':
        return KosuModel
    else:
        raise ValueError(f"Unknown document type: {doc_type}")
