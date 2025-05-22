# Production Setup for TypeComplex

This document outlines the steps to deploy the TypeComplex application to a production Linux server. It assumes a dedicated server (or VPS) running a modern Linux distribution (e.g., Ubuntu, Fedora).

**Key Components of this Production Setup:**
*   **Gunicorn:** WSGI server to run the Flask application.
*   **Celery:** Distributed task queue for background processing.
*   **Nginx:** Reverse proxy, HTTPS/SSL termination, static file serving.
*   **systemd:** Process management for Gunicorn and Celery workers.
*   **Redis:** Message broker for Celery and for rate limiting (assumed to be installed and running).
*   **Environment Variables (`.env`):** For all configuration.

## 1. Server Prerequisites & Initial Setup

1.  **Update System:**
    ```bash
    sudo apt update && sudo apt upgrade -y # For Debian/Ubuntu
    # sudo dnf update -y # For Fedora/CentOS
    ```

2.  **Install Python, venv, pip, Nginx, Git:**
    ```bash
    sudo apt install python3 python3-venv python3-pip nginx git -y # For Debian/Ubuntu
    # sudo dnf install python3 python3-pip nginx git -y # For Fedora/CentOS
    # sudo dnf groupinstall "Development Tools" -y # For Fedora, for build tools
    ```

3.  **Install Redis (if not already available):**
    Follow official Redis installation guides. Ensure it's running and enabled.
    ```bash
    sudo apt install redis-server -y # For Debian/Ubuntu
    sudo systemctl enable --now redis-server
    # sudo dnf install redis -y # For Fedora/CentOS
    # sudo systemctl enable --now redis
    ```

4.  **Create a Dedicated User (Recommended):**
    It's good practice to run your application under a non-root user. Let's assume the user is `pepper`.
    ```bash
    # sudo adduser pepper
    # sudo usermod -aG sudo pepper # If this user needs sudo privileges for setup
    # su - pepper # Switch to the new user for subsequent steps
    ```
    *Ensure this user has a home directory, e.g., `/home/pepper`.*

5.  **Configure Firewall:**
    Allow SSH, HTTP, and HTTPS. `ufw` example for Ubuntu:
    ```bash
    sudo ufw allow OpenSSH
    sudo ufw allow http
    sudo ufw allow https
    sudo ufw enable
    ```
    For `firewalld` (Fedora/CentOS):
    ```bash
    sudo firewall-cmd --permanent --add-service=ssh
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
    ```

## 2. Deploy Application Code

1.  **Clone Repository:**
    (As the `pepper` user, or your deployment user)
    ```bash
    cd /home/pepper # Or your desired deployment directory parent
    git clone <your-repository-url> typecomplex
    cd typecomplex
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Deactivate the virtual environment for now if you wish: `deactivate`)*

## 3. Environment Configuration (`.env` file)

Create a `.env` file in the project root (`/home/pepper/typecomplex/.env`).
**This file should NOT be committed to Git if it contains real secrets.**

```env
# Flask Core Settings
FLASK_ENV='production'
FLASK_DEBUG='false'
SECRET_KEY='generate_a_very_strong_random_secret_key_for_production' # Use: python -c 'import secrets; print(secrets.token_hex(32))'

# Gunicorn settings
HOST='0.0.0.0' # Gunicorn bind host
PORT='5001'    # Gunicorn bind port (Nginx will proxy to this)
GUNICORN_WORKERS='3' # Example: (2 * number_of_cpu_cores) + 1. Adjust based on server.
# GUNICORN_THREADS='1' # If using a sync worker type (default)
# GUNICORN_TIMEOUT='30'
# GUNICORN_LOG_LEVEL='info'
# GUNICORN_ACCESSLOG='-' # To stdout, for systemd to capture
# GUNICORN_ERRORLOG='-'  # To stderr, for systemd to capture
# PRELOAD_APP='false' # Set to 'true' to preload app, test for memory savings vs. issues

# Celery and Redis
CELERY_BROKER_URL='redis://localhost:6379/0'
CELERY_RESULT_BACKEND='redis://localhost:6379/0'
RATE_LIMITER_REDIS_URL='redis://localhost:6379/0'
CELERY_CONCURRENCY='1'  # Recommended: Start with 1 worker for memory-constrained Bert usage
CELERY_MAX_MEMORY_KB='1024000' # Recommended: ~1GB max memory per Celery worker child process. Adjust as needed.

# Sentry (Error Monitoring)
SENTRY_DSN='your_sentry_dsn_for_production' # If using Sentry

# API Keys (if your application uses them)
# GEMINI_API_KEY='your_production_gemini_api_key'
# DEEPSEEK_API_KEY='your_production_deepseek_api_key'

# Database (if applicable and not SQLite)
# DATABASE_URL='postgresql://user:password@host:port/database'
```

**Important:**
*   Generate a **strong, unique `SECRET_KEY`** for your production environment.
*   Adjust `GUNICORN_WORKERS` based on your server's CPU cores.
*   Set `SENTRY_DSN` if you use Sentry.
*   Ensure Redis URLs are correct for your Redis server setup.

## 4. NLTK Data & Frontend Assets

1.  **Download NLTK Data:**
    (Activate virtual environment: `source /home/pepper/typecomplex/.venv/bin/activate`)
    ```bash
    python -c "import nltk; nltk.download('punkt', download_dir='/home/pepper/typecomplex/nltk_data'); nltk.download('wordnet', download_dir='/home/pepper/typecomplex/nltk_data'); nltk.download('omw-1.4', download_dir='/home/pepper/typecomplex/nltk_data');"
    ```
    *It's often better to specify `download_dir` to a persistent location within your project or a shared data directory accessible by your application user, especially if `nltk.data.path` isn't automatically picking it up correctly in the production environment.*
    You might need to configure `app/__init__.py` or use environment variable `NLTK_DATA` to point to this custom path if NLTK doesn't find it.

2.  **Install Frontend Dependencies & Build Assets:**
    (Still in project root, with venv active if any Python scripts are involved in build)
    ```bash
    npm install
    npm run build:css
    ```

## 5. Gunicorn Configuration (`gunicorn.conf.py`)

Your project should already have a `gunicorn.conf.py` file. Ensure it's configured to load settings primarily from environment variables (which will be supplied from the `.env` file or systemd service).

Example content for `/home/pepper/typecomplex/gunicorn.conf.py`:
```python
import os

# General Settings
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '5001')}"
workers = int(os.getenv('GUNICORN_WORKERS', '2')) # Number of worker processes
threads = int(os.getenv('GUNICORN_THREADS', '1')) # Threads per worker for sync workers
timeout = int(os.getenv('GUNICORN_TIMEOUT', '30')) # Worker timeout

# Logging
accesslog = os.getenv('GUNICORN_ACCESSLOG', '-') # '-' means log to stdout
errorlog = os.getenv('GUNICORN_ERRORLOG', '-')   # '-' means log to stderr
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')

# Preloading application (can save memory, but ensure app is fork-safe)
# Be cautious with this setting, especially if you have complex initializations (e.g., ML models)
# Test thoroughly if you enable it.
preload_app = os.getenv('PRELOAD_APP', 'false').lower() == 'true'

# Server Hooks (if any needed, e.g. for Sentry with Gunicorn)
# def on_starting(server):
#     # Code to run on Gunicorn master start
#     pass

# def post_fork(server, worker):
#     # Code to run after a worker has been forked
#     pass

# Ensure a .env file is loaded if not already by the application itself or systemd
# from dotenv import load_dotenv
# load_dotenv() # Load .env file from current directory or specified path
```
*The `app/__init__.py` already loads `.env`, so explicit loading here might be redundant if systemd also passes it, but doesn't hurt.*

## 6. `systemd` Service for Gunicorn (`typecomplex.service`)

Create a systemd service file to manage the Gunicorn process.
File: `/etc/systemd/system/typecomplex.service`

```ini
[Unit]
Description=TypeComplex Gunicorn Daemon
After=network.target

[Service]
User=pepper
Group=pepper # Or the primary group of the 'pepper' user
WorkingDirectory=/home/pepper/typecomplex
EnvironmentFile=/home/pepper/typecomplex/.env # Load environment variables

# Path to Gunicorn executable in the virtual environment
ExecStart=/home/pepper/typecomplex/.venv/bin/gunicorn -c /home/pepper/typecomplex/gunicorn.conf.py "app:app"

Restart=always
RestartSec=5s # Restart service after 5 seconds if it crashes

# Standard output and error logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=typecomplex-gunicorn

[Install]
WantedBy=multi-user.target
```

**Commands to manage the Gunicorn service:**
```bash
sudo systemctl daemon-reload  # After creating or modifying the file
sudo systemctl start typecomplex
sudo systemctl enable typecomplex # To start on boot
sudo systemctl status typecomplex
sudo journalctl -u typecomplex -f # To view logs
```

## 7. `systemd` Service for Celery Workers (`typecomplex-celery.service`)

Create a systemd service file to manage the Celery workers.
File: `/etc/systemd/system/typecomplex-celery.service`

```ini
[Unit]
Description=TypeComplex Celery Worker Daemon
After=network.target redis.service # Ensure network and Redis are up
Requires=redis.service # Or your specific Redis service name

[Service]
User=pepper
Group=pepper
WorkingDirectory=/home/pepper/typecomplex
EnvironmentFile=/home/pepper/typecomplex/.env # Load environment variables

# Path to Celery executable in the virtual environment
# The '-A app.celery' points to your Celery application instance
# '-l info' sets the log level. Adjust as needed.
# Using environment variables for concurrency and max memory, set in .env
ExecStart=/home/pepper/typecomplex/.venv/bin/celery -A app.celery worker -l info --concurrency=${CELERY_CONCURRENCY} --max-memory-per-child=${CELERY_MAX_MEMORY_KB}

Restart=always
RestartSec=10s # Restart service after 10 seconds if it crashes

# Standard output and error logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=typecomplex-celery

[Install]
WantedBy=multi-user.target
```

**Commands to manage the Celery service:**
```bash
sudo systemctl daemon-reload
sudo systemctl start typecomplex-celery
sudo systemctl enable typecomplex-celery
sudo systemctl status typecomplex-celery
sudo journalctl -u typecomplex-celery -f
```

## 8. Nginx (Reverse Proxy & HTTPS)

1.  **Ensure Nginx is Installed:** (Covered in prerequisites)

2.  **Create Nginx Server Block Configuration:**
    Use the template created earlier.
    File: `/etc/nginx/conf.d/typecomplex.conf`
    *(Ensure you replace `your_server_ip_or_domain` with your actual domain name or server IP when you go live).*

    ```nginx
    server {
        listen 80;
        listen [::]:80;
        server_name your_server_ip_or_domain; # Replace with your actual domain

        # Redirect all HTTP traffic to HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }

    server {
        listen 443 ssl; # Removed deprecated http2 here, add 'http2 on;' later if needed
        http2 on;
        listen [::]:443 ssl; # Removed deprecated http2 here, add 'http2 on;' later if needed
        http2 on;
        server_name your_server_ip_or_domain; # Replace with your actual domain

        # SSL Certificate paths (Certbot will manage these)
        ssl_certificate /etc/letsencrypt/live/your_server_ip_or_domain/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your_server_ip_or_domain/privkey.pem;
        # include /etc/letsencrypt/options-ssl-nginx.conf; # Recommended by Certbot
        # ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # Recommended by Certbot

        # Recommended SSL settings (Certbot often provides these in options-ssl-nginx.conf)
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers on;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:10m;
        ssl_session_tickets off;
        # ssl_stapling on;
        # ssl_stapling_verify on;
        # resolver 8.8.8.8 8.8.4.4 valid=300s;
        # resolver_timeout 5s;

        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

        location /static {
            alias /home/pepper/typecomplex/app/static;
            expires 30d;
            add_header Cache-Control "public";
        }

        location / {
            proxy_pass http://127.0.0.1:5001; # Matches Gunicorn bind in .env (PORT=5001)
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Access and error logs (optional, systemd journal might be primary)
        # access_log /var/log/nginx/typecomplex.access.log;
        # error_log /var/log/nginx/typecomplex.error.log;
    }
    ```

3.  **Obtain SSL Certificates with Certbot:**
    *   First, ensure your domain name's DNS A record points to your server's public IP address.
    *   Install Certbot and its Nginx plugin:
        ```bash
        sudo apt install certbot python3-certbot-nginx -y # Debian/Ubuntu
        # sudo dnf install certbot python3-certbot-nginx -y # Fedora
        ```
    *   Run Certbot:
        ```bash
        sudo certbot --nginx -d your_server_ip_or_domain
        ```
        Follow the prompts. Certbot should automatically update your Nginx configuration (`typecomplex.conf`) to use the SSL certificates and set up auto-renewal. It may also add includes like `options-ssl-nginx.conf`.

4.  **Test Nginx Configuration and Reload:**
    ```bash
    sudo nginx -t
    sudo systemctl reload nginx
    ```

## 9. Final Firewall Check

Ensure your firewall (e.g., `ufw` or `firewalld`) allows traffic on port 80 (for HTTP to HTTPS redirect) and port 443 (for HTTPS). This was covered in prerequisites but double-check.

## 10. Database & Cache Considerations

*   **Database:** If you're using a database like PostgreSQL or MySQL instead of SQLite for production:
    *   Ensure it's installed, secured, and configured for production (e.g., backups, connection pooling).
    *   Update `DATABASE_URL` in your `.env` file with the correct credentials.
*   **Cache:** The default Flask `SimpleCache` is not suitable for a multi-process Gunicorn setup.
    *   If your application uses caching extensively, consider `RedisCache` or `MemcachedCache`.
    *   Update your Flask app's cache configuration and relevant environment variables (e.g., `CACHE_REDIS_URL`).

## 11. Error Monitoring (Sentry)

*   Ensure `SENTRY_DSN` is correctly set in your `.env` file.
*   Verify that errors from both the Flask app (via Gunicorn) and Celery tasks are being reported to your Sentry instance.

## 12. Thorough Testing

*   Access your application via `https://your_server_ip_or_domain`.
*   Test all key user workflows, PDF processing, Celery task execution, static file serving.
*   Verify that HTTP redirects to HTTPS.
*   Check logs for Gunicorn, Celery, and Nginx after testing:
    ```bash
    sudo journalctl -u typecomplex -n 100 --no-pager
    sudo journalctl -u typecomplex-celery -n 100 --no-pager
    sudo tail -n 100 /var/log/nginx/access.log
    sudo tail -n 100 /var/log/nginx/error.log
    ```
*   Test `systemd` services by rebooting the server (`sudo reboot`) and ensuring both `typecomplex` and `typecomplex-celery` services start automatically.
    ```bash
    sudo systemctl status typecomplex typecomplex-celery
    ```

## 13. Optional: Gunicorn `--preload`

*   Once your deployment is stable, you can experiment with `PRELOAD_APP='true'` in your `.env` file (which `gunicorn.conf.py` uses).
*   This loads the application code once before forking worker processes, potentially saving memory.
*   **Test thoroughly** after enabling, as it can cause issues if your application has resources that are not fork-safe (e.g., some database connections, ML models loaded in a specific way). Monitor memory usage and application behavior.

## 14. Ongoing Maintenance

*   Regularly update your server's OS and packages: `sudo apt update && sudo apt upgrade -y` or `sudo dnf update -y`.
*   Monitor logs for errors.
*   Ensure Certbot's auto-renewal for SSL certificates is working (`sudo certbot renew --dry-run`).
*   Back up your application data and configurations.
*   Review security best practices periodically.

---
This guide provides a comprehensive setup. Adapt paths and commands based on your specific Linux distribution and server configuration. 