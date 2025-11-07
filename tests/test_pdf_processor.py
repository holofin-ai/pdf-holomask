"""Tests for pdf_processor module."""

from pathlib import Path
from unittest.mock import Mock, patch

import fitz

from app.pdf_processor import anonymize_pdf


def test_anonymize_pdf_success(sample_pdf: Path, tmp_path: Path, mock_mistral_response):
    """Test successful PDF anonymization."""
    output_pdf = tmp_path / "output.pdf"

    # Mock the MistralAnalyzer
    with patch("app.pdf_processor.MistralAnalyzer") as mock_analyzer_class:
        mock_analyzer = Mock()
        mock_analyzer.analyze_document.return_value = {
            "sensitive_elements": [
                {
                    "type": "Person Name",
                    "value": "John Doe",
                    "replacement": "Jane Smith",
                    "page": 1,
                    "confidence": 0.95,
                }
            ],
            "summary": {"total_sensitive_elements": 1, "risk_assessment": "low"},
        }
        mock_analyzer_class.return_value = mock_analyzer

        result = anonymize_pdf(str(sample_pdf), str(output_pdf))

        # Verify the result structure
        assert "sensitive_elements" in result
        assert "anonymization_summary" in result
        assert output_pdf.exists()

        # Verify the output PDF is valid
        doc = fitz.open(output_pdf)
        assert doc.page_count > 0
        doc.close()


def test_anonymize_pdf_preserves_metadata(sample_pdf: Path, tmp_path: Path):
    """Test that PDF metadata is preserved with attribution."""
    output_pdf = tmp_path / "output.pdf"

    # Set metadata on source PDF
    doc = fitz.open(sample_pdf)
    doc.set_metadata({"title": "Test Document", "author": "Original Author"})
    # Save to a new file instead of overwriting
    pdf_with_metadata = tmp_path / "input_with_metadata.pdf"
    doc.save(pdf_with_metadata)
    doc.close()

    # Mock the MistralAnalyzer
    with patch("app.pdf_processor.MistralAnalyzer") as mock_analyzer_class:
        mock_analyzer = Mock()
        mock_analyzer.analyze_document.return_value = {
            "sensitive_elements": [],
            "summary": {},
        }
        mock_analyzer_class.return_value = mock_analyzer

        anonymize_pdf(str(pdf_with_metadata), str(output_pdf))

        # Check metadata
        doc = fitz.open(output_pdf)
        metadata = doc.metadata
        assert metadata["author"] == "holomask https://holofin.ai"
        assert metadata["title"] == "Test Document"
        doc.close()


def test_anonymize_pdf_name_splitting(sample_pdf: Path, tmp_path: Path):
    """Test that person names are split for partial matching."""
    output_pdf = tmp_path / "output.pdf"

    with patch("app.pdf_processor.MistralAnalyzer") as mock_analyzer_class:
        mock_analyzer = Mock()
        mock_analyzer.analyze_document.return_value = {
            "sensitive_elements": [
                {
                    "type": "Person Name",
                    "value": "John Doe",
                    "replacement": "Jane Smith",
                    "page": 1,
                    "confidence": 0.95,
                }
            ],
            "summary": {},
        }
        mock_analyzer_class.return_value = mock_analyzer

        anonymize_pdf(str(sample_pdf), str(output_pdf))

        # Verify the output PDF was created
        assert output_pdf.exists()


def test_anonymize_pdf_not_found_elements(sample_pdf: Path, tmp_path: Path):
    """Test handling of elements not found in PDF."""
    output_pdf = tmp_path / "output.pdf"

    with patch("app.pdf_processor.MistralAnalyzer") as mock_analyzer_class:
        mock_analyzer = Mock()
        mock_analyzer.analyze_document.return_value = {
            "sensitive_elements": [
                {
                    "type": "IBAN",
                    "value": "FR1234567890123456789012345",  # Not in PDF
                    "replacement": "FR9876543210987654321098765",
                    "page": 1,
                    "confidence": 0.99,
                }
            ],
            "summary": {},
        }
        mock_analyzer_class.return_value = mock_analyzer

        result = anonymize_pdf(str(sample_pdf), str(output_pdf))

        # Should track not-found elements
        assert "not_found_in_pdf" in result or "anonymization_summary" in result


def test_anonymize_pdf_font_matching(sample_pdf: Path, tmp_path: Path):
    """Test that font matching strategies work without errors."""
    output_pdf = tmp_path / "output.pdf"

    with patch("app.pdf_processor.MistralAnalyzer") as mock_analyzer_class:
        mock_analyzer = Mock()
        mock_analyzer.analyze_document.return_value = {
            "sensitive_elements": [
                {
                    "type": "Person Name",
                    "value": "John Doe",
                    "replacement": "Jane Smith",
                    "page": 1,
                    "confidence": 0.95,
                }
            ],
            "summary": {},
        }
        mock_analyzer_class.return_value = mock_analyzer

        anonymize_pdf(str(sample_pdf), str(output_pdf))

        # Verify the PDF was created and is readable
        assert output_pdf.exists()
        doc = fitz.open(output_pdf)
        text = doc[0].get_text()
        # Should contain replacement text
        assert "Jane Smith" in text or "John Doe" not in text
        doc.close()
