import logging # Add logging
from flask import render_template, request, jsonify
from app import app
# Import the analysis, synonym, and new gemini functions
from app.analysis import analyze_text_complexity
from app.synonyms import get_ranked_synonyms
from app.gemini_analysis import analyze_with_gemini # Import the new function
# frequency module is loaded automatically when synonyms/analysis imports it if needed

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
    """
    data = request.get_json()
    if not data or 'text' not in data:
        logging.warning("'/analyze' request missing 'text' field.")
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    # Get target audience profile for statistical analysis
    target_audience_profile = data.get('target_audience', 'Standard')
    # Get context awareness toggle state and goal for Gemini analysis
    context_awareness_enabled = data.get('context_awareness_enabled', False)
    target_audience_goal = data.get('target_audience_goal', '')

    logging.info(f"Received analysis request. Audience Profile: {target_audience_profile}, Context Aware: {context_awareness_enabled}, Goal: '{target_audience_goal[:50]}...'")

    # --- 1. Perform Statistical Analysis (Always) ---
    statistical_results = analyze_text_complexity(text_to_analyze, target_audience=target_audience_profile)

    # --- 2. Perform Gemini Analysis (Conditional) ---
    gemini_results = None
    if context_awareness_enabled and target_audience_goal and target_audience_goal.strip():
        logging.info("Context awareness enabled, calling Gemini analysis.")
        try:
            gemini_results = analyze_with_gemini(text_to_analyze, target_audience_goal)
            if gemini_results and "error" in gemini_results:
                 logging.warning(f"Gemini analysis returned an error: {gemini_results['error']}")
            elif not gemini_results:
                 logging.warning("Gemini analysis returned None.")
        except Exception as e:
            logging.error(f"Exception during Gemini analysis call: {e}", exc_info=True)
            gemini_results = {"error": f"Server error during Gemini analysis: {e}"}
    elif context_awareness_enabled:
        logging.warning("Context awareness enabled but target audience goal is missing. Skipping Gemini.")


    # --- 3. Combine Results ---
    # Start with the statistical results
    final_results = statistical_results
    # Add Gemini results if they exist
    if gemini_results:
        final_results['gemini_analysis'] = gemini_results
    else:
        # Explicitly set to null if not run or failed, so frontend knows
        final_results['gemini_analysis'] = None

    return jsonify(final_results)

# /synonyms endpoint (POST) - Remains unchanged for now
@app.route('/synonyms', methods=['POST'])
def get_synonyms():
    """Provides synonym suggestions."""
    data = request.get_json()
    if not data or 'word' not in data:
        return jsonify({"error": "Missing 'word' in request body"}), 400

    word_to_lookup = data.get('word', '')
    # Call the actual synonym function
    synonyms_list = get_ranked_synonyms(word_to_lookup)
    # Sort by rank for the API response
    synonyms_list.sort(key=lambda x: (x['rank'], x['word']))
    return jsonify({"synonyms": synonyms_list})
