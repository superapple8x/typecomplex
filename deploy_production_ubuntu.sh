#!/bin/bash

# TypeComplex Production Setup Script for Ubuntu
# Based on PRODUCTION_SETUP.MD

# Exit on errors
set -e

#########################
# HELPER FUNCTIONS
#########################

ask_yes_no() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0 ;;
            [Nn]* ) return 1 ;;
            * ) echo "Please answer yes or no." ;;
        esac
    done
}

print_step() {
    echo "-----------------------------------------------------"
    echo "STEP: $1"
    echo "-----------------------------------------------------"
}

get_user_input() {
    print_step "Gathering Information"

    read -p "Enter deployment username (default: pepper): " DEPLOY_USER
    DEPLOY_USER=${DEPLOY_USER:-pepper}

    read -p "Enter parent directory (default: /home/$DEPLOY_USER): " PROJECT_DIR_PARENT
    PROJECT_DIR_PARENT=${PROJECT_DIR_PARENT:-/home/$DEPLOY_USER}

    read -p "Enter project directory name (default: typecomplex): " PROJECT_NAME
    PROJECT_NAME=${PROJECT_NAME:-typecomplex}
    PROJECT_PATH="$PROJECT_DIR_PARENT/$PROJECT_NAME"

    read -p "Enter Git repository URL: " REPO_URL
    if [ -z "$REPO_URL" ]; then
        echo "Repository URL is required." >&2
        exit 1
    fi

    read -p "Enter domain name or server IP: " DOMAIN_OR_IP
    if [ -z "$DOMAIN_OR_IP" ]; then
        echo "Domain name or server IP is required." >&2
        exit 1
    fi

    read -s -p "Enter SECRET_KEY for Flask (leave blank to generate): " FLASK_SECRET_KEY
    echo
    if [ -z "$FLASK_SECRET_KEY" ]; then
        echo "Generating a new SECRET_KEY..."
        FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
        echo "Generated SECRET_KEY: $FLASK_SECRET_KEY"
    fi

    read -p "Enter Sentry DSN (leave blank if not using): " SENTRY_DSN_PROD

    read -p "Enter Gunicorn port (default: 5001): " GUNICORN_PORT
    GUNICORN_PORT=${GUNICORN_PORT:-5001}

    read -p "Enter Gunicorn workers (default: 3): " GUNICORN_WORKERS
    GUNICORN_WORKERS=${GUNICORN_WORKERS:-3}
}

setup_prerequisites() {
    print_step "System Prerequisites & Initial Setup"

    echo "Updating system packages..."
    sudo apt update && sudo apt upgrade -y

    echo "Installing required packages..."
    sudo apt install python3 python3-venv python3-pip nginx git redis-server -y

    echo "Enabling and starting Redis server..."
    sudo systemctl enable --now redis-server

    setup_deploy_user
    configure_firewall
}

setup_deploy_user() {
    if ! id "$DEPLOY_USER" &>/dev/null; then
        if ask_yes_no "User '$DEPLOY_USER' does not exist. Create this user?"; then
            sudo adduser --disabled-password --gecos "" "$DEPLOY_USER"
            echo "User '$DEPLOY_USER' created. Set a password or SSH keys manually."
            if [ "$PROJECT_DIR_PARENT" == "/home/$DEPLOY_USER" ]; then
                sudo mkdir -p "$PROJECT_DIR_PARENT"
                sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR_PARENT"
            fi
        else
            echo "User '$DEPLOY_USER' not created. Ensure the user exists with permissions to $PROJECT_DIR_PARENT." >&2
        fi
    else
        echo "User '$DEPLOY_USER' already exists."
    fi
}

configure_firewall() {
    echo "Configuring firewall (ufw)..."
    sudo ufw allow OpenSSH
    sudo ufw allow http
    sudo ufw allow https
    sudo ufw --force enable
}

deploy_application() {
    print_step "Deploying Application Code"

    # Ensure parent directory exists
    if [ ! -d "$PROJECT_DIR_PARENT" ]; then
        echo "Creating parent directory $PROJECT_DIR_PARENT..."
        sudo mkdir -p "$PROJECT_DIR_PARENT"
        sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR_PARENT" || 
            echo "Warning: Could not chown $PROJECT_DIR_PARENT to $DEPLOY_USER. Manual adjustment needed."
    fi

    # Clone repository if needed
    if [ -d "$PROJECT_PATH" ]; then
        echo "Project directory $PROJECT_PATH already exists. Skipping clone."
    else
        echo "Cloning repository $REPO_URL into $PROJECT_PATH..."
        sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$PROJECT_PATH"
    fi

    # Setup Python environment
    echo "Setting up Python virtual environment..."
    sudo -u "$DEPLOY_USER" python3 -m venv "$PROJECT_PATH/.venv"

    echo "Installing Python dependencies..."
    sudo -u "$DEPLOY_USER" "$PROJECT_PATH/.venv/bin/pip" install -r "$PROJECT_PATH/requirements.txt"
}

create_env_file() {
    print_step "Creating .env file"
    DOTENV_PATH="$PROJECT_PATH/.env"

    echo "Creating $DOTENV_PATH..."
    TMP_ENV_FILE=$(mktemp)

    cat << EOF > "$TMP_ENV_FILE"
# Flask Core Settings
FLASK_ENV='production'
FLASK_DEBUG='false'
SECRET_KEY='$FLASK_SECRET_KEY'

# Gunicorn settings
HOST='0.0.0.0'
PORT='$GUNICORN_PORT'
GUNICORN_WORKERS='$GUNICORN_WORKERS'
# GUNICORN_ACCESSLOG='-'
# GUNICORN_ERRORLOG='-'

# Celery and Redis
CELERY_BROKER_URL='redis://localhost:6379/0'
CELERY_RESULT_BACKEND='redis://localhost:6379/0'
RATE_LIMITER_REDIS_URL='redis://localhost:6379/0'
CELERY_CONCURRENCY='1'  # Recommended for memory optimization
CELERY_MAX_MEMORY_KB='1024000' # Recommended for memory optimization (~1GB)

# Sentry (Error Monitoring)
SENTRY_DSN='$SENTRY_DSN_PROD'
EOF

    sudo cp "$TMP_ENV_FILE" "$DOTENV_PATH"
    sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$DOTENV_PATH"
    sudo chmod 600 "$DOTENV_PATH"
    rm "$TMP_ENV_FILE"
    echo ".env file created at $DOTENV_PATH"
}

setup_nltk_and_frontend() {
    print_step "Setting up NLTK Data & Frontend Assets"

    # Download NLTK data
    NLTK_DATA_PATH="$PROJECT_PATH/nltk_data"
    sudo -u "$DEPLOY_USER" mkdir -p "$NLTK_DATA_PATH"
    echo "Downloading NLTK data to $NLTK_DATA_PATH..."
    sudo -u "$DEPLOY_USER" "$PROJECT_PATH/.venv/bin/python" -c "import nltk; nltk.download('punkt', download_dir='$NLTK_DATA_PATH'); nltk.download('wordnet', download_dir='$NLTK_DATA_PATH'); nltk.download('omw-1.4', download_dir='$NLTK_DATA_PATH');"

    # Build frontend assets if needed
    if [ -f "$PROJECT_PATH/package.json" ]; then
        echo "Building frontend assets..."
        if ! command -v npm &> /dev/null; then
            echo "npm not found. Install Node.js and npm manually to build frontend assets." >&2
        else
            echo "Running npm install..."
            sudo -u "$DEPLOY_USER" bash -c "cd '$PROJECT_PATH' && npm install"
            echo "Building frontend assets..."
            sudo -u "$DEPLOY_USER" bash -c "cd '$PROJECT_PATH' && npm run build:css"
        fi
    else
        echo "No package.json found. Skipping frontend build."
    fi
}

create_gunicorn_config() {
    print_step "Setting up Gunicorn Configuration"
    GUNICORN_CONF_PATH="$PROJECT_PATH/gunicorn.conf.py"
    
    if [ ! -f "$GUNICORN_CONF_PATH" ]; then
        echo "Creating $GUNICORN_CONF_PATH..."
        TMP_GUNICORN_CONF_FILE=$(mktemp)
        cat << EOF > "$TMP_GUNICORN_CONF_FILE"
import os
from dotenv import load_dotenv

# Load .env file from the project's root directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '$GUNICORN_PORT')}"
workers = int(os.getenv('GUNICORN_WORKERS', '$GUNICORN_WORKERS'))
threads = int(os.getenv('GUNICORN_THREADS', '1'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '30'))

accesslog = os.getenv('GUNICORN_ACCESSLOG', '-')
errorlog = os.getenv('GUNICORN_ERRORLOG', '-')
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')

preload_app = os.getenv('PRELOAD_APP', 'false').lower() == 'true'
EOF
        sudo cp "$TMP_GUNICORN_CONF_FILE" "$GUNICORN_CONF_PATH"
        sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$GUNICORN_CONF_PATH"
        rm "$TMP_GUNICORN_CONF_FILE"
    else
        echo "Using existing $GUNICORN_CONF_PATH."
    fi
}

setup_systemd_services() {
    # Gunicorn service
    print_step "Setting up systemd Services"
    
    echo "Creating Gunicorn systemd service..."
    SYSTEMD_GUNICORN_SERVICE_PATH="/etc/systemd/system/${PROJECT_NAME}.service"
    TMP_GUNICORN_SYSTEMD_FILE=$(mktemp)
    
    cat << EOF > "$TMP_GUNICORN_SYSTEMD_FILE"
[Unit]
Description=${PROJECT_NAME} Gunicorn Daemon
After=network.target

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_PATH
EnvironmentFile=$PROJECT_PATH/.env
ExecStart=$PROJECT_PATH/.venv/bin/gunicorn -c $PROJECT_PATH/gunicorn.conf.py "app:app"
Restart=always
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${PROJECT_NAME}-gunicorn

[Install]
WantedBy=multi-user.target
EOF
    sudo cp "$TMP_GUNICORN_SYSTEMD_FILE" "$SYSTEMD_GUNICORN_SERVICE_PATH"
    rm "$TMP_GUNICORN_SYSTEMD_FILE"

    # Celery service
    echo "Creating Celery systemd service..."
    SYSTEMD_CELERY_SERVICE_PATH="/etc/systemd/system/${PROJECT_NAME}-celery.service"
    TMP_CELERY_SYSTEMD_FILE=$(mktemp)
    
    cat << EOF > "$TMP_CELERY_SYSTEMD_FILE"
[Unit]
Description=${PROJECT_NAME} Celery Worker Daemon
After=network.target redis.service
Requires=redis.service

[Service]
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_PATH
EnvironmentFile=$PROJECT_PATH/.env
ExecStart=$PROJECT_PATH/.venv/bin/celery -A app.celery worker -l info --concurrency=${CELERY_CONCURRENCY} --max-memory-per-child=${CELERY_MAX_MEMORY_KB}
Restart=always
RestartSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${PROJECT_NAME}-celery

[Install]
WantedBy=multi-user.target
EOF
    sudo cp "$TMP_CELERY_SYSTEMD_FILE" "$SYSTEMD_CELERY_SERVICE_PATH"
    rm "$TMP_CELERY_SYSTEMD_FILE"

    echo "Reloading systemd daemon..."
    sudo systemctl daemon-reload
}

setup_nginx() {
    print_step "Setting up Nginx"
    NGINX_CONF_PATH="/etc/nginx/conf.d/${PROJECT_NAME}.conf"

    echo "Creating Nginx configuration..."
    TMP_NGINX_CONF_FILE=$(mktemp)
    
    cat << EOF > "$TMP_NGINX_CONF_FILE"
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN_OR_IP;

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    listen [::]:443 ssl;
    http2 on;
    server_name $DOMAIN_OR_IP;

    # Placeholder until Certbot runs
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;

    # Certbot will manage these lines:
    # ssl_certificate /etc/letsencrypt/live/$DOMAIN_OR_IP/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/$DOMAIN_OR_IP/privkey.pem;
    # include /etc/letsencrypt/options-ssl-nginx.conf;
    # ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    location /static {
        alias $PROJECT_PATH/app/static;
        expires 30d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:$GUNICORN_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    sudo cp "$TMP_NGINX_CONF_FILE" "$NGINX_CONF_PATH"
    rm "$TMP_NGINX_CONF_FILE"

    echo "Testing Nginx configuration..."
    sudo nginx -t
}

print_final_instructions() {
    print_step "Setup Complete! Next Steps:"

    cat << EOF
1. Enable and start services:
   sudo systemctl enable ${PROJECT_NAME}.service
   sudo systemctl start ${PROJECT_NAME}.service
   sudo systemctl status ${PROJECT_NAME}.service

   sudo systemctl enable ${PROJECT_NAME}-celery.service
   sudo systemctl start ${PROJECT_NAME}-celery.service
   sudo systemctl status ${PROJECT_NAME}-celery.service

   sudo systemctl reload nginx

2. Setup HTTPS with Certbot:
   Ensure your domain '$DOMAIN_OR_IP' DNS A record points to this server's IP.
   Then run:
   sudo apt install certbot python3-certbot-nginx -y
   sudo certbot --nginx -d $DOMAIN_OR_IP

3. Test your application at: https://$DOMAIN_OR_IP

4. Review PRODUCTION_SETUP.MD for more details on testing, database, Sentry, etc.
EOF
}

#########################
# MAIN EXECUTION
#########################

# Get user input for deployment configuration
get_user_input

# Setup the server environment
setup_prerequisites

# Deploy the application
deploy_application

# Create configuration files
create_env_file
create_gunicorn_config

# Setup NLTK data and build frontend assets
setup_nltk_and_frontend

# Configure services
setup_systemd_services
setup_nginx

# Print final instructions
print_final_instructions

echo "Script finished." 