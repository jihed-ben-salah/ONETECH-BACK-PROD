# Fix MongoDB Atlas Connection with LibreSSL

## Problem
Your Python is compiled with LibreSSL 2.8.3, which cannot establish TLS connections with MongoDB Atlas, causing SSL handshake failures.

## Solution: Install Python with OpenSSL

### Option 1: Use Homebrew Python (Recommended)

```bash
# Install Python 3.11 or 3.12 via Homebrew (these use OpenSSL)
brew install python@3.11

# Create a new virtual environment with the Homebrew Python
python3.11 -m venv venv-openssl
source venv-openssl/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify OpenSSL
python -c "import ssl; print(ssl.OPENSSL_VERSION)"
# Should show: OpenSSL 3.x.x or OpenSSL 1.1.1+ (NOT LibreSSL)

# Restart Django server
python manage.py runserver
```

### Option 2: Use pyenv to Install Python with OpenSSL

```bash
# Install pyenv if not already installed
brew install pyenv

# Install Python 3.11 with OpenSSL
pyenv install 3.11.9

# Set it for your project
cd /Users/fedi/Desktop/Onetech/ONETECH-BACK-PROD
pyenv local 3.11.9

# Create new virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Option 3: Temporary Workaround - Use Local MongoDB

If you need to keep working immediately without changing Python:

```bash
# In .env file, change:
MONGODB_URI=mongodb://localhost:27017/onetech
```

## Verify SSL Library

After installing new Python:

```bash
python -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

If it shows "LibreSSL", the connection will still fail. It must show "OpenSSL" for MongoDB Atlas to work.

## Current Status

- ✅ Connection code configured correctly for Atlas
- ✅ SSL options set to be as permissive as possible
- ❌ LibreSSL 2.8.3 cannot complete TLS handshake with Atlas
- ⚠️ **Action Required**: Install Python with OpenSSL support

