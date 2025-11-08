#!/bin/bash

# Enhanced XLSX Export - Installation Script
# This script installs the required dependencies for the enhanced Excel export feature

echo "=================================="
echo "Enhanced XLSX Export Installation"
echo "=================================="
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found"
    echo "Please run this script from the ONETECH-BACK-PROD directory"
    exit 1
fi

echo "📦 Installing openpyxl..."
pip install openpyxl==3.1.2

if [ $? -eq 0 ]; then
    echo "✅ openpyxl installed successfully"
else
    echo "❌ Failed to install openpyxl"
    exit 1
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "📋 Summary:"
echo "  • openpyxl 3.1.2 installed"
echo "  • Enhanced Excel export module: extraction/excel_export.py"
echo "  • New API endpoint: /documents/export-excel/"
echo ""
echo "🚀 You can now export documents with enhanced styling!"
echo ""
echo "📚 For more information, see ENHANCED_XLSX_EXPORT.md"
echo ""






