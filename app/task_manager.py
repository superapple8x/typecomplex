# app/task_manager.py
import threading
import logging

# Dictionary to store ongoing task statuses
# Key: task_id (string), Value: {'cancelled': bool}
ongoing_tasks = {}

# Lock to ensure thread safety when accessing the dictionary
task_lock = threading.Lock()

def register_task(task_id):
    """Registers a new task ID."""
    if not task_id:
        logging.warning("Attempted to register task with empty ID.")
        return
    with task_lock:
        if task_id in ongoing_tasks:
            logging.warning(f"Task ID {task_id} already registered. Overwriting.")
        ongoing_tasks[task_id] = {'cancelled': False}
        logging.info(f"Task {task_id} registered.")

def cancel_task(task_id):
    """Marks a task as cancelled."""
    if not task_id:
        logging.warning("Attempted to cancel task with empty ID.")
        return
    with task_lock:
        if task_id in ongoing_tasks:
            ongoing_tasks[task_id]['cancelled'] = True
            logging.info(f"Cancellation requested for task {task_id}.")
        else:
            logging.warning(f"Attempted to cancel non-existent task ID: {task_id}")

def is_cancelled(task_id):
    """Checks if a task has been marked as cancelled."""
    if not task_id:
        return False # Cannot be cancelled if ID is invalid
    with task_lock:
        task = ongoing_tasks.get(task_id)
        if task:
            return task['cancelled']
        else:
            # If the task is not found, it might have completed and been removed,
            # or was never registered. Treat as not actively cancelled.
            # logging.debug(f"Checked cancellation for non-existent/removed task ID: {task_id}")
            return False

def remove_task(task_id):
    """Removes a task ID from tracking (usually upon completion or final error)."""
    if not task_id:
        logging.warning("Attempted to remove task with empty ID.")
        return
    with task_lock:
        if task_id in ongoing_tasks:
            del ongoing_tasks[task_id]
            logging.info(f"Task {task_id} removed from tracking.")
        else:
            # This might happen if cancellation occurred and removal was attempted again
            # logging.debug(f"Attempted to remove non-existent task ID: {task_id}")
            pass

def get_active_tasks():
    """Returns a list of currently tracked task IDs (for debugging/monitoring)."""
    with task_lock:
        return list(ongoing_tasks.keys())