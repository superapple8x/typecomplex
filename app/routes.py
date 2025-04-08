from flask import render_template, request, jsonify
from app import app
# Import the analysis and synonym functions
from app.analysis import analyze_text_complexity
from app.synonyms import get_ranked_synonyms
# frequency module is loaded automatically when synonyms/analysis imports it if needed

@app.route('/')
def index():
    """Renders the main page."""
    # This will look for index.html in the 'templates' folder
    return render_template('index.html')

# Placeholder for the /analyze endpoint (POST)
@app.route('/analyze', methods=['POST'])
def analyze_text():
    """Analyzes the text complexity."""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' in request body"}), 400

    text_to_analyze = data.get('text', '')
    # Call the actual analysis function
    results = analyze_text_complexity(text_to_analyze)
    return jsonify(results) # Return the whole dictionary {results: [...], overall_score: ...}

# Placeholder for the /synonyms endpoint (POST)
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