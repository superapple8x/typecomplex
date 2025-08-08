# Design Document

## Overview

The TypeComplex Electron conversion will transform the current Flask web application into a desktop application while preserving all existing NLP functionality. The design follows a hybrid architecture where Electron manages the UI and desktop integration while a Python subprocess handles all NLP processing.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│                 Electron Main Process            │
│  - Window Management                            │
│  - Python Process Spawning & Monitoring        │
│  - File System Operations                      │
│  - Auto-Update Management                      │
│  - Settings Storage                            │
└─────────────────┬───────────────────────────────┘
                  │ IPC/HTTP
┌─────────────────┴───────────────────────────────┐
│            Electron Renderer Process             │
│  - UI Components (migrated from web)           │
│  - API Client for Python Backend              │
│  - File Drag & Drop Handling                  │
│  - Progress Indicators                         │
└─────────────────┬───────────────────────────────┘
                  │ HTTP (127.0.0.1:5001)
┌─────────────────┴───────────────────────────────┐
│            Python Backend Process                │
│  - Flask API Server (modified for Electron)    │
│  - NLP Processing Engine                       │
│  - Local Task Queue (replaces Celery)         │
│  - SQLite Database (replaces Redis)           │
│  - DeepSeek API Client                         │
└─────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. Electron Main Process
- **Process Manager**: Spawns and monitors Python backend
- **Window Manager**: Creates and manages application windows
- **File Handler**: Manages native file operations (open/save dialogs)
- **Update Manager**: Handles automatic updates
- **Settings Manager**: Stores user preferences locally

#### 2. Electron Renderer Process
- **UI Framework**: Migrated web interface with desktop enhancements
- **API Client**: Communicates with Python backend via HTTP
- **File Operations**: Handles drag-and-drop and file selection
- **Progress Management**: Shows loading states and progress bars

#### 3. Python Backend Process
- **Flask Server**: Modified to run as subprocess with Waitress
- **NLP Engine**: All existing analysis functionality preserved
- **Local Queue**: ThreadPoolExecutor replaces Celery
- **Data Storage**: SQLite replaces Redis for task tracking
- **DeepSeek Client**: Handles authenticated API calls for AI features

## Components and Interfaces

### 1. Process Communication Interface

```python
# Communication Protocol
class ElectronIPCProtocol:
    MESSAGE_TYPES = {
        'ANALYZE_TEXT': 'analyze_text',
        'ANALYZE_RESPONSE': 'analyze_response', 
        'MODEL_STATUS': 'model_status',
        'PROGRESS_UPDATE': 'progress_update',
        'ERROR': 'error',
        'HEALTH_CHECK': 'health_check'
    }
```

### 2. Local Task Queue System

```python
class LocalTaskQueue:
    def __init__(self, max_workers=3, db_path='tasks.db'):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.db_path = db_path
        self._init_database()
    
    def submit_task(self, func, *args, **kwargs) -> str:
        """Submit task and return task_id"""
        
    def get_task_status(self, task_id: str) -> dict:
        """Get current task status and results"""
        
    def cancel_task(self, task_id: str) -> bool:
        """Cancel running task"""
```

### 3. DeepSeek API Client

```python
class DeepSeekClient:
    def __init__(self, key_provider, base_url: str = "https://api.deepseek.com"):
        self.key_provider = key_provider
        self.base_url = base_url

    def rewrite(self, text: str, options: dict) -> dict:
        """Call DeepSeek rewrite endpoint with retries and backoff"""

    def synonyms(self, word: str, options: dict) -> dict:
        """Call DeepSeek synonyms endpoint with retries and backoff"""

    def test_key(self) -> dict:
        """Minimal request to validate API key without sending user content"""
```

### 4. File System Integration

```javascript
// Electron Main Process File Operations
class FileManager {
    async selectPDF() {
        const result = await dialog.showOpenDialog({
            properties: ['openFile'],
            filters: [{ name: 'PDF Files', extensions: ['pdf'] }]
        });
        return result.filePaths[0];
    }
    
    async savePDF(data, defaultName) {
        const result = await dialog.showSaveDialog({
            defaultPath: defaultName,
            filters: [{ name: 'PDF Files', extensions: ['pdf'] }]
        });
        if (!result.canceled) {
            await fs.writeFile(result.filePath, data);
        }
    }
}
```

## Data Models

### 1. Task Tracking Schema

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed'
    input_data TEXT,
    result_data TEXT,
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Settings Schema

```javascript
// Electron Store Schema
const settingsSchema = {
    targetAudience: {
        type: 'string',
        default: 'Standard',
        enum: ['Standard', 'General Public', 'Academic / Technical']
    },
    analysisMode: {
        type: 'string', 
        default: 'better',
        enum: ['fast', 'better', 'best']
    },
    deepseekKeyStatus: {
        type: 'string',
        default: 'unset',
        enum: ['unset', 'set']
    },
    modelCache: {
        type: 'boolean',
        default: true
    },
    autoUpdate: {
        type: 'boolean',
        default: true
    }
};
```

### 3. Analysis Result Model

```python
@dataclass
class AnalysisResult:
    text: str
    overall_complexity: float
    readability_scores: Dict[str, float]
    sentence_analyses: List[SentenceAnalysis]
    target_audience: str
    processing_time: float
    model_versions: Dict[str, str]
```

## Error Handling

### 1. Python Process Management

```javascript
class PythonProcessManager {
    constructor() {
        this.process = null;
        this.restartAttempts = 0;
        this.maxRestartAttempts = 3;
    }
    
    async startProcess() {
        // Start Python backend with health monitoring
    }
    
    async restartProcess() {
        // Restart failed Python process with exponential backoff
    }
    
    monitorHealth() {
        // Periodic health checks with automatic restart
    }
}
```

### 2. Memory Management

```python
class MemoryMonitor:
    def __init__(self, threshold_gb=3.5):
        self.threshold = threshold_gb * 1024**3
        
    def check_and_cleanup(self):
        """Check memory usage and cleanup if needed"""
        current_usage = psutil.Process().memory_info().rss
        
        if current_usage > self.threshold:
            self._emergency_cleanup()
            
    def _emergency_cleanup(self):
        """Emergency memory cleanup procedures"""
        # Force garbage collection
        # Clear caches
```

### 3. Network Error Handling

```javascript
class APIClient {
    async makeRequest(endpoint, data, retries = 3) {
        for (let i = 0; i < retries; i++) {
            try {
                return await this._request(endpoint, data);
            } catch (error) {
                if (i === retries - 1) throw error;
                await this._delay(Math.pow(2, i) * 1000);
            }
        }
    }
    
    async _handleOfflineMode(error) {
        // Graceful degradation to offline functionality (non-AI features)
        // Distinguish invalid key vs. network vs. quota errors
    }
}
```

## Testing Strategy

### 1. Unit Testing
- **Python Backend**: Test all NLP processing functions independently
- **Electron Main**: Test process management and file operations
- **Electron Renderer**: Test UI components and API client

### 2. Integration Testing
- **Process Communication**: Test Electron ↔ Python communication
- **File Operations**: Test PDF processing pipeline
- **Memory Management**: Test model loading/unloading under stress

### 3. End-to-End Testing
- **Full Analysis Pipeline**: Test complete text analysis workflow
- **Cross-Platform**: Test on Windows, macOS, and Linux
- **Performance**: Test with large documents and memory constraints

### 4. Testing Tools
```javascript
// Jest for Electron testing
// pytest for Python backend
// Spectron for E2E Electron testing
// Memory profiling with py-spy and heapdump
```

## Performance Considerations

### 1. Startup Optimization
- **Lazy Loading**: Load NLP models only when needed
- **Progressive Enhancement**: Start with basic UI, load features incrementally
- **Caching**: Cache frequently used models and results

### 2. Memory Optimization
- **Model Rotation**: Unload unused models automatically
- **Garbage Collection**: Aggressive cleanup of temporary objects
- **Memory Monitoring**: Real-time memory usage tracking

### 3. Disk Usage Optimization
- **Model Compression**: Use compressed model formats where possible
- **Cache Management**: Implement LRU cache for analysis results
- **Temporary File Cleanup**: Automatic cleanup of processed files

## Security Considerations

### 1. Electron Security
```javascript
// Secure BrowserWindow configuration
const securePreferences = {
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false
};
```

### 2. Data Protection
- **Local Storage**: All sensitive data stored locally
- **API Key Management**: Secure storage of external API keys
- **File Permissions**: Proper file system permissions

### 3. Process Isolation
- **Subprocess Sandboxing**: Python process runs with limited privileges
- **IPC Validation**: All inter-process communication validated
- **Error Isolation**: Failures in one component don't crash others