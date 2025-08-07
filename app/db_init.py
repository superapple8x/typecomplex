"""
Database initialization and migration utilities for LocalTaskQueue
"""

import sqlite3
import os
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database schema and migrations for LocalTaskQueue"""
    
    def __init__(self, db_path: str = 'tasks.db'):
        self.db_path = db_path
        self.schema_version = 1
    
    def init_database(self) -> bool:
        """Initialize database with current schema"""
        try:
            # Ensure directory exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            
            # Create tasks table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                    result_data TEXT,
                    error_message TEXT,
                    progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
                    meta_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create schema_info table for version tracking
            conn.execute('''
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            ''')
            
            # Insert initial schema version if not exists
            conn.execute('''
                INSERT OR IGNORE INTO schema_info (version, description)
                VALUES (?, 'Initial schema with tasks table')
            ''', (self.schema_version,))
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at)')
            
            conn.commit()
            conn.close()
            
            logger.info(f"Database initialized successfully at {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False
    
    def get_schema_version(self) -> int:
        """Get current database schema version"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute('SELECT MAX(version) FROM schema_info')
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result and result[0] is not None else 0
            
        except sqlite3.OperationalError:
            # Table doesn't exist, assume version 0
            return 0
        except Exception as e:
            logger.error(f"Failed to get schema version: {e}")
            return 0
    
    def migrate_database(self) -> bool:
        """Apply any pending database migrations"""
        current_version = self.get_schema_version()
        
        if current_version >= self.schema_version:
            logger.info(f"Database is up to date (version {current_version})")
            return True
        
        logger.info(f"Migrating database from version {current_version} to {self.schema_version}")
        
        try:
            # Apply migrations based on current version
            if current_version < 1:
                self._migrate_to_v1()
            
            # Add future migrations here
            # if current_version < 2:
            #     self._migrate_to_v2()
            
            logger.info("Database migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database migration failed: {e}")
            return False
    
    def _migrate_to_v1(self):
        """Migrate to version 1 (initial schema)"""
        # This is handled by init_database()
        self.init_database()
    
    def cleanup_old_tasks(self, days_old: int = 7) -> int:
        """Clean up completed tasks older than specified days"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # First, count how many will be deleted
            cursor = conn.execute('''
                SELECT COUNT(*) FROM tasks 
                WHERE status IN ('completed', 'failed', 'cancelled') 
                AND created_at < datetime('now', '-{} days')
            '''.format(days_old))
            
            count_to_delete = cursor.fetchone()[0]
            
            if count_to_delete > 0:
                # Delete old tasks
                conn.execute('''
                    DELETE FROM tasks 
                    WHERE status IN ('completed', 'failed', 'cancelled') 
                    AND created_at < datetime('now', '-{} days')
                '''.format(days_old))
                
                conn.commit()
                logger.info(f"Cleaned up {count_to_delete} old tasks")
            
            conn.close()
            return count_to_delete
            
        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
            return 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get task counts by status
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = dict(cursor.fetchall())
            
            # Get total task count
            cursor = conn.execute('SELECT COUNT(*) FROM tasks')
            total_tasks = cursor.fetchone()[0]
            
            # Get database file size
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            # Get oldest and newest task dates
            cursor = conn.execute('''
                SELECT MIN(created_at), MAX(created_at) FROM tasks
            ''')
            date_range = cursor.fetchone()
            
            conn.close()
            
            return {
                'total_tasks': total_tasks,
                'status_counts': status_counts,
                'database_size_bytes': db_size,
                'oldest_task': date_range[0],
                'newest_task': date_range[1],
                'schema_version': self.get_schema_version()
            }
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}
    
    def vacuum_database(self) -> bool:
        """Vacuum database to reclaim space and optimize performance"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('VACUUM')
            conn.close()
            
            logger.info("Database vacuum completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to vacuum database: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database"""
        try:
            import shutil
            
            # Ensure backup directory exists
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"Database backed up to {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            return False
    
    def restore_database(self, backup_path: str) -> bool:
        """Restore database from backup"""
        try:
            import shutil
            
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Create backup of current database
            if os.path.exists(self.db_path):
                backup_current = f"{self.db_path}.backup.{int(datetime.now().timestamp())}"
                shutil.copy2(self.db_path, backup_current)
                logger.info(f"Current database backed up to {backup_current}")
            
            # Restore from backup
            shutil.copy2(backup_path, self.db_path)
            
            logger.info(f"Database restored from {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore database: {e}")
            return False


def init_database(db_path: str = 'tasks.db') -> bool:
    """Initialize database with current schema"""
    db_manager = DatabaseManager(db_path)
    return db_manager.init_database()


def migrate_database(db_path: str = 'tasks.db') -> bool:
    """Apply any pending database migrations"""
    db_manager = DatabaseManager(db_path)
    return db_manager.migrate_database()


def cleanup_old_tasks(db_path: str = 'tasks.db', days_old: int = 7) -> int:
    """Clean up old completed tasks"""
    db_manager = DatabaseManager(db_path)
    return db_manager.cleanup_old_tasks(days_old)


if __name__ == '__main__':
    # Command line interface for database management
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python db_init.py <command> [args]")
        print("Commands:")
        print("  init [db_path] - Initialize database")
        print("  migrate [db_path] - Apply migrations")
        print("  cleanup [db_path] [days] - Cleanup old tasks")
        print("  stats [db_path] - Show database statistics")
        print("  vacuum [db_path] - Vacuum database")
        print("  backup [db_path] [backup_path] - Backup database")
        print("  restore [db_path] [backup_path] - Restore database")
        sys.exit(1)
    
    command = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else 'tasks.db'
    
    db_manager = DatabaseManager(db_path)
    
    if command == 'init':
        success = db_manager.init_database()
        print(f"Database initialization: {'SUCCESS' if success else 'FAILED'}")
    
    elif command == 'migrate':
        success = db_manager.migrate_database()
        print(f"Database migration: {'SUCCESS' if success else 'FAILED'}")
    
    elif command == 'cleanup':
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 7
        count = db_manager.cleanup_old_tasks(days)
        print(f"Cleaned up {count} old tasks")
    
    elif command == 'stats':
        stats = db_manager.get_database_stats()
        print("Database Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    elif command == 'vacuum':
        success = db_manager.vacuum_database()
        print(f"Database vacuum: {'SUCCESS' if success else 'FAILED'}")
    
    elif command == 'backup':
        if len(sys.argv) < 4:
            print("Usage: python db_init.py backup <db_path> <backup_path>")
            sys.exit(1)
        backup_path = sys.argv[3]
        success = db_manager.backup_database(backup_path)
        print(f"Database backup: {'SUCCESS' if success else 'FAILED'}")
    
    elif command == 'restore':
        if len(sys.argv) < 4:
            print("Usage: python db_init.py restore <db_path> <backup_path>")
            sys.exit(1)
        backup_path = sys.argv[3]
        success = db_manager.restore_database(backup_path)
        print(f"Database restore: {'SUCCESS' if success else 'FAILED'}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)