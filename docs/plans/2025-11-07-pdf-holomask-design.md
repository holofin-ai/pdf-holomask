# pdf-holomask Design Document

**Date:** 2025-11-07
**Status:** Approved
**Architecture:** Simple synchronous processing with entity list + side-by-side PDF view

---

## Overview

pdf-holomask is an open-source tool that automatically detects and replaces sensitive information in PDFs using AI-powered entity recognition. It transforms real-world data into synthetic lookalikes that preserve structure, readability, and realism.

**Core Philosophy:**
Like a Holocron guarding ancient knowledge, pdf-holomask protects data by transforming it — preserving meaning without revealing truth. No redaction. No leaks. Just clean, synthetic privacy.

---

## Goals

1. **Privacy-first:** Process PDFs entirely offline with no external API calls except Mistral AI
2. **Format-aware anonymization:** Replace entities with contextually appropriate synthetic data (not just black boxes)
3. **Metadata preservation:** Keep original PDF metadata intact (creation date, author, etc.)
4. **Simple local deployment:** Single command setup with `uv`, no complex infrastructure
5. **Transparency:** Show users exactly what was detected and replaced

---

## Non-Goals

- Cloud deployment or SaaS offering
- Database for job persistence
- User authentication/multi-tenancy
- Batch processing or API integration
- Support for non-PDF formats

---

## Architecture

### System Design

**Type:** Single-page web application with synchronous processing
**Backend:** FastAPI
**Frontend:** HTML + Tailwind CSS (CDN) + Alpine.js + PDF.js
**Processing:** Synchronous (user waits for results)

### High-Level Flow

```
User → Upload PDF → FastAPI receives file
                  ↓
            Extract text (pdfplumber)
                  ↓
            Analyze with Mistral AI
                  ↓
            Anonymize PDF (PyMuPDF)
                  ↓
            Return JSON response
                  ↓
Frontend ← { anonymized_pdf (base64), entities[], stats }
                  ↓
            Render both PDFs side-by-side
            Display entity list below
```

---

## Project Structure

```
pdf-holomask/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + routes
│   ├── mistral_analyzer.py  # Mistral AI integration
│   ├── pdf_processor.py     # PDF anonymization with PyMuPDF
│   └── models.py            # Pydantic models
├── static/
│   ├── index.html           # Single-page app UI
│   └── app.js               # Frontend logic (Alpine.js)
├── uploads/                 # Temporary file storage (auto-cleanup)
├── .env.example             # Template for environment variables
├── .gitignore
├── pyproject.toml           # uv/pip dependencies
├── README.md
└── LICENSE                  # MIT License
```

---

## Backend Components

### 1. FastAPI Application (`app/main.py`)

**Routes:**
- `GET /` - Serve static HTML (index.html)
- `POST /api/process` - Process PDF upload

**POST /api/process workflow:**
1. Validate file type (PDF only)
2. Save to temporary storage
3. Call `MistralAnalyzer.analyze_document(pdf_path)`
4. Call `pdf_processor.anonymize_pdf(pdf_path, analysis_result)`
5. Read anonymized PDF, encode as base64
6. Clean up temporary files
7. Return JSON response

**Error handling:**
- Invalid file type → 400 Bad Request
- Missing MISTRAL_API_KEY → 500 Internal Server Error
- Mistral API errors → 502 Bad Gateway with error message
- File too large → 413 Payload Too Large

**Configuration:**
- CORS enabled for local development
- File upload size limit: 50MB
- Temp file cleanup after each request

---

### 2. Mistral Analyzer (`app/mistral_analyzer.py`)

Adapted from old Django implementation.

**Class:** `MistralAnalyzer`

**Method:** `analyze_document(pdf_path: str) -> dict`

**Process:**
1. Extract text with `pdfplumber` (page-aware, up to 8000 chars to avoid token limits)
2. Send prompt to Mistral API requesting structured JSON output
3. Parse response into standardized format

**Detected Entity Types:**
- Registration/Company codes
- VAT numbers
- IBANs and bank account numbers
- Client names (individual/company)
- Addresses
- Phone numbers
- Email addresses
- Other sensitive identifiers

**Prompt Strategy:**
Request Mistral to return JSON with:
```json
{
  "sensitive_elements": [
    {
      "type": "IBAN",
      "value": "FR7619733000010100001466083",
      "replacement": "FR7630006000012345678912345",
      "page": 1,
      "confidence": 0.95
    },
    ...
  ],
  "summary": {
    "total_sensitive_elements": 5,
    "risk_assessment": "high"
  }
}
```

**API Configuration:**
- Model: `mistral-large-latest`
- Response format: `{"type": "json_object"}`
- Headers: Bearer token from `MISTRAL_API_KEY` env var

---

### 3. PDF Processor (`app/pdf_processor.py`)

Adapted from old Django implementation.

**Function:** `anonymize_pdf(input_path: str, output_path: str, analysis_result: dict) -> None`

**Process:**
1. Open PDF with PyMuPDF (fitz)
2. Store original metadata
3. For each detected entity:
   - Search for text on specified page
   - Record bounding box position
   - Extract font properties (name, size, color)
4. Apply white redaction annotations to all bounding boxes
5. Rewrite synthetic replacements using original font properties
6. Restore original metadata
7. Save to output path

**Metadata Preservation:**
```python
original_metadata = doc.metadata
# ... perform anonymization ...
doc.set_metadata(original_metadata)
doc.save(output_path, garbage=0, deflate=True)
```

**Text Replacement Strategy:**
- Use `page.search_for(original_text)` to find exact matches
- Apply `page.add_redact_annot(rect, fill=(1, 1, 1))` for white fill
- Use `TextWriter` to rewrite replacement text with matched font/size
- Handle baseline offset for proper vertical alignment

---

### 4. Data Models (`app/models.py`)

**Pydantic Models:**

```python
class SensitiveElement(BaseModel):
    type: str          # "IBAN", "VAT", "Name", "Email", etc.
    value: str         # Original detected text
    replacement: str   # Synthetic replacement
    page: int          # Page number (1-indexed)
    confidence: float  # AI confidence score (0.0 - 1.0)

class ProcessingStats(BaseModel):
    total_elements: int
    processing_time: float  # seconds
    elements_by_type: dict[str, int]

class ProcessResponse(BaseModel):
    anonymized_pdf: str  # base64 encoded PDF bytes
    entities: list[SensitiveElement]
    stats: ProcessingStats
```

---

## Frontend Components

### UI Layout

**Single HTML page** with three sections:

#### 1. Upload Zone (Header)
- Drag-and-drop area with file picker fallback
- File validation (PDF only, max 50MB)
- Display selected file name + size
- "Process PDF" button (disabled until file selected)
- Loading spinner during processing
- Error message display area

#### 2. PDF Viewers (Main - Side by Side)
- **Left panel:** Original PDF rendered with PDF.js
- **Right panel:** Anonymized PDF rendered with PDF.js
- Both panels use canvas rendering
- Optional: synchronized scrolling between panels
- Show/hide based on processing state

#### 3. Entity List (Bottom)
- Table with columns: Type | Original | Replacement | Page | Confidence
- Color-coded by entity type for visual distinction
- "Download Anonymized PDF" button
- Stats summary (total elements, processing time)

---

### State Management (Alpine.js)

```javascript
Alpine.data('pdfAnonymizer', () => ({
  file: null,
  processing: false,
  result: null,  // { anonymized_pdf, entities, stats }
  error: null,
  originalPdfUrl: null,

  selectFile(event) {
    const file = event.target.files[0];
    if (file && file.type === 'application/pdf') {
      this.file = file;
      this.originalPdfUrl = URL.createObjectURL(file);
      this.error = null;
    } else {
      this.error = 'Please select a valid PDF file';
    }
  },

  async processFile() {
    this.processing = true;
    this.error = null;

    const formData = new FormData();
    formData.append('file', this.file);

    try {
      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Processing failed');
      }

      this.result = await response.json();
      this.renderPdfs();
    } catch (err) {
      this.error = err.message;
    } finally {
      this.processing = false;
    }
  },

  renderPdfs() {
    // Render original PDF in left canvas
    // Render anonymized PDF (base64 decoded) in right canvas
    // Using PDF.js rendering API
  },

  downloadAnonymized() {
    const blob = this.base64ToBlob(this.result.anonymized_pdf);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'anonymized_' + this.file.name;
    a.click();
  }
}));
```

---

### Technology Stack

**Frontend:**
- **Tailwind CSS** (CDN) - Styling
- **Alpine.js** (CDN) - Reactive state management
- **PDF.js** (CDN) - PDF rendering in canvas

**Backend:**
- **FastAPI** - Web framework
- **Uvicorn** - ASGI server
- **PyMuPDF (fitz)** - PDF manipulation
- **pdfplumber** - Text extraction
- **requests** - Mistral API calls
- **python-dotenv** - Environment variable management

---

## Dependencies

**pyproject.toml:**
```toml
[project]
name = "pdf-holomask"
version = "0.1.0"
description = "Auto-anonymize PDFs with synthetic data"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "python-multipart>=0.0.6",
    "pymupdf>=1.23.0",
    "pdfplumber>=0.10.0",
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
]
```

---

## Configuration

**.env.example:**
```
# Mistral AI API Key (required)
MISTRAL_API_KEY=your_api_key_here

# Optional: Server configuration
HOST=0.0.0.0
PORT=8000
```

**.gitignore:**
```
.env
__pycache__/
*.pyc
.venv/
venv/
uploads/
*.pdf
.DS_Store
```

---

## Security Considerations

1. **API Key Protection:** Never commit `.env` file, provide `.env.example` template
2. **File Upload Validation:** Strict PDF-only validation, size limits
3. **Temporary File Cleanup:** Auto-delete uploaded/processed files after response
4. **CORS Configuration:** Restrict to localhost in production
5. **No Data Persistence:** No database, no file storage beyond request lifecycle
6. **Offline Processing:** All PDF manipulation happens locally (only Mistral API is external)

---

## Testing Strategy

**Manual Testing:**
1. Upload various PDF types (financial docs, invoices, forms)
2. Verify entity detection accuracy
3. Confirm metadata preservation
4. Check visual layout integrity
5. Test error handling (invalid API key, large files, corrupt PDFs)

**Future: Automated Testing:**
- Unit tests for `MistralAnalyzer` (mock API responses)
- Unit tests for `pdf_processor` (fixture PDFs)
- Integration tests for `/api/process` endpoint

---

## Deployment

**Local Development:**
```bash
# Clone and setup
git clone https://github.com/username/pdf-holomask.git
cd pdf-holomask
cp .env.example .env
# Edit .env to add MISTRAL_API_KEY

# Install dependencies with uv
uv sync

# Run server
uv run uvicorn app.main:app --reload

# Access at http://localhost:8000
```

**Production Considerations:**
- Use `--host 0.0.0.0 --port 8000` for network access
- Consider nginx reverse proxy for HTTPS
- Set appropriate file size limits
- Monitor Mistral API usage/costs

---

## Future Enhancements

**Potential additions (not in MVP):**
1. JSON export of detected entities
2. Bounding box overlay visualization
3. Async processing with job queue
4. Batch processing multiple PDFs
5. Custom entity type configuration
6. Support for scanned PDFs (OCR integration)
7. Multi-language support beyond French/English
8. CLI mode for scripting

---

## License

MIT License - Open source, privacy shouldn't cost transparency.

---

## README Outline

The README.md will include:

1. **Project Description** - Holocron philosophy, core features
2. **Demo/Screenshots** - Visual examples of the UI
3. **Features** - Bulleted list of capabilities
4. **Installation** - Step-by-step setup with uv
5. **Usage** - How to run and use the tool
6. **How It Works** - Technical overview (Mistral AI + PyMuPDF)
7. **Privacy & Security** - Offline processing guarantees
8. **Contributing** - Guidelines for contributions
9. **License** - MIT
10. **Acknowledgments** - Mistral AI, PyMuPDF, etc.

---

## Success Criteria

The design is successful when:

1. Users can upload a PDF and see anonymized results in < 30 seconds
2. All detected entities are replaced with realistic synthetic data
3. Original PDF metadata remains unchanged
4. UI clearly shows what was changed (entity list)
5. Setup requires only: `uv sync`, add API key, run server
6. No data persists after request completes
