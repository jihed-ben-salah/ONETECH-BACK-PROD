#!/bin/bash
# MongoDB security configuration script
# This script sets up additional security measures for MongoDB

echo "Setting up MongoDB security configuration..."

# Create MongoDB configuration directory
mkdir -p /data/configdb

# Create mongod.conf with security settings
cat > /data/configdb/mongod.conf << EOF
# MongoDB Configuration File
# Security settings
security:
  authorization: enabled

# Network settings
net:
  port: 27017
  bindIpAll: true

# Storage settings
storage:
  dbPath: /data/db
  journal:
    enabled: true

# Logging
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log

# Process management
processManagement:
  fork: false
  pidFilePath: /var/run/mongodb/mongod.pid

# Set parameters for better performance
setParameter:
  enableLocalhostAuthBypass: false
EOF

echo "MongoDB security configuration completed"

