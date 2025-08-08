"""
Local task implementations using LocalTaskQueue instead of Celery
"""

from app.pdf_handler import extract_text_and_sentence_coordinates, generate_highlighted_pdf
from app.analysis import analyze_text_complexity
import os
from flask import current_app
import time
import fitz
import logging

logger = logging.getLogger(__name__)

def process_pdf_task(mock_task, file_path, original_filename, action='full_analysis', target_audience='Standard',
                     include_overview_page: bool = True,
                     overview_top_x_count: int = 5,
                     overview_top_x_type: str = "complex",
                     overview_show_visual_map: bool = True,
                     analysis_mode: str = 'best',
                     client_ip_address: str = None):
    """
    Local task to process a PDF (replaces Celery task):
    - If action is 'extract_text': Only extracts text and coordinates.
    - If action is 'full_analysis': Performs full extraction, analysis, and highlighting.
    """
    # Import Electron-mode app instance directly to avoid circular import issues
    from app.__init___electron import app  # type: ignore
    
    task_id = mock_task.request.id
    
    # Log Fitz version and path AT THE START of the task
    try:
        logger.info(f"Task {task_id}: PyMuPDF (fitz) version: {fitz.__version__}")
        logger.info(f"Task {task_id}: PyMuPDF (fitz) path: {fitz.__file__}")
    except Exception as log_exc:
        logger.error(f"Task {task_id}: Could not log fitz version/path: {log_exc}")

    logger.info(f"Starting PDF processing for: {original_filename} (Task ID: {task_id}) at path: {file_path}")
    
    # Application-level rate limiting removed. Provider limits only.

    try:
        # Step 1: Extract text and sentence coordinates from PDF
        mock_task.update_state(state='PROGRESS', meta={'current_step': 1, 'total_steps': 3, 'status_message': 'Extracting text from PDF...'})
        logger.info(f"Task {task_id}: Extracting text and coordinates from {file_path}...")
        plain_text, sentence_coordinates_map = extract_text_and_sentence_coordinates(file_path)

        if not plain_text and not sentence_coordinates_map and action == 'full_analysis':
            logger.error(f"Task {task_id}: Failed to extract any text or sentence map from {file_path} for full_analysis. Aborting.")
            raise ValueError("Failed to extract text from PDF for analysis. The document might be empty or corrupted.")
        elif not plain_text and action == 'full_analysis':
            logger.warning(f"Task {task_id}: No plain text extracted from {file_path} for full_analysis, but a sentence map was generated. Analysis might be limited.")

        logger.info(f"Task {task_id}: Text extraction complete for action '{action}'. Extracted {len(plain_text)} characters. Found {len(sentence_coordinates_map)} potential sentence coordinate entries.")

        if action == 'extract_text':
            mock_task.update_state(state='PROGRESS', meta={'current_step': 1, 'total_steps': 1, 'status_message': 'Text extracted successfully.'})
            extracted_data = {
                'original_filename': original_filename,
                'extracted_text': plain_text,
                'status_message': 'Text extracted successfully.',
                'action_performed': 'extract_text'
            }
            logger.info(f"Task {task_id}: Text extraction action complete. Result: {{original_filename: {original_filename}, text_length: {len(plain_text)}, action: {action}}}")
            return extracted_data

        # Continue with full_analysis specific steps
        num_sentences_with_coords = sum(1 for s in sentence_coordinates_map if s.get('line_segment_coords'))
        logger.info(f"Task {task_id}: {num_sentences_with_coords} sentences have coordinate data for full analysis.")

        # Step 2: Analyze text complexity
        mock_task.update_state(state='PROGRESS', meta={'current_step': 2, 'total_steps': 3, 'status_message': 'Analyzing text complexity...'})
        logger.info(f"Task {task_id}: Analyzing text complexity with mode '{analysis_mode}'...")
        # Extract sentence texts from sentence_coordinates_map for analysis
        sentences_for_analysis = [entry['text'] for entry in sentence_coordinates_map]
        logger.info(f"Task {task_id}: Extracted {len(sentences_for_analysis)} sentences for analysis.")
        # Pass both plain_text and sentences_for_analysis to analyze_text_complexity
        analysis_results = analyze_text_complexity(
            plain_text_for_doc_stats=plain_text,
            sentences_list=sentences_for_analysis,
            target_audience=target_audience,
            mode=analysis_mode
        )
        logger.info(f"Task {task_id}: Text analysis complete. Overall level: {analysis_results.get('overall_level',{}).get('description')}")
        num_sentences_analyzed = len(analysis_results.get('sentences', []))
        logger.info(f"Task {task_id}: Analyzed {num_sentences_analyzed} sentences.")

        # Step 3: Generate new PDF with highlights
        mock_task.update_state(state='PROGRESS', meta={'current_step': 3, 'total_steps': 3, 'status_message': 'Generating highlighted PDF...'})
        logger.info(f"Task {task_id}: Generating highlighted PDF...")
        
        # Ensure PROCESSED_FOLDER exists (though it should be created at app startup)
        # Use the Electron-mode Flask app's config directly to avoid missing context
        from app.__init___electron import app as electron_app  # local import to avoid cycles
        processed_folder_path = electron_app.config['PROCESSED_FOLDER']
        os.makedirs(processed_folder_path, exist_ok=True)

        highlighted_pdf_filename = f"{task_id}_highlighted.pdf"
        highlighted_pdf_full_path = os.path.join(processed_folder_path, highlighted_pdf_filename)

        success_highlighting = generate_highlighted_pdf(
            original_pdf_path=file_path, 
            analysis_results=analysis_results, 
            sentence_coordinates_map=sentence_coordinates_map, 
            output_pdf_path=highlighted_pdf_full_path,
            include_overview_page=include_overview_page,
            overview_top_x_count=overview_top_x_count,
            overview_top_x_type=overview_top_x_type,
            overview_show_visual_map=overview_show_visual_map
        )

        if not success_highlighting:
            logger.error(f"Task {task_id}: Failed to generate highlighted PDF and save to {highlighted_pdf_full_path}.")
            raise RuntimeError("Failed to generate the highlighted PDF document.")

        logger.info(f"Task {task_id}: Highlighted PDF generated: {highlighted_pdf_filename}")

        # Step 4: Prepare and return results
        result_data = {
            'original_filename': original_filename,
            'highlighted_pdf_filename': highlighted_pdf_filename,
            'overall_level': analysis_results.get('overall_level'),
            'readability_scores': analysis_results.get('readability_scores'),
            'num_sentences_analyzed': num_sentences_analyzed,
            'num_sentences_with_coords': num_sentences_with_coords,
            'processed_text_preview': plain_text[:200] + '...' if plain_text else 'No text extracted.',
            'status_message': 'PDF processed successfully.'
        }
        logger.info(f"Task {task_id}: Processing complete. Result: {result_data}")
        return result_data

    except Exception as e:
        logger.error(f"Error processing PDF (Task ID: {task_id}) for {original_filename}: {e}", exc_info=True)
        # Update task state to failure with more details
        mock_task.update_state(state='FAILURE', meta={
            'exc_type': type(e).__name__,
            'exc_message': str(e),
            'original_filename': original_filename,
            'status_message': f'Error processing PDF: {str(e)}'
        })
        # For the client, return a serializable error structure
        return {
            'original_filename': original_filename,
            'status_message': f'Error processing PDF: {str(e)}',
            'error': True,
            'error_details': f"{type(e).__name__}: {str(e)}"
        }


def add_task(x, y):
    """Simple addition task for testing"""
    return x + y