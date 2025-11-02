# MongoDB Atlas Connection with LibreSSL

## Issue
Your system uses LibreSSL 2.8.3, which has a known compatibility issue with MongoDB Atlas TLS connections. This causes SSL handshake failures with errors like:
```
SSL handshake failed: [SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error
```

## Current Configuration
- **Connection String**: `mongodb+srv://Onetech:elepzia1235@cluster0.5mo88wt.mongodb.net/onetech?appName=Cluster0`
- **Database**: `onetech`
- **SSL Configuration**: `tlsAllowInvalidCertificates=True`, `ssl_cert_reqs=ssl.CERT_NONE`

## Solutions

### Option 1: Use Python with OpenSSL (Recommended)
Install Python using Homebrew, which uses OpenSSL:
```bash
brew install python@3.11
# Create new virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Option 2: Update LibreSSL
Update your system's LibreSSL to a newer version that may have better compatibility.

### Option 3: Use Local MongoDB
Switch to the local MongoDB instance which doesn't require SSL/TLS:
```
MONGODB_URI=mongodb://localhost:27017/onetech
```

## Workaround Applied
The connection code has been configured to:
- Skip immediate connection testing for Atlas (to avoid blocking startup)
- Use relaxed SSL certificate validation
- Attempt connection on first actual database operation

## Testing
After restarting your Django server, the connection will be attempted when you first access documents. If it still fails, consider using one of the solutions above.

