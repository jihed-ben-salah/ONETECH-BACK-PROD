"""
MongoDB connection and utilities for document storage.
All database operations should go through this module.
"""
import os
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from django.conf import settings

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_mongodb_client() -> MongoClient:
    """Get or create MongoDB client singleton."""
    global _client
    if _client is None:
        mongodb_uri = settings.MONGODB_URI
        if not mongodb_uri:
            raise ValueError("MONGODB_URI is not configured in settings")
        _client = MongoClient(mongodb_uri)
    return _client


def get_database() -> Database:
    """Get or create MongoDB database singleton."""
    global _db
    if _db is None:
        client = get_mongodb_client()
        db_name = settings.MONGODB_DB_NAME
        _db = client[db_name]
    return _db


def get_collection(collection_name: str) -> Collection:
    """Get a MongoDB collection by name."""
    db = get_database()
    return db[collection_name]


def close_connection():
    """Close MongoDB connection. Call this on application shutdown."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
