import logging
import math
import re

import fitz  # PyMuPDF

from app.mistral_analyzer import MistralAnalyzer

logger = logging.getLogger(__name__)


def _merge_line_rects(rects, y_tol: float = 2.0, x_gap: float = 6.0):
    """Merge the per-word rects that page.search_for returns for a multi-token phrase.

    search_for("16 bd des Italiens, 75009 Paris") returns one rect per word, all on the
    same line. Without merging, the full replacement string is written once per word-rect
    -> the replacement is stamped on top of itself many times ("Champs-Élysées" x6).
    We merge rects that sit on the same baseline with only a small horizontal gap into a
    single region (one occurrence); genuinely separate occurrences stay split.
    """
    if not rects:
        return rects
    ordered = sorted(rects, key=lambda r: (round(r.y0, 1), r.x0))
    merged = [fitz.Rect(ordered[0])]
    for r in ordered[1:]:
        cur = merged[-1]
        same_line = abs(r.y0 - cur.y0) <= y_tol and abs(r.y1 - cur.y1) <= y_tol
        if same_line and (r.x0 - cur.x1) <= x_gap:
            merged[-1] = cur | r  # union
        else:
            merged.append(fitz.Rect(r))
    return merged


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

            elif "Address" in element_type and "Email" not in element_type:
                # Addresses usually wrap across lines (street on one line, postal+city on
                # the next), so search_for() of the whole value finds nothing and the
                # address is left untouched. Split both value and replacement at the postal
                # code (last 4-5 digit run) and search the street and city parts separately.
                o_codes = list(re.finditer(r"\b\d{4,5}\b", original_text))
                r_codes = list(re.finditer(r"\b\d{4,5}\b", replacement))
                if o_codes and r_codes:
                    om, rm = o_codes[-1], r_codes[-1]
                    street_o = original_text[: om.start()].strip(" ,;")
                    city_o = original_text[om.start():].strip(" ,;")
                    street_r = replacement[: rm.start()].strip(" ,;")
                    city_r = replacement[rm.start():].strip(" ,;")
                    if street_o and street_r:
                        elements_to_search.append((street_o, street_r))
                    if city_o and city_r:
                        elements_to_search.append((city_o, city_r))

            if page_num < len(doc):
                page = doc[page_num]

                # Search for each element (full name + individual parts)
                for search_text, search_replacement in elements_to_search:
                    text_instances = _merge_line_rects(page.search_for(search_text))

                    if text_instances:
                        logger.info(f"Found {len(text_instances)} instance(s) of {element_type}: '{search_text}' on page {page_num + 1}")

                        # Store positions and properties for each instance
                        for rect in text_instances:
                            # Skip matches that overlap a region already slated for
                            # replacement. The name-splitting above searches the full
                            # name AND its last name separately; the last-name match lands
                            # inside the full-name span and would be written on top of it
                            # ("PIERRE PIERRE"). Standalone occurrences elsewhere don't
                            # overlap, so they are still replaced.
                            overlaps = False
                            for _k, _info in text_positions.items():
                                if not _k.startswith(f"{page_num}_"):
                                    continue
                                other = _info["rect"]
                                ix = min(rect.x1, other.x1) - max(rect.x0, other.x0)
                                iy = min(rect.y1, other.y1) - max(rect.y0, other.y0)
                                if ix > 0 and iy > 0:
                                    smaller = min(rect.get_area(), other.get_area())
                                    if smaller > 0 and (ix * iy) > 0.5 * smaller:
                                        overlaps = True
                                        break
                            if overlaps:
                                continue

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
                                                    "dir": line.get("dir", (1, 0)),
                                                }
                                                break
                                        if span_info:
                                            break
                                if span_info:
                                    break

                            if not span_info:
                                span_info = {"font": "helv", "size": 10, "color": 0, "dir": (1, 0)}

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
            written_rects = []  # regions already drawn on this page (write-time dedup)
            for key, info in text_positions.items():
                if key.startswith(f"{page_num}_"):
                    rect = info["rect"]
                    replacement = info["replacement"]
                    span_info = info["span_info"]
                    original_font = span_info["font"]
                    font_size = span_info["size"]

                    # Safety net: skip if a replacement was already drawn over this region.
                    # Different detected entities can share a trailing token (e.g. a city
                    # "Paris" inside an address ".. 75002 Paris"); without this guard both
                    # are drawn and the glyphs double up.
                    _dup = False
                    for wr in written_rects:
                        ix = min(rect.x1, wr.x1) - max(rect.x0, wr.x0)
                        iy = min(rect.y1, wr.y1) - max(rect.y0, wr.y0)
                        if ix > 0 and iy > 0:
                            smaller = min(rect.get_area(), wr.get_area())
                            if smaller > 0 and (ix * iy) >= 0.4 * smaller:
                                _dup = True
                                break
                    if _dup:
                        continue
                    written_rects.append(fitz.Rect(rect))

                    raw_color = span_info.get("color", 0)
                    try:
                        text_color = fitz.sRGB_to_pdf(raw_color) if raw_color else (0, 0, 0)
                    except Exception:
                        text_color = (0, 0, 0)

                    # Rotated text (e.g. the vertical reference strip printed up the page
                    # margin of many French statements). TextWriter writes horizontally,
                    # which would pile the replacement up garbled in the corner. Detect the
                    # writing direction and render with insert_textbox at the matching
                    # 90-degree rotation instead. The original was already white-redacted.
                    dirx, diry = span_info.get("dir", (1, 0))
                    angle = int(round(math.degrees(math.atan2(-diry, dirx)))) % 360
                    if angle != 0:
                        rot = int(round(angle / 90) * 90) % 360
                        box = fitz.Rect(rect)
                        # extend the box along the writing direction so longer synthetic
                        # values are not clipped (the margin around the strip is empty)
                        extra = max(60.0, font_size * len(replacement) * 0.65)
                        if rot in (90, 270):
                            box.y0 -= extra; box.y1 += extra
                        else:
                            box.x0 -= extra; box.x1 += extra
                        try:
                            page.insert_textbox(
                                box, replacement, fontname="helv", fontsize=font_size,
                                rotate=rot, color=text_color,
                            )
                        except Exception:
                            pass
                        continue

                    # NOTE: we intentionally do NOT reuse the page's embedded font
                    # reference (font_map) via page.insert_text. When the embedded font
                    # has a missing FontDescriptor (common in bank-statement PDFs), that
                    # call renders nothing without raising — blanking the field (e.g.
                    # IBAN/BIC). Instead we always render via TextWriter with a
                    # guaranteed-loadable font below.
                    font = None

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

                    # Preserve original text color (span color is a packed sRGB int)
                    raw_color = span_info.get("color", 0)
                    try:
                        text_color = fitz.sRGB_to_pdf(raw_color) if raw_color else (0, 0, 0)
                    except Exception:
                        text_color = (0, 0, 0)

                    # Append and write the text
                    tw.append(point, replacement, font=font, fontsize=font_size)
                    tw.write_text(page, color=text_color)

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
