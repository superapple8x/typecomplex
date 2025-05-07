import fitz  # PyMuPDF
import nltk
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure 'punkt' tokenizer is available
try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    logger.info("NLTK 'punkt' tokenizer not found. Downloading...")
    nltk.download('punkt')
    logger.info("'punkt' tokenizer downloaded.")

def extract_text_and_sentence_coordinates(pdf_path):
    """
    Extracts all plain text from a PDF and attempts to map sentences
    to their page numbers and bounding box coordinates.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        tuple: (full_text, sentence_map)
            - full_text (str): The concatenated plain text from all pages.
            - sentence_map (list): A list of dictionaries, where each dict
              represents a sentence and contains:
                - 'text' (str): The sentence text.
                - 'page_num' (int): The 1-based page number.
                - 'coords' (tuple | None): The bounding box (x0, y0, x1, y1)
                                           or None if coords cannot be determined.
    """
    sentence_map = []
    doc = None
    try:
        doc = fitz.open(pdf_path)
        # === DIAGNOSTIC: Log attributes of the doc object ===
        logger.info(f"Attributes of doc object for {pdf_path}: {dir(doc)}")
        # === END DIAGNOSTIC ===
    except Exception as e:
        logger.error(f"Error opening PDF {pdf_path}: {e}")
        return "", []

    # Flags for text extraction and searching to maintain consistency
    text_extraction_flags = 3  # Corresponds to fitz.TEXT_PRESERVE_LIGATURES (1) | fitz.TEXT_PRESERVE_WHITESPACE (2)
    search_flags = 7           # Corresponds to fitz.TEXT_SEARCH_MATCH_WORDS (2) | fitz.TEXT_SEARCH_PRESERVE_LIGATURES (1) | fitz.TEXT_SEARCH_PRESERVE_WHITESPACE (4)

    # Workaround for 'Document' object has no attribute 'get_text'
    # Manually iterate through pages to get full text
    all_page_texts = []
    if doc.page_count > 0:
        for page_num_idx in range(doc.page_count):
            try:
                page_for_full_text = doc.load_page(page_num_idx) # Load each page
                all_page_texts.append(page_for_full_text.get_text(flags=text_extraction_flags))
            except Exception as e_page_text:
                logger.error(f"Error getting text from page {page_num_idx} for {pdf_path}: {e_page_text}")
                all_page_texts.append("") # Append empty string on error to not break join
    full_text = "\n".join(all_page_texts)
    
    # Keep track of how many times a sentence text has been found and processed on a given page
    processed_sentence_occurrences_on_page = {}

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        processed_sentence_occurrences_on_page[page_num] = {}
        
        try:
            # Extract text for NLTK using consistent flags
            page_text_for_nltk = page.get_text(flags=text_extraction_flags)
            if not page_text_for_nltk.strip():
                continue
                
            page_nltk_sentences = nltk.sent_tokenize(page_text_for_nltk)
        except Exception as e:
            logger.warning(f"Could not tokenize text on page {page_num} for PDF {pdf_path}: {e}")
            continue

        for sentence_text in page_nltk_sentences:
            sentence_text_clean = sentence_text.strip()
            if not sentence_text_clean:
                continue

            try:
                # Search for the cleaned sentence text on the current page
                # search_for returns a list of fitz.Rect objects (quads are also rects in this context)
                hit_rects = page.search_for(sentence_text_clean, flags=search_flags)
                
                current_occurrence_count = processed_sentence_occurrences_on_page[page_num].get(sentence_text_clean, 0)

                if hit_rects and current_occurrence_count < len(hit_rects):
                    # Get the rectangle for the current_occurrence_count-th occurrence
                    rect = hit_rects[current_occurrence_count]
                    sentence_map.append({
                        'text': sentence_text_clean,
                        'page_num': page_num,
                        'coords': tuple(rect)  # rect is (x0, y0, x1, y1)
                    })
                    processed_sentence_occurrences_on_page[page_num][sentence_text_clean] = current_occurrence_count + 1
                else:
                    # Sentence found by NLTK but not by PyMuPDF search_for, or all occurrences already processed
                    logger.warning(
                        f"Could not find coordinates for sentence on page {page_num}: '{sentence_text_clean[:100]}...'"
                        f" (Found by NLTK, but not PyMuPDF search_for or all occurrences processed)."
                        f" NLTK sentences: {len(page_nltk_sentences)}, PyMuPDF hits: {len(hit_rects) if hit_rects else 0}, Processed: {current_occurrence_count}"
                    )
                    sentence_map.append({
                        'text': sentence_text_clean,
                        'page_num': page_num,
                        'coords': None
                    })
            except Exception as e:
                logger.error(f"Error searching for sentence on page {page_num}: '{sentence_text_clean[:100]}...' - {e}")
                sentence_map.append({
                    'text': sentence_text_clean,
                    'page_num': page_num,
                    'coords': None
                })
    
    if doc:
        doc.close()
        
    return full_text, sentence_map

# Define complexity colors (RGB tuples, 0-1 range)
COMPLEXITY_COLORS = {
    "Very Simple": (0.68, 1, 0.18),  # Light Green (e.g., lime green)
    "Simple": (0.56, 0.93, 0.56),    # Standard Green (e.g., lightgreen)
    "Moderate": (1, 1, 0.0),         # Yellow
    "Complex": (1, 0.647, 0),        # Orange
    "Very Complex": (1, 0, 0),       # Red
    "unknown": (0.8, 0.8, 0.8)       # Grey for fallback
}

def generate_highlighted_pdf(original_pdf_path, analysis_results, sentence_coordinates_map, output_pdf_path):
    """
    Generates a new PDF with sentences highlighted based on their complexity scores.

    Args:
        original_pdf_path (str): Path to the original PDF.
        analysis_results (dict): The output from analyze_text_complexity,
                                 expected to contain a 'sentences' list with
                                 'text' and 'level' (complexity description string).
        sentence_coordinates_map (list): A list of sentence coordinate data,
                                         as returned by extract_text_and_sentence_coordinates.
        output_pdf_path (str): Path to save the new highlighted PDF.

    Returns:
        bool: True if successful, False otherwise.
    """
    doc = None
    try:
        doc = fitz.open(original_pdf_path)
        
        analyzed_sentences = analysis_results.get('sentences', [])
        if not analyzed_sentences:
            logger.warning(f"No sentences found in analysis_results for {original_pdf_path}. Output PDF will not have highlights.")
            # Save a copy of the original if no sentences to highlight
            doc.save(output_pdf_path)
            return True

        # Create a list of dicts from sentence_coordinates_map for easier management of 'used' status
        # Only include entries that have valid coordinates.
        available_coords_entries = []
        for i, map_entry in enumerate(sentence_coordinates_map):
            if map_entry.get('coords'): # Ensure 'coords' key exists and is not None
                available_coords_entries.append({
                    'text': map_entry['text'].strip(),
                    'page_num': map_entry['page_num'],
                    'coords': map_entry['coords'],
                    'original_map_idx': i, 
                    'used': False
                })

        for analyzed_sentence_info in analyzed_sentences:
            analyzed_text = analyzed_sentence_info['sentence'].strip()
            # 'level' from analysis.py is the descriptive string like "Moderate"
            level_description = analyzed_sentence_info.get('level', 'unknown') 
            color = COMPLEXITY_COLORS.get(level_description, COMPLEXITY_COLORS['unknown'])

            matched_coord_info = None
            match_internal_idx = -1

            # Find the first unused matching coordinate entry
            for idx, coord_entry in enumerate(available_coords_entries):
                if not coord_entry['used'] and coord_entry['text'] == analyzed_text:
                    matched_coord_info = coord_entry
                    match_internal_idx = idx
                    break
            
            if matched_coord_info:
                page_num = matched_coord_info['page_num']
                coords = matched_coord_info['coords'] # This is (x0, y0, x1, y1)
                
                if page_num <= 0 or page_num > doc.page_count:
                    logger.warning(f"Invalid page number {page_num} for sentence \'{analyzed_text[:50]}...\'. Skipping highlight.")
                    available_coords_entries[match_internal_idx]['used'] = True # Mark as used to avoid re-processing
                    continue

                page = doc[page_num - 1] # PyMuPDF page indexing is 0-based
                
                # Create a fitz.Rect for highlighting
                highlight_rect = fitz.Rect(coords[0], coords[1], coords[2], coords[3])
                
                # Add highlight annotation (default color is yellow)
                annot = page.add_highlight_annot(highlight_rect)
                
                if annot: # Check if annotation was successfully created
                    try:
                        # Set the desired color for the highlight
                        # For highlights, 'stroke' color is what's typically visible
                        annot.set_colors(stroke=color) 
                        annot.update() # Apply the changes to the annotation
                    except Exception as e_annot_update:
                        logger.error(f"Error updating highlight annotation color for sentence \'{analyzed_text[:50]}...\' on page {page_num}: {e_annot_update}")
                else:
                    logger.warning(f"Could not create highlight annotation for sentence \'{analyzed_text[:50]}...\' on page {page_num}.")

                available_coords_entries[match_internal_idx]['used'] = True
            else:
                logger.warning(f"Could not find coordinates for analyzed sentence (or already used): \'{analyzed_text[:50]}...\'")

        doc.save(output_pdf_path)
        logger.info(f"Highlighted PDF saved to {output_pdf_path}")
        return True

    except Exception as e:
        logger.error(f"Error generating highlighted PDF {output_pdf_path} from {original_pdf_path}: {e}", exc_info=True)
        return False
    finally:
        if doc:
            doc.close() 