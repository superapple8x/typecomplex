import fitz  # PyMuPDF
import nltk
import logging
import re # Added import
import urllib.error # Added for more specific exception handling
import unicodedata # For aggressive normalization
from thefuzz import fuzz # For fuzzy matching

# Configure logging
# logging.basicConfig(level=logging.INFO)
# Changed to DEBUG to see the new logs from previous step
logging.basicConfig(level=logging.DEBUG) 
logger = logging.getLogger(__name__)

# Original helper function for normalization (used for storing sentence text)
def normalize_sentence_text(text):
    """Replaces newline characters and multiple spaces with a single space, and strips."""
    text = text.replace('\n', ' ').replace('\r', ' ') # Replace various newline representations
    text = re.sub(r'\s+', ' ', text) # Replace multiple whitespace characters with a single space
    return text.strip()

# New aggressive normalization for robust matching logic
def aggressively_normalize_for_matching(text):
    """Aggressively normalizes text for robust matching."""
    if not isinstance(text, str): # Ensure text is a string
        text = str(text)

    # Decompose Unicode characters (e.g., accented chars)
    try:
        text = unicodedata.normalize('NFKD', text)
        # Filter to keep ASCII letters, digits, and a basic set of punctuation/spaces
        # This is less lossy than .encode('ascii', 'ignore') for letters.
        normalized_chars = []
        for char in text:
            if 'a' <= char.lower() <= 'z' or '0' <= char <= '9':
                normalized_chars.append(char)
            elif char in ' -\'".,;:!?()': # Common ASCII punc and space
                normalized_chars.append(char)
            # Other characters (like combining diacritics after NFKD, strange symbols) are dropped
        text = "".join(normalized_chars)
    except Exception as e:
        logger.error(f"Error during unicodedata normalization/filtering: {e} on text: {repr(text)[:100]}")
        pass 

    # Standardize various types of hyphens and dashes to a common hyphen
    text = re.sub(r'[\\u2010-\\u2015\\u2212\\uFE58\\uFE63\\uFF0D]', '-', text)
    # Standardize various types of apostrophes and single quotes
    text = re.sub(r'[\\u2018\\u2019\\u201B\\u2032\\uFF07]', "'", text)
    # Standardize various types of double quotes
    text = re.sub(r'[\\u201C\\u201D\\u201F\\u2033\\uFF02]', '"', text)
    
    text = text.lower() # Convert to lowercase for case-insensitive matching
    
    # Normalize all whitespace (including newlines, tabs) to a single space
    # and remove leading/trailing whitespace that might result from dropped chars.
    text = re.sub(r'\\s+', ' ', text).strip()
    
    return text

# Ensure NLTK resources are available (using corrected exception handling)
def ensure_nltk_resource(resource_path, package_name):
    try:
        nltk.data.find(resource_path)
        logger.debug(f"NLTK resource '{package_name}' found.")
    except LookupError: # NLTK uses LookupError if resource not found
        logger.warning(f"NLTK resource '{package_name}' not found at {resource_path}. Attempting download...")
        try:
            nltk.download(package_name)
            logger.info(f"NLTK resource '{package_name}' downloaded successfully.")
        except urllib.error.URLError as url_e: # Catch network errors specifically
            logger.error(f"Failed to download '{package_name}' due to a network error: {url_e}", exc_info=True)
        except OSError as os_e: # Catch potential filesystem errors
            logger.error(f"Failed to download '{package_name}' due to a filesystem error: {os_e}", exc_info=True)
        except Exception as download_e:
            # Catching other general exceptions during download
            logger.error(f"Failed to download '{package_name}': {download_e}", exc_info=True)
            # Depending on criticality, you might want to raise this error
            # raise RuntimeError(f"Failed to download essential NLTK resource: {package_name}") from download_e

ensure_nltk_resource('tokenizers/punkt', 'punkt')
ensure_nltk_resource('corpora/wordnet', 'wordnet') # Needed for some tokenizers/lemmatizers indirectly

# --- Constants ---
# TEXT_EXTRACTION_FLAGS = fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_INHIBIT_SPACES
TEXT_EXTRACTION_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_INHIBIT_SPACES # Removed TEXT_PRESERVE_LIGATURES

# Define a threshold for what constitutes a significant vertical gap (e.g., as a factor of line height)
# This will require testing and tuning. Let's start with a basic idea.
MIN_VERTICAL_GAP_FACTOR = 0.3 # e.g., if gap is > 0.3 * typical_line_height

def get_base_font_name(font_name_str: str) -> str:
    """Extracts a base font name by stripping common style suffixes."""
    if not isinstance(font_name_str, str):
        return "unknown"
    name = font_name_str
    # Common suffixes and patterns to strip. Order might matter.
    # More specific (like PS-BoldMT) before general (like Bold)
    suffixes_to_strip = [
        "PS-BoldMT", "PS-ItalicMT", "PSMT",
        "-BoldItalic", "-Bold", "-Italic", "-Regular", "-Light", "-Medium",
        " Bold Italic", " Bold", " Italic", " Regular", " Light", " Medium", # With space
        "MT", "PS" # General Monotype/PostScript indicators if at end
    ]
    for suffix in suffixes_to_strip:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break # Stop after first suffix match to avoid over-stripping
    
    # Remove any remaining common style keywords if they appear separated (e.g. "Arial Black" vs "Arial")
    # This is trickier; for now, focus on suffixes.
    # A common pattern is FontName,Style - e.g., "Arial,Bold"
    if ',' in name:
        name = name.split(',')[0]
        
    return name.strip()

def derive_coords_from_spans(spans_in_sentence, page_height, page_width):
    """
    Derives line segment coordinates by merging bboxes of spans that form a sentence.
    Spans are grouped by their original line, and then their bboxes are merged.
    """
    if not spans_in_sentence:
        return []

    # Group spans by their original line's y0 coordinate (approximate line grouping)
    # More robust would be to use line_bbox if consistently available and accurate
    lines_data = {}
    for span_info in spans_in_sentence:
        # Using the span's own bbox y0 as a primary key for line grouping initially
        # A more robust approach might use the line_bbox if available and reliable,
        # or cluster spans by y-coordinates.
        line_y0 = span_info['bbox'][1] 
        
        # Heuristic to group nearby y-coordinates into the same line,
        # e.g., by truncating to an integer or a small band.
        # For now, let's try direct y0, assuming spans on the same line have very close y0.
        # This might need refinement if y0 varies slightly for spans on the same visual line.
        # A better approach might be to use the line_dict['bbox'] from the original extraction if passed down.
        # For now, we use the span's line_bbox which we will ensure is collected.
        line_key_tuple = span_info.get('line_bbox')
        if not line_key_tuple: # Fallback if line_bbox is not there
             line_key_tuple = (span_info['bbox'][0], span_info['bbox'][1], span_info['bbox'][2], span_info['bbox'][3])


        if line_key_tuple not in lines_data:
            lines_data[line_key_tuple] = {
                'spans': [],
                'min_y0_on_line': span_info['bbox'][1], # Keep track of original min_y0 for sorting
             }
        lines_data[line_key_tuple]['spans'].append(span_info['bbox'])

    # Sort lines by their vertical position (min_y0_on_line)
    # The dictionary keys (line_key_tuple which are bboxes) don't guarantee order.
    # So, we convert to a list of tuples and sort by the y0 of the line_bbox (or span's y0 as proxy).
    # line_key_tuple is (x0,y0,x1,y1)
    sorted_line_keys = sorted(lines_data.keys(), key=lambda k: k[1])

    final_line_segment_coords = []
    for line_key in sorted_line_keys:
        span_bboxes_on_line = lines_data[line_key]['spans']
        if not span_bboxes_on_line:
            continue
        
        # Merge bboxes for the current line segment
        min_x0 = min(bbox[0] for bbox in span_bboxes_on_line)
        # y0 for the line segment should be taken from the line_key (which is the line's bbox y0)
        # or be the min of span y0s on this line if line_key isn't a reliable line bbox.
        # For now, using min_y0_on_line stored with the group.
        min_y0 = lines_data[line_key]['min_y0_on_line'] # More accurately, this should be line_key[1]
                                                       # if line_key is guaranteed to be the actual line bbox.
                                                       # Let's assume line_key[1] is the line's y0.
        min_y0_for_segment = line_key[1]


        max_x1 = max(bbox[2] for bbox in span_bboxes_on_line)
        # Similarly for y1, it should be the line_key[3] or max of span y1s.
        max_y1_for_segment = line_key[3]

        # Ensure coordinates are within page boundaries (safety check)
        min_x0 = max(0, min_x0)
        min_y0_for_segment = max(0, min_y0_for_segment)
        max_x1 = min(page_width, max_x1) if 'page_width' in locals() and page_width is not None else max_x1 # Use passed page_width
        max_y1_for_segment = min(page_height, max_y1_for_segment)


        segment_rect = (min_x0, min_y0_for_segment, max_x1, max_y1_for_segment)
        final_line_segment_coords.append(segment_rect)
        
    return final_line_segment_coords


def extract_text_and_sentence_coordinates(pdf_path):
    """
    Extracts text from a PDF using a span-first approach.
    Sentences are identified by grouping sequential spans based on layout heuristics
    (punctuation, gaps, font changes) within each text block.
    Coordinates are derived directly from these span groups.
    """
    sentence_map = []
    full_text_for_analysis = ""
    doc = None

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"Error opening PDF {pdf_path}: {e}")
        return "", []

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        page_width = page.rect.width
        page_height = page.rect.height
        
        try:
            # Get all words with detailed info to better infer sentence structure
            # Using get_text("words") gives more granular control than "dict" for this approach.
            # Format: [x0, y0, x1, y1, "word", block_no, line_no, word_no]
            # We'll process block by block.
            blocks = page.get_text("blocks", flags=TEXT_EXTRACTION_FLAGS) # Get blocks first

            for block_idx, block_dict_raw in enumerate(blocks):
                # block_dict_raw: (x0, y0, x1, y1, text_content, block_no, block_type)
                if block_dict_raw[6] != 0: # block_type, 0 for text
                    continue

                block_bbox = block_dict_raw[:4]
                block_no = block_dict_raw[5] # PyMuPDF block number for reference

                # Get spans (words) within this block
                # We need to iterate through lines and spans to get font info, which "words" doesn't directly give easily per span.
                # So, let's use "dict" for this block.
                # To get block specific dict, we can clip the page to block_bbox and get dict
                # This is complex. Alternative: use page.get_text("dict") and filter by block_no.
                
                # Reverting to page.get_text("dict") and filtering by block seems easier to manage span details
                page_dict = page.get_text("dict", flags=TEXT_EXTRACTION_FLAGS)
                
                current_block_spans_with_context = []
                for block_from_dict in page_dict.get("blocks", []):
                    if block_from_dict.get("number") == block_no and block_from_dict.get("type") == 0:
                        for line_dict in block_from_dict.get("lines", []):
                            line_bbox_tuple = tuple(line_dict.get("bbox", (0,0,0,0)))
                            for span_dict in line_dict.get("spans", []):
                                current_block_spans_with_context.append({
                                    'text': span_dict.get("text", ""),
                                    'bbox': tuple(span_dict.get("bbox", (0,0,0,0))),
                                    'font': span_dict.get("font", "Unknown"),
                                    'size': span_dict.get("size", 0.0),
                                    'flags': span_dict.get("flags", 0),
                                    'line_bbox': line_bbox_tuple,
                                    'block_no': block_no,
                                    'page_num': page_num
                                })
                        break

                if not current_block_spans_with_context:
                    continue

                # --- Refined NLTK Integration & Heuristic Application ---
                spans_for_subsequent_heuristic_processing = []
                for original_span_info in current_block_spans_with_context:
                    original_text = original_span_info.get('text', "")
                    if not isinstance(original_text, str):
                        original_text = str(original_text)

                    nltk_segments = []
                    if original_text.strip():
                        try:
                            nltk_segments = nltk.sent_tokenize(original_text)
                        except Exception as e_nltk:
                            logger.warning(f"NLTK sent_tokenize failed for span text '{original_text[:100]}...': {e_nltk}")
                            nltk_segments = [original_text] # Fallback
                    elif original_text: 
                        nltk_segments = [original_text]
                    
                    if len(nltk_segments) > 1:
                        # NLTK found multiple sentences within this single original span.
                        for segment_text in nltk_segments:
                            segment_text_stripped = segment_text.strip()
                            if not segment_text_stripped:
                                continue

                            highlight_coords = []
                            try:
                                # Search for this specific NLTK segment text on the page, clipped to the original span's bbox
                                clip_rect = fitz.Rect(original_span_info['bbox'])
                                # Using default flags for search_for, which include TEXT_NORMALIZE_WHITESPACE
                                segment_actual_rects = page.search_for(segment_text_stripped, clip=clip_rect)
                                
                                if not segment_actual_rects:
                                    logger.warning(f"NLTK segment '{segment_text_stripped[:50]}...' not found by search_for. Using original span bbox as fallback.")
                                    highlight_coords = [original_span_info['bbox']] # Fallback to original full span bbox
                                else:
                                    highlight_coords = [tuple(r) for r in segment_actual_rects]

                            except Exception as e_search:
                                logger.error(f"Error during page.search_for for NLTK segment '{segment_text_stripped[:50]}...': {e_search}. Using original span bbox.")
                                highlight_coords = [original_span_info['bbox']] # Fallback
                            
                            normalized_nltk_sentence = normalize_sentence_text(segment_text_stripped)
                            non_punc_chars = [char for char in normalized_nltk_sentence if char.isalnum()]

                            if len(non_punc_chars) > 1 and highlight_coords: # Junk filter and ensure coords exist
                                sentence_map.append({
                                    'text': normalized_nltk_sentence,
                                    'line_segment_coords': highlight_coords, # Directly use precise coordinates
                                    'page_num': page_num,
                                    'block_no': block_no,
                                })
                                if full_text_for_analysis and normalized_nltk_sentence:
                                    full_text_for_analysis += "\n\n"
                                full_text_for_analysis += normalized_nltk_sentence
                                logger.info(f"  SUCCESS (NLTK-searched): Sentence: '{normalized_nltk_sentence[:70]}...' Coords: {len(highlight_coords)} segments.")
                    
                    elif nltk_segments: # NLTK returned one segment (or fallback to original text)
                        # This original span (or its single NLTK equivalent) goes to the main heuristic loop
                        updated_span_info = original_span_info.copy()
                        updated_span_info['text'] = nltk_segments[0] # Use NLTK's version (e.g. stripped)
                        spans_for_subsequent_heuristic_processing.append(updated_span_info)
                
                # --- Existing Span-First Sentence Segmentation Logic (now operates on spans_for_subsequent_heuristic_processing) ---
                current_sentence_accumulated_spans = []
                last_span_info = None
                prev_span_info = None  # Track previous span for layout heuristics

                for i, span_info in enumerate(spans_for_subsequent_heuristic_processing):
                    current_sentence_accumulated_spans.append(span_info)
                    
                    sentence_boundary_detected = False
                    current_span_text_stripped = span_info['text'].strip()
                    is_last_span_in_block = (i == len(spans_for_subsequent_heuristic_processing) - 1)

                    # 1. Punctuation at the end of the current span's text
                    if current_span_text_stripped.endswith(('.', '!', '?')):
                        is_potential_abbreviation = False
                        if current_span_text_stripped.endswith('.'):
                            abbrev_pattern = r"""(^([A-Z][a-z]{0,3}|[A-Z])\.$|
                                                   ^(e\.g\.|i\.e\.|etc\.|vs\.|Fig\.|Figs\.|No\.|Nos\.|et al\.)|
                                                   \b[A-Z]\.(?:[A-Z]\.)*$)|\[\d+\]\.$""" 
                            if re.match(abbrev_pattern, current_span_text_stripped, re.IGNORECASE):
                                is_potential_abbreviation = True
                            elif len(current_span_text_stripped) <= 2 and current_span_text_stripped != '.': 
                                is_potential_abbreviation = True
                        
                        if not is_potential_abbreviation:
                            if is_last_span_in_block:
                                sentence_boundary_detected = True
                            elif i + 1 < len(spans_for_subsequent_heuristic_processing):
                                next_span_info = spans_for_subsequent_heuristic_processing[i+1]
                                next_span_text_stripped = next_span_info['text'].strip()
                                
                                if next_span_text_stripped and next_span_text_stripped[0].isupper():
                                    sentence_boundary_detected = True
                                elif not next_span_text_stripped: 
                                    sentence_boundary_detected = True

                    # 2. Layout heuristics: vertical gap, font-size/style, indent, hyphenation
                    if prev_span_info is not None and not sentence_boundary_detected:
                        prev_bbox = prev_span_info['bbox']
                        curr_bbox = span_info['bbox']
                        # Vertical gap detection
                        line_height = prev_bbox[3] - prev_bbox[1]
                        gap = curr_bbox[1] - prev_bbox[3]
                        if gap > MIN_VERTICAL_GAP_FACTOR * line_height:
                            sentence_boundary_detected = True
                            logger.debug(f"  BOUNDARY (Gap): gap={gap:.2f} > threshold")
                        # Font size change
                        prev_size = prev_span_info.get('size', 0)
                        curr_size = span_info.get('size', 0)
                        if not sentence_boundary_detected and abs(curr_size - prev_size) >= 1.0:
                            sentence_boundary_detected = True
                            logger.debug(f"  BOUNDARY (FontSize): {prev_size}->{curr_size}")
                        # Font style change
                        if not sentence_boundary_detected and prev_span_info.get('font') != span_info.get('font'):
                            sentence_boundary_detected = True
                            logger.debug(f"  BOUNDARY (FontStyle): '{prev_span_info.get('font')}'->'{span_info.get('font')}'")
                        # Indentation change detection
                        if not sentence_boundary_detected:
                            prev_x0 = prev_bbox[0]
                            curr_x0 = curr_bbox[0]
                            if abs(curr_x0 - prev_x0) > (0.5 * prev_size):
                                sentence_boundary_detected = True
                                logger.debug(f"  BOUNDARY (Indent): x0 {prev_x0:.1f}->{curr_x0:.1f}")
                        # Hyphenation merge
                        if not sentence_boundary_detected and prev_span_info['text'].strip().endswith('-') and current_span_text_stripped and current_span_text_stripped[0].islower():
                            # Merge hyphenated words (remove trailing hyphen)
                            current_sentence_accumulated_spans[-2]['text'] = current_sentence_accumulated_spans[-2]['text'].rstrip('-')
                            logger.debug("  CONTINUE (Hyphenation): merging hyphenated word")
                            sentence_boundary_detected = False
                    # After layout heuristics, skip split if next span starts lowercase (line wrap)
                    if sentence_boundary_detected and current_span_text_stripped and current_span_text_stripped[0].islower():
                        sentence_boundary_detected = False
                        logger.debug("  SKIP (Lowercase start): continuing sentence across wrap")
                    # 3. Mid-block sentence split
                    if sentence_boundary_detected and not is_last_span_in_block:
                        sentence_text_raw = "".join(s['text'] for s in current_sentence_accumulated_spans)
                        sentence_for_storage = normalize_sentence_text(sentence_text_raw)
                        non_punc_chars = [c for c in sentence_for_storage if c.isalnum()]
                        if sentence_for_storage and len(non_punc_chars) > 1:
                            coords = derive_coords_from_spans(current_sentence_accumulated_spans, page_height, page_width)
                            if coords:
                                sentence_map.append({
                                    'text': sentence_for_storage,
                                    'line_segment_coords': coords,
                                    'page_num': page_num,
                                    'block_no': block_no,
                                })
                                if full_text_for_analysis:
                                    full_text_for_analysis += "\n\n"
                                full_text_for_analysis += sentence_for_storage
                                logger.info(f"  SUCCESS (Span-First-Heuristic): '{sentence_for_storage[:70]}...' Coords: {len(coords)}")
                        current_sentence_accumulated_spans = []
                    # Update prev_span_info
                    prev_span_info = span_info
                
                # After iterating all spans in a block, if there are leftovers in current_sentence_accumulated_spans
                if current_sentence_accumulated_spans:
                    sentence_text_raw = "".join(s['text'] for s in current_sentence_accumulated_spans)
                    sentence_for_storage = normalize_sentence_text(sentence_text_raw)

                    is_junk_sentence = True
                    if sentence_for_storage:
                        non_punc_chars = [char for char in sentence_for_storage if char.isalnum()]
                        if len(non_punc_chars) > 1:
                            is_junk_sentence = False

                    if sentence_for_storage and not is_junk_sentence:
                        coords = derive_coords_from_spans(current_sentence_accumulated_spans, page_height, page_width) # Pass page_height & page_width
                        if coords:
                            sentence_map.append({
                                'text': sentence_for_storage,
                                'line_segment_coords': coords,
                                'page_num': page_num,
                                'block_no': block_no,
                            })
                            if full_text_for_analysis and sentence_for_storage:
                                full_text_for_analysis += "\n\n" 
                            full_text_for_analysis += sentence_for_storage
                            logger.info(f"  SUCCESS (Span-First EOF Block): Sentence: '{sentence_for_storage[:70]}...' Coords: {len(coords)} segments.")
                        else:
                            logger.warning(f"  EMPTY COORDS (Span-First EOF Block): Sentence: '{sentence_for_storage[:70]}...' but no coords derived.")
            
        except Exception as e_page:
            logger.error(f"Error processing page {page_num} of {pdf_path}: {e_page}", exc_info=True)
            # Continue to next page if one fails
            continue

    if doc:
        doc.close()
    
    logger.info(f"Span-First Extraction Complete for {pdf_path}. Total sentences mapped: {len(sentence_map)}")
    return full_text_for_analysis, sentence_map

# Define complexity colors (RGB tuples, 0-1 range)
COMPLEXITY_COLORS = {
    # Matches Tailwind bg-green-500, bg-lime-500, bg-yellow-500, bg-orange-500, bg-red-500, bg-gray-500
    "Very Simple": (0.133, 0.773, 0.369),  # rgb(34,197,94)
    "Simple": (0.518, 0.800, 0.086),       # rgb(132,204,22)
    "Moderate": (0.918, 0.702, 0.031),     # rgb(234,179,8)
    "Complex": (0.976, 0.451, 0.086),      # rgb(249,115,22)
    "Very Complex": (0.937, 0.267, 0.267), # rgb(239,68,68)
    "unknown": (0.424, 0.459, 0.490)       # rgb(108,117,125)
}

def generate_highlighted_pdf(original_pdf_path, analysis_results, sentence_coordinates_map, output_pdf_path):
    """
    Generates a new PDF with sentences highlighted based on their complexity scores.
    Relies on sentence_coordinates_map having 'line_segment_coords' and 'page_num'.
    The 'analysis_results' should have a 'sentences' list, where each item has a 'text'
    and 'color_class' (or similar scoring attribute like 'score' or 'level').
    The order of sentences in analysis_results.sentences MUST match the order
    in sentence_coordinates_map for correct highlighting.
    """
    doc = None
    try:
        doc = fitz.open(original_pdf_path)
    except Exception as e:
        logger.error(f"Error opening original PDF for highlighting {original_pdf_path}: {e}")
        return False

    # Create a mapping from normalized sentence text to its analysis result (color, score, etc.)
    # This assumes that `normalize_sentence_text` used in `extract_text_and_sentence_coordinates`
    # and the text stored in `analysis_results.sentences[i].text` are very similar or can be matched.
    # A robust way is to ensure analyze_text_complexity gets sentences in the exact same order
    # as they appear in sentence_coordinates_map.
    
    # The current tasks.py passes sentences_for_analysis = [entry['text'] for entry in sentence_coordinates_map]
    # So, the order *should* be preserved. We can iterate both lists in parallel.

    analysis_sentence_details = analysis_results.get('sentences', [])

    if len(sentence_coordinates_map) != len(analysis_sentence_details):
        logger.warning(f"Mismatch in sentence counts for highlighting: map={len(sentence_coordinates_map)}, analysis={len(analysis_sentence_details)}. Highlights may be incorrect.")
        # Decide how to handle: proceed with shorter list, or abort? For now, proceed cautiously.

    matched_highlight_count = 0
    # Iterate through sentence_coordinates_map, which contains the geometry
    for i, coord_entry in enumerate(sentence_coordinates_map):
        if i >= len(analysis_sentence_details): # Safety break if lists are mismatched
            logger.warning(f"Reached end of analysis_sentence_details ({i}) while coord_map has more entries. Stopping highlights.")
            break

        sentence_text_from_map = coord_entry.get('text')
        page_num = coord_entry.get('page_num')
        line_segments = coord_entry.get('line_segment_coords') # This is a list of bboxes

        analysis_detail_for_this_sentence = analysis_sentence_details[i]
        # sentence_text_from_analysis = analysis_detail_for_this_sentence.get('sentence') # The key is 'sentence'
        # It seems the key from analysis.py is 'sentence', not 'text' for the individual sentence string.
        # Let's verify structure of analysis_results['sentences'][i]
        # It is: {'sentence': '...', 'score': ..., 'level': ..., 'color_class': ...}
        sentence_text_from_analysis = analysis_detail_for_this_sentence.get('sentence')


        # Optional: Sanity check if texts match (after normalization if necessary)
        # if normalize_sentence_text(sentence_text_from_map).lower() != normalize_sentence_text(sentence_text_from_analysis).lower():
        #    logger.warning(f"Text mismatch for highlighting at index {i}: MAP='{sentence_text_from_map[:50]}...' != ANLS='{sentence_text_from_analysis[:50]}...'")
            # This indicates a potential de-sync if it happens often.

        if page_num is None or not line_segments:
            # logger.debug(f"Skipping sentence for highlight (no page/coords): '{sentence_text_from_map[:50]}...'")
            continue
        
        try:
            page = doc[page_num - 1] # page_num is 1-indexed
        except IndexError:
            logger.error(f"Invalid page number {page_num} for highlighting.")
            continue

        # color_class = analysis_detail_for_this_sentence.get('color_class', 'bg-gray-300') # Default color
        
        # # Determine PyMuPDF color from color_class string (e.g., 'bg-red-500')
        # highlight_color_rgb = None # PyMuPDF expects (r, g, b) tuple, values 0-1
        # if 'bg-red-500' in color_class: highlight_color_rgb = (1.0, 0.7, 0.7)  # Light Red
        # elif 'bg-yellow-500' in color_class: highlight_color_rgb = (1.0, 1.0, 0.7) # Light Yellow
        # elif 'bg-lime-500' in color_class: highlight_color_rgb = (0.7, 1.0, 0.7)  # Light Lime (used for simple)
        # elif 'bg-green-500' in color_class: highlight_color_rgb = (0.6, 0.9, 0.6) # Light Green (very simple)
        # elif 'bg-sky-500' in color_class: highlight_color_rgb = (0.7, 0.9, 1.0) # Light Blue (Moderate)
        # else: highlight_color_rgb = (0.9, 0.9, 0.9) # Light Gray for default/unknown

        sentence_level = analysis_detail_for_this_sentence.get('level', 'unknown') # Get the textual level
        highlight_color_rgb = COMPLEXITY_COLORS.get(sentence_level, COMPLEXITY_COLORS['unknown'])

        if not highlight_color_rgb:
            # logger.debug(f"No color determined for class '{color_class}' on sentence '{sentence_text_from_map[:50]}...'" )
            # The above log used color_class, changing to sentence_level for consistency
            logger.debug(f"No color determined for level '{sentence_level}' on sentence '{sentence_text_from_map[:50]}...'" )
            continue
            
        for segment_bbox in line_segments:
            if not all(isinstance(val, (int, float)) for val in segment_bbox) or len(segment_bbox) != 4:
                logger.warning(f"Invalid segment_bbox for highlighting: {segment_bbox} for sentence '{sentence_text_from_map[:30]}...'")
                continue
            
            try:
                # Ensure the rectangle has positive width and height
                if segment_bbox[0] < segment_bbox[2] and segment_bbox[1] < segment_bbox[3]:
                    highlight = page.add_highlight_annot(segment_bbox)
                    highlight.set_colors(stroke=highlight_color_rgb)
                    # Match UI opacity (30%) for highlight fill
                    highlight.update(opacity=0.3)
                    matched_highlight_count +=1
                else:
                    logger.warning(f"Skipping zero-area or invalid bbox for highlight: {segment_bbox} on sentence '{sentence_text_from_map[:30]}...'" )
            except Exception as e_annot:
                logger.error(f"Error adding highlight annotation for bbox {segment_bbox} on page {page_num}: {e_annot}", exc_info=True)
    
    logger.info(f"Highlighting process complete. Added {matched_highlight_count} highlight annotations total across all pages.")

    try:
        doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
        logger.info(f"Highlighted PDF saved to: {output_pdf_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving highlighted PDF {output_pdf_path}: {e}")
        return False
    finally:
        if doc:
            doc.close()

# Ensure NLTK resources (rest of the file remains the same) 