import logging # Add logging
from flask import render_template, request, jsonify, Response, send_from_directory, current_app # Import Response, send_from_directory, current_app
from app import app, celery # Import celery
# Import the analysis and synonym functions
from app.analysis import analyze_text_complexity, analyze_single_spacy_sentence, nlp, AUDIENCE_PROFILES # Import nlp, the new function, and AUDIENCE_PROFILES
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
    mode = data.get('mode', 'full') # <<< NEW: Get mode, default to 'full'

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
            doc_for_sentences = nlp(text_to_analyze)
            sentences_list = [sent.text for sent in doc_for_sentences.sents]
        except Exception:
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

    if not nlp:
         logging.error("spaCy model not loaded. Cannot perform sequential analysis.")
         return jsonify({"error": "Analysis service not available (spaCy model not loaded)."}), 500

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
            logging.debug(f"Task {analysis_id}: Starting spaCy processing.")
            doc = nlp(text_to_analyze)
            logging.debug(f"Task {analysis_id}: Finished spaCy processing.")

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


# /synonyms endpoint (POST) - Remains unchanged for now
# /synonyms endpoint (POST) - Updated for contextual enhancement
@app.route('/synonyms', methods=['POST'])
def get_synonyms():
    """
    Provides ranked synonym suggestions using WordNet and optionally enhances
    them with context-aware recommendations from Gemini.
    """
    data = request.get_json()
    # Add checks for new required fields
    if not data or 'word' not in data or 'sentence_context' not in data or 'target_audience' not in data:
        logging.warning("'/synonyms' request missing 'word', 'sentence_context', or 'target_audience'.")
        return jsonify({"error": "Missing 'word', 'sentence_context', or 'target_audience' in request body"}), 400

    word_to_lookup = data.get('word', '')
    sentence_context = data.get('sentence_context', '') # Get sentence context
    target_audience_profile = data.get('target_audience', 'Standard') # Get profile
    context_awareness_enabled = data.get('context_awareness_enabled', False) # Get toggle state

    logging.info(f"Received synonym request for '{word_to_lookup}'. Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    # --- 1. Get Base Ranked Synonyms (Always) ---
    ranked_synonyms = get_ranked_synonyms(word_to_lookup)
    # Sort by rank for the base list in the API response
    ranked_synonyms.sort(key=lambda x: (x['rank'], x['word']))

    # --- 2. Get DeepSeek Recommendation (Conditional) ---
    deepseek_recommendation = None # Renamed variable
    logging.debug(f"Synonym request debug: ranked_synonyms={ranked_synonyms}, sentence_context='{sentence_context}'") # ADDED LOG
    if context_awareness_enabled and ranked_synonyms and sentence_context:
        logging.info("Context awareness enabled, calling DeepSeek synonym recommendation.") # Updated log message
        try:
            deepseek_recommendation = recommend_synonym( # Call the imported DeepSeek function
                original_word=word_to_lookup,
                sentence_context=sentence_context,
                ranked_synonyms_list=ranked_synonyms, # Pass the base list
                target_audience_profile=target_audience_profile
            )
            if deepseek_recommendation and "error" in deepseek_recommendation:
                 logging.warning(f"DeepSeek synonym recommendation returned an error: {deepseek_recommendation['error']}") # Updated log message
            elif not deepseek_recommendation:
                 logging.warning("DeepSeek synonym recommendation returned None.") # Updated log message
        except Exception as e:
            logging.error(f"Exception during DeepSeek synonym recommendation call: {e}", exc_info=True) # Updated log message
            deepseek_recommendation = {"error": f"Server error during recommendation: {e}"}
    elif context_awareness_enabled:
        logging.warning("Context awareness enabled but prerequisites (synonyms found, context provided) not met. Skipping DeepSeek recommendation.") # Updated log message

    # --- 3. Combine and Return Results ---
    # RENAME the key in the response for clarity. Frontend will need adjustment.
    return jsonify({
        "ranked_synonyms": ranked_synonyms, # Always return the base list
        "llm_recommendation": deepseek_recommendation # Use a generic key 'llm_recommendation'
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
    """
    Provides feedback and rewrite suggestions for a specific sentence using DeepSeek.
    """
    data = request.get_json()
    required_fields = ['sentence_text', 'surrounding_context', 'target_audience', 'complexity_score']
    if not data or not all(field in data for field in required_fields):
        missing = [field for field in required_fields if field not in (data or {})]
        logging.warning(f"'/rewrite_suggestion' request missing fields: {missing}")
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    sentence_text = data.get('sentence_text')
    surrounding_context = data.get('surrounding_context')
    target_audience = data.get('target_audience')
    complexity_score = data.get('complexity_score') # Frontend sends this directly

    logging.info(f"Received rewrite suggestion request. Audience: {target_audience}, Score: {complexity_score:.2f}")

    try:
        result = get_rewrite_suggestion(
            sentence_text=sentence_text,
            surrounding_context=surrounding_context,
            target_audience_profile=target_audience,
            complexity_score=complexity_score
        )
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error during rewrite suggestion call: {e}", exc_info=True)
        return jsonify({"error": f"Server error during rewrite suggestion: {e}"}), 500

# --- PDF Processing Routes ---

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        # Save the file temporarily with a unique name to avoid conflicts
        temp_filename = str(uuid.uuid4()) + "_" + original_filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(file_path)

        # Get the action from the form data (e.g., 'extract_text' or 'full_analysis')
        action = request.form.get('action', 'full_analysis') 
        app.logger.info(f"Uploading PDF: {original_filename}, Action: {action}")

        # Launch Celery task with the file path, original name, and action
        task = process_pdf_task.delay(file_path, original_filename, action)
        app.logger.info(f"Celery task {task.id} started for {original_filename} with action '{action}'.")
        return jsonify({"task_id": task.id}), 202
    
    return jsonify({"error": "File type not allowed or error saving file"}), 400

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
