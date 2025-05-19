#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipes return the exit code of the last command to exit with a non-zero status,
# or zero if all commands in the pipe exit successfully.
set -o pipefail

# --- Configuration ---
PYTHON_VERSION="python3"
VENV_DIR=".venv"
ENV_FILE=".env"
GITIGNORE_FILE=".gitignore"

# --- Helper Functions ---
print_info() {
    echo -e "\033[34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $1"
}

print_warning() {
    echo -e "\033[33m[WARNING]\033[0m $1"
}

print_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

# --- Main Script ---

print_info "Starting Development Environment Setup for Ubuntu..."

# 1. Install System Dependencies
print_info "Checking and installing system dependencies..."
sudo apt-get update -y

# Prompt before installing system packages
read -p "The script will attempt to install: python3, python3-venv, python3-pip, nodejs, npm, redis-server. Continue? (y/N) " -n 1 -r
echo # Move to a new line
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    print_warning "User aborted system package installation."
    exit 1
fi

sudo apt-get install -y $PYTHON_VERSION $PYTHON_VERSION-venv $PYTHON_VERSION-pip nodejs npm redis-server
print_success "System dependencies checked/installed."

# Start and enable Redis (common for servers)
print_info "Ensuring Redis server is running and enabled..."
sudo systemctl start redis-server
sudo systemctl enable redis-server
if sudo systemctl is-active --quiet redis-server; then
    print_success "Redis server is active."
else
    print_warning "Redis server does not seem to be active. Please check Redis installation."
fi


# 2. Create and Activate Virtual Environment
print_info "Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_VERSION -m venv $VENV_DIR
    print_success "Virtual environment created at $VENV_DIR."
else
    print_info "Virtual environment already exists at $VENV_DIR."
fi
# Commands will use the venv's python/pip directly

# 3. Install Python Dependencies
print_info "Installing Python dependencies from requirements.txt..."
"$VENV_DIR/bin/pip" install -r requirements.txt
print_success "Python dependencies installed."

# 4. Set up Environment Variables (.env file)
print_info "Setting up .env file..."
if [ ! -f "$ENV_FILE" ]; then
    print_info "Creating $ENV_FILE..."
    # Generate SECRET_KEY
    SECRET_KEY=$("$VENV_DIR/bin/python" -c 'import secrets; print(secrets.token_hex(32))')
    
    cat > "$ENV_FILE" << EOF
# Flask Core Settings
FLASK_ENV='development'
FLASK_DEBUG='true'
SECRET_KEY='$SECRET_KEY'

# API Keys (if you use these features - REPLACE with your actual keys)
# GEMINI_API_KEY=''
# DEEPSEEK_API_KEY=''

# Celery and Redis (defaults are usually fine if Redis is local)
# CELERY_BROKER_URL='redis://localhost:6379/0'
# CELERY_RESULT_BACKEND='redis://localhost:6379/0'
# RATE_LIMITER_REDIS_URL='redis://localhost:6379/0'

# Gunicorn settings (can also be set here, or in gunicorn.conf.py, or command line)
PORT='5001' # Port Gunicorn should bind to for development
GUNICORN_WORKERS='2' # Number of workers for development
EOF
    print_success "$ENV_FILE created with a new SECRET_KEY and development defaults."
    print_warning "Please review $ENV_FILE and add your API keys if needed."
else
    print_info "$ENV_FILE already exists. Skipping creation. Ensure it's configured correctly."
    if ! grep -q "SECRET_KEY=" "$ENV_FILE" || grep -q "SECRET_KEY='your_strong_random_secret_key_here'" "$ENV_FILE"; then
        print_warning "SECRET_KEY might be missing or using a placeholder in $ENV_FILE. Please verify."
    fi
fi

# Ensure .env is in .gitignore
if [ -f "$GITIGNORE_FILE" ]; then
    if ! grep -Fxq ".env" "$GITIGNORE_FILE"; then
        print_info "Adding .env to $GITIGNORE_FILE"
        echo ".env" >> "$GITIGNORE_FILE"
    fi
else
    print_info "Creating $GITIGNORE_FILE and adding .env"
    echo ".env" > "$GITIGNORE_FILE"
fi

# 5. Download NLTK Data
print_info "Downloading NLTK data (punkt, wordnet, omw-1.4, punkt_tab)..."
"$VENV_DIR/bin/python" -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('wordnet', quiet=True); nltk.download('omw-1.4', quiet=True); nltk.download('punkt_tab', quiet=True);"
print_success "NLTK data downloaded."

# 6. Install Frontend Dependencies
print_info "Installing frontend dependencies (npm install)..."
if [ -f "package.json" ]; then
    npm install
    print_success "Frontend dependencies installed."
else
    print_warning "package.json not found. Skipping npm install."
fi

# 7. Build Frontend Assets
print_info "Building frontend assets (npm run build:css)..."
if [ -f "package.json" ]; then # Check again in case npm install created it (unlikely but safe)
    if grep -q "build:css" package.json; then # Check if build:css script exists
        npm run build:css
        print_success "Frontend assets built."
    else
        print_warning "\"build:css\" script not found in package.json. Skipping CSS build."
    fi
else
    print_warning "package.json not found. Skipping CSS build."
fi

print_success "Development setup script completed!"
echo ""
print_info "To run the application (ensure Redis is running):"
print_info "1. Activate the virtual environment: source $VENV_DIR/bin/activate"
print_info "2. Run Gunicorn (with auto-reload for development): gunicorn --reload -c gunicorn.conf.py \"app:app\""
print_info "   (The app should be available at http://127.0.0.1:5001 or the port set in .env/gunicorn.conf.py)"
echo ""
print_info "Remember to manually add your API keys to the $ENV_FILE if needed." 