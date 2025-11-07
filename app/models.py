from pydantic import BaseModel


class SensitiveElement(BaseModel):
    """Represents a detected sensitive entity in the PDF."""
    type: str          # e.g., "IBAN", "VAT", "Name", "Email"
    value: str         # Original detected text
    replacement: str   # Synthetic replacement text
    page: int          # Page number (1-indexed)
    confidence: float  # AI confidence score (0.0 - 1.0)


class ProcessingStats(BaseModel):
    """Statistics about the anonymization process."""
    total_elements: int
    processing_time: float  # seconds
    elements_by_type: dict[str, int]


class ProcessResponse(BaseModel):
    """Response from the /api/process endpoint."""
    anonymized_pdf: str  # base64 encoded PDF bytes
    entities: list[SensitiveElement]
    stats: ProcessingStats


class ErrorResponse(BaseModel):
    """Error response for API errors."""
    detail: str
