import logging # Add logging
from flask import render_template, request, jsonify, Response, send_from_directory, current_app # Import Response, send_from_directory, current_app
from app import app, celery, rate_limiter # Import celery AND rate_limiter
# Import the analysis and synonym functions
from app.analysis import analyze_text_complexity, analyze_single_spacy_sentence, AUDIENCE_PROFILES, get_active_spacy_model # UPDATED: Removed nlp, Added get_active_spacy_model
from app.synonyms import get_ranked_synonyms
# Import the DeepSeek synonym function (complexity enhancement was unused)
from app.deepseek_analysis import recommend_synonym, get_rewrite_suggestion # Import new function
# frequency module is loaded automatically when synonyms/analysis imports it if needed
import json # Import json for streaming
# Import the task manager
from app import task_manager # This might be replaced or augmented by Celery's task management

# Import for PDF handling
import os
import uuid
from werkzeug.utils import secure_filename
from app.tasks import process_pdf_task, add as add_task # Import Celery tasks

# Get the absolute path to the project directory (assuming this file is in app/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Configuration for PDF uploads
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads') 
PROCESSED_FOLDER = os.path.join(BASE_DIR, 'processed_pdfs')
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
# Ensure these directories exist when the app starts
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)
    app.logger.info(f"Upload folder set to: {app.config['UPLOAD_FOLDER']}")
    app.logger.info(f"Processed folder set to: {app.config['PROCESSED_FOLDER']}")
except OSError as e:
    app.logger.error(f"Error creating UPLOAD_FOLDER or PROCESSED_FOLDER: {e}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Renders the main page."""
    # This will look for index.html in the 'templates' folder
    return render_template('index.html')

# /analyze endpoint (POST)
@app.route('/analyze', methods=['POST'])
def analyze_text():
    """
    Analyzes the text complexity using statistical methods and optionally
    performs context-aware analysis using Gemini based on frontend inputs.
    This endpoint is now primarily for overall analysis (readability scores, etc.)
    and can return all sentence results at once for smaller texts or initial load.
    Accepts an 'analysisId' for cancellation tracking.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    target_audience_profile = data.get('target_audience', 'Standard')
    context_awareness_enabled = data.get('context_awareness_enabled', False) # Keep the toggle state
    analysis_id = data.get('analysisId') # <<< Get analysisId from request
    mode = data.get('mode', 'better') # <<< NEW: Get mode, default to 'better'

    # --- Rate Limiting Check ---
    client_ip = request.remote_addr
    if not rate_limiter.check_and_update_limit(client_ip, mode):
        logging.warning(f"Rate limit exceeded for IP: {client_ip}, Mode: {mode} on /analyze route.")
        return jsonify({"error": f"Rate limit exceeded for {mode} analysis. Please try again later."}), 429
    # --- End Rate Limiting Check ---

    logging.info(f"Received analysis request (ID: {analysis_id}). Mode: {mode}, Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}") # Added mode to log

    # --- Register Task ---
    if analysis_id: # Only register if ID is provided
        task_manager.register_task(analysis_id)
    else:
        logging.warning("'/analyze' request received without analysisId.")


    analysis_results = None # Initialize
    try:
        # Split the input text into sentences for per-sentence analysis
        try:
            # Get the spaCy model appropriate for the current analysis mode
            active_nlp = get_active_spacy_model(mode)
            if not active_nlp:
                logging.error(f"spaCy model for mode '{mode}' not loaded. Cannot perform analysis for ID: {analysis_id}.")
                # task_manager.remove_task should be handled by finally block
                return jsonify({"error": f"Analysis service not available (spaCy model for mode '{mode}' not loaded)."}), 500
            
            doc_for_sentences = active_nlp(text_to_analyze)
            sentences_list = [sent.text for sent in doc_for_sentences.sents]
        except Exception as e_segment: # More specific exception catch for segmentation
            logging.warning(f"spaCy segmentation failed for mode '{mode}' (ID: {analysis_id}): {e_segment}. Falling back to NLTK.")
            # Fallback: use NLTK if spaCy segmentation fails
            from nltk import sent_tokenize
            sentences_list = sent_tokenize(text_to_analyze)
        analysis_results = analyze_text_complexity(
            plain_text_for_doc_stats=text_to_analyze,
            sentences_list=sentences_list,
            target_audience=target_audience_profile,
            mode=mode,
            analysis_id=analysis_id
        )
    except Exception as e:
        logging.error(f"Error during full analysis (ID: {analysis_id}): {e}", exc_info=True)
        # Ensure task is removed even on error
        if analysis_id:
            task_manager.remove_task(analysis_id)
        return jsonify({"error": f"Server error during analysis: {e}"}), 500
    finally:
        # --- Remove Task ---
        if analysis_id:
            task_manager.remove_task(analysis_id)

    # --- Return Results ---
    # Check if analysis was cancelled internally
    if analysis_results and analysis_results.get("overall_level", {}).get("description") == "Analysis cancelled":
         logging.info(f"Analysis (ID: {analysis_id}) was cancelled. Returning cancelled status.")
         # Return a specific response or the partial results indicating cancellation
         return jsonify(analysis_results) # Return the result dict which indicates cancellation

    logging.info(f"Analysis (ID: {analysis_id}) completed successfully.")
    return jsonify(analysis_results)

# /analyze_sequential endpoint (POST)
@app.route('/analyze_sequential', methods=['POST'])
def analyze_text_sequential():
    """
    Analyzes text complexity sentence by sentence and streams results back.
    Uses 'fast' mode for quick per-sentence analysis.
    Accepts an 'analysisId' for cancellation tracking.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze_sequential' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    target_audience_profile = data.get('target_audience', 'Standard')
    context_awareness_enabled = data.get('context_awareness_enabled', False)
    analysis_id = data.get('analysisId') # <<< Get analysisId from request

    logging.info(f"Received sequential analysis request (ID: {analysis_id}). Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    # For sequential analysis, we typically use the 'fast' mode's spaCy model for quick sentence splitting.
    # The actual per-sentence complexity in analyze_single_spacy_sentence is hardcoded to 'fast' for this endpoint.
    active_nlp_for_sequential = get_active_spacy_model('fast') 

    if not active_nlp_for_sequential:
         logging.error(f"spaCy model for 'fast' mode not loaded. Cannot perform sequential analysis (ID: {analysis_id}).")
         return jsonify({"error": "Analysis service not available (spaCy model for 'fast' mode not loaded)."}), 500

    if not analysis_id:
        logging.error("'/analyze_sequential' request received without analysisId.")
        return jsonify({"error": "Missing 'analysisId' in request body"}), 400

    def generate_results():
        """Generator function to yield sentence analysis results."""
        # --- Register Task ---
        task_manager.register_task(analysis_id)
        try:
            # --- Check for immediate cancellation ---
            if task_manager.is_cancelled(analysis_id):
                logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled before starting.")
                yield json.dumps({"status": "cancelled"}) + "\n"
                return

            # --- Check cancellation before potentially long spaCy processing ---
            logging.debug(f"Task {analysis_id}: Starting spaCy processing for sequential.")
            doc = active_nlp_for_sequential(text_to_analyze) # Use the fetched 'fast' model
            logging.debug(f"Task {analysis_id}: Finished spaCy processing for sequential.")

            if task_manager.is_cancelled(analysis_id):
                logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled after spaCy processing, before sentence iteration.")
                yield json.dumps({"status": "cancelled"}) + "\n"
                return

            if not doc.has_annotation("SENT_START"):
                yield json.dumps({"error": "Sentence segmentation failed."}) + "\n"
                return # Stop generation

            # Select the profile
            profile = AUDIENCE_PROFILES.get(target_audience_profile, AUDIENCE_PROFILES["Standard"])

            for i, spacy_sentence in enumerate(doc.sents):
                # --- Check for cancellation before processing each sentence ---
                if task_manager.is_cancelled(analysis_id):
                    logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled during processing at sentence {i}.")
                    yield json.dumps({"status": "cancelled"}) + "\n"
                    break # Exit the loop

                # Analyze the single sentence in 'fast' mode
                # Pass analysis_id for potential future checks within analyze_single_spacy_sentence if needed
                # Analyze the single sentence in 'fast' mode
                # Pass target_audience_profile for cache key consistency
                analysis_output = analyze_single_spacy_sentence(
                    spacy_sentence,
                    doc,
                    profile,
                    i,
                    target_audience_name=target_audience_profile, # Pass name for cache key
                    mode='fast',
                    analysis_id=analysis_id # Pass ID
                )
                # Only yield if the result was newly calculated (not from cache)
                if analysis_output and not analysis_output['from_cache']:
                    # Yield the actual result dictionary
                    yield json.dumps(analysis_output['result']) + "\n"

            # After all sentences, the frontend will trigger the full analysis.
            # No need to calculate overall scores here in the sequential stream.

        except Exception as e:
            logging.error(f"Error during sequential analysis streaming (ID: {analysis_id}): {e}", exc_info=True)
            yield json.dumps({"error": f"Server error during analysis: {e}"}) + "\n"
        finally:
            # --- Remove Task ---
            task_manager.remove_task(analysis_id)
            logging.info(f"Sequential analysis (ID: {analysis_id}) stream finished or cancelled.")

    # Return a streaming response
    return Response(generate_results(), mimetype='application/json')


# /synonyms endpoint (POST) - Updated for contextual enhancement
@app.route('/synonyms', methods=['POST'])
def get_synonyms():
    """
    Provides ranked synonym suggestions using WordNet and optionally enhances
    them with context-aware recommendations from DeepSeek.
    """
    data = request.get_json()
    if not data or 'word' not in data or 'sentence_context' not in data or 'target_audience' not in data:
        logging.warning("'/synonyms' request missing 'word', 'sentence_context', or 'target_audience'.")
        return jsonify({"error": "Missing 'word', 'sentence_context', or 'target_audience' in request body"}), 400

    word_to_lookup = data.get('word', '')
    sentence_context = data.get('sentence_context', '') 
    target_audience_profile = data.get('target_audience', 'Standard') 
    context_awareness_enabled = data.get('context_awareness_enabled', False) 

    logging.info(f"Received synonym request for '{word_to_lookup}'. Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    ranked_synonyms = get_ranked_synonyms(word_to_lookup)
    ranked_synonyms.sort(key=lambda x: (x['rank'], x['word']))

    deepseek_recommendation = None 
    if context_awareness_enabled and ranked_synonyms and sentence_context:
        # --- Rate Limiting Check for LLM Synonym Suggestion ---
        client_ip = request.remote_addr
        if not rate_limiter.check_and_update_limit(client_ip, 'llm_synonym'):
            logging.warning(f"Rate limit exceeded for LLM synonym suggestion. IP: {client_ip}")
            # Return the base synonyms but indicate LLM part was skipped due to rate limit
            return jsonify({
                "ranked_synonyms": ranked_synonyms,
                "llm_recommendation": {"error": "Contextual suggestion rate limit exceeded. Please try again later."}
            }), 200 # Return 200 as base synonyms are still provided
        # --- End Rate Limiting Check ---

        logging.info("Context awareness enabled, calling DeepSeek synonym recommendation.") 
        try:
            deepseek_recommendation = recommend_synonym( 
                original_word=word_to_lookup,
                sentence_context=sentence_context,
                ranked_synonyms_list=ranked_synonyms, 
                target_audience_profile=target_audience_profile
            )
            if deepseek_recommendation and "error" in deepseek_recommendation:
                 logging.warning(f"DeepSeek synonym recommendation returned an error: {deepseek_recommendation['error']}") 
            elif not deepseek_recommendation:
                 logging.warning("DeepSeek synonym recommendation returned None.") 
        except Exception as e:
            logging.error(f"Exception during DeepSeek synonym recommendation call: {e}", exc_info=True) 
            deepseek_recommendation = {"error": f"Server error during recommendation: {e}"}
    elif context_awareness_enabled:
        if not ranked_synonyms and not sentence_context:
            logging.warning("Context awareness enabled but no base synonyms found and no sentence context provided. Skipping LLM recommendation.")
        elif not ranked_synonyms:
            logging.warning("Context awareness enabled but no base synonyms found. Skipping LLM recommendation.")
        elif not sentence_context:
            logging.warning("Context awareness enabled but no sentence context provided. Skipping LLM recommendation.")
        else:
            # This case should ideally not be reached if the main 'if' condition failed,
            # but including for completeness or future logic changes.
            logging.warning("Context awareness enabled but prerequisites (synonyms found, context provided) not met for an unknown reason. Skipping LLM recommendation.")

    return jsonify({
        "ranked_synonyms": ranked_synonyms, 
        "llm_recommendation": deepseek_recommendation 
    })

# --- NEW: Cancellation Endpoint ---
@app.route('/cancel_analysis', methods=['POST'])
def cancel_analysis_task():
    """Endpoint for the frontend to request cancellation of an ongoing analysis task."""
    data = request.get_json()
    if not data or 'analysisId' not in data:
        logging.warning("'/cancel_analysis' request missing 'analysisId'.")
        return jsonify({"error": "Missing 'analysisId' in request body"}), 400

    analysis_id_to_cancel = data.get('analysisId')
    logging.info(f"Received cancellation request for analysis ID: {analysis_id_to_cancel}")

    task_manager.cancel_task(analysis_id_to_cancel)

    return jsonify({"status": "Cancellation requested", "analysisId": analysis_id_to_cancel})

# --- NEW: Rewrite Suggestion Endpoint ---
@app.route('/rewrite_suggestion', methods=['POST'])
def rewrite_suggestion():
    """Provides rewrite suggestions for a sentence using DeepSeek."""
    data = request.get_json()
    if not data or not all(k in data for k in ('sentence_text', 'surrounding_context', 'target_audience', 'complexity_analysis_details')):
        logging.warning("'/rewrite_suggestion' request missing required fields.")
        return jsonify({"error": "Missing required fields (sentence_text, surrounding_context, target_audience, complexity_analysis_details)"}), 400

    # --- Rate Limiting Check for LLM Rewrite Suggestion ---
    client_ip = request.remote_addr
    if not rate_limiter.check_and_update_limit(client_ip, 'llm_rewrite'):
        logging.warning(f"Rate limit exceeded for LLM rewrite suggestion. IP: {client_ip}")
        return jsonify({
            "status": "Error", 
            "feedback": "LLM rewrite suggestion rate limit exceeded. Please try again later.", 
            "suggestion": None,
            "reasoning": "Rate limit exceeded."
        }), 429
    # --- End Rate Limiting Check ---

    sentence_text = data['sentence_text']
    surrounding_context = data['surrounding_context']
    target_audience = data['target_audience']
    complexity_details = data['complexity_analysis_details'] # NEW: Get the dictionary

    logging.info(f"Received rewrite suggestion request for sentence: '{sentence_text[:50]}...', Audience: {target_audience}")

    try:
        # Call the DeepSeek analysis function from deepseek_analysis.py
        suggestion = get_rewrite_suggestion(
            sentence_text,
            surrounding_context, # Pass surrounding_context
            target_audience,
            complexity_details # Pass the full dictionary
        )
        if 'error' in suggestion:
            logging.error(f"Error from DeepSeek rewrite: {suggestion['error']}")
            # Ensure a 500 is returned for internal LLM call errors if not already an API error code
            return jsonify({"error": suggestion.get('error', "Failed to get rewrite suggestion.")}), 500 
        return jsonify(suggestion)
    except Exception as e:
        logging.error(f"Error in /rewrite_suggestion: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {e}"}), 500

# --- PDF Processing Routes ---

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf_file():
    """Handles PDF file uploads, saves it, and triggers Celery task for processing."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Get other parameters from form data
    action = request.form.get('action', 'full_analysis')
    target_audience = request.form.get('target_audience', 'Standard')
    analysis_mode_pdf = request.form.get('analysis_mode', 'best') # Get analysis_mode for PDF
    # Parameters for overview page generation
    include_overview_page_str = request.form.get('include_overview_page', 'true').lower()
    include_overview_page = include_overview_page_str == 'true'
    overview_top_x_count = int(request.form.get('overview_top_x_count', 5))
    overview_top_x_type = request.form.get('overview_top_x_type', 'complex')
    overview_show_visual_map_str = request.form.get('overview_show_visual_map', 'true').lower()
    overview_show_visual_map = overview_show_visual_map_str == 'true'


    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Generate a unique ID for the file to avoid conflicts and for tracking
        unique_id = str(uuid.uuid4())
        temp_filename = f"{unique_id}_{filename}" # Prepend unique_id to original filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        
        try:
            file.save(file_path)
            app.logger.info(f"File '{filename}' (temp: '{temp_filename}') saved to '{file_path}'")

            # --- Rate Limiting Check for PDF analysis ---
            # PDF analysis rate limiting is handled by the task itself if it's 'better' or 'best'
            # However, if we want to prevent even queuing the task, we can check here.
            # For now, let's assume the task will handle it, but we need to pass the IP.
            client_ip = request.remote_addr
            # If the chosen mode for PDF is 'fast', it won't be rate-limited.
            # If it's 'better' or 'best', the task will check.

            # Trigger Celery task for PDF processing
            task = process_pdf_task.delay(
                file_path=file_path, 
                original_filename=filename, # Pass original filename for user reference
                action=action,
                target_audience=target_audience,
                include_overview_page=include_overview_page,
                overview_top_x_count=overview_top_x_count,
                overview_top_x_type=overview_top_x_type,
                overview_show_visual_map=overview_show_visual_map,
                analysis_mode=analysis_mode_pdf, # Pass the mode for PDF analysis
                client_ip_address=client_ip # <<< PASS CLIENT IP TO TASK
            )
            app.logger.info(f"Celery task '{task.id}' created for PDF: {filename} with mode: {analysis_mode_pdf} from IP: {client_ip}")

            return jsonify({
                "message": "File uploaded successfully, processing started.", 
                "task_id": task.id, 
                "original_filename": filename,
                "upload_id": unique_id # Return unique_id if client wants to track by it
            }), 202

        except Exception as e:
            app.logger.error(f"Error during PDF upload or task creation for {filename}: {e}", exc_info=True)
            return jsonify({"error": f"Could not process file: {str(e)}"}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/task_status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Checks the status of a Celery task."""
    task = process_pdf_task.AsyncResult(task_id)
    response_data = {
        'task_id': task_id,
        'state': task.state
    }
    if task.state == 'PENDING':
        response_data['status_message'] = 'Task is pending.'
    elif task.state == 'PROGRESS':
        response_data['meta'] = task.info # task.info contains the meta data
        response_data['status_message'] = task.info.get('status_message', 'Processing...')
    elif task.state == 'SUCCESS':
        result = task.result
        if isinstance(result, dict):
            response_data['result'] = result # Include the actual result
            response_data['status_message'] = result.get('status_message', 'Task completed successfully.')
            if result.get('error'): # If the task itself reported an error in its result structure
                response_data['error_details'] = result.get('error_details', 'Unknown error from task')
        else:
            # Handle cases where result might not be a dict (e.g. older task versions)
            response_data['result'] = {'raw_result': str(result)} # Basic representation
            response_data['status_message'] = 'Task completed successfully (raw result).'

    elif task.state == 'FAILURE':
        result = task.result # This should be the dict returned by the task on failure
        if isinstance(result, dict) and result.get('error'):
            response_data['error_details'] = result.get('error_details', 'Unknown error')
            response_data['status_message'] = result.get('status_message', 'Task failed.')
        elif isinstance(task.info, Exception): # Sometimes Celery stores the exception instance in task.info
            response_data['error_details'] = f"{type(task.info).__name__}: {str(task.info)}"
            response_data['status_message'] = f'Task failed: {str(task.info)}'
        else: # Fallback for other failure scenarios
            response_data['error_details'] = 'Task failed with an unknown error.'
            response_data['status_message'] = 'Task failed.'
        response_data['result'] = task.info # This is where Celery stores exception info on failure
    else:
        response_data['status_message'] = task.state # e.g., RETRY, REVOKED
    
    app.logger.debug(f"Task status for {task_id}: {response_data}")
    return jsonify(response_data)

@app.route('/get_extracted_text/<task_id>', methods=['GET'])
def get_extracted_text_result(task_id):
    """Retrieves the result of a text extraction task."""
    task = process_pdf_task.AsyncResult(task_id)
    if task.state == 'SUCCESS':
        result = task.result
        if isinstance(result, dict) and result.get('action_performed') == 'extract_text':
            app.logger.info(f"Returning extracted text for task {task_id}.")
            return jsonify({
                "task_id": task_id,
                "status": "SUCCESS",
                "extracted_text": result.get('extracted_text', ''),
                # "sentence_coordinates_map": result.get('sentence_coordinates_map', []) # Optionally return coordinates
            })
        elif isinstance(result, dict):
            app.logger.warning(f"Task {task_id} succeeded but was not an 'extract_text' action or missing data. Result: {result}")
            return jsonify({"error": "Task was not a text extraction task or result format is incorrect.", "task_id": task_id, "actual_action": result.get('action_performed', 'unknown')}), 404
        else:
            app.logger.error(f"Task {task_id} succeeded but result is not a dictionary: {result}")
            return jsonify({"error": "Task result format error.", "task_id": task_id}), 500
    elif task.state == 'FAILURE':
        app.logger.error(f"Attempt to get extracted text from failed task {task_id}. Info: {task.info}")
        return jsonify({"error": "Text extraction task failed.", "task_id": task_id, "details": str(task.info)}), 500
    else:
        app.logger.warning(f"Attempt to get extracted text from task {task_id} not yet in SUCCESS state. State: {task.state}")
        return jsonify({"error": "Text extraction task not yet complete or failed.", "task_id": task_id, "state": task.state}), 202 # Accepted, but not ready

@app.route('/download_highlighted_pdf/<task_id>', methods=['GET'])
def download_highlighted_pdf(task_id):
    task = process_pdf_task.AsyncResult(task_id)
    if task.state == 'SUCCESS':
        result = task.result
        app.logger.debug(f"Download request for task {task_id}. Task result: {result}") # Log the entire result

        if result and not result.get('error') and result.get('highlighted_pdf_filename'):
            filename = result.get('highlighted_pdf_filename')
            safe_filename = secure_filename(filename)
            
            processed_dir = current_app.config['PROCESSED_FOLDER']
            
            app.logger.info(f"Attempting to send file: '{safe_filename}' from directory: '{processed_dir}' for task_id {task_id}")
            try:
                return send_from_directory(processed_dir, safe_filename, as_attachment=True)
            except FileNotFoundError:
                app.logger.error(f"File not found for download: '{safe_filename}' in '{processed_dir}'. Full path attempted: {os.path.join(processed_dir, safe_filename)}")
                return jsonify({"error": "Processed file not found. It might still be generating or an error occurred."}), 404
            except Exception as e:
                app.logger.error(f"Error sending file '{safe_filename}': {e}", exc_info=True)
                return jsonify({"error": f"Server error while sending file: {str(e)}"}), 500
        else:
            app.logger.warning(f"Task {task_id} SUCCEEDED but result structure is not as expected for download or error flag present. Result: {result}")
            return jsonify({"error": "Task completed but no valid processed file found or an error occurred in task details."}), 404
    elif task.state == 'FAILURE':
        app.logger.error(f"Task {task_id} FAILED. Cannot download file. Info: {task.info}, Result: {task.result}")
        return jsonify({"error": "Task failed, cannot download file."}), 400
    else:
        app.logger.warning(f"Task {task_id} not completed. State: {task.state}. Cannot download file.")
        return jsonify({"error": "Task not completed or does not exist."}), 404


@app.route('/pdf_summary/<task_id>', methods=['GET'])
def get_pdf_summary(task_id):
    task = process_pdf_task.AsyncResult(task_id)
    if task.state == 'SUCCESS':
        result = task.result
        if result and not result.get('error'):
            summary_data = {
                "overall_level": result.get("overall_level"),
                "readability_scores": result.get("readability_scores"),
                "original_filename": result.get("original_filename")
            }
            return jsonify(summary_data)
        else:
            return jsonify({"error": "Task completed but no summary data found or an error occurred in task."}), 404
    elif task.state == 'FAILURE':
        return jsonify({"error": "Task failed, cannot retrieve summary."}), 400
    else:
        return jsonify({"error": "Task not completed or does not exist."}), 404

# --- Celery Test Route ---
@app.route('/test_celery_add/<int:a>/<int:b>', methods=['GET'])
def test_celery_add(a, b):
    """
    Test route to dispatch the 'add' Celery task.
    """
    try:
        task = add_task.delay(a, b)
        app.logger.info(f"Dispatched 'add' task {task.id} with arguments ({a}, {b})")
        return jsonify({
            "message": f"Celery 'add' task dispatched with args ({a}, {b}).",
            "task_id": task.id,
            "status_check_url": f"/task_status/{task.id}"
        }), 202
    except Exception as e:
        app.logger.error(f"Error dispatching 'add' task: {e}", exc_info=True)
        return jsonify({"error": f"Server error during 'add' task dispatch: {str(e)}"}), 500

# --- NEW: API Endpoint for Rate Limits ---
@app.route('/api/get_rate_limits', methods=['GET'])
def get_rate_limits_config():
    """Returns the configured rate limits and current remaining counts for the user."""
    client_ip = request.remote_addr
    total_limits = {
        'fast': current_app.config.get('RATE_LIMIT_FAST_PER_DAY', 10),
        'better': current_app.config.get('RATE_LIMIT_BETTER_PER_DAY', 5),
        'best': current_app.config.get('RATE_LIMIT_BEST_PER_DAY', 2),
        'llm_synonym': current_app.config.get('RATE_LIMIT_LLM_SYNONYM_PER_DAY', 5),
        'llm_rewrite': current_app.config.get('RATE_LIMIT_LLM_REWRITE_PER_DAY', 5)
    }
    
    current_usage = rate_limiter.get_current_usage(client_ip)
    
    remaining_counts = {}
    for mode, total in total_limits.items():
        remaining_counts[mode] = total - current_usage.get(mode, 0)
        if remaining_counts[mode] < 0:
            remaining_counts[mode] = 0 # Ensure it doesn't go negative
            
    return jsonify({
        'total_limits': total_limits,
        'remaining_counts': remaining_counts
    })
# --- END NEW API Endpoint ---

# --- Admin UI Route for Rate Limit Reset ---
@app.route('/admin/reset-ui', methods=['GET'])
def admin_reset_ui():
    """Serves the HTML page for resetting rate limits via UI."""
    return render_template('admin_reset.html')

# --- NEW: Admin Route to Reset Rate Limits ---
@app.route('/admin/reset_rate_limit', methods=['POST'])
def admin_reset_rate_limit():
    """
    Resets the rate limits for the requester's IP address if a valid special key is provided.
    Expects JSON: {"key": "YOUR_SPECIAL_KEY"}
    """
    data = request.get_json()
    if not data or 'key' not in data:
        logging.warning("Admin rate limit reset: Missing key in request.")
        return jsonify({"error": "Missing 'key' in request body"}), 400

    special_key_provided = data.get('key')
    ip_to_reset = request.remote_addr # Automatically use the requester's IP

    # Validate IP address format (basic validation) - request.remote_addr should be reliable
    # but an explicit check is good practice if there's any doubt or proxy involvement
    try:
        import ipaddress
        ipaddress.ip_address(ip_to_reset)
    except ValueError:
        # This should ideally not happen with request.remote_addr but good to have a safeguard
        logging.error(f"Admin rate limit reset: Invalid IP address obtained from request.remote_addr: {ip_to_reset}")
        return jsonify({"error": "Invalid IP address obtained from request."}), 400

    valid_keys = []
    key_file_path = os.path.join(app.root_path, '..', 'special_keys.txt') # Assuming special_keys.txt is in the workspace root
    
    try:
        with open(key_file_path, 'r') as f:
            valid_keys = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"Admin rate limit reset: special_keys.txt not found at {key_file_path}")
        # Do not expose file path in error to client
        return jsonify({"error": "Server configuration error. Key file not found."}), 500
    except Exception as e:
        logging.error(f"Admin rate limit reset: Error reading special_keys.txt: {e}")
        return jsonify({"error": "Server error while validating key."}), 500

    if not valid_keys:
        logging.error(f"Admin rate limit reset: No valid keys found in special_keys.txt.")
        return jsonify({"error": "Server configuration error. No special keys configured."}), 500

    if special_key_provided in valid_keys:
        logging.info(f"Admin rate limit reset: Valid key received. Attempting to reset limits for IP: {ip_to_reset}")
        # Assuming rate_limiter is the global instance from app/__init__.py
        success = rate_limiter.reset_limits_for_ip(ip_to_reset)
        if success:
            return jsonify({"message": f"Rate limits successfully reset for IP: {ip_to_reset}"}), 200
        else:
            # This could mean no keys were found for the IP, or a Redis error occurred.
            # The RateLimiter class logs specifics.
            return jsonify({"message": f"Attempted to reset limits for IP: {ip_to_reset}. No active limits found or Redis issue."}), 200
    else:
        logging.warning(f"Admin rate limit reset: Invalid key provided for IP: {ip_to_reset}")
        return jsonify({"error": "Invalid special key."}), 403


if __name__ == '__main__':
    # Note: Debug mode should be False in a production environment!
    # Use a proper WSGI server like Gunicorn or uWSGI for production.
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5001)))
