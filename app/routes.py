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
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    target_audience_profile = data.get('target_audience', 'Standard')
    context_awareness_enabled = data.get('context_awareness_enabled', False) # Keep the toggle state

    logging.info(f"Received analysis request. Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    # --- Perform Full Analysis ---
    # This will now use the refactored analyze_text_complexity which calls
    # analyze_single_spacy_sentence internally for all sentences.
    analysis_results = analyze_text_complexity(text_to_analyze, target_audience=target_audience_profile)

    # --- Return Results ---
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

    logging.info(f"Received sequential analysis request. Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}")

    if not nlp:
         logging.error("spaCy model not loaded. Cannot perform sequential analysis.")
         return jsonify({"error": "Analysis service not available (spaCy model not loaded)."}), 500

    def generate_results():
        """Generator function to yield sentence analysis results."""
        try:
            doc = nlp(text_to_analyze)
            if not doc.has_annotation("SENT_START"):
                yield json.dumps({"error": "Sentence segmentation failed."}) + "\n"
                return # Stop generation

            # Select the profile
            profile = AUDIENCE_PROFILES.get(target_audience_profile, AUDIENCE_PROFILES["Standard"])

            for i, spacy_sentence in enumerate(doc.sents):
                # Analyze the single sentence
                sentence_result = analyze_single_spacy_sentence(spacy_sentence, doc, profile, i)
                if sentence_result:
                    # Yield the JSON result for the sentence
                    yield json.dumps(sentence_result) + "\n"

            # After all sentences, calculate and yield overall scores and readability
            # This requires iterating through the doc again or storing results temporarily.
            # For simplicity in streaming, let's calculate overall scores on the frontend
            # based on the received sentence results.
            # We can send a final message indicating completion or overall scores if needed.
            # For now, just ending the stream signals completion.

        except Exception as e:
            logging.error(f"Error during sequential analysis streaming: {e}", exc_info=True)
            yield json.dumps({"error": f"Server error during analysis: {e}"}) + "\n"

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
