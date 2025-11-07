"""Pytest configuration and fixtures."""

import os
from pathlib import Path

import fitz
import pytest


@pytest.fixture
def mock_api_key():
    """Provide a mock Mistral API key."""
    return "test-api-key-12345"


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a simple test PDF with text."""
    pdf_path = tmp_path / "test.pdf"

    # Create a simple PDF with PyMuPDF
    doc = fitz.open()
    page = doc.new_page()

    # Add some text to the page
    page.insert_text(
        (72, 72),  # position (1 inch from top-left)
        "John Doe\n"
        "john.doe@example.com\n"
        "123 Main Street\n"
        "Phone: +1-555-123-4567\n"
        "IBAN: FR7630006000011234567890189\n"
        "VAT: FR12345678901",
        fontsize=12,
    )

    doc.save(pdf_path)
    doc.close()

    return pdf_path


@pytest.fixture
def mock_mistral_response():
    """Provide a mock Mistral API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": """{
                        "sensitive_elements": [
                            {
                                "type": "Person Name",
                                "value": "John Doe",
                                "replacement": "Jane Smith",
                                "page": 1,
                                "confidence": 0.95
                            },
                            {
                                "type": "Email Address",
                                "value": "john.doe@example.com",
                                "replacement": "jane.smith@example.com",
                                "page": 1,
                                "confidence": 0.98
                            },
                            {
                                "type": "IBAN",
                                "value": "FR7630006000011234567890189",
                                "replacement": "FR7630006000019876543210987",
                                "page": 1,
                                "confidence": 0.99
                            }
                        ],
                        "summary": {
                            "total_sensitive_elements": 3,
                            "risk_assessment": "medium"
                        }
                    }"""
                }
            }
        ]
    }


@pytest.fixture(autouse=True)
def set_test_env():
    """Set test environment variables."""
    os.environ["MISTRAL_API_KEY"] = "test-api-key"
    yield
    # Cleanup not strictly necessary as pytest runs in isolated processes
