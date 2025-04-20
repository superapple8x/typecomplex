import logging # Add logging
from flask import render_template, request, jsonify, Response # Import Response
from app import app
# Import the analysis and synonym functions
from app.analysis import analyze_text_complexity, analyze_single_spacy_sentence, nlp, AUDIENCE_PROFILES # Import nlp, the new function, and AUDIENCE_PROFILES
from app.synonyms import get_ranked_synonyms
# Import the NEW DeepSeek enhancement functions (replacing Gemini)
from app.deepseek_analysis import enhance_sentence_complexity, recommend_synonym
# frequency module is loaded automatically when synonyms/analysis imports it if needed
import json # Import json for streaming
# Import the task manager
from app import task_manager

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

    logging.info(f"Received analysis request (ID: {analysis_id}). Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    # --- Register Task ---
    if analysis_id: # Only register if ID is provided
        task_manager.register_task(analysis_id)
    else:
        logging.warning("'/analyze' request received without analysisId.")


    analysis_results = None # Initialize
    try:
        # --- Perform Full Analysis ---
        # This will now use the refactored analyze_text_complexity which calls
        # analyze_single_spacy_sentence internally for all sentences.
        # Pass mode='full' for the standard analysis endpoint
        # Pass analysis_id for cancellation checks
        analysis_results = analyze_text_complexity(
            text_to_analyze,
            target_audience=target_audience_profile,
            mode='full',
            analysis_id=analysis_id # Pass ID
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
