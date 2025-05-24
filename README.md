# TypeComplex - Sentence Complexity Analyzer

## Overview

TypeComplex is a web application designed to analyze the complexity of English sentences. It helps writers, educators, and researchers assess text readability and identify areas for improvement. Users can input text directly or upload PDF documents. The application provides a suite of metrics, leveraging traditional readability formulas, NLP techniques, and optional LLM-powered insights.

## Demo

TypeComplex empowers users to deeply understand and refine their writing through an interactive and intuitive interface. Here's a glimpse of its core capabilities:

1.  **Comprehensive Text Analysis:**
    *   Simply paste your text into the editor or upload a PDF document.
    *   Instantly receive an overall complexity assessment, along with traditional readability scores (Flesch-Kincaid Grade Level, Gunning Fog Index, SMOG Index).
    *   Dive deeper with a sentence-by-sentence breakdown, where each sentence's complexity is evaluated based on a configurable "Target Audience" profile.
    *   The analysis considers a rich set of linguistic features:
        *   **Lexical:** Word frequency, use of nominalizations, balance of content vs. function words.
        *   **Syntactic:** Sentence structure depth, clause counts, complexity of grammatical dependencies, and prepositional phrase usage.
        *   **Semantic:** Contextual word meaning complexity (via embeddings) and logical coherence within sentences.
    *   `![TypeComplex Analysis UI](https://github.com/superapple8x/typecomplex/blob/main/docs/analysis.gif)`

2.  **Target Audience Adaptation:**
    *   Choose from predefined "Target Audience" profiles (e.g., "General Public", "Academic / Technical", "Standard").
    *   The complexity metrics and their weighting are adjusted based on the selected profile, providing tailored feedback on whether your text is appropriate for the intended readers.
    *   `![TypeComplex Audience Selection](https://github.com/superapple8x/typecomplex/blob/main/docs/target.gif)`

3.  **Intelligent Rewrite Suggestions:**
    *   For sentences identified as overly complex or awkward for the target audience, TypeComplex can offer LLM-powered rewrite suggestions (leveraging models like DeepSeek/Gemini).
    *   These suggestions aim to improve clarity and readability while preserving the original meaning.
    *   `![TypeComplex Rewrite Suggestion](https://github.com/superapple8x/typecomplex/blob/main/docs/rewrite.gif)`

4.  **Contextual Synonym Suggestions:**
    *   Select a word within your text to receive a list of contextually relevant synonyms.
    *   The system can use both traditional thesaurus lookups (WordNet) and LLM-enhanced suggestions to provide fitting alternatives that can help vary vocabulary or adjust tone.
    *   `![TypeComplex Synonym Feature](https://github.com/superapple8x/typecomplex/blob/main/docs/synonym.gif)`

5.  **Seamless PDF Import & Analysis:**
    *   Upload PDF documents directly through the "PDF Toolkit".
    *   TypeComplex extracts the text content and performs the same comprehensive complexity analysis as for pasted text.
    *   This is ideal for reviewing existing documents, reports, or academic papers.
    *   `![TypeComplex PDF Import](https://github.com/superapple8x/typecomplex/blob/main/docs/pdf.gif)`

## Features

*   **Input Methods:**
    *   Direct text pasting.
    *   PDF document upload (text is extracted using PyMuPDF).
*   **Comprehensive Complexity Analysis:**
    *   **Audience Profiles:** Tailor analysis with predefined profiles ("Standard", "General Public", "Academic / Technical"), each with specific weighting and thresholds for metrics.
    *   **Traditional Readability Scores:** (calculated via `textstat`)
        *   Flesch-Kincaid Grade Level
        *   Gunning Fog Index
        *   SMOG Index
    *   **Core Textual Statistics:** (calculated via `textstat` and custom logic)
        *   Sentence count, word count, character count
    *   **Lexical Analysis:**
        *   Average word frequency ( leveraging `app.frequency.get_word_frequency` which uses a frequency corpus)
        *   Nominalization density (identifying nouns derived from verbs or adjectives, indicating potentially abstract or complex language - via spaCy)
        *   Content word vs. function word ratio (analyzing the balance of meaning-carrying words to grammatical words - via spaCy)
    *   **Syntactic Analysis (using spaCy):**
        *   **Syntactic Complexity Score Component:** Derived from:
            *   Parse Tree Depth: Measures the depth of the syntactic structure of a sentence.
            *   Clause Count: Number of clauses within a sentence.
        *   **Dependency Complexity Score Component:** Derived from:
            *   Complex Dependency Density: Identifies and quantifies complex grammatical relationships (e.g., clausal subjects/objects).
            *   Subordination Density: Measures the ratio of subordinate clauses to main clauses.
            *   Prepositional Phrase (PP) Density & Nesting: Assesses the frequency and a PPs within PPs.
    *   **Semantic Analysis:**
        *   **Contextual Embedding Complexity:** (using Hugging Face Transformer models like BERT, or remote endpoints). This metric assesses how context-dependent and potentially ambiguous word meanings are, based on their embeddings.
        *   **Semantic Coherence:** (using spaCy word vectors or transformer embeddings). This measures the relatedness of words and concepts within a sentence, indicating how well the sentence flows logically.
    *   **LLM-Powered Enhancements (Optional, via DeepSeek/Gemini integrations):**
        *   Contextual synonym suggestions.
        *   Sentence rewrite/simplification suggestions.
*   **Asynchronous Processing:** Celery and Redis handle computationally intensive analyses (especially PDF processing and potentially some "best" mode analyses) in the background, improving UI responsiveness.
*   **User Interface:** Web-based interface built with Flask, HTML, and Tailwind CSS.
*   **Task Management:** Supports cancellation of ongoing analysis tasks.
*   **Rate Limiting:** Protects the service from abuse, with configurable limits for different analysis modes.

## Tech Stack

*   **Backend:** Python 3.x, Flask
*   **Task Queue:** Celery
*   **Message Broker & Cache:** Redis
*   **NLP Libraries:**
    *   NLTK (sentence tokenization, POS tagging, WordNet)
    *   spaCy (`en_core_web_sm`, `en_core_web_lg` for sentence segmentation, tokenization, POS tagging, dependency parsing, named entity recognition, word vectors)
    *   `textstat` (for a wide range of readability scores)
    *   Hugging Face `transformers` (for BERT-like models, e.g., `bert-base-uncased`)
    *   `sentence-transformers` (potentially used for generating sentence embeddings)
    *   `torch` (underlying library for deep learning models)
*   **PDF Processing:** PyMuPDF (`fitz`)
*   **Frontend:** HTML, Tailwind CSS, JavaScript (primarily for UI interactions and API calls)
*   **WSGI Server (Production):** Gunicorn
*   **Reverse Proxy (Production):** Nginx (recommended in `PRODUCTION_SETUP.MD`)
*   **Database:**
    *   Redis: Used extensively for Celery, caching, and rate limiting.
    *   `psycopg2-binary` is listed in `requirements.txt`, suggesting potential (optional or future) integration with PostgreSQL. The core functionality described seems to rely on Redis and file system for persistence.
*   **Error Monitoring:** Sentry (configurable via environment variable `SENTRY_DSN`)
*   **Environment Management:** `python-dotenv` (loads `.env` file)

## Project Structure

A brief overview of key directories:

*   `app/`: Core Flask application.
    *   `__init__.py`: Flask app factory, Celery initialization.
    *   `routes.py`: Defines web page routes and API endpoints.
    *   `analysis.py`: Contains the primary logic for sentence complexity calculation.
    *   `pdf_handler.py`: Logic for PDF uploading and text extraction.
    *   `tasks.py`: Celery background task definitions (e.g., `process_pdf_task`).
    *   `deepseek_analysis.py`, `gemini_analysis.py`: Integrations with external AI models.
    *   `rate_limiter.py`: Implements request rate limiting.
    *   `static/`: Static frontend assets (CSS, JS, images). Compiled CSS is usually here.
    *   `templates/`: HTML templates rendered by Flask.
    *   `data/`: May contain data files for NLP models or frequency lists.
*   `requirements.txt`: Python dependencies for `pip`.
*   `package.json`: Frontend (npm) dependencies and script definitions (e.g., for Tailwind CSS).
*   `tailwind.config.js`, `postcss.config.js`: Configuration for Tailwind CSS.
*   `gunicorn.conf.py`: Gunicorn server configuration.
*   `.env.example`: Template for environment variables (see content in conversation).
*   `DEVELOPMENT_SETUP.MD`: Detailed guide for setting up a local development environment.
*   `PRODUCTION_SETUP.MD`: Detailed guide for deploying to a production server.
*   `uploads/`: Default directory for temporary storage of uploaded files.
*   `processed_pdfs/`: Default directory for storing outputs of PDF processing tasks.
*   `test_pdfs/`: Likely contains sample PDFs for testing.
*   `LICENSE`: Project's license file.

## Getting Started

### Prerequisites

*   Python (version as per `DEVELOPMENT_SETUP.MD`, typically 3.8+)
*   Node.js and npm (for frontend asset building)
*   Redis server (running locally or accessible via network)

### Development Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url> typecomplex
    cd typecomplex
    ```
2.  **Create and activate a Python virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up environment variables:**
    *   Copy `.env.example` to `.env`: `cp .env.example .env`
    *   Modify `.env` with your specific settings:
        *   **Crucially, generate a `SECRET_KEY`**:
            ```bash
            python -c "import secrets; print(secrets.token_hex(32))"
            ```
        *   Ensure `FLASK_ENV=development` and `FLASK_DEBUG=true`.
        *   Configure `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` if your Redis server is not at `redis://localhost:6379/0`.
        *   Add API keys (`GEMINI_API_KEY`, `DEEPSEEK_API_KEY`) if you plan to use those features.
        *   Review other settings like `APP_BERT_LOCAL_MODEL_NAME` or `APP_BERT_EXECUTION_MODE` if you want to change default NLP model behavior.
5.  **Download NLTK data:**
    The application may download these on first use, but pre-downloading is recommended.
    ```bash
    python -c "import nltk; nltk.download('punkt'); nltk.download('wordnet'); nltk.download('omw-1.4'); nltk.download('averaged_perceptron_tagger'); nltk.download('universal_tagset');"
    ```
    As noted in `DEVELOPMENT_SETUP.MD`, on some systems you might also need:
    ```bash
    python -c "import nltk; nltk.download('punkt_tab');"
    ```
6.  **Download spaCy models:**
    The application attempts to download these if missing, but manual download ensures they are available.
    ```bash
    python -m spacy download en_core_web_sm
    python -m spacy download en_core_web_lg # Required for 'best' analysis mode
    ```
7.  **Install frontend dependencies:**
    ```bash
    npm install
    ```
8.  **Build frontend assets (Tailwind CSS):**
    ```bash
    npm run build:css 
    # For development, you can use npm run watch:css to auto-rebuild on changes
    ```

### Running the Application (Development)

1.  **Ensure your Redis Server is running.**
2.  **Activate the virtual environment:** `source .venv/bin/activate`
3.  **Start the Celery Worker (in a dedicated terminal):**
    ```bash
    celery -A app.celery worker -l info --concurrency=1 # Adjust concurrency based on your dev machine
    ```
4.  **Run the Flask/Gunicorn Server (in another dedicated terminal):**
    The `DEVELOPMENT_SETUP.MD` recommends Gunicorn with reload for a development experience closer to production:
    ```bash
    gunicorn --reload -c gunicorn.conf.py "app:app"
    ```
    Alternatively, for simpler Flask debugging (might not fully represent all Gunicorn behaviors or support all concurrent features as robustly):
    ```bash
    # Ensure FLASK_APP=app:app and FLASK_DEBUG=true are in your .env or shell environment
    # flask run -p 5001 
    ```
    The application should typically be accessible at `http://127.0.0.1:5001` (or the port configured in `.env` / `gunicorn.conf.py`).

## Production Deployment

For deploying TypeComplex to a production environment, refer to the comprehensive guide: `PRODUCTION_SETUP.MD`. This document covers setup using Gunicorn, Nginx (as a reverse proxy, for SSL termination, and serving static files), and `systemd` for process management.

## API Endpoints

The application provides several HTTP endpoints for its functionality. Key endpoints include:

*   **`POST /analyze`**:
    *   Purpose: Analyzes the full text complexity.
    *   Request (JSON): `{ "text": "...", "target_audience": "Standard", "mode": "better", "analysisId": "client-uuid", "context_awareness_enabled": false }`
    *   Response (JSON): Detailed analysis results.
*   **`POST /analyze_sequential`**:
    *   Purpose: Streams sentence-by-sentence analysis results.
    *   Request (JSON): `{ "text": "...", "target_audience": "Standard", "analysisId": "client-uuid", "context_awareness_enabled": false }`
    *   Response (Streaming JSON): Individual sentence analysis objects.
*   **`POST /synonyms`**:
    *   Purpose: Get ranked synonym suggestions.
    *   Request (JSON): `{ "word": "...", "sentence_context": "...", "target_audience": "Standard", "context_awareness_enabled": false }`
    *   Response (JSON): List of synonyms.
*   **`POST /rewrite_suggestion`**:
    *   Purpose: Get AI-powered sentence rewrite suggestions.
    *   Request (JSON): `{ "sentence": "...", "target_audience": "Standard", "instruction": "simplify" }`
    *   Response (JSON): Rewrite suggestions.
*   **`POST /upload_pdf`**:
    *   Purpose: Uploads a PDF for asynchronous analysis.
    *   Request (form-data): `file` (PDF), `target_audience`, `mode`.
    *   Response (JSON): `{ "task_id": "..." }`.
*   **`GET /task_status/<task_id>`**:
    *   Purpose: Check status of a background task.
    *   Response (JSON): Task status and progress.
*   **`GET /get_extracted_text/<task_id>`**:
    *   Purpose: Retrieve results from a completed PDF processing task.
    *   Response (JSON): Extracted text and analysis.
*   **`GET /download_highlighted_pdf/<task_id>`**:
    *   Purpose: Download PDF with highlighted complex sentences.
    *   Response: PDF file stream.
*   **`POST /cancel_analysis`**:
    *   Purpose: Request cancellation of an ongoing analysis.
    *   Request (JSON): `{ "analysisId": "..." }`
    *   Response (JSON): Cancellation status.
*   **`GET /api/get_rate_limits`**:
    *   Purpose: Provides client with current rate limit settings.
    *   Response (JSON): Rate limit configuration.

See `app/routes.py` for full details on request/response structures.

Please ensure your code adheres to PEP 8 guidelines for Python and any existing code style.
For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the terms of the **MIT License**. See the `LICENSE` file for more details.