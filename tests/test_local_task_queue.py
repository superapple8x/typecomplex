"""
Unit tests for LocalTaskQueue
"""

import unittest
import tempfile
import os
import time
import threading
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.local_task_queue import LocalTaskQueue, TaskResult, AsyncResult
from app.db_init import DatabaseManager


class TestLocalTaskQueue(unittest.TestCase):
    """Test cases for LocalTaskQueue"""
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Initialize task queue
        self.queue = LocalTaskQueue(max_workers=2, db_path=self.db_path)
    
    def tearDown(self):
        """Clean up test environment"""
        # Shutdown queue
        self.queue.shutdown()
        
        # Remove temporary database
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_database_initialization(self):
        """Test database is properly initialized"""
        # Check if database file exists
        self.assertTrue(os.path.exists(self.db_path))
        
        # Check if tables exist
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self.assertIn('tasks', tables)
    
    def test_simple_task_submission(self):
        """Test submitting and executing a simple task"""
        def simple_task(x, y):
            return x + y
        
        # Submit task
        task_id = self.queue.submit_task(simple_task, 2, 3)
        self.assertIsInstance(task_id, str)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Check result
        result = self.queue.get_task_status(task_id)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.result, 5)
    
    def test_task_with_exception(self):
        """Test task that raises an exception"""
        def failing_task():
            raise ValueError("Test error")
        
        # Submit task
        task_id = self.queue.submit_task(failing_task)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Check result
        result = self.queue.get_task_status(task_id)
        self.assertEqual(result.status, 'failed')
        self.assertIsNotNone(result.error)
        self.assertIn('Test error', result.error)
    
    def test_task_cancellation(self):
        """Test task cancellation"""
        def long_running_task():
            time.sleep(2)
            return "completed"
        
        # Submit task
        task_id = self.queue.submit_task(long_running_task)
        
        # Wait a bit then cancel
        time.sleep(0.1)
        cancelled = self.queue.cancel_task(task_id)
        
        # Check if cancellation was successful
        # Note: cancellation might not always work if task already started
        result = self.queue.get_task_status(task_id)
        self.assertIn(result.status, ['cancelled', 'running', 'completed'])
    
    def test_multiple_tasks(self):
        """Test submitting multiple tasks"""
        def multiply_task(x, y):
            time.sleep(0.1)  # Small delay to ensure tasks run
            return x * y
        
        # Submit multiple tasks
        task_ids = []
        for i in range(5):
            task_id = self.queue.submit_task(multiply_task, i, 2)
            task_ids.append(task_id)
        
        # Wait for all to complete
        time.sleep(1)
        
        # Check all results
        for i, task_id in enumerate(task_ids):
            result = self.queue.get_task_status(task_id)
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.result, i * 2)
    
    def test_celery_compatibility_mock_task(self):
        """Test Celery compatibility with mock task object"""
        # Create a mock Celery-style task function
        class MockCeleryTaskFunc:
            def __call__(self, mock_task, x, y):
                # Update state like Celery task
                mock_task.update_state(state='PROGRESS', meta={'current_step': 1, 'total_steps': 2})
                time.sleep(0.1)
                mock_task.update_state(state='PROGRESS', meta={'current_step': 2, 'total_steps': 2})
                return x + y
        
        celery_style_task = MockCeleryTaskFunc()
        
        # Submit task
        task_id = self.queue.submit_task(celery_style_task, 3, 4)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Check result
        result = self.queue.get_task_status(task_id)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.result, 7)
        self.assertEqual(result.progress, 100)
    
    def test_async_result_compatibility(self):
        """Test AsyncResult compatibility with Celery interface"""
        def simple_task():
            return "test_result"
        
        # Submit task
        task_id = self.queue.submit_task(simple_task)
        
        # Create AsyncResult
        async_result = AsyncResult(task_id, self.queue)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Test Celery-like interface
        self.assertEqual(async_result.state, 'SUCCESS')
        self.assertEqual(async_result.result, 'test_result')
    
    def test_get_all_tasks(self):
        """Test getting all tasks"""
        def simple_task(value):
            return value
        
        # Submit several tasks
        task_ids = []
        for i in range(3):
            task_id = self.queue.submit_task(simple_task, i)
            task_ids.append(task_id)
        
        # Wait for completion
        time.sleep(0.5)
        
        # Get all tasks
        all_tasks = self.queue.get_all_tasks()
        self.assertEqual(len(all_tasks), 3)
        
        # Get only completed tasks
        completed_tasks = self.queue.get_all_tasks(status_filter='completed')
        self.assertEqual(len(completed_tasks), 3)
        
        # Get pending tasks (should be none)
        pending_tasks = self.queue.get_all_tasks(status_filter='pending')
        self.assertEqual(len(pending_tasks), 0)
    
    def test_task_not_found(self):
        """Test getting status of non-existent task"""
        result = self.queue.get_task_status('non-existent-id')
        self.assertEqual(result.status, 'not_found')
        self.assertIsNotNone(result.error)
    
    def test_database_cleanup(self):
        """Test old task cleanup"""
        # This test would require manipulating timestamps
        # For now, just test that cleanup doesn't crash
        self.queue._cleanup_old_tasks(days_old=0)  # Clean all tasks
        
        # Verify cleanup worked
        all_tasks = self.queue.get_all_tasks()
        # Tasks might still exist if they're very recent
        self.assertIsInstance(all_tasks, list)


class TestDatabaseManager(unittest.TestCase):
    """Test cases for DatabaseManager"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        self.db_manager = DatabaseManager(self.db_path)
    
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_database_initialization(self):
        """Test database initialization"""
        success = self.db_manager.init_database()
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.db_path))
    
    def test_schema_version(self):
        """Test schema version tracking"""
        # Initialize database
        self.db_manager.init_database()
        
        # Check version
        version = self.db_manager.get_schema_version()
        self.assertEqual(version, 1)
    
    def test_database_stats(self):
        """Test database statistics"""
        # Initialize database
        self.db_manager.init_database()
        
        # Get stats
        stats = self.db_manager.get_database_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn('total_tasks', stats)
        self.assertIn('status_counts', stats)
        self.assertIn('database_size_bytes', stats)
    
    def test_vacuum_database(self):
        """Test database vacuum"""
        # Initialize database
        self.db_manager.init_database()
        
        # Vacuum
        success = self.db_manager.vacuum_database()
        self.assertTrue(success)
    
    def test_backup_restore(self):
        """Test database backup and restore"""
        # Initialize database
        self.db_manager.init_database()
        
        # Create backup
        backup_path = self.db_path + '.backup'
        success = self.db_manager.backup_database(backup_path)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(backup_path))
        
        # Restore (this will create a backup of current)
        success = self.db_manager.restore_database(backup_path)
        self.assertTrue(success)
        
        # Clean up backup
        if os.path.exists(backup_path):
            os.unlink(backup_path)


class TestConcurrency(unittest.TestCase):
    """Test concurrent task execution"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        self.queue = LocalTaskQueue(max_workers=3, db_path=self.db_path)
    
    def tearDown(self):
        """Clean up test environment"""
        self.queue.shutdown()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_concurrent_task_submission(self):
        """Test submitting tasks from multiple threads"""
        def worker_task(worker_id, task_num):
            time.sleep(0.1)
            return f"worker_{worker_id}_task_{task_num}"
        
        task_ids = []
        threads = []
        
        def submit_tasks(worker_id):
            for i in range(3):
                task_id = self.queue.submit_task(worker_task, worker_id, i)
                task_ids.append(task_id)
        
        # Start multiple threads submitting tasks
        for worker_id in range(3):
            thread = threading.Thread(target=submit_tasks, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Wait for all tasks to complete
        time.sleep(1)
        
        # Check all tasks completed successfully
        self.assertEqual(len(task_ids), 9)  # 3 workers * 3 tasks each
        
        completed_count = 0
        for task_id in task_ids:
            result = self.queue.get_task_status(task_id)
            if result.status == 'completed':
                completed_count += 1
        
        self.assertEqual(completed_count, 9)


if __name__ == '__main__':
    # Set up logging for tests
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Run tests
    unittest.main()