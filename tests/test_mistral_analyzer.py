"""Tests for mistral_analyzer module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.mistral_analyzer import MistralAnalyzer


def test_mistral_analyzer_init_with_key(mock_api_key):
    """Test MistralAnalyzer initialization with API key."""
    analyzer = MistralAnalyzer(api_key=mock_api_key)
    assert analyzer.api_key == mock_api_key


def test_mistral_analyzer_init_from_env():
    """Test MistralAnalyzer initialization from environment."""
    analyzer = MistralAnalyzer()
    assert analyzer.api_key is not None


def test_mistral_analyzer_init_no_key():
    """Test MistralAnalyzer initialization fails without API key."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="Mistral API key is required"):
            MistralAnalyzer()


def test_extract_text_from_pdf(sample_pdf: Path, mock_api_key):
    """Test text extraction from PDF."""
    analyzer = MistralAnalyzer(api_key=mock_api_key)
    text = analyzer.extract_text_from_pdf(str(sample_pdf))

    assert "--- Page 1 ---" in text
    assert "John Doe" in text
    assert "john.doe@example.com" in text


def test_analyze_document_success(sample_pdf: Path, mock_api_key, mock_mistral_response):
    """Test successful document analysis."""
    analyzer = MistralAnalyzer(api_key=mock_api_key)

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_mistral_response
        mock_post.return_value = mock_response

        result = analyzer.analyze_document(str(sample_pdf))

        assert "sensitive_elements" in result
        assert len(result["sensitive_elements"]) == 3
        assert result["sensitive_elements"][0]["type"] == "Person Name"
        assert result["sensitive_elements"][0]["value"] == "John Doe"


def test_analyze_document_api_error(sample_pdf: Path, mock_api_key):
    """Test document analysis with API error."""
    analyzer = MistralAnalyzer(api_key=mock_api_key)

    with patch("requests.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="401"):
            analyzer.analyze_document(str(sample_pdf))


def test_entity_config_loading(mock_api_key, tmp_path):
    """Test entity configuration loading."""
    # Create a custom config file
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text("""
entities:
  - type: "Email Address"
    description: "Email addresses"
    example: "test@example.com"
    enabled: true
""")

    analyzer = MistralAnalyzer(api_key=mock_api_key, config_path=str(config_path))
    assert "entities" in analyzer.entity_config
    assert len(analyzer.entity_config["entities"]) == 1
    assert analyzer.entity_config["entities"][0]["type"] == "Email Address"


def test_build_entity_list_prompt(mock_api_key):
    """Test entity list prompt building."""
    analyzer = MistralAnalyzer(api_key=mock_api_key)
    prompt = analyzer._build_entity_list_prompt()

    assert "Person Name" in prompt or "Email" in prompt
    assert len(prompt) > 0
