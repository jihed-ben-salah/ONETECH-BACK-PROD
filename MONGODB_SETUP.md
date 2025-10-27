# MongoDB Local Setup Guide

This guide explains how to set up a secure local MongoDB instance on your production server to replace MongoDB Atlas.

## Overview

The new setup includes:
- **MongoDB 7.0** running in a Docker container
- **Authentication** enabled for security
- **Persistent volumes** for data storage
- **Automatic initialization** of collections and indexes
- **Network isolation** between services

## Environment Variables

Create or update your `.env` file with the following variables:

\`\`\`bash
# MongoDB Configuration
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=<secure-root-password>
MONGO_APP_USERNAME=onetech_user
MONGO_APP_PASSWORD=<secure-app-password>
MONGODB_DB_NAME=onetech
\`\`\`

## Deployment Steps

### 1. Update Environment Variables on Production Server

\`\`\`bash
ssh admin@10.4.101.154
cd onetech-production
nano .env
\`\`\`

Add the MongoDB variables as shown above.

### 2. Deploy Updated Configuration

\`\`\`bash
./deploy-production.sh
\`\`\`

### 3. Migrate Data from Atlas (if needed)

\`\`\`bash
# Using mongodump/mongorestore
mongodump --uri="<atlas-uri>" --out=./atlas-backup
mongorestore --uri="mongodb://onetech_user:password@localhost:27017/onetech?authSource=admin" ./atlas-backup/onetech
\`\`\`

## Testing

\`\`\`bash
# Check MongoDB logs
docker logs onetech_mongodb

# Test connection
docker exec -it onetech_mongodb mongosh -u admin -p
\`\`\`

## Benefits Over Atlas

- ✅ No connection limits
- ✅ Better performance (local network)
- ✅ No data size restrictions
- ✅ Works offline
- ✅ Full control over data
