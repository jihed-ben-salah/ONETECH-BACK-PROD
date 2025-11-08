// MongoDB initialization script for OneTech application
// This script runs when MongoDB container starts for the first time

// Switch to the application database
db = db.getSiblingDB(process.env.MONGO_INITDB_DATABASE || 'onetech');

// Create application user with read/write permissions
db.createUser({
  user: process.env.MONGO_APP_USERNAME || 'onetech_user',
  pwd: process.env.MONGO_APP_PASSWORD || 'onetech_secure_password',
  roles: [
    {
      role: 'readWrite',
      db: process.env.MONGO_INITDB_DATABASE || 'onetech'
    }
  ]
});

// Create collections with proper indexes for performance
const collections = ['rebuts', 'npts', 'kosus'];

collections.forEach(collectionName => {
  // Create collection if it doesn't exist
  db.createCollection(collectionName);
  
  // Create indexes for better performance
  db[collectionName].createIndex({ "id": 1 }, { unique: true });
  db[collectionName].createIndex({ "created_at": -1 });
  db[collectionName].createIndex({ "updated_at": -1 });
  db[collectionName].createIndex({ "metadata.document_type": 1 });
  db[collectionName].createIndex({ "verification_status": 1 });
  
  print(`Created collection '${collectionName}' with indexes`);
});

// Create a system info collection to track migrations
db.createCollection('system_info');
db.system_info.insertOne({
  _id: 'migration_info',
  version: '1.0.0',
  migrated_from_atlas: false,
  created_at: new Date(),
  updated_at: new Date()
});

print('MongoDB initialization completed successfully');



