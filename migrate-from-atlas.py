#!/usr/bin/env python3
"""
MongoDB Migration Script
Migrates data from MongoDB Atlas to local MongoDB instance
"""
import os
import sys
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def migrate_database():
    """Migrate data from Atlas to local MongoDB"""
    
    # Source (Atlas) and destination (local) URIs
    atlas_uri = os.getenv('MONGODB_ATLAS_URI', input("Enter Atlas URI: "))
    local_uri = os.getenv('MONGODB_LOCAL_URI', 'mongodb://onetech_user:onetech_secure_password@localhost:29991/onetech?authSource=admin')
    db_name = os.getenv('MONGODB_DB_NAME', 'onetech')
    
    if not atlas_uri:
        print("ERROR: MongoDB Atlas URI is required")
        sys.exit(1)
    
    print("=" * 60)
    print("MongoDB Migration: Atlas → Local")
    print("=" * 60)
    
    try:
        # Connect to source (Atlas)
        print("\n[1/5] Connecting to MongoDB Atlas...")
        atlas_client = MongoClient(atlas_uri)
        atlas_db = atlas_client[db_name]
        print("✓ Connected to Atlas")
        
        # Connect to destination (local)
        print("\n[2/5] Connecting to local MongoDB...")
        local_client = MongoClient(local_uri)
        local_db = local_client[db_name]
        print("✓ Connected to local MongoDB")
        
        # Get list of collections
        print("\n[3/5] Discovering collections...")
        collections = ['rebuts', 'npts', 'kosus']
        
        total_documents = 0
        
        # Migrate each collection
        for collection_name in collections:
            atlas_collection = atlas_db[collection_name]
            local_collection = local_db[collection_name]
            
            # Count documents
            doc_count = atlas_collection.count_documents({})
            print(f"\n  Collection: {collection_name}")
            print(f"  Documents to migrate: {doc_count}")
            
            if doc_count == 0:
                print(f"  ⚠ No documents to migrate")
                continue
            
            # Clear existing data (optional - comment out if you want to merge)
            local_collection.delete_many({})
            
            # Migrate documents in batches
            batch_size = 1000
            migrated = 0
            
            cursor = atlas_collection.find({})
            batch = []
            
            for doc in cursor:
                batch.append(doc)
                
                if len(batch) >= batch_size:
                    local_collection.insert_many(batch)
                    migrated += len(batch)
                    print(f"  Migrated: {migrated}/{doc_count} documents", end='\r')
                    batch = []
            
            # Insert remaining documents
            if batch:
                local_collection.insert_many(batch)
                migrated += len(batch)
            
            print(f"  ✓ Migrated: {migrated}/{doc_count} documents")
            total_documents += migrated
        
        # Verify migration
        print("\n[4/5] Verifying migration...")
        for collection_name in collections:
            atlas_count = atlas_db[collection_name].count_documents({})
            local_count = local_db[collection_name].count_documents({})
            
            if atlas_count == local_count:
                print(f"  ✓ {collection_name}: {local_count} documents")
            else:
                print(f"  ⚠ {collection_name}: Atlas={atlas_count}, Local={local_count}")
        
        # Create migration record
        print("\n[5/5] Recording migration...")
        migration_record = {
            'migration_date': datetime.utcnow(),
            'from': 'MongoDB Atlas',
            'to': 'Local MongoDB',
            'total_documents': total_documents,
            'collections': collections
        }
        local_db.migration_log.insert_one(migration_record)
        
        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print(f"Total documents migrated: {total_documents}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nERROR: Migration failed: {str(e)}")
        sys.exit(1)
    
    finally:
        # Close connections
        if 'atlas_client' in locals():
            atlas_client.close()
        if 'local_client' in locals():
            local_client.close()
        print("\n✓ Connections closed")

if __name__ == '__main__':
    migrate_database()
