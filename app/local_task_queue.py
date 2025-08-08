"""
Local Task Queue System for Electron Conversion
Replaces Celery with ThreadPoolExecutor and SQLite for task management
"""

import sqlite3
import json
import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import inspect
import os

logger = logging.getLogger(__name__)

@dataclass
class TaskResult:
    """Data class for task results"""
    task_id: str
    status: str  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    meta: Optional[Dict[str, Any]] = None

class LocalTaskQueue:
    """
    Local task queue implementation using ThreadPoolExecutor and SQLite
    Provides Celery-like interface for task management
    """
    
    def __init__(self, max_workers: int = 3, db_path: str = 'tasks.db'):
        self.max_workers = max_workers
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks: Dict[str, Future] = {}
        self.task_callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        
        # Initialize database
        self._init_database()
        
        # Clean up old completed tasks on startup
        self._cleanup_old_tasks()
        
        logger.info(f"LocalTaskQueue initialized with {max_workers} workers, database: {db_path}")
    
    def _init_database(self):
        """Initialize SQLite database for task tracking"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result_data TEXT,
                    error_message TEXT,
                    progress INTEGER DEFAULT 0,
                    meta_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("Task database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize task database: {e}")
            raise
    
    def _cleanup_old_tasks(self, days_old: int = 7):
        """Clean up completed tasks older than specified days"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                DELETE FROM tasks 
                WHERE status IN ('completed', 'failed', 'cancelled') 
                AND created_at < datetime('now', '-{} days')
            '''.format(days_old))
            deleted_count = conn.total_changes
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old completed tasks")
        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
    
    def _update_task_status(self, task_id: str, status: str, result: Any = None, 
                           error: str = None, progress: int = None, meta: Dict = None):
        """Update task status in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Prepare update data
            update_data = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            
            if result is not None:
                update_data['result_data'] = json.dumps(result, default=str)
            if error is not None:
                update_data['error_message'] = error
            if progress is not None:
                update_data['progress'] = progress
            if meta is not None:
                update_data['meta_data'] = json.dumps(meta, default=str)
            
            # Build SQL query
            set_clause = ', '.join([f"{key} = ?" for key in update_data.keys()])
            values = list(update_data.values()) + [task_id]
            
            conn.execute(f'''
                UPDATE tasks 
                SET {set_clause}
                WHERE id = ?
            ''', values)
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Task {task_id} status updated to {status}")
            
        except Exception as e:
            logger.error(f"Failed to update task {task_id} status: {e}")
    
    def _create_task_record(self, task_id: str) -> bool:
        """Create initial task record in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                INSERT INTO tasks (id, status, created_at, updated_at)
                VALUES (?, 'pending', ?, ?)
            ''', (task_id, datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to create task record {task_id}: {e}")
            return False
    
    def _run_task_wrapper(self, task_id: str, func: Callable, *args, **kwargs):
        """Wrapper function to run task with proper error handling and status updates"""
        try:
            # Update status to running
            self._update_task_status(task_id, 'running', progress=0)
            
            # Detect if the target function expects a Celery-like task object
            # by checking for a parameter named 'mock_task'. If present, pass
            # our MockCeleryTask instance as the first argument for
            # compatibility with legacy Celery task signatures.
            try:
                sig = inspect.signature(func)
                expects_mock = 'mock_task' in sig.parameters
            except Exception:
                expects_mock = False

            if expects_mock:
                mock_task = MockCeleryTask(task_id, self)
                # Prefer positional for first arg to satisfy positional-only
                # definitions, but most functions also accept keyword.
                try:
                    result = func(mock_task, *args, **kwargs)
                except TypeError:
                    # Fallback to keyword injection if positional failed
                    kwargs_with_mock = dict(kwargs)
                    kwargs_with_mock['mock_task'] = mock_task
                    result = func(*args, **kwargs_with_mock)
            else:
                result = func(*args, **kwargs)
            
            # Update status to completed
            self._update_task_status(task_id, 'completed', result=result, progress=100)
            
            logger.info(f"Task {task_id} completed successfully")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task {task_id} failed: {error_msg}", exc_info=True)
            
            # Update status to failed
            self._update_task_status(task_id, 'failed', error=error_msg)
            
            # Return error result in Celery-compatible format
            return {
                'error': True,
                'error_details': f"{type(e).__name__}: {error_msg}",
                'status_message': f'Error processing: {error_msg}'
            }
        finally:
            # Clean up running task reference
            with self._lock:
                self.running_tasks.pop(task_id, None)
                self.task_callbacks.pop(task_id, None)
    
    def submit_task(self, func: Callable, *args, **kwargs) -> str:
        """
        Submit a task for execution
        Returns task_id for tracking
        """
        task_id = str(uuid.uuid4())
        
        # Create task record
        if not self._create_task_record(task_id):
            raise RuntimeError(f"Failed to create task record for {task_id}")
        
        # Submit to thread pool
        future = self.executor.submit(self._run_task_wrapper, task_id, func, *args, **kwargs)
        
        # Store future reference
        with self._lock:
            self.running_tasks[task_id] = future
        
        logger.info(f"Task {task_id} submitted for execution")
        return task_id
    
    def get_task_status(self, task_id: str) -> TaskResult:
        """Get current task status and results"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute('''
                SELECT id, status, result_data, error_message, progress, 
                       meta_data, created_at, updated_at
                FROM tasks WHERE id = ?
            ''', (task_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return TaskResult(
                    task_id=task_id,
                    status='not_found',
                    error='Task not found'
                )
            
            # Parse JSON data
            result_data = None
            meta_data = None
            
            if row[2]:  # result_data
                try:
                    result_data = json.loads(row[2])
                except json.JSONDecodeError:
                    result_data = row[2]  # Keep as string if not valid JSON
            
            if row[5]:  # meta_data
                try:
                    meta_data = json.loads(row[5])
                except json.JSONDecodeError:
                    meta_data = {}
            
            return TaskResult(
                task_id=row[0],
                status=row[1],
                result=result_data,
                error=row[3],
                progress=row[4] or 0,
                meta=meta_data,
                created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                updated_at=datetime.fromisoformat(row[7]) if row[7] else None
            )
            
        except Exception as e:
            logger.error(f"Failed to get task status for {task_id}: {e}")
            return TaskResult(
                task_id=task_id,
                status='error',
                error=f'Failed to retrieve task status: {str(e)}'
            )
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        with self._lock:
            future = self.running_tasks.get(task_id)
            
            if future and not future.done():
                # Try to cancel the future
                cancelled = future.cancel()
                
                if cancelled:
                    self._update_task_status(task_id, 'cancelled')
                    self.running_tasks.pop(task_id, None)
                    logger.info(f"Task {task_id} cancelled successfully")
                    return True
                else:
                    logger.warning(f"Task {task_id} could not be cancelled (already running)")
                    return False
            else:
                # Task not running or already completed
                task_status = self.get_task_status(task_id)
                if task_status.status in ['pending', 'running']:
                    self._update_task_status(task_id, 'cancelled')
                    logger.info(f"Task {task_id} marked as cancelled")
                    return True
                else:
                    logger.warning(f"Task {task_id} cannot be cancelled (status: {task_status.status})")
                    return False
    
    def get_all_tasks(self, status_filter: Optional[str] = None) -> list[TaskResult]:
        """Get all tasks, optionally filtered by status"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            if status_filter:
                cursor = conn.execute('''
                    SELECT id, status, result_data, error_message, progress, 
                           meta_data, created_at, updated_at
                    FROM tasks WHERE status = ?
                    ORDER BY created_at DESC
                ''', (status_filter,))
            else:
                cursor = conn.execute('''
                    SELECT id, status, result_data, error_message, progress, 
                           meta_data, created_at, updated_at
                    FROM tasks
                    ORDER BY created_at DESC
                ''')
            
            tasks = []
            for row in cursor.fetchall():
                # Parse JSON data
                result_data = None
                meta_data = None
                
                if row[2]:  # result_data
                    try:
                        result_data = json.loads(row[2])
                    except json.JSONDecodeError:
                        result_data = row[2]
                
                if row[5]:  # meta_data
                    try:
                        meta_data = json.loads(row[5])
                    except json.JSONDecodeError:
                        meta_data = {}
                
                tasks.append(TaskResult(
                    task_id=row[0],
                    status=row[1],
                    result=result_data,
                    error=row[3],
                    progress=row[4] or 0,
                    meta=meta_data,
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    updated_at=datetime.fromisoformat(row[7]) if row[7] else None
                ))
            
            conn.close()
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to get all tasks: {e}")
            return []
    
    def shutdown(self):
        """Shutdown the task queue and cleanup resources"""
        logger.info("Shutting down LocalTaskQueue...")
        
        # Cancel all running tasks
        with self._lock:
            for task_id, future in self.running_tasks.items():
                if not future.done():
                    future.cancel()
                    self._update_task_status(task_id, 'cancelled')
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        logger.info("LocalTaskQueue shutdown complete")


class MockCeleryTask:
    """Mock Celery task object for compatibility with existing task functions"""
    
    def __init__(self, task_id: str, queue: LocalTaskQueue):
        self.request = MockRequest(task_id)
        self.queue = queue
    
    def update_state(self, state: str, meta: Dict[str, Any] = None):
        """Update task state (Celery compatibility method)"""
        progress = 0
        if meta and 'current_step' in meta and 'total_steps' in meta:
            progress = int((meta['current_step'] / meta['total_steps']) * 100)
        
        # Map Celery states to our states
        status_mapping = {
            'PENDING': 'pending',
            'PROGRESS': 'running',
            'SUCCESS': 'completed',
            'FAILURE': 'failed',
            'RETRY': 'running',
            'REVOKED': 'cancelled'
        }
        
        local_status = status_mapping.get(state, state.lower())
        self.queue._update_task_status(
            self.request.id, 
            local_status, 
            progress=progress, 
            meta=meta
        )


class MockRequest:
    """Mock Celery request object"""
    
    def __init__(self, task_id: str):
        self.id = task_id


class AsyncResult:
    """Mock Celery AsyncResult for compatibility"""
    
    def __init__(self, task_id: str, queue: LocalTaskQueue):
        self.task_id = task_id
        self.queue = queue
    
    @property
    def state(self) -> str:
        """Get task state in Celery format"""
        task_result = self.queue.get_task_status(self.task_id)
        
        # Map our states to Celery states
        state_mapping = {
            'pending': 'PENDING',
            'running': 'PROGRESS',
            'completed': 'SUCCESS',
            'failed': 'FAILURE',
            'cancelled': 'REVOKED',
            'not_found': 'PENDING',
            'error': 'FAILURE'
        }
        
        return state_mapping.get(task_result.status, 'PENDING')
    
    @property
    def result(self):
        """Get task result"""
        task_result = self.queue.get_task_status(self.task_id)
        return task_result.result
    
    @property
    def info(self):
        """Get task info/meta data"""
        task_result = self.queue.get_task_status(self.task_id)
        if task_result.status == 'failed':
            return task_result.error
        return task_result.meta or {}
    
    def get(self, timeout=None):
        """Get result (blocking) - simplified implementation"""
        # For now, just return current result
        # In a full implementation, this would wait for completion
        return self.result


# Global instance (will be initialized in app factory)
local_task_queue: Optional[LocalTaskQueue] = None


def init_local_task_queue(max_workers: int = 3, db_path: str = 'tasks.db') -> LocalTaskQueue:
    """Initialize global task queue instance"""
    global local_task_queue
    local_task_queue = LocalTaskQueue(max_workers=max_workers, db_path=db_path)
    return local_task_queue


def get_local_task_queue() -> LocalTaskQueue:
    """Get global task queue instance"""
    if local_task_queue is None:
        raise RuntimeError("LocalTaskQueue not initialized. Call init_local_task_queue() first.")
    return local_task_queue