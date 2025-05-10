import fitz  # PyMuPDF
import nltk
import logging
import re # Added import
import urllib.error # Added for more specific exception handling
import unicodedata # For aggressive normalization
from thefuzz import fuzz # For fuzzy matching
import difflib # Added for word-sequence matching fallback

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
TEXT_EXTRACTION_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE # Removed TEXT_PRESERVE_LIGATURES and TEXT_INHIBIT_SPACES

# Define a threshold for what constitutes a significant vertical gap (e.g., as a factor of line height)
# This will require testing and tuning. Let's start with a basic idea.
MIN_VERTICAL_GAP_FACTOR = 0.3 # e.g., if gap is > 0.3 * typical_line_height

# Helper function to group individual word bounding boxes into line segments
def group_word_bboxes_into_lines(matched_word_data_tuples: list, page_width: float, page_height: float) -> list[tuple[float, float, float, float]]:
    """
    Groups a list of word data tuples (from page.get_text("words")) into line segments.
    Each word_data_tuple is expected to be [x0, y0, x1, y1, text, block_no, line_no, word_no].
    Line segments are formed by merging bboxes of words on the same original line_no.
    """
    if not matched_word_data_tuples:
        return []

    lines_dict = {}  # key: line_no, value: list of fitz.Rect for words on that line
    for word_data in matched_word_data_tuples:
        try:
            line_no = word_data[6]  # line_no from get_text("words")
            word_rect = fitz.Rect(word_data[0], word_data[1], word_data[2], word_data[3])
            if line_no not in lines_dict:
                lines_dict[line_no] = []
            lines_dict[line_no].append(word_rect)
        except IndexError:
            logger.warning(f"Word data tuple has unexpected format: {word_data}")
            continue
        except Exception as e_word_proc:
            logger.warning(f"Error processing word_data {word_data}: {e_word_proc}")
            continue


    final_line_segment_coords = []
    if not lines_dict: # if, for some reason, lines_dict ended up empty
        return []
        
    sorted_line_nos = sorted(lines_dict.keys())

    for line_no in sorted_line_nos:
        rects_on_line = lines_dict[line_no]
        if not rects_on_line:
            continue
        
        # Merge bboxes for the current line segment
        min_x0 = min(r.x0 for r in rects_on_line)
        # Use the y0 of the first word on the line as the line's y0. Could also average or take min.
        min_y0 = min(r.y0 for r in rects_on_line) 
        max_x1 = max(r.x1 for r in rects_on_line)
        # Use the y1 of the last word on the line (or max y1 on line).
        max_y1 = max(r.y1 for r in rects_on_line)

        # Ensure coordinates are within page boundaries (safety check)
        min_x0 = max(0, min_x0)
        min_y0 = max(0, min_y0)
        max_x1 = min(page_width, max_x1)
        max_y1 = min(page_height, max_y1)
        
        # Ensure the rectangle has positive width and height
        if min_x0 < max_x1 and min_y0 < max_y1:
            final_line_segment_coords.append((min_x0, min_y0, max_x1, max_y1))
            
    return final_line_segment_coords

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
            # Get text blocks. Each block_data_tuple is (x0, y0, x1, y1, text_content, block_no, block_type)
            # text_content has lines separated by literal \n.
            blocks = page.get_text("blocks", flags=TEXT_EXTRACTION_FLAGS)

            for block_data_tuple in blocks:
                if block_data_tuple[6] != 0: # block_type, 0 for text block
                    continue

                block_bbox_tuple = block_data_tuple[0:4]
                block_text_from_pymupdf = block_data_tuple[4]
                block_no_for_map = block_data_tuple[5]

                # Process block_text_from_pymupdf for NLTK:
                # Replace literal '\n' newlines (that PyMuPDF uses to separate lines within a block) with spaces.
                processed_block_text_for_nltk = block_text_from_pymupdf.replace('\n', ' ').strip()
                # Consolidate multiple spaces that might have resulted from the replacement or original text.
                processed_block_text_for_nltk = re.sub(r'\s+', ' ', processed_block_text_for_nltk)

                if not processed_block_text_for_nltk:
                    logger.debug(f"Skipping empty block after processing. Page {page_num}, Block {block_no_for_map}")
                    continue

                try:
                    nltk_sentences_in_block = nltk.sent_tokenize(processed_block_text_for_nltk)
                except Exception as e_nltk:
                    logger.warning(f"NLTK sent_tokenize failed for block. Page {page_num}, Block {block_no_for_map}. Text: '{processed_block_text_for_nltk[:100]}...'. Error: {e_nltk}")
                    nltk_sentences_in_block = [processed_block_text_for_nltk] # Fallback: treat whole block as one sentence

                for sentence_text_raw_from_nltk in nltk_sentences_in_block:
                    sentence_for_search = sentence_text_raw_from_nltk.strip() # Keep original NLTK output
                    
                    if not sentence_for_search: # Skip empty strings that NLTK might produce
                        continue

                    # normalized_sentence_for_storage = normalize_sentence_text(sentence_for_search_and_storage)
                    # Normalize for storage (used in sentence_map and full_text_for_analysis)
                    normalized_sentence_for_storage = normalize_sentence_text(sentence_for_search)

                    # Create a version of the sentence string specifically for PyMuPDF search_for:
                    # 1. Replace various hyphens/dashes with a standard hyphen-minus.
                    # 2. Normalize all whitespace to single spaces.
                    # This makes the search string more tolerant to variations in the PDF.
                    search_string_variant = re.sub(r'[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]', '-', sentence_for_search) # Normalize hyphens
                    search_string_variant = re.sub(r'\s+', ' ', search_string_variant).strip() # Normalize whitespace
                    
                    highlight_coords_for_sentence = []
                    try:
                        search_clip_rect = fitz.Rect(block_bbox_tuple)
                        # Use the search_string_variant for searching first
                        found_rects = page.search_for(search_string_variant, clip=search_clip_rect)
                        
                        # If the variant search failed and the variant was different from the original NLTK sentence,
                        # try searching with the original NLTK sentence text as a fallback.
                        if not found_rects and search_string_variant != sentence_for_search:
                            logger.debug(f"Search variant '{search_string_variant[:60]}...' failed or returned no rects. Trying original NLTK sentence '{sentence_for_search[:60]}...' for P{page_num} B{block_no_for_map}")
                            found_rects = page.search_for(sentence_for_search, clip=search_clip_rect)

                        if found_rects:
                            highlight_coords_for_sentence = [tuple(r) for r in found_rects]
                        else:
                            # --- Word-level fallback using difflib ---
                            logger.warning(f"Block-Search: Sentence '{sentence_for_search[:60]}...' NOT FOUND by page.search_for(). Attempting word-level fallback. P{page_num} B{block_no_for_map}.")
                            
                            try:
                                block_words_data = page.get_text("words", clip=search_clip_rect, sort=True)
                                # Prepare word lists for matching (lowercase, ignore empty)
                                page_word_texts_for_match = [w[4].lower() for w in block_words_data if w[4] and w[4].strip()]
                                nltk_sentence_words_for_match = [word.lower() for word in sentence_for_search.split() if word and word.strip()]

                                if page_word_texts_for_match and nltk_sentence_words_for_match:
                                    matcher = difflib.SequenceMatcher(None, page_word_texts_for_match, nltk_sentence_words_for_match, autojunk=False)
                                    match = matcher.find_longest_match(0, len(page_word_texts_for_match), 0, len(nltk_sentence_words_for_match))

                                    # Check if the longest match covers all words of the NLTK sentence
                                    is_full_nltk_sentence_match = (match.size > 0 and \
                                                                   match.size == len(nltk_sentence_words_for_match) and \
                                                                   match.b == 0) # Match starts at the beginning of nltk_sentence_words

                                    if is_full_nltk_sentence_match:
                                        # Get the corresponding original word data (with coordinates)
                                        matched_page_word_data_tuples = block_words_data[match.a : match.a + match.size]
                                        
                                        derived_coords = group_word_bboxes_into_lines(matched_page_word_data_tuples, page_width, page_height)
                                        
                                        if derived_coords:
                                            highlight_coords_for_sentence = derived_coords
                                            logger.info(f"  SUCCESS (Word-Fallback): Found coords for '{sentence_for_search[:60]}...'. P{page_num} B{block_no_for_map}. Coords: {len(derived_coords)}")
                                        else:
                                            logger.warning(f"  FAILURE (Word-Fallback): group_word_bboxes_into_lines returned no coords for '{sentence_for_search[:60]}...'. P{page_num} B{block_no_for_map}.")
                                    else:
                                        logger.warning(f"  FAILURE (Word-Fallback): No sufficient word sequence match for '{sentence_for_search[:60]}...'. Match size: {match.size}/{len(nltk_sentence_words_for_match)}. P{page_num} B{block_no_for_map}.")
                                else:
                                    logger.warning(f"  SKIPPED (Word-Fallback): Empty word list from page or NLTK sentence for '{sentence_for_search[:60]}...'. P{page_num} B{block_no_for_map}.")
                            except Exception as e_fallback:
                                logger.error(f"Error during word-level fallback for '{sentence_for_search[:60]}...': {e_fallback}", exc_info=True)
                            
                            # If fallback also failed, original warning about not found / stored w/o coords applies implicitly by highlight_coords_for_sentence remaining empty.
                            # The primary "NOT FOUND" log is now before this block. We only log fallback success/specific failure here.
                            # If highlight_coords_for_sentence is still empty, the later logs (STORED W/O COORDS) will indicate this.
                            # Re-evaluate: The original "NOT FOUND by search_for" is above.
                            # If we reach here and highlight_coords_for_sentence is STILL empty, then the original log stands.
                            # We should only log a "final" failure if the fallback also failed.

                            if not highlight_coords_for_sentence:
                                # This log is now somewhat redundant if STORED W/O COORDS is still active later.
                                # Let's rely on the subsequent checks and logs for "STORED W/O COORDS".
                                pass # logger.warning(f"Block-Search & Word-Fallback: Sentence '{sentence_for_search[:60]}...': STILL NOT FOUND. P{page_num} B{block_no_for_map}.")


                            # Fallback: if it's the only sentence NLTK found in this block (and block wasn't just whitespace originally)
                            # This original fallback should only apply if page.search_for AND word-level fallback failed.
                            if not highlight_coords_for_sentence and len(nltk_sentences_in_block) == 1 and block_text_from_pymupdf.strip():
                                logger.info(f"Using block bbox as FINAL fallback for single sentence not found by any method: '{sentence_for_search[:60]}...':")
                                highlight_coords_for_sentence = [block_bbox_tuple]
                            # Otherwise, highlight_coords_for_sentence remains empty.
                                            
                    except Exception as e_search:
                        logger.error(f"Error during page.search_for() for block-level sentence '{sentence_for_search[:60]}...': {e_search}. P{page_num} B{block_no_for_map}", exc_info=True)

                    # Add to sentence_map if text is valid (non-junk)
                    # Store sentence text even if coordinates were not found, so it can be analyzed.
                    non_punc_chars = [char for char in normalized_sentence_for_storage if char.isalnum()]
                    if len(non_punc_chars) > 1: # Basic junk filter
                        sentence_map.append({
                            'text': normalized_sentence_for_storage,
                            'line_segment_coords': highlight_coords_for_sentence, # Will be empty if not found
                            'page_num': page_num,
                            'block_no': block_no_for_map,
                        })
                        
                        # Build full_text_for_analysis (used by analysis.py)
                        if full_text_for_analysis and normalized_sentence_for_storage: # Check if not empty
                            full_text_for_analysis += "\n\n" # Standard separator for analysis
                        full_text_for_analysis += normalized_sentence_for_storage

                        if highlight_coords_for_sentence:
                            logger.info(f"  SUCCESS (Block-NLTK): '{normalized_sentence_for_storage[:70]}...' Coords: {len(highlight_coords_for_sentence)}. P{page_num} B{block_no_for_map}")
                        else:
                            logger.warning(f"  STORED W/O COORDS (Block-NLTK): '{normalized_sentence_for_storage[:70]}...'. P{page_num} B{block_no_for_map}")
                    else:
                        logger.debug(f"Skipping junk sentence: '{normalized_sentence_for_storage[:70]}...' P{page_num} B{block_no_for_map}")
            # End of loop for sentences within a block
        # End of loop for blocks within a page
            
        except Exception as e_page:
            logger.error(f"Error processing page {page_num} of {pdf_path}: {e_page}", exc_info=True)
            # Continue to next page if one fails
            continue

    if doc:
        doc.close()
    
    logger.info(f"Block-Level NLTK Extraction Complete for {pdf_path}. Total sentences mapped: {len(sentence_map)}")
    return full_text_for_analysis, sentence_map

# Define complexity colors (RGB tuples, 0-1 range)
# Keys are now Tailwind CSS class names to match analysis.py output
COMPLEXITY_COLORS = {
    "bg-green-500": (0.133, 0.773, 0.369),  # Tailwind green-500 (Very Simple)
    "bg-lime-500": (0.518, 0.800, 0.086),   # Tailwind lime-500 (Simple)
    "bg-yellow-500": (0.918, 0.702, 0.031), # Tailwind yellow-500 (Moderate)
    "bg-orange-500": (0.976, 0.451, 0.086), # Tailwind orange-500 (Complex)
    "bg-red-500": (0.937, 0.267, 0.267),   # Tailwind red-500 (Very Complex)
    "bg-gray-500": (0.424, 0.459, 0.490),   # Tailwind gray-500 (Unknown/Default)
    "bg-gray-600": (0.325, 0.361, 0.408)    # Tailwind gray-600 (e.g. for "No sentences found" or "Analysis cancelled") - Added for completeness
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

        # Use the color_class directly from analysis results
        color_class_from_analysis = analysis_detail_for_this_sentence.get('color_class', 'bg-gray-500') # Default to gray
        highlight_color_rgb = COMPLEXITY_COLORS.get(color_class_from_analysis, COMPLEXITY_COLORS.get('bg-gray-500')) # Fallback to gray key if class not found

        if not highlight_color_rgb:
            # logger.debug(f"No color determined for class '{color_class}' on sentence '{sentence_text_from_map[:50]}...'" )
            # The above log used color_class, changing to sentence_level for consistency
            # logger.debug(f"No color determined for level '{sentence_level}' on sentence '{sentence_text_from_map[:50]}...'" )
            # Corrected log to use color_class_from_analysis
            logger.debug(f"No PyMuPDF RGB color determined for color_class '{color_class_from_analysis}' on sentence '{sentence_text_from_map[:50]}...'. Using default.")
            # If COMPLEXITY_COLORS.get('bg-gray-500') also somehow failed, though it shouldn't:
            highlight_color_rgb = (0.424, 0.459, 0.490) # Explicit default gray
            # continue # Original code would continue; let's ensure it highlights with a default gray instead.

        # Add sentence start/end markers
        if line_segments:
            # Define marker properties
            marker_radius = 1.5  # Radius in points
            start_marker_color = (0.0, 0.0, 1.0)  # Blue for start (RGB 0-1 range)
            end_marker_color = (1.0, 0.0, 0.0)    # Red for end (RGB 0-1 range)
            marker_opacity = 0.7

            # Start marker: at the top-left of the first segment
            first_segment_bbox = line_segments[0]
            if all(isinstance(val, (int, float)) for val in first_segment_bbox) and len(first_segment_bbox) == 4:
                start_marker_cx = first_segment_bbox[0]
                start_marker_cy = first_segment_bbox[1]
                # Create a small square for the circle's bounding box
                start_marker_rect = fitz.Rect(
                    start_marker_cx - marker_radius,
                    start_marker_cy - marker_radius,
                    start_marker_cx + marker_radius,
                    start_marker_cy + marker_radius
                )
                if start_marker_rect.is_valid and not start_marker_rect.is_empty:
                    try:
                        start_annot = page.add_circle_annot(start_marker_rect)
                        start_annot.set_colors(stroke=start_marker_color, fill=start_marker_color)
                        start_annot.update(opacity=marker_opacity)
                    except Exception as e_marker:
                        logger.warning(f"Could not add start marker for sentence '{sentence_text_from_map[:30]}...': {e_marker}")
            else:
                logger.warning(f"Invalid first_segment_bbox for start marker: {first_segment_bbox} for sentence '{sentence_text_from_map[:30]}...'")

            # End marker: at the bottom-right of the last segment
            last_segment_bbox = line_segments[-1]
            if all(isinstance(val, (int, float)) for val in last_segment_bbox) and len(last_segment_bbox) == 4:
                end_marker_cx = last_segment_bbox[2]
                end_marker_cy = last_segment_bbox[3]
                # Create a small square for the circle's bounding box
                end_marker_rect = fitz.Rect(
                    end_marker_cx - marker_radius,
                    end_marker_cy - marker_radius,
                    end_marker_cx + marker_radius,
                    end_marker_cy + marker_radius
                )
                if end_marker_rect.is_valid and not end_marker_rect.is_empty:
                    try:
                        end_annot = page.add_circle_annot(end_marker_rect)
                        end_annot.set_colors(stroke=end_marker_color, fill=end_marker_color)
                        end_annot.update(opacity=marker_opacity)
                    except Exception as e_marker:
                        logger.warning(f"Could not add end marker for sentence '{sentence_text_from_map[:30]}...': {e_marker}")
            else:
                logger.warning(f"Invalid last_segment_bbox for end marker: {last_segment_bbox} for sentence '{sentence_text_from_map[:30]}...'")
            
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
        logger.info(f"Highlighted PDF successfully saved to: {output_pdf_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving highlighted PDF to {output_pdf_path}: {e}", exc_info=True)
        return False
    finally:
        if doc:
            doc.close()

# Ensure NLTK resources (rest of the file remains the same) 