# Server Optimization for 4GB RAM

This document outlines strategies to optimize the application for deployment on a server with 4GB of RAM, focusing on managing the memory footprint of the Flask application and its machine learning models.

## 1. Lazy Loading of BERT Model

- **Strategy**: Implement lazy loading for the BERT model (`sentence-transformers`, `torch`). The model should only be loaded into memory when a user triggers a feature that explicitly requires it.
- **Implementation**:
    - Ensure the model is not imported or initialized at the global scope of any module that gets loaded when the Flask app starts.
    - Create a dedicated function or class method to get the model. This function should check if the model is already loaded; if not, it loads it and stores it in a global-like variable (e.g., `app.bert_model` or a module-level variable) for reuse in subsequent requests *within the same worker process*.
    - **Example Sketch**:
      ```python
      # In your tasks.py or a dedicated ml_loader.py
      _bert_model = None

      def get_bert_model():
          global _bert_model
          if _bert_model is None:
              print("Loading BERT model into memory...")
              # from sentence_transformers import SentenceTransformer # Keep import local
              # _bert_model = SentenceTransformer('model_name')
              # Simulate model loading
              _bert_model = "BERT Model Loaded" 
              print("BERT model loaded.")
          return _bert_model

      # In your Flask route or Celery task
      # bert_model = get_bert_model()
      # bert_model.encode(...)
      ```
- **Consideration**: If `preload_app = True` in Gunicorn, the model loaded this way will reside in the worker process's memory once loaded, not shared across workers unless loaded *before* forking, which contradicts on-demand lazy loading. The goal here is that only workers handling BERT-related requests will incur the memory cost of the model.

## 2. Gunicorn Configuration (`gunicorn.conf.py`)

- **Workers**:
    - `workers = int(os.environ.get('GUNICORN_WORKERS', '2'))`
    - Start with a low number of workers (e.g., 1 or 2) for a 4GB RAM server. Monitor memory usage and adjust.
    - Use the `GUNICORN_WORKERS` environment variable to tune this.
- **Worker Class**:
    - `worker_class = 'sync'` is a good default for memory predictability.
    - If I/O bound, consider `gevent` or `eventlet` after careful testing, but be mindful of peak memory with BERT.
- **Preload App**:
    - `preload_app = True`
    - This is generally beneficial for sharing the memory of the Flask application code and non-lazily-loaded libraries among worker processes (due to copy-on-write).
- **Timeout**:
    - `timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))`
    - Increase the timeout if model loading or processing can take longer than the default 30s.
- **Keepalive**:
    - `keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))`
    - Default is usually fine.

## 3. `requirements.txt` Review & Pruning

- **Remove Unused Development/OS-Specific Libraries**:
    - Thoroughly check `requirements.txt`. Remove any libraries not strictly needed for the *production application runtime*. Examples identified: `matplotlib` (if not used for runtime image generation), `fedora-third-party`, `dnf`, etc.
- **`spacy` vs. `sentence-transformers`**:
    - Evaluate if both are needed. If `sentence-transformers` (BERT) is primary, can `spacy` be removed or replaced with a smaller model (`en_core_web_sm`) if its specific functionalities are still required?
- **`pandas` and `numpy` Usage**:
    - If processing large datasets, optimize by:
        - Processing data in chunks.
        - Using memory-efficient data types (e.g., `float32` instead of `float64`, `int16` vs `int64`).
        - Deleting large objects (DataFrames, arrays) when no longer needed (`del df`).

## 4. Celery Worker Configuration

- **Command**: Your Celery app instance seems to be `app.celery` (defined in `app/__init__.py`).
  The systemd service in your `deploy_production_ubuntu.sh` and `PRODUCTION_SETUP.MD` uses:
  `ExecStart=$PROJECT_PATH/.venv/bin/celery -A app.celery worker -l info`

- **Recommended Optimized Command**:
  `ExecStart=$PROJECT_PATH/.venv/bin/celery -A app.celery worker -l info --concurrency=1 --max-memory-per-child=1024000`
  (This sets concurrency to 1 and max memory to ~1GB (1024000 KB) per child. Adjust these values based on your model's actual memory footprint and server capacity).

- **Using Environment Variables for Systemd (Recommended for flexibility)**:
    1. Add to your `.env` file:
       ```env
       CELERY_CONCURRENCY=1
       CELERY_MAX_MEMORY_KB=1024000 
       ```
    2. Update `ExecStart` in your Celery systemd service file (e.g., `typecomplex-celery.service`):
       `ExecStart=$PROJECT_PATH/.venv/bin/celery -A app.celery worker -l info --concurrency=${CELERY_CONCURRENCY} --max-memory-per-child=${CELERY_MAX_MEMORY_KB}`

- **Concurrency**:
    - `celery -A app.celery worker --loglevel=info --concurrency=1` (or 2, start low).
    - Limit concurrency to control memory. Each Celery worker process can also be memory-intensive if it loads the BERT model.
- **Memory Limits**:
    - `celery -A app.celery worker --max-memory-per-child=XXX` (in Kilobytes).
    - Set a max memory per child process. Celery will restart a worker if it exceeds this, helping to manage leaks or large model memory. `XXX` could be e.g., 500MB (512000 KB) to 1GB (1024000 KB), depending on BERT model size and other worker tasks. The command above uses `1024000`.
- **Task Routing for Model Tasks**:
    - If possible, consider routing tasks that require the BERT model to a specific Celery queue with dedicated workers that are configured for higher memory usage, while other non-ML tasks run on different workers with lower memory footprints. This is more advanced.

## 5. Python Version and Environment

- **Latest Python 3.x**: Use a recent, stable version of Python 3 (e.g., 3.9+). Newer versions often include performance and memory optimizations.
- **Virtual Environments**: Always use virtual environments (`.venv`) to isolate dependencies.

## 6. System-Level Optimizations

- **Swap Space**: Ensure your server has adequate swap space (e.g., 2GB-4GB). While not a replacement for RAM, it can prevent OOM killer from terminating your app under temporary high load, at the cost of performance.
- **Disable Unnecessary Services**: Turn off any unused services on the server to free up RAM.
- **Monitoring**:
    - Use tools like `htop`, `vmstat`, `free` to monitor server memory usage.
    - Monitor Gunicorn and Celery logs for errors or performance issues.
    - Consider application performance monitoring (APM) tools (Sentry is in your `requirements.txt`, which is good for error tracking; it might offer some performance insights too).

## 7. Code Optimizations

- **Resource Management**:
    - Ensure files (`PyMuPDF`, `Pillow`) are closed properly (`with open(...) as f:`).
    - Explicitly delete large objects when done (`del large_variable`).
- **Caching**:
    - Use `Flask-Caching` for frequently accessed data or expensive computations that don't change often.
- **Database Queries**:
    - Optimize SQL queries (via `SQLAlchemy`) to fetch only necessary data. Avoid loading large datasets into memory if only a subset is needed. Use pagination.

## 8. BERT Model Specific Optimizations

- **Smaller Models**:
    - Investigate if a smaller, distilled BERT variant (e.g., DistilBERT, ALBERT, MiniLM) can provide acceptable accuracy for your use case. These use significantly less RAM and are faster.
- **Quantization/Pruning**:
    - Advanced techniques like model quantization (e.g., converting weights to int8) or pruning can reduce model size. Libraries like `torch.quantization` or ONNX runtime can help. This often requires fine-tuning.

## 9. Review Deployment Scripts

- Files like `deploy_production_ubuntu.sh` and `PRODUCTION_SETUP.MD` should be updated to reflect these optimization strategies, especially environment variable settings for Gunicorn and Celery.

## Next Steps / Action Plan:

1.  **Implement Lazy Loading for BERT model** (most critical for on-demand usage).
2.  **Refine `requirements.txt`**: Remove `matplotlib` if not needed in production. Evaluate `spacy`.
3.  **Tune `gunicorn.conf.py`** (already partially done - workers, preload, timeout).
4.  **Configure Celery Workers**: Set concurrency and max memory per child.
5.  **Profile**: Use `memory_profiler` to find specific memory hotspots in your Python code.
6.  **Test Smaller BERT models**: If performance allows, this could be a big win.
7.  **Monitor**: Continuously monitor memory usage in your staging/production environment.

By systematically applying these strategies, you should be able to run your application effectively on a 4GB RAM server. 