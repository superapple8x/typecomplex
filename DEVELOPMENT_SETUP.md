# Development Setup

This document outlines the steps required to set up and run the Sentence Complexity Analyzer project locally for development.

## Prerequisites

*   Python 3.x installed
*   Node.js and npm installed (for frontend dependencies and build process)
*   Access to a Redis server (for Celery; app-level rate limiting has been removed)

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create and Activate Virtual Environment:**
    It's recommended to use a virtual environment to manage Python dependencies.
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```

3.  **Install Python Dependencies:**
    Install the required Python packages, including Flask, Gunicorn, Celery, NLTK, and python-dotenv.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables (`.env` file):**
    The application uses a `.env` file in the project root to manage configuration and secrets.
    *   Create a file named `.env` in the root of the project (`/home/pepper/typecomplex/.env`).
    *   Add the following necessary configurations. Generate a strong `SECRET_KEY`.

    ```env
    # Flask Core Settings
    FLASK_ENV='development'
    FLASK_DEBUG='true'
    SECRET_KEY='your_strong_random_secret_key_here' # Generate one using: python -c 'import secrets; print(secrets.token_hex(32))'

    # API Keys (if you use these features)
    # GEMINI_API_KEY='your_gemini_api_key'
    # DEEPSEEK_API_KEY='your_deepseek_api_key'

    # Celery and Redis (defaults are usually fine if Redis is local)
    # CELERY_BROKER_URL='redis://localhost:6379/0'
    # CELERY_RESULT_BACKEND='redis://localhost:6379/0'
    # (rate limiter removed; no RATE_LIMITER_* variables)

    # Gunicorn settings (can also be set here, or in gunicorn.conf.py, or command line)
    # PORT='5001' # Port Gunicorn should bind to
    # GUNICORN_WORKERS='2' # Number of workers for development
    ```
    **Important:** Add `.env` to your `.gitignore` file to prevent committing secrets.

5.  **Download NLTK Data:**
    Run Python and download the necessary NLTK data (`punkt` for tokenization, `wordnet` and `omw-1.4` for synonyms).
    ```bash
    python -c "import nltk; nltk.download('punkt'); nltk.download('wordnet'); nltk.download('omw-1.4');"
    ```
    *(See Troubleshooting section below for potential issues with 'punkt' on some systems).*

6.  **Install Frontend Dependencies:**
    Install Node.js packages defined in `package.json`.
    ```bash
    npm install
    ```

7.  **Build Frontend Assets:**
    Compile the Tailwind CSS.
    ```bash
    npm run build:css
    ```
    *(See Troubleshooting section below if this command fails).)*

## Running the Application

The application is run using the Gunicorn WSGI server.

1.  **Ensure Redis Server is Running:**
    The application uses Redis for Celery task queues. App-level rate limiting has been removed. Make sure your Redis server is running.

2.  **Activate Virtual Environment (if not already active):**
    ```bash
    source .venv/bin/activate # On Windows use: .venv\Scripts\activate
    ```

3.  **Run the Gunicorn Server:**
    The project includes a `gunicorn.conf.py` file that's configured to pick up environment variables (like `PORT` from your `.env` file).
    ```bash
    gunicorn -c gunicorn.conf.py "app:app"
    ```
    Alternatively, you can run Gunicorn with specific command-line options (though the config file is preferred for consistency):
    ```bash
    # Example: gunicorn --workers 2 --bind 0.0.0.0:5001 "app:app"
    ```
    The application should now be accessible based on the Gunicorn configuration (e.g., `http://127.0.0.1:5001` if `PORT=5001` is set and Gunicorn binds to `0.0.0.0` or `127.0.0.1`). Check Gunicorn's startup messages for the exact address.

    Your Flask app (`app/__init__.py`) is configured to load variables from the `.env` file, so `FLASK_DEBUG=true` and your `SECRET_KEY` will be used.

## Development Workflow

*   **Backend Changes:** Gunicorn by default does not auto-reload on Python code changes like `flask run --debug` does. For development, you can run Gunicorn with the `--reload` flag:
    ```bash
    gunicorn --reload -c gunicorn.conf.py "app:app"
    ```
    This will restart workers when Python files are modified. Be aware that `--reload` is not suitable for production.
*   **Frontend Changes:** For CSS changes, you can run `npm run watch:css` in a separate terminal to automatically rebuild `style.css` when `input.css` or related files change.
*   **Settings Schema & Migrations:** Electron settings are stored via `electron-store` without secrets (preferences only). A versioned schema with migrations ensures forward compatibility. Secrets (like the DeepSeek API key) are stored by the backend using the OS keychain or an encrypted-file fallback and never appear in the Electron store.
  * Schema version is managed in `electron/settingsStore.js` (`SETTINGS_SCHEMA_VERSION`).
  * On app startup, migrations run automatically.
  * Preferences can be exported/imported (non-secret) through the `settings` API exposed by preload.
*   Remember to activate the virtual environment (`source .venv/bin/activate`) in any new terminal session before running `gunicorn` or Python commands.

## Troubleshooting / Environment Notes

### Tailwind CSS Build Failure (Especially on WSL or after OS change)

If the `npm run build:css` command fails with an error like `../tailwindcss/lib/cli.js: not found`, it might be due to issues with the Node.js module installation, potentially caused by switching operating systems (e.g., from Linux to Windows/WSL) or corrupted dependencies.

**Solution:** Perform a clean reinstall of Node.js dependencies:
```bash
# 1. Remove existing modules and lock file
rm -rf node_modules package-lock.json

# 2. Reinstall dependencies
npm install

# 3. Try the build command again
npm run build:css
```
This ensures that the dependencies are installed correctly for the current environment.

### NLTK 'punkt' Tokenizer Issues (Ubuntu/WSL)

On some systems (observed on Ubuntu 24 within WSL), the application might fail to load the NLTK 'punkt' tokenizer even after `nltk.download('punkt')` reports success. This can manifest as errors mentioning `punkt_tab` not found during application startup.

**Solution:** Explicitly download the `punkt_tab` resource using the NLTK downloader:
```bash
python -c "import nltk; nltk.download('punkt_tab');"
```
Run this command within your activated virtual environment after installing Python dependencies. This seems necessary for NLTK to correctly locate the required tokenizer data in these specific environments.