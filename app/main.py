import base64
import logging
import os
import time
from pathlib import Path

import fitz
import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import ProcessingStats, ProcessResponse, SensitiveElement
from app.pdf_processor import anonymize_pdf

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="pdf-holomask",
    description="Auto-anonymize PDFs with synthetic data — same layout, zero leaks",
    version="0.1.0",
)

# CORS middleware - configure based on environment
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure uploads directory exists
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/")
async def serve_index():
    """Serve the main HTML page."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/api/process", response_model=ProcessResponse)
async def process_pdf(file: UploadFile = File(...)):
    """
    Process an uploaded PDF: analyze with Mistral AI and anonymize.

    Args:
        file: Uploaded PDF file

    Returns:
        ProcessResponse with anonymized PDF (base64), entities, and stats

    Raises:
        HTTPException: For validation errors or processing failures
    """
    # Validate file type (filename check)
    logger.info(f"Upload request received - filename: {file.filename}, content_type: {file.content_type}")

    if not file.filename:
        logger.error("Upload failed: No filename provided")
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        logger.error(f"Upload failed: Invalid file type - {file.filename}")
        raise HTTPException(status_code=400, detail=f"Only PDF files are supported (got: {file.filename})")

    logger.info(f"File validation passed: {file.filename}")

    # Generate unique filenames
    timestamp = int(time.time() * 1000)
    input_filename = f"{timestamp}_original.pdf"
    output_filename = f"{timestamp}_anonymized.pdf"
    input_path = UPLOAD_DIR / input_filename
    output_path = UPLOAD_DIR / output_filename

    try:
        # Save uploaded file
        content = await file.read()

        # Check file size (50MB limit) before writing
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")

        # Check if content is not empty
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        with open(input_path, "wb") as f:
            f.write(content)

        logger.info(f"Processing PDF: {file.filename}, size: {len(content)} bytes")

        # Verify it's a valid PDF by checking header
        try:
            with fitz.open(input_path) as test_doc:
                if test_doc.page_count == 0:
                    raise HTTPException(status_code=400, detail="PDF has no pages")
                logger.info(f"PDF validated: {test_doc.page_count} page(s)")
        except Exception as e:
            logger.error(f"Invalid PDF file: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid PDF file: {str(e)}") from e

        # Process PDF
        start_time = time.time()
        logger.info("Starting PDF anonymization...")
        analysis_result = anonymize_pdf(str(input_path), str(output_path))
        processing_time = time.time() - start_time

        logger.info(f"Anonymization complete. Raw result contains {len(analysis_result.get('sensitive_elements', []))} elements")

        # Group entities by page for logging
        entities_by_page = {}
        for element in analysis_result.get("sensitive_elements", []):
            page = element.get("page", 1)
            if page not in entities_by_page:
                entities_by_page[page] = []
            entities_by_page[page].append(element.get("type", "Unknown"))

        logger.info(f"PDF processed successfully in {processing_time:.2f}s")
        logger.info(f"Found {len(analysis_result.get('sensitive_elements', []))} entities across {len(entities_by_page)} pages:")
        for page in sorted(entities_by_page.keys()):
            logger.info(f"  📄 Page {page}: {len(entities_by_page[page])} elements - {', '.join(entities_by_page[page])}")

        # Read anonymized PDF and encode as base64
        with open(output_path, "rb") as f:
            anonymized_bytes = f.read()
            anonymized_b64 = base64.b64encode(anonymized_bytes).decode("utf-8")

        # Build response
        entities = [
            SensitiveElement(**element)
            for element in analysis_result.get("sensitive_elements", [])
        ]

        elements_by_type = analysis_result.get("anonymization_summary", {}).get(
            "elements_by_type", {}
        )

        stats = ProcessingStats(
            total_elements=len(entities),
            processing_time=round(processing_time, 2),
            elements_by_type=elements_by_type,
        )

        return ProcessResponse(
            anonymized_pdf=anonymized_b64,
            entities=entities,
            stats=stats,
        )

    except ValueError as e:
        # Missing API key or configuration error
        logger.error(f"Configuration error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    except requests.RequestException as e:
        # Mistral API errors
        logger.error(f"Mistral API error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}") from e
    except fitz.FileDataError as e:
        # Invalid PDF file
        logger.error(f"Invalid PDF file: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid PDF file: {str(e)}") from e
    except Exception as e:
        # Other processing errors
        logger.error(f"Processing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}") from e
    finally:
        # Cleanup temporary files
        try:
            input_path.unlink()
        except FileNotFoundError:
            pass
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass


# Mount static files (after defining routes to avoid conflicts)
app.mount("/static", StaticFiles(directory="static"), name="static")
