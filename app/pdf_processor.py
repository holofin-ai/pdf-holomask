import logging

import fitz  # PyMuPDF

from app.mistral_analyzer import MistralAnalyzer

logger = logging.getLogger(__name__)


def anonymize_pdf(input_path: str, output_path: str, api_key: str | None = None) -> dict:
    """
    Anonymize a PDF using AI analysis to detect sensitive information and replace it
    with contextually appropriate synthetic alternatives.

    Args:
        input_path: Path to the input PDF file
        output_path: Path to save the anonymized PDF
        api_key: Optional Mistral API key (uses env var if not provided)

    Returns:
        dict: Analysis result containing identified sensitive information

    Raises:
        Exception: If analysis or PDF processing fails
    """
    # Analyze the PDF with Mistral AI
    analyzer = MistralAnalyzer(api_key)
    analysis_result = analyzer.analyze_document(input_path)

    # Open PDF with PyMuPDF
    doc = fitz.open(input_path)
    try:
        # Store original metadata to preserve it
        original_metadata = doc.metadata

        # Store text positions and replacement info
        text_positions = {}
        not_found_elements = []

        # First pass: identify and store positions of all sensitive elements
        for element in analysis_result.get("sensitive_elements", []):
            page_num = element.get("page", 1) - 1  # Convert to 0-based
            original_text = element.get("value", "")
            element_type = element.get("type", "Unknown")
            replacement = element.get("replacement", "XXXXX")

            # For person names, also search for individual first/last names
            elements_to_search = [(original_text, replacement)]

            if element_type in ["Person Name", "Client Name"]:
                # Split into first and last name
                name_parts = original_text.split()
                replacement_parts = replacement.split()

                if len(name_parts) >= 2 and len(replacement_parts) >= 2:
                    # Add first name as separate search
                    elements_to_search.append((name_parts[0], replacement_parts[0]))
                    # Add last name as separate search
                    elements_to_search.append((name_parts[-1], replacement_parts[-1]))

            if page_num < len(doc):
                page = doc[page_num]

                # Search for each element (full name + individual parts)
                for search_text, search_replacement in elements_to_search:
                    text_instances = page.search_for(search_text)

                    if text_instances:
                        logger.info(f"Found {len(text_instances)} instance(s) of {element_type}: '{search_text}' on page {page_num + 1}")

                        # Store positions and properties for each instance
                        for rect in text_instances:
                            key = f"{page_num}_{search_text}_{rect.x0}_{rect.y0}"

                            # Extract font information from the text at this position
                            span_info = None
                            text_dict = page.get_text("dict")
                            for block in text_dict["blocks"]:
                                if "lines" in block:
                                    for line in block["lines"]:
                                        for span in line["spans"]:
                                            span_rect = fitz.Rect(span["bbox"])
                                            if span_rect.intersects(rect):
                                                # Calculate actual visual font size from bbox height
                                                # PDFs may use transformation matrices that aren't reflected in size
                                                reported_size = span.get("size", 10)
                                                visual_height = span["bbox"][3] - span["bbox"][1]

                                                # Use visual height if significantly different from reported size
                                                if visual_height > reported_size * 1.5:
                                                    actual_size = visual_height * 0.85  # Approximate ascent
                                                else:
                                                    actual_size = reported_size

                                                span_info = {
                                                    "font": span.get("font", "helv"),
                                                    "size": actual_size,
                                                    "color": span.get("color", 0),
                                                }
                                                break
                                        if span_info:
                                            break
                                if span_info:
                                    break

                            if not span_info:
                                span_info = {"font": "helv", "size": 10, "color": 0}

                            text_positions[key] = {
                                "rect": rect,
                                "replacement": search_replacement,
                                "span_info": span_info,
                            }

                # Only log "not found" for the main element, not the parts
                if not page.search_for(original_text):
                    logger.warning(f"✗ NOT FOUND in PDF - {element_type}: '{original_text}' on page {page_num + 1} (AI may have hallucinated this)")
                    not_found_elements.append({
                        "type": element_type,
                        "value": original_text,
                        "page": page_num + 1,
                        "replacement": replacement
                    })

        # Second pass: process each page
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Collect all rectangles to redact on this page
            redact_rects = []
            for key, info in text_positions.items():
                if key.startswith(f"{page_num}_"):
                    redact_rects.append(info["rect"])

            # Apply white redactions
            for rect in redact_rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))  # White fill

            if redact_rects:
                logger.info(f"Applying {len(redact_rects)} redaction(s) on page {page_num + 1}")
            page.apply_redactions()

            # Get available fonts on this page for better matching
            page_fonts = page.get_fonts(full=True)
            font_map = {}  # Map extracted font names to PDF font references
            for font_info in page_fonts:
                if len(font_info) >= 5:
                    basefont = font_info[3]  # e.g., "Helvetica", "Roboto-Bold"
                    ref_name = font_info[4]  # e.g., "F1", "F2"
                    font_map[basefont] = ref_name

            # Add replacement text
            for key, info in text_positions.items():
                if key.startswith(f"{page_num}_"):
                    rect = info["rect"]
                    replacement = info["replacement"]
                    span_info = info["span_info"]
                    original_font = span_info["font"]
                    font_size = span_info["size"]

                    # Strategy 1: Try to reuse the exact font from the page
                    font = None
                    if original_font in font_map:
                        try:
                            # Use page.insert_text with the font reference
                            baseline_offset = font_size * 0.8
                            point = (rect.x0, rect.y0 + baseline_offset)
                            page.insert_text(
                                point,
                                replacement,
                                fontname=font_map[original_font],
                                fontsize=font_size,
                                color=span_info.get("color", 0)
                            )
                            continue  # Skip TextWriter fallback
                        except Exception:
                            pass  # Fall through to TextWriter strategy

                    # Strategy 2: Try to load the font by name
                    tw = fitz.TextWriter(page.rect)

                    # Try fonts in order of preference
                    font_attempts = [
                        original_font,                    # Exact match
                        original_font.replace("-", ""),   # Try without dash (e.g., "RobotoBold")
                        "helv",                           # Helvetica fallback
                        "Times-Roman",                    # Times fallback
                    ]

                    for font_name in font_attempts:
                        try:
                            font = fitz.Font(font_name)
                            break
                        except Exception:
                            continue

                    # Strategy 3: Use base font as last resort
                    if font is None:
                        font = fitz.Font()

                    # Position at the top-left of the original rect, but adjust for baseline
                    baseline_offset = font_size * 0.8
                    point = (rect.x0, rect.y0 + baseline_offset)

                    # Append and write the text
                    tw.append(point, replacement, font=font, fontsize=font_size)
                    tw.write_text(page)

        # Preserve original metadata but add holomask attribution
        metadata = original_metadata.copy() if original_metadata else {}
        metadata["author"] = "holomask https://holofin.ai"
        doc.set_metadata(metadata)

        # Calculate statistics
        elements_by_type = {}
        for element in analysis_result.get("sensitive_elements", []):
            element_type = element.get("type", "Unknown")
            elements_by_type[element_type] = elements_by_type.get(element_type, 0) + 1

        analysis_result["anonymization_summary"] = {
            "total_elements_found": len(analysis_result.get("sensitive_elements", [])),
            "total_replacements": len(text_positions),
            "elements_by_type": elements_by_type,
            "ai_detected_count": len(analysis_result.get("sensitive_elements", [])),
            "actually_found_count": len(text_positions),
            "not_found_count": len(not_found_elements),
        }

        # Add debug info about elements that weren't found
        if not_found_elements:
            analysis_result["not_found_in_pdf"] = not_found_elements
            logger.warning(f"AI detected {len(not_found_elements)} elements that were not found in the actual PDF")

        # Save the anonymized PDF with full garbage collection and sanitization
        # garbage=4: Remove all unused/deleted objects to prevent recovery
        # clean=True: Sanitize PDF structure for maximum security
        # deflate=True: Compress for smaller file size
        doc.save(output_path, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    return analysis_result
