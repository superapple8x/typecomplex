"""
Routes for Electron version using LocalTaskQueue instead of Celery
"""

import logging
from flask import render_template, request, jsonify, Response, send_from_directory, current_app
from app.__init___electron import app, rate_limiter
from app.analysis import analyze_text_complexity, analyze_single_spacy_sentence, AUDIENCE_PROFILES, get_active_spacy_model
from app.synonyms import get_ranked_synonyms
from app.deepseek_analysis import recommend_synonym, get_rewrite_suggestion, test_key_connectivity, reset_client
from app.api_keys import ApiKeyStore
from app.local_task_queue import get_local_task_queue, AsyncResult
from app.tasks_local import process_pdf_task, add_task
import json
import os
import uuid
import time
from werkzeug.utils import secure_filename
from app import task_manager

# Base path for local storage (prefer app config if provided by Electron initializer)
BASE_DIR = app.config.get('BASE_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

# Initialize key store (backend-only)
_api_keys = ApiKeyStore()

# In-process cache for AI readiness probe results
_ai_readiness_cache = {
    'last_test': None,      # dict | None: { ok: bool, error: str|None, at: float }
    'expires_at': 0.0,      # float epoch seconds when cache entry expires
    'inflight_until': 0.0,  # float epoch seconds to deduplicate rapid probes
}

def _probe_ai_connectivity_with_timeout(timeout_seconds: float = 3.0) -> dict:
    """Run test_key_connectivity() with a hard timeout.

    Returns a dict: { ok: bool, error: str|None, at: float }
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    started_at = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(test_key_connectivity)
            try:
                ok, reason = future.result(timeout=timeout_seconds)
                return {
                    'ok': bool(ok),
                    'error': (None if ok else (reason or 'unknown')),
                    'at': started_at
                }
            except TimeoutError:
                return {'ok': False, 'error': 'timeout', 'at': started_at}
    except Exception:
        # Any unexpected failure should not break /health
        return {'ok': False, 'error': 'network', 'at': started_at}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/settings/api-key', methods=['POST'])
def set_api_key():
    """Set DeepSeek API key securely. Never echoes key back."""
    data = request.get_json(silent=True) or {}
    api_key = data.get('api_key')
    if not api_key or not isinstance(api_key, str) or len(api_key) < 10:
        return jsonify({"error": "invalid_api_key"}), 400
    try:
        _api_keys.set_key(api_key)
        reset_client()
        # Clear AI readiness cache on key change
        global _ai_readiness_cache
        _ai_readiness_cache = {'last_test': None, 'expires_at': 0.0, 'inflight_until': 0.0}
        return jsonify({"status": "set"})
    except Exception as e:
        app.logger.error(f"Failed to set API key: {e}", exc_info=True)
        return jsonify({"error": "store_failed"}), 500


@app.route('/settings/api-key/status', methods=['GET'])
def get_api_key_status():
    """Return masked status of API key presence."""
    try:
        status = 'set' if _api_keys.is_set() else 'unset'
        return jsonify({"status": status})
    except Exception as e:
        app.logger.error(f"Failed to get API key status: {e}", exc_info=True)
        return jsonify({"status": "unset"}), 200


@app.route('/settings/api-key/test', methods=['POST'])
def test_api_key():
    """Connectivity test without sending user content."""
    ok, reason = test_key_connectivity()
    return jsonify({"ok": bool(ok), "error": (None if ok else reason)})


@app.route('/settings/api-key', methods=['DELETE'])
def delete_api_key():
    try:
        _api_keys.delete_key()
        reset_client()
        # Clear AI readiness cache on key removal
        global _ai_readiness_cache
        _ai_readiness_cache = {'last_test': None, 'expires_at': 0.0, 'inflight_until': 0.0}
        return jsonify({"status": "removed"})
    except Exception as e:
        app.logger.error(f"Failed to delete API key: {e}", exc_info=True)
        return jsonify({"error": "delete_failed"}), 500

@app.route('/')
def index():
    """Renders the main page."""
    return render_template('index.html')

# /analyze endpoint (POST)
@app.route('/analyze', methods=['POST'])
def analyze_text():
    """
    Analyzes the text complexity using statistical methods and optionally
    performs context-aware analysis using Gemini based on frontend inputs.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    target_audience_profile = data.get('target_audience', 'Standard')
    context_awareness_enabled = data.get('context_awareness_enabled', False)
    analysis_id = data.get('analysisId')
    mode = data.get('mode', 'better')

    # --- Rate Limiting Check ---
    client_ip = request.remote_addr
    if not rate_limiter.check_and_update_limit(client_ip, mode):
        logging.warning(f"Rate limit exceeded for IP: {client_ip}, Mode: {mode} on /analyze route.")
        return jsonify({"error": f"Rate limit exceeded for {mode} analysis. Please try again later."}), 429

    logging.info(f"Received analysis request (ID: {analysis_id}). Mode: {mode}, Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    # --- Register Task ---
    if analysis_id:
        task_manager.register_task(analysis_id)
    else:
        logging.warning("'/analyze' request received without analysisId.")

    analysis_results = None
    try:
        # Split the input text into sentences for per-sentence analysis
        try:
            active_nlp = get_active_spacy_model(mode)
            if not active_nlp:
                logging.error(f"spaCy model for mode '{mode}' not loaded. Cannot perform analysis for ID: {analysis_id}.")
                return jsonify({"error": f"Analysis service not available (spaCy model for mode '{mode}' not loaded)."}), 500
            
            doc_for_sentences = active_nlp(text_to_analyze)
            sentences_list = [sent.text for sent in doc_for_sentences.sents]
        except Exception as e_segment:
            logging.warning(f"spaCy segmentation failed for mode '{mode}' (ID: {analysis_id}): {e_segment}. Falling back to NLTK.")
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
        if analysis_id:
            task_manager.remove_task(analysis_id)
        return jsonify({"error": f"Server error during analysis: {e}"}), 500
    finally:
        if analysis_id:
            task_manager.remove_task(analysis_id)

    # Check if analysis was cancelled internally
    if analysis_results and analysis_results.get("overall_level", {}).get("description") == "Analysis cancelled":
         logging.info(f"Analysis (ID: {analysis_id}) was cancelled. Returning cancelled status.")
         return jsonify(analysis_results)

    logging.info(f"Analysis (ID: {analysis_id}) completed successfully.")
    return jsonify(analysis_results)

# /analyze_sequential endpoint (POST)
@app.route('/analyze_sequential', methods=['POST'])
def analyze_text_sequential():
    """
    Analyzes text complexity sentence by sentence and streams results back.
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze_sequential' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    target_audience_profile = data.get('target_audience', 'Standard')
    context_awareness_enabled = data.get('context_awareness_enabled', False)
    analysis_id = data.get('analysisId')

    logging.info(f"Received sequential analysis request (ID: {analysis_id}). Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    active_nlp_for_sequential = get_active_spacy_model('fast') 

    if not active_nlp_for_sequential:
         logging.error(f"spaCy model for 'fast' mode not loaded. Cannot perform sequential analysis (ID: {analysis_id}).")
         return jsonify({"error": "Analysis service not available (spaCy model for 'fast' mode not loaded)."}), 500

    if not analysis_id:
        logging.error("'/analyze_sequential' request received without analysisId.")
        return jsonify({"error": "Missing 'analysisId' in request body"}), 400

    def generate_results():
        """Generator function to yield sentence analysis results."""
        task_manager.register_task(analysis_id)
        try:
            if task_manager.is_cancelled(analysis_id):
                logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled before starting.")
                yield json.dumps({"status": "cancelled"}) + "\n"
                return

            logging.debug(f"Task {analysis_id}: Starting spaCy processing for sequential.")
            doc = active_nlp_for_sequential(text_to_analyze)
            logging.debug(f"Task {analysis_id}: Finished spaCy processing for sequential.")

            if task_manager.is_cancelled(analysis_id):
                logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled after spaCy processing, before sentence iteration.")
                yield json.dumps({"status": "cancelled"}) + "\n"
                return

            if not doc.has_annotation("SENT_START"):
                yield json.dumps({"error": "Sentence segmentation failed."}) + "\n"
                return

            profile = AUDIENCE_PROFILES.get(target_audience_profile, AUDIENCE_PROFILES["Standard"])

            for i, spacy_sentence in enumerate(doc.sents):
                if task_manager.is_cancelled(analysis_id):
                    logging.info(f"Sequential analysis (ID: {analysis_id}) cancelled during processing at sentence {i}.")
                    yield json.dumps({"status": "cancelled"}) + "\n"
                    break

                analysis_output = analyze_single_spacy_sentence(
                    spacy_sentence,
                    doc,
                    profile,
                    i,
                    target_audience_name=target_audience_profile,
                    mode='fast',
                    analysis_id=analysis_id
                )
                
                if analysis_output and not analysis_output['from_cache']:
                    yield json.dumps(analysis_output['result']) + "\n"

        except Exception as e:
            logging.error(f"Error during sequential analysis streaming (ID: {analysis_id}): {e}", exc_info=True)
            yield json.dumps({"error": f"Server error during analysis: {e}"}) + "\n"
        finally:
            task_manager.remove_task(analysis_id)
            logging.info(f"Sequential analysis (ID: {analysis_id}) stream finished or cancelled.")

    return Response(generate_results(), mimetype='application/json')

# /synonyms endpoint (POST)
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
            return jsonify({
                "ranked_synonyms": ranked_synonyms,
                "llm_recommendation": {"error": "Contextual suggestion rate limit exceeded. Please try again later."}
            }), 200

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

    return jsonify({
        "ranked_synonyms": ranked_synonyms, 
        "llm_recommendation": deepseek_recommendation 
    })

# --- Cancellation Endpoint ---
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

# --- Rewrite Suggestion Endpoint ---
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

    sentence_text = data['sentence_text']
    surrounding_context = data['surrounding_context']
    target_audience = data['target_audience']
    complexity_details = data['complexity_analysis_details']

    logging.info(f"Received rewrite suggestion request for sentence: '{sentence_text[:50]}...', Audience: {target_audience}")

    try:
        suggestion = get_rewrite_suggestion(
            sentence_text,
            surrounding_context,
            target_audience,
            complexity_details
        )
        if 'error' in suggestion:
            logging.error(f"Error from DeepSeek rewrite: {suggestion['error']}")
            return jsonify({"error": suggestion.get('error', "Failed to get rewrite suggestion.")}), 500 
        return jsonify(suggestion)
    except Exception as e:
        logging.error(f"Error in /rewrite_suggestion: {e}", exc_info=True)
        return jsonify({"error": f"Server error: {e}"}), 500


# --- AI namespace proxy endpoints ---
@app.route('/ai/rewrite', methods=['POST'])
def ai_rewrite():
    data = request.get_json(silent=True) or {}
    missing = [k for k in ('sentence_text', 'surrounding_context', 'target_audience', 'complexity_analysis_details') if k not in data]
    if missing:
        return jsonify({"error": "missing_fields", "fields": missing}), 400
    try:
        result = get_rewrite_suggestion(
            data['sentence_text'],
            data['surrounding_context'],
            data['target_audience'],
            data['complexity_analysis_details']
        )
        if 'error' in result:
            # Normalize common errors
            err = result.get('error')
            code = 401 if 'Authentication' in err or 'api_client_unavailable' in err else 502
            return jsonify({"error": err}), code
        return jsonify(result)
    except Exception as e:
        logging.error(f"/ai/rewrite error: {e}", exc_info=True)
        return jsonify({"error": "server_error"}), 500


@app.route('/ai/synonyms', methods=['POST'])
def ai_synonyms():
    data = request.get_json(silent=True) or {}
    missing = [k for k in ('word', 'sentence_context', 'target_audience', 'ranked_synonyms_list') if k not in data]
    if missing:
        return jsonify({"error": "missing_fields", "fields": missing}), 400
    try:
        result = recommend_synonym(
            original_word=data['word'],
            sentence_context=data['sentence_context'],
            ranked_synonyms_list=data['ranked_synonyms_list'],
            target_audience_profile=data['target_audience']
        )
        if result and 'error' in result:
            err = result.get('error')
            code = 401 if 'Authentication' in err or 'api_client_unavailable' in err else 502
            return jsonify({"error": err}), code
        return jsonify(result)
    except Exception as e:
        logging.error(f"/ai/synonyms error: {e}", exc_info=True)
        return jsonify({"error": "server_error"}), 500

# --- PDF Processing Routes ---

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf_file():
    """Handles PDF file uploads, saves it, and triggers LocalTaskQueue task for processing."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Get other parameters from form data
    action = request.form.get('action', 'full_analysis')
    target_audience = request.form.get('target_audience', 'Standard')
    analysis_mode_pdf = request.form.get('analysis_mode', 'best')
    include_overview_page_str = request.form.get('include_overview_page', 'true').lower()
    include_overview_page = include_overview_page_str == 'true'
    overview_top_x_count = int(request.form.get('overview_top_x_count', 5))
    overview_top_x_type = request.form.get('overview_top_x_type', 'complex')
    overview_show_visual_map_str = request.form.get('overview_show_visual_map', 'true').lower()
    overview_show_visual_map = overview_show_visual_map_str == 'true'

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        temp_filename = f"{unique_id}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        
        try:
            file.save(file_path)
            app.logger.info(f"File '{filename}' (temp: '{temp_filename}') saved to '{file_path}'")

            client_ip = request.remote_addr

            # Get LocalTaskQueue instance and submit task
            task_queue = get_local_task_queue()
            task_id = task_queue.submit_task(
                process_pdf_task,
                file_path=file_path, 
                original_filename=filename,
                action=action,
                target_audience=target_audience,
                include_overview_page=include_overview_page,
                overview_top_x_count=overview_top_x_count,
                overview_top_x_type=overview_top_x_type,
                overview_show_visual_map=overview_show_visual_map,
                analysis_mode=analysis_mode_pdf,
                client_ip_address=client_ip
            )
            
            app.logger.info(f"LocalTaskQueue task '{task_id}' created for PDF: {filename} with mode: {analysis_mode_pdf} from IP: {client_ip}")

            return jsonify({
                "message": "File uploaded successfully, processing started.", 
                "task_id": task_id, 
                "original_filename": filename,
                "upload_id": unique_id
            }), 202

        except Exception as e:
            app.logger.error(f"Error during PDF upload or task creation for {filename}: {e}", exc_info=True)
            return jsonify({"error": f"Could not process file: {str(e)}"}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/task_status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Checks the status of a LocalTaskQueue task."""
    task_queue = get_local_task_queue()
    task_result = task_queue.get_task_status(task_id)
    
    # Convert to Celery-compatible format
    response_data = {
        'task_id': task_id,
        'state': task_result.status.upper()
    }
    
    if task_result.status == 'pending':
        response_data['status_message'] = 'Task is pending.'
    elif task_result.status == 'running':
        response_data['state'] = 'PROGRESS'
        response_data['meta'] = task_result.meta or {}
        response_data['status_message'] = task_result.meta.get('status_message', 'Processing...') if task_result.meta else 'Processing...'
    elif task_result.status == 'completed':
        response_data['state'] = 'SUCCESS'
        result = task_result.result
        if isinstance(result, dict):
            response_data['result'] = result
            response_data['status_message'] = result.get('status_message', 'Task completed successfully.')
            if result.get('error'):
                response_data['error_details'] = result.get('error_details', 'Unknown error from task')
        else:
            response_data['result'] = {'raw_result': str(result)}
            response_data['status_message'] = 'Task completed successfully (raw result).'
    elif task_result.status == 'failed':
        response_data['state'] = 'FAILURE'
        response_data['error_details'] = task_result.error or 'Unknown error'
        response_data['status_message'] = f'Task failed: {task_result.error}'
        response_data['result'] = task_result.result
    elif task_result.status == 'cancelled':
        response_data['state'] = 'REVOKED'
        response_data['status_message'] = 'Task was cancelled.'
    else:
        response_data['status_message'] = task_result.status
    
    app.logger.debug(f"Task status for {task_id}: {response_data}")
    return jsonify(response_data)

@app.route('/get_extracted_text/<task_id>', methods=['GET'])
def get_extracted_text_result(task_id):
    """Retrieves the result of a text extraction task."""
    task_queue = get_local_task_queue()
    task_result = task_queue.get_task_status(task_id)
    
    if task_result.status == 'completed':
        result = task_result.result
        if isinstance(result, dict) and result.get('action_performed') == 'extract_text':
            app.logger.info(f"Returning extracted text for task {task_id}.")
            return jsonify({
                "task_id": task_id,
                "status": "SUCCESS",
                "extracted_text": result.get('extracted_text', ''),
            })
        elif isinstance(result, dict):
            app.logger.warning(f"Task {task_id} succeeded but was not an 'extract_text' action or missing data. Result: {result}")
            return jsonify({"error": "Task was not a text extraction task or result format is incorrect.", "task_id": task_id, "actual_action": result.get('action_performed', 'unknown')}), 404
        else:
            app.logger.error(f"Task {task_id} succeeded but result is not a dictionary: {result}")
            return jsonify({"error": "Task result format error.", "task_id": task_id}), 500
    elif task_result.status == 'failed':
        app.logger.error(f"Attempt to get extracted text from failed task {task_id}. Error: {task_result.error}")
        return jsonify({"error": "Text extraction task failed.", "task_id": task_id, "details": task_result.error}), 500
    else:
        app.logger.warning(f"Attempt to get extracted text from task {task_id} not yet in completed state. State: {task_result.status}")
        return jsonify({"error": "Text extraction task not yet complete or failed.", "task_id": task_id, "state": task_result.status}), 202

@app.route('/download_highlighted_pdf/<task_id>', methods=['GET'])
def download_highlighted_pdf(task_id):
    task_queue = get_local_task_queue()
    task_result = task_queue.get_task_status(task_id)
    
    if task_result.status == 'completed':
        result = task_result.result
        app.logger.debug(f"Download request for task {task_id}. Task result: {result}")

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
            app.logger.warning(f"Task {task_id} completed but result structure is not as expected for download or error flag present. Result: {result}")
            return jsonify({"error": "Task completed but no valid processed file found or an error occurred in task details."}), 404
    elif task_result.status == 'failed':
        app.logger.error(f"Task {task_id} failed. Cannot download file. Error: {task_result.error}")
        return jsonify({"error": "Task failed, cannot download file."}), 400
    else:
        app.logger.warning(f"Task {task_id} not completed. State: {task_result.status}. Cannot download file.")
        return jsonify({"error": "Task not completed or does not exist."}), 404

@app.route('/pdf_summary/<task_id>', methods=['GET'])
def get_pdf_summary(task_id):
    task_queue = get_local_task_queue()
    task_result = task_queue.get_task_status(task_id)
    
    if task_result.status == 'completed':
        result = task_result.result
        if result and not result.get('error'):
            summary_data = {
                "overall_level": result.get("overall_level"),
                "readability_scores": result.get("readability_scores"),
                "original_filename": result.get("original_filename")
            }
            return jsonify(summary_data)
        else:
            return jsonify({"error": "Task completed but no summary data found or an error occurred in task."}), 404
    elif task_result.status == 'failed':
        return jsonify({"error": "Task failed, cannot retrieve summary."}), 400
    else:
        return jsonify({"error": "Task not completed or does not exist."}), 404

# --- LocalTaskQueue Test Route ---
@app.route('/test_local_add/<int:a>/<int:b>', methods=['GET'])
def test_local_add(a, b):
    """Test route to dispatch the 'add' LocalTaskQueue task"""
    try:
        task_queue = get_local_task_queue()
        task_id = task_queue.submit_task(add_task, a, b)
        
        app.logger.info(f"Dispatched 'add' task {task_id} with arguments ({a}, {b})")
        return jsonify({
            "message": f"'add' task dispatched successfully with arguments ({a}, {b})",
            "task_id": task_id,
            "status": "Task submitted for processing"
        }), 202
    except Exception as e:
        app.logger.error(f"Error dispatching 'add' task: {e}", exc_info=True)
        return jsonify({"error": f"Server error during 'add' task dispatch: {str(e)}"}), 500

# Health check endpoint for Electron process monitoring
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for process monitoring with AI readiness details."""
    try:
        # Basic queue sanity
        get_local_task_queue()

        # Optional memory stats
        try:
            import psutil  # type: ignore
            process = psutil.Process()
            mem_info = process.memory_info()
            memory = {
                'rss_bytes': mem_info.rss,
                'vms_bytes': getattr(mem_info, 'vms', None),
            }
        except Exception:
            memory = None

        # AI readiness info
        key_status = 'set' if _api_keys.is_set() else 'unset'
        ai_info = {
            'key_status': key_status,
            'ready': False,
            'last_test': None
        }

        if key_status == 'set':
            now = time.time()
            ttl_seconds = 300.0  # 5 minutes
            dedup_seconds = 10.0
            probe_requested = request.args.get('probe_ai', default='0') in ('1', 'true', 'True')

            # Use cached result if valid and no probe requested
            global _ai_readiness_cache
            cached = _ai_readiness_cache.get('last_test')
            if (not probe_requested) and cached and _ai_readiness_cache.get('expires_at', 0.0) > now:
                ai_info['last_test'] = cached
                ai_info['ready'] = bool(cached and cached.get('ok'))
            elif probe_requested:
                # Deduplicate rapid probes
                if _ai_readiness_cache.get('inflight_until', 0.0) > now:
                    # Return whatever we have without triggering a new probe
                    ai_info['last_test'] = cached
                    ai_info['ready'] = bool(cached and cached.get('ok'))
                else:
                    # Mark inflight and perform a short probe
                    _ai_readiness_cache['inflight_until'] = now + dedup_seconds
                    test = _probe_ai_connectivity_with_timeout(timeout_seconds=3.0)
                    _ai_readiness_cache['last_test'] = test
                    _ai_readiness_cache['expires_at'] = now + ttl_seconds
                    _ai_readiness_cache['inflight_until'] = 0.0
                    ai_info['last_test'] = test
                    ai_info['ready'] = bool(test.get('ok'))
            else:
                # No cached result and probe not requested: report key set but not ready yet
                ai_info['last_test'] = None
                ai_info['ready'] = False

        stats = {
            'status': 'healthy',
            'task_queue': 'operational',
            'timestamp': time.time(),
            'memory': memory,
            'ai': ai_info,
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }), 500


# Optional: cancel a PDF background task by task_id
@app.route('/cancel_pdf_task', methods=['POST'])
def cancel_pdf_task():
    data = request.get_json() or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': "Missing 'task_id' in request body"}), 400

    try:
        task_queue = get_local_task_queue()
        cancelled = task_queue.cancel_task(task_id)
        return jsonify({'task_id': task_id, 'cancelled': bool(cancelled)})
    except Exception as e:
        app.logger.error(f"Error cancelling task {task_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500