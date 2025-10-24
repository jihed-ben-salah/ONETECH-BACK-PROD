"""
Simple in-memory session storage for batch processing.
This will be replaced with database-backed storage for production persistence.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading

class SessionStorage:
    """Thread-safe in-memory session storage"""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def create_session(self, session_data: Dict[str, Any]) -> None:
        """Create a new session"""
        with self._lock:
            session_id = session_data['session_id']
            self._sessions[session_id] = {
                **session_data,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            }
            print(f"[DEBUG] Session {session_id} created in storage")
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                print(f"[DEBUG] Session {session_id} retrieved from storage")
            return session
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session fields"""
        with self._lock:
            if session_id not in self._sessions:
                print(f"[ERROR] Session {session_id} not found for update")
                return False
            
            self._sessions[session_id].update(updates)
            self._sessions[session_id]['updated_at'] = datetime.utcnow()
            print(f"[DEBUG] Session {session_id} updated: {list(updates.keys())}")
            return True
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session status (same as get_session for now)"""
        return self.get_session(session_id)
    
    def set_processing_page(self, session_id: str, page_num: int) -> None:
        """Set currently processing page"""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]['processing_page'] = page_num
                self._sessions[session_id]['updated_at'] = datetime.utcnow()
    
    def add_success(self, session_id: str, page_num: int, doc_id: str, extraction_data: Dict[str, Any]) -> None:
        """Record successful page processing"""
        with self._lock:
            if session_id not in self._sessions:
                return
            
            session = self._sessions[session_id]
            
            # Update counters
            session['completed_pages'] = session.get('completed_pages', 0) + 1
            session['processing_page'] = None
            session['updated_at'] = datetime.utcnow()
            
            # Store document info
            if 'documents' not in session:
                session['documents'] = []
            
            session['documents'].append({
                'page': page_num,
                'id': doc_id,
                'extraction_confidence': extraction_data.get('extraction_confidence'),
                'final_confidence': extraction_data.get('final_confidence'),
            })
            
            # Update status if all pages are processed
            total_processed = session['completed_pages'] + session.get('failed_pages', 0)
            if total_processed >= session['total_pages']:
                session['status'] = 'completed'
            
            print(f"[DEBUG] Session {session_id}: Page {page_num} marked as success")
    
    def add_error(self, session_id: str, page_num: int, error: str) -> None:
        """Record failed page processing"""
        with self._lock:
            if session_id not in self._sessions:
                return
            
            session = self._sessions[session_id]
            
            # Update counters
            session['failed_pages'] = session.get('failed_pages', 0) + 1
            session['processing_page'] = None
            session['updated_at'] = datetime.utcnow()
            
            # Store error info
            if 'errors' not in session:
                session['errors'] = []
            
            session['errors'].append({
                'page': page_num,
                'error': str(error),
                'timestamp': datetime.utcnow().isoformat()
            })
            
            # Update status if all pages are processed
            total_processed = session.get('completed_pages', 0) + session['failed_pages']
            if total_processed >= session['total_pages']:
                if session.get('completed_pages', 0) > 0:
                    session['status'] = 'completed'
                else:
                    session['status'] = 'failed'
            
            print(f"[DEBUG] Session {session_id}: Page {page_num} marked as failed: {error}")
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions, sorted by creation time"""
        with self._lock:
            sessions = list(self._sessions.values())
            sessions.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
            return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                print(f"[DEBUG] Session {session_id} deleted from storage")
                return True
            return False
    
    def cleanup_old_sessions(self, hours: int = 24) -> int:
        """Clean up sessions older than specified hours"""
        with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            to_delete = []
            
            for session_id, session in self._sessions.items():
                created_at = session.get('created_at', datetime.min)
                if created_at < cutoff_time and session.get('status') in ['completed', 'failed']:
                    to_delete.append(session_id)
            
            for session_id in to_delete:
                del self._sessions[session_id]
            
            print(f"[DEBUG] Cleaned up {len(to_delete)} old sessions")
            return len(to_delete)

# Global singleton instance
session_storage = SessionStorage()

