"""Tests for FastAPI endpoints."""

from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_serve_index():
    """Test that index page is served."""
    response = client.get("/")
    assert response.status_code == 200


def test_process_pdf_no_file():
    """Test processing without a file."""
    response = client.post("/api/process")
    assert response.status_code == 422  # Unprocessable Entity


def test_process_pdf_invalid_file_type(tmp_path: Path):
    """Test processing with non-PDF file."""
    text_file = tmp_path / "test.txt"
    text_file.write_text("This is not a PDF")

    with open(text_file, "rb") as f:
        response = client.post(
            "/api/process", files={"file": ("test.txt", f, "text/plain")}
        )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_process_pdf_empty_file():
    """Test processing with empty file."""
    response = client.post(
        "/api/process", files={"file": ("test.pdf", b"", "application/pdf")}
    )

    assert response.status_code in [400, 500]
    assert "empty" in response.json()["detail"].lower()


def test_process_pdf_success(sample_pdf: Path, tmp_path: Path):
    """Test successful PDF processing."""
    output_pdf = tmp_path / "output.pdf"

    def mock_anonymize(input_path, output_path, api_key=None):
        # Create a simple output PDF
        doc = fitz.open(input_path)
        doc.save(output_path)
        doc.close()
        return {
            "sensitive_elements": [
                {
                    "type": "Person Name",
                    "value": "John Doe",
                    "replacement": "Jane Smith",
                    "page": 1,
                    "confidence": 0.95,
                }
            ],
            "anonymization_summary": {
                "total_elements_found": 1,
                "total_replacements": 1,
                "elements_by_type": {"Person Name": 1},
            },
        }

    with patch("app.main.anonymize_pdf", side_effect=mock_anonymize):
        with open(sample_pdf, "rb") as f:
            response = client.post(
                "/api/process", files={"file": ("test.pdf", f, "application/pdf")}
            )

        assert response.status_code == 200
        data = response.json()
        assert "anonymized_pdf" in data
        assert "entities" in data
        assert "stats" in data
        assert len(data["entities"]) == 1


def test_process_pdf_api_key_missing(sample_pdf: Path):
    """Test processing when Mistral API key is missing."""
    with patch("app.main.anonymize_pdf") as mock_anonymize:
        mock_anonymize.side_effect = ValueError("Mistral API key is required")

        with open(sample_pdf, "rb") as f:
            response = client.post(
                "/api/process", files={"file": ("test.pdf", f, "application/pdf")}
            )

        assert response.status_code == 500


def test_process_pdf_file_too_large():
    """Test processing with file exceeding size limit."""
    # Create file content larger than 50MB
    large_content = b"x" * (51 * 1024 * 1024)

    response = client.post(
        "/api/process", files={"file": ("large.pdf", large_content, "application/pdf")}
    )

    assert response.status_code in [400, 413, 500]
    assert "large" in response.json()["detail"].lower() or "failed" in response.json()["detail"].lower()


def test_process_pdf_invalid_pdf(tmp_path: Path):
    """Test processing with invalid PDF content."""
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"This is not a valid PDF")

    with open(fake_pdf, "rb") as f:
        response = client.post(
            "/api/process", files={"file": ("fake.pdf", f, "application/pdf")}
        )

    assert response.status_code in [400, 500]
    assert "Invalid PDF" in response.json()["detail"] or "failed" in response.json()["detail"].lower()
