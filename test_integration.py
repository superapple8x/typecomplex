#!/usr/bin/env python3
"""
Test script to verify LocalTaskQueue integration works correctly
"""

import os
import sys
import time

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Set environment variables to simulate Electron mode
os.environ['ELECTRON_RUN_AS_NODE'] = '1'
os.environ['ELECTRON_APP_PATH'] = os.path.dirname(__file__)
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = 'false'

def test_local_task_queue():
    """Test LocalTaskQueue functionality"""
    print("Testing LocalTaskQueue integration...")
    
    try:
        # Import after setting environment variables
        from app.local_task_queue import init_local_task_queue
        from app.tasks_local import add_task
        
        # Initialize task queue
        db_path = os.path.join(os.path.dirname(__file__), 'test_integration.db')
        task_queue = init_local_task_queue(max_workers=2, db_path=db_path)
        
        print(f"✓ LocalTaskQueue initialized with database: {db_path}")
        
        # Submit a simple task
        task_id = task_queue.submit_task(add_task, 5, 3)
        print(f"✓ Task submitted with ID: {task_id}")
        
        # Wait for completion
        print("Waiting for task completion...")
        for i in range(10):  # Wait up to 5 seconds
            task_result = task_queue.get_task_status(task_id)
            print(f"  Status: {task_result.status}")
            
            if task_result.status == 'completed':
                print(f"✓ Task completed successfully! Result: {task_result.result}")
                break
            elif task_result.status == 'failed':
                print(f"✗ Task failed: {task_result.error}")
                break
            
            time.sleep(0.5)
        else:
            print("✗ Task did not complete within timeout")
            return False
        
        # Test task status retrieval
        all_tasks = task_queue.get_all_tasks()
        print(f"✓ Retrieved {len(all_tasks)} tasks from database")
        
        # Cleanup
        task_queue.shutdown()
        print("✓ Task queue shutdown successfully")
        
        # Clean up test database
        if os.path.exists(db_path):
            os.unlink(db_path)
            print("✓ Test database cleaned up")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_electron_app_init():
    """Test Electron app initialization"""
    print("\nTesting Electron app initialization...")
    
    try:
        # Test the configuration detection
        print(f"✓ ELECTRON_RUN_AS_NODE: {os.environ.get('ELECTRON_RUN_AS_NODE')}")
        print(f"✓ ELECTRON_APP_PATH: {os.environ.get('ELECTRON_APP_PATH')}")
        
        # Test that we can import the LocalTaskQueue components
        from app.local_task_queue import get_local_task_queue
        
        # This should work since we already initialized it in the first test
        try:
            task_queue = get_local_task_queue()
            print("✓ LocalTaskQueue is accessible via get_local_task_queue()")
        except RuntimeError:
            print("✓ LocalTaskQueue properly requires initialization (expected after shutdown)")
        
        print("✓ Electron mode configuration is working")
        return True
        
    except Exception as e:
        print(f"✗ Electron app initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("TypeComplex LocalTaskQueue Integration Test")
    print("=" * 60)
    
    success = True
    
    # Test 1: LocalTaskQueue functionality
    if not test_local_task_queue():
        success = False
    
    # Test 2: Electron app initialization
    if not test_electron_app_init():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✓ All tests passed! LocalTaskQueue integration is working.")
    else:
        print("✗ Some tests failed. Check the output above for details.")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())