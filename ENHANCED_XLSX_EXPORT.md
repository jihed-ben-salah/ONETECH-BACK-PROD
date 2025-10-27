# Enhanced XLSX Export Feature

## Overview

The enhanced XLSX export feature provides professional, styled Excel documents that match the original document structure and frontend display. Each document type (Rebut, NPT, Kosu) has its own custom styling and layout.

## Features

### 🎨 Professional Styling
- **Color-coded headers** based on document type
  - Rebut: Indigo/Emerald theme
  - NPT: Purple theme
  - Kosu: Amber theme
- **Alternating row colors** for better readability
- **Proper borders** and cell formatting
- **Custom fonts** and alignment
- **Merged cells** for headers and sections

### 📋 Document Structure

Each exported Excel file includes:
1. **Document Title Section** - Prominently displayed with type-specific colors
2. **Document Information Section** - Key metadata (filename, date, processed time, etc.)
3. **Header Information** - Document-specific header fields in a clean 2-column layout
4. **Data Tables** - All data arrays rendered as formatted tables with:
   - Column headers with proper naming
   - Alternating row colors
   - Proper alignment and borders
   - Auto-sized columns

### 📊 Supported Document Types

#### Rebut (Rejection Declaration Form)
- Company header (TTE International - A Onetech company)
- Document metadata (filename, type, date, ligne, OF number, mat, equipe, visa)
- Items table with all rejection items
- Professional indigo/emerald color scheme

#### NPT (Non-Productive Time Report)
- Document metadata (filename, type, date, UAP, equipe)
- Downtime events table with all events
- Professional purple color scheme

#### Kosu (Production Report)
- Document metadata (filename, type, date, ligne info, OF number, ref PF)
- Dynamic sections (all data arrays in the document)
- Team summary and production data
- Professional amber color scheme

## API Endpoints

### Single Document Export
```
GET /documents/export-excel/?id={doc_id}&type={doc_type}
```

**Parameters:**
- `id` (required): Document ID
- `type` (required): Document type (Rebut, NPT, or Kosu)

**Response:**
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Filename: `{filename}_{type}_{timestamp}.xlsx`

### Bulk Document Export
```
POST /documents/export-excel/
Content-Type: application/json

{
  "type": "Rebut",
  "export_all": true,
  "ids": ["id1", "id2", ...]  // optional if export_all is false
}
```

**Parameters:**
- `type` (required): Document type (Rebut, NPT, or Kosu)
- `export_all` (optional): Export all documents of this type (default: false)
- `ids` (optional): Array of document IDs to export (required if export_all is false)

**Response:**
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Multiple sheets, one per document
- Filename: `{type}_export_{timestamp}.xlsx`

## Frontend Integration

### Usage from Frontend

The frontend automatically uses the enhanced Excel export when format is 'xlsx':

```typescript
const response = await fetch('/api/documents/export-bulk', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        type: 'Rebut', // or 'NPT', 'Kosu'
        format: 'xlsx',
    }),
});

const blob = await response.blob();
const url = window.URL.createObjectURL(blob);
const link = document.createElement('a');
link.href = url;
link.download = 'export.xlsx';
link.click();
```

## Installation

### Backend Requirements

Add to `requirements.txt`:
```
openpyxl==3.1.2
```

Install:
```bash
cd ONETECH-BACK-PROD
pip install -r requirements.txt
```

### Files Added/Modified

**New Files:**
- `ONETECH-BACK-PROD/extraction/excel_export.py` - Enhanced Excel export functionality

**Modified Files:**
- `ONETECH-BACK-PROD/requirements.txt` - Added openpyxl
- `ONETECH-BACK-PROD/extraction/document_views.py` - Added EnhancedExcelExportView
- `ONETECH-BACK-PROD/extraction/urls.py` - Added export-excel endpoint
- `onetech-document-extractor/app/api/documents/export-bulk/route.ts` - Updated to use enhanced export

## Technical Details

### Color Schemes

```python
# Rebut Colors
REBUT_HEADER_BG = "4F46E5"  # Indigo-600
REBUT_TABLE_BG = "10B981"   # Emerald-600

# NPT Colors
NPT_HEADER_BG = "7C3AED"    # Purple-600
NPT_TABLE_BG = "8B5CF6"     # Purple-500

# Kosu Colors
KOSU_HEADER_BG = "F59E0B"   # Amber-500
KOSU_TABLE_BG = "FBBF24"    # Amber-400

# Common Colors
TABLE_HEADER_BG = "DBEAFE"  # Blue-100
ALT_ROW_BG = "F3F4F6"       # Gray-100
BORDER_COLOR = "D1D5DB"     # Gray-300
```

### Excel Structure

Each Excel file follows this structure:
1. **Row 1**: Document title (merged cells, colored background)
2. **Row 2-3**: Spacing
3. **Row 4**: "Document Information" header
4. **Rows 5-N**: Header fields in 2-column layout
5. **Row N+1**: Spacing
6. **Row N+2**: Section header (e.g., "Items Data")
7. **Row N+3**: Table column headers
8. **Rows N+4+**: Data rows with alternating colors

### Column Width
All columns are automatically set to 15 characters width for consistency.

## Example Output

### Rebut Document
```
┌──────────────────────────────────────────────────┐
│   Formulaire de déclaration Rebuts               │  ← Indigo header
├──────────────────────────────────────────────────┤
│   Document Information                           │  ← Blue subheader
├──────────────────────────────────────────────────┤
│ Filename: document.pdf    │ Type: Rebut         │
│ Date: 2024-10-25          │ Ligne: L1           │
│ OF Number: OF-12345       │ Mat: MAT-001        │
├──────────────────────────────────────────────────┤
│   Items Data                                     │  ← Emerald header
├──────────────────────────────────────────────────┤
│ Reference    │ Designation    │ Quantity │ ...  │
├──────────────────────────────────────────────────┤
│ REF-001      │ Part A         │ 10       │ ...  │  ← White background
│ REF-002      │ Part B         │ 5        │ ...  │  ← Gray background
│ REF-003      │ Part C         │ 8        │ ...  │  ← White background
└──────────────────────────────────────────────────┘
```

## Benefits

✅ **Professional appearance** - Matches the original document styling
✅ **Better readability** - Color coding and alternating rows
✅ **Type-specific layouts** - Each document type has optimized structure
✅ **Complete data export** - All fields and tables included
✅ **Maintains consistency** - Frontend and Excel exports match
✅ **Easy to use** - Simple API endpoints
✅ **Multiple document support** - Export single or multiple documents

## Troubleshooting

### Import Error
If you get `ModuleNotFoundError: No module named 'openpyxl'`:
```bash
pip install openpyxl==3.1.2
```

### Empty Excel File
Check that the document has data in the correct structure:
- Rebut: `data.items` should be a list
- NPT: `data.downtime_events` should be a list
- Kosu: Dynamic sections should exist

### Styling Not Applied
Ensure you're using the enhanced Excel export endpoint (`/documents/export-excel/`) not the old CSV export endpoint.

## Future Enhancements

Potential improvements:
- Add charts and graphs
- Include summary statistics
- Add filtering options
- Custom column widths based on content
- Image embedding (company logo)
- PDF conversion option
- Email export functionality

## Support

For issues or questions, check:
1. Backend logs for export errors
2. Frontend console for API errors
3. Document structure in MongoDB
4. openpyxl is properly installed

---

**Created:** October 2024
**Version:** 1.0
**Dependencies:** openpyxl 3.1.2, Django 5.0.7



