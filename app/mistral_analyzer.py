import json
import logging
import os
from pathlib import Path

import fitz  # PyMuPDF
import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MistralAnalyzer:
    """
    Analyzes PDF documents using Mistral AI API to identify sensitive information
    and generate contextually appropriate synthetic replacements.
    """

    def __init__(self, api_key: str | None = None, config_path: str | None = None):
        """Initialize with API key from parameter, environment, or raise error."""
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Mistral API key is required. Set MISTRAL_API_KEY environment variable."
            )

        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.model = "mistral-medium-latest"

        # Load entity configuration
        self.entity_config = self._load_entity_config(config_path)

    def _load_entity_config(self, config_path: str | None = None) -> dict:
        """Load entity detection configuration from YAML file."""
        if config_path is None:
            # Default to entity_config.yaml in project root
            project_root = Path(__file__).parent.parent
            config_path = project_root / "entity_config.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Entity config file not found at {config_path}, using default configuration")
            return self._get_default_config()

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded entity configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load entity config from {config_path}: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> dict:
        """Return default entity configuration if config file is not available."""
        return {
            "entities": [
                {"type": "VAT Number", "enabled": True},
                {"type": "IBAN", "enabled": True},
                {"type": "Person Name", "enabled": True},
                {"type": "Company Name", "enabled": True},
                {"type": "Address", "enabled": True},
                {"type": "Phone Number", "enabled": True},
                {"type": "Email Address", "enabled": True},
            ]
        }

    def _build_entity_list_prompt(self) -> str:
        """Build the entity detection list from configuration."""
        enabled_entities = [
            entity for entity in self.entity_config.get("entities", [])
            if entity.get("enabled", True)
        ]

        entity_lines = []
        for entity in enabled_entities:
            entity_type = entity.get("type", "Unknown")
            description = entity.get("description", "")
            example = entity.get("example", "")

            if description and example:
                entity_lines.append(f"- {entity_type}: {description} (e.g., {example})")
            elif description:
                entity_lines.append(f"- {entity_type}: {description}")
            else:
                entity_lines.append(f"- {entity_type}")

        return "\n".join(entity_lines)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text content from a PDF file with page markers.
        Uses PyMuPDF to extract visible text while filtering out overlapping/hidden content.
        """
        text_content = []

        # Use PyMuPDF for better control over text extraction
        doc = fitz.open(pdf_path)
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # Get text blocks with their positions
                text_dict = page.get_text("dict", sort=True)
                page_text_parts = []
                seen_positions = set()

                for block in text_dict["blocks"]:
                    if "lines" not in block:
                        continue

                    for line in block["lines"]:
                        line_text = ""
                        line_bbox = line.get("bbox")

                        # Check if this line overlaps with already-seen text (indicates overlay)
                        is_overlapping = False
                        if line_bbox:
                            line_rect = fitz.Rect(line_bbox)
                            for seen_rect in seen_positions:
                                if line_rect.intersects(seen_rect):
                                    # Only skip if there's significant overlap (>50% area)
                                    intersection = line_rect & seen_rect
                                    overlap_ratio = intersection.get_area() / line_rect.get_area() if line_rect.get_area() > 0 else 0
                                    if overlap_ratio > 0.5:
                                        is_overlapping = True
                                        break

                            if not is_overlapping:
                                seen_positions.add(line_rect)

                        # Extract text from spans in this line
                        for span in line["spans"]:
                            line_text += span.get("text", "")

                        if line_text.strip() and not is_overlapping:
                            page_text_parts.append(line_text)

                page_text = "\n".join(page_text_parts)
                text_content.append((page_num + 1, page_text))
        finally:
            doc.close()

        # Format with page markers
        formatted_content = []
        for page_num, page_text in text_content:
            if page_text.strip():
                formatted_content.append(f"--- Page {page_num} ---\n{page_text}")

        return "\n\n".join(formatted_content)

    def analyze_document(self, pdf_path: str) -> dict:
        """
        Analyze a PDF document to identify sensitive information and generate
        appropriate synthetic replacements.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            dict: JSON response containing identified sensitive information with
                  suggested replacements

        Raises:
            Exception: If API request fails or response parsing fails
        """
        # Extract text from PDF (limit to 8000 chars to avoid token limits)
        full_text = self.extract_text_from_pdf(pdf_path)
        was_truncated = len(full_text) > 8000
        pdf_text = full_text[:8000]

        if was_truncated:
            logger.warning(f"PDF text truncated from {len(full_text)} to 8000 characters for analysis")

        # Build entity list from configuration
        entity_list = self._build_entity_list_prompt()

        # Prepare prompt for Mistral AI
        prompt = f"""This document appears to be a financial or official document.
Please analyze it and identify all instances of the following sensitive information:

{entity_list}

IMPORTANT INSTRUCTIONS:
1. The document text below contains page markers in the format "--- Page X ---"
2. For EACH sensitive element you find, you MUST determine which page it appears on by looking at the most recent "--- Page X ---" marker BEFORE that element
3. If a sensitive value appears multiple times on different pages, report it as SEPARATE entries with the correct page number for each occurrence
4. Be precise with page numbers - they are critical for proper redaction

For each sensitive element found, please also generate a contextually appropriate random replacement
that maintains the same format but contains completely different information.

For example:
- If you find a French VAT number like "FR64850529256", generate a random French VAT number like "FR21387569432"
- If you find an IBAN like "FR7619733000010100001466083", generate a random IBAN with the same country code
- If you find a company name like "Viva Payments Services S.A.", generate a random company name like "TechCorp Solutions Ltd."
- If you find an address like "22 rue Chauchat, Paris 75009", generate a random address with similar structure
- If you find a person's name like "Jean Dupont", generate a random name like "Marie Laurent"

Return your findings as a structured JSON object with the following format:
{{
  "sensitive_elements": [
    {{
      "type": "IBAN",
      "value": "FR7619733000010100001466083",
      "replacement": "FR7630006000012345678912345",
      "page": 1,
      "confidence": 0.95
    }},
    {{
      "type": "VAT",
      "value": "FR64850529256",
      "replacement": "FR21387569432",
      "page": 1,
      "confidence": 0.98
    }},
    {{
      "type": "Social Security Number",
      "value": "183043726102195",
      "replacement": "275129837465201",
      "page": 2,
      "confidence": 0.99
    }},
    ...
  ],
  "summary": {{
    "total_sensitive_elements": 5,
    "risk_assessment": "high"
  }}
}}

REMINDER: If the same value appears on multiple pages (e.g., a header or footer), create a SEPARATE entry for EACH occurrence with its correct page number.

Document text:
{pdf_text}
"""

        # Call Mistral API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }

        logger.info("Calling Mistral AI API for PDF analysis")
        response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)

        if response.status_code != 200:
            logger.error(f"Mistral API request failed with status {response.status_code}")
            raise requests.RequestException(
                f"Mistral API request failed with status {response.status_code}: {response.text}"
            )

        try:
            analysis_result = response.json()
            content_str = analysis_result["choices"][0]["message"]["content"]
            parsed_result = json.loads(content_str)

            # Add truncation info to summary
            if "summary" not in parsed_result:
                parsed_result["summary"] = {}
            parsed_result["summary"]["text_truncated"] = was_truncated

            logger.info(f"Mistral AI analysis complete, found {len(parsed_result.get('sensitive_elements', []))} sensitive elements")
            return parsed_result
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Mistral API response: {str(e)}")
            raise ValueError(f"Failed to parse Mistral API response: {str(e)}") from e
