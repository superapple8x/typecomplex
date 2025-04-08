# Development Setup

This document outlines the steps required to set up and run the Sentence Complexity Analyzer project locally.

## Prerequisites

*   Python 3.x installed
*   Node.js and npm installed (for frontend dependencies and build process)

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
    Install the required Python packages, including Flask and NLTK.
    ```bash
    pip install -r requirements.txt # Assuming a requirements.txt exists or create one
    # If requirements.txt doesn't exist, install manually:
    # pip install Flask nltk
    ```
    *Note: The initial setup might have installed Flask globally, but using a venv is preferred.*

4.  **Download NLTK Data:**
    Run Python and download the necessary NLTK data (`punkt` for tokenization, `wordnet` and `omw-1.4` for synonyms).
    ```python
    import nltk
    nltk.download('punkt')
    nltk.download('wordnet')
    nltk.download('omw-1.4')
    exit()
    ```

5.  **Install Frontend Dependencies:**
    Install Node.js packages defined in `package.json`.
    ```bash
    npm install
    ```

6.  **Build Frontend Assets:**
    Compile the Tailwind CSS.
    ```bash
    npm run build:css
    ```

## Running the Application

1.  **Activate Virtual Environment (if not already active):**
    ```bash
    source .venv/bin/activate # On Windows use: .venv\Scripts\activate
    ```

2.  **Run the Flask Development Server:**
    ```bash
    flask run
    ```
    The application should now be accessible at `http://127.0.0.1:5000` (or the address provided by Flask).

## Development Workflow

*   For CSS changes, you can run `npm run watch:css` in a separate terminal to automatically rebuild `style.css` when `input.css` or related files change.
*   Remember to activate the virtual environment (`source .venv/bin/activate`) in any new terminal session before running `flask` commands.