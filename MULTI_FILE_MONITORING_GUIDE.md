# Multi-File Log Monitoring - Complete Implementation Guide

**Project:** Resolvix Daemon Enhancement  
**Feature:** Multi-File Log Monitoring  
**Date:** December 18, 2025  
**Version:** 2.0

---

## 📋 Table of Contents

- [Overview](#overview)
- [Option A: Config File Implementation (Recommended)](#option-a-config-file-implementation-recommended)
  - [Daemon Developer Guide](#option-a-daemon-developer-guide)
  - [Backend Developer Guide](#option-a-backend-developer-guide)
  - [Frontend Developer Guide](#option-a-frontend-developer-guide)
- [Option B: Multiple --log-file Implementation (Quick Fix)](#option-b-multiple---log-file-implementation-quick-fix)
  - [Daemon Developer Guide](#option-b-daemon-developer-guide)
  - [Backend Developer Guide](#option-b-backend-developer-guide)
  - [Frontend Developer Guide](#option-b-frontend-developer-guide)
- [Migration Path](#migration-path)
- [Testing Strategy](#testing-strategy)

---

# Overview

## Current Problem

The daemon currently monitors **only ONE log file**, forcing users to:
- Choose which log file to monitor (confusing)
- Run multiple daemon instances (resource waste)
- Miss errors from other log sources

## Solution Comparison

| Feature | Current | Option B | Option A |
|---------|---------|----------|----------|
| **Files Monitored** | 1 | Multiple | Multiple + Patterns |
| **Configuration** | CLI only | CLI only | YAML Config |
| **Wildcards** | ❌ No | ❌ No | ✅ Yes |
| **Per-File Settings** | ❌ No | ❌ No | ✅ Yes |
| **Auto-Discovery** | ❌ No | ❌ No | ✅ Optional |
| **Implementation Time** | - | 30 min | 2 hours |
| **User Experience** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

# Option A: Config File Implementation (Recommended)

## Why Config File?

✅ **Industry Standard** - How Datadog, Splunk, Filebeat work  
✅ **Flexible** - Each file can have different settings  
✅ **Scalable** - Easy to add/remove files  
✅ **Professional** - Looks like enterprise software  
✅ **Maintainable** - No restart needed for config changes  

---

## Option A: Daemon Developer Guide

### Step 1: Create Config File Structure

**File:** `log_config.py`

```python
#!/usr/bin/env python3
"""
Log monitoring configuration module
Supports YAML config files for flexible log monitoring
"""

import yaml
import os
import glob
from typing import List, Dict, Optional
import logging

logger = logging.getLogger('resolvix.config')


class LogFileConfig:
    """Configuration for a single log file or pattern"""
    
    def __init__(self, config_dict: Dict):
        self.path = config_dict.get('path')
        self.label = config_dict.get('label', 'unlabeled')
        self.priority = config_dict.get('priority', 'medium')
        self.enabled = config_dict.get('enabled', True)
        self.glob_pattern = config_dict.get('glob', False)
        self.recursive = config_dict.get('recursive', False)
        self.exclude_patterns = config_dict.get('exclude', [])
        
    def resolve_files(self) -> List[str]:
        """
        Resolve the path to actual file(s).
        Handles glob patterns, directories, and single files.
        
        Returns:
            List of absolute file paths
        """
        if not self.path:
            return []
        
        files = []
        
        # Handle glob patterns
        if self.glob_pattern or '*' in self.path or '?' in self.path:
            matched_files = glob.glob(self.path, recursive=self.recursive)
            files.extend([f for f in matched_files if os.path.isfile(f)])
        
        # Handle directories
        elif os.path.isdir(self.path):
            if self.recursive:
                for root, dirs, filenames in os.walk(self.path):
                    for filename in filenames:
                        if filename.endswith('.log'):
                            files.append(os.path.join(root, filename))
            else:
                for filename in os.listdir(self.path):
                    filepath = os.path.join(self.path, filename)
                    if os.path.isfile(filepath) and filename.endswith('.log'):
                        files.append(filepath)
        
        # Handle single file
        elif os.path.isfile(self.path):
            files.append(self.path)
        
        # Filter out excluded patterns
        if self.exclude_patterns:
            files = [f for f in files if not any(pattern in f for pattern in self.exclude_patterns)]
        
        return [os.path.abspath(f) for f in files]
    
    def __repr__(self):
        return f"LogFileConfig(path={self.path}, label={self.label}, priority={self.priority})"


class LogMonitoringConfig:
    """Main configuration class for log monitoring"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.mode = 'auto'  # auto, custom, single
        self.log_files: List[LogFileConfig] = []
        self.api_url = None
        self.node_id = None
        
        if config_file:
            self.load_from_file(config_file)
    
    def load_from_file(self, config_file: str):
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            self.mode = config.get('log_monitoring', {}).get('mode', 'auto')
            
            # Load API configuration
            api_config = config.get('api', {})
            self.api_url = api_config.get('url')
            self.node_id = api_config.get('node_id')
            
            # Load log files
            files_config = config.get('log_monitoring', {}).get('files', [])
            self.log_files = [LogFileConfig(f) for f in files_config]
            
            logger.info(f"Loaded configuration from {config_file}")
            logger.info(f"Mode: {self.mode}, Files: {len(self.log_files)}")
            
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {e}")
            raise
    
    def get_all_files(self) -> List[Dict]:
        """
        Get all resolved log files with their configurations.
        
        Returns:
            List of dicts with 'path', 'label', 'priority' for each file
        """
        all_files = []
        
        for config in self.log_files:
            if not config.enabled:
                continue
            
            resolved_files = config.resolve_files()
            for filepath in resolved_files:
                all_files.append({
                    'path': filepath,
                    'label': config.label,
                    'priority': config.priority
                })
        
        return all_files
    
    def add_auto_discovery_files(self):
        """Add common log locations automatically"""
        common_logs = [
            {'path': '/var/log/syslog', 'label': 'system', 'priority': 'high'},
            {'path': '/var/log/messages', 'label': 'system', 'priority': 'high'},
            {'path': '/var/log/apache2/*.log', 'label': 'apache', 'priority': 'high', 'glob': True},
            {'path': '/var/log/nginx/*.log', 'label': 'nginx', 'priority': 'high', 'glob': True},
            {'path': '/var/log/mysql/', 'label': 'mysql', 'priority': 'high', 'recursive': False},
        ]
        
        for log_config in common_logs:
            self.log_files.append(LogFileConfig(log_config))
    
    @staticmethod
    def create_default_config(output_file: str):
        """Create a default configuration file"""
        default_config = """# Resolvix Daemon Configuration
# Version: 2.0

# API Configuration
api:
  url: "http://your-backend:3000/api/ticket"
  node_id: null  # Auto-detect if null

# Database Configuration (for suppression rules)
database:
  host: "localhost"
  name: "resolvix_db"
  user: "resolvix_user"
  password: "your_password"
  port: 5432

# Log Monitoring Configuration
log_monitoring:
  mode: custom  # Options: auto, custom, single
  
  files:
    # System logs
    - path: /var/log/syslog
      label: system_logs
      priority: high
      enabled: true
    
    # Apache logs (with wildcard)
    - path: /var/log/apache2/*.log
      label: apache
      priority: critical
      enabled: true
      glob: true
      exclude:
        - access.log
    
    # Nginx logs (directory)
    - path: /var/log/nginx/
      label: nginx
      priority: high
      enabled: true
      recursive: false
    
    # Application logs (recursive directory)
    - path: /var/log/myapp/
      label: application
      priority: high
      enabled: true
      recursive: true
    
    # Custom application log
    - path: /home/user/app/logs/app.log
      label: custom_app
      priority: medium
      enabled: false  # Disabled by default

# Telemetry Configuration
telemetry:
  interval: 60  # seconds
  ws_port: 8756

# Control Configuration
control:
  port: 8754
  ws_port: 8755
"""
        with open(output_file, 'w') as f:
            f.write(default_config)
        
        logger.info(f"Created default config at {output_file}")


# Example usage
if __name__ == "__main__":
    # Create a default config
    LogMonitoringConfig.create_default_config('resolvix_config.yaml')
    
    # Load and test
    config = LogMonitoringConfig('resolvix_config.yaml')
    files = config.get_all_files()
    
    print(f"Found {len(files)} log files to monitor:")
    for file in files:
        print(f"  - {file['path']} [{file['label']}] ({file['priority']})")
```

### Step 2: Modify Main Daemon to Support Multiple Files

**File:** `log_collector_daemon.py` (modifications)

**Add these imports:**
```python
from log_config import LogMonitoringConfig, LogFileConfig
import yaml
```

**Modify LogCollectorDaemon class:**

```python
class LogCollectorDaemon:
    def __init__(self, log_file=None, config_file=None, api_url=None, 
                 ws_port=DEFAULT_WS_PORT, telemetry_ws_port=DEFAULT_TELEMETRY_WS_PORT, 
                 node_id=None, interval=1, tail_lines=200, 
                 telemetry_interval=DEFAULT_TELEMETRY_INTERVAL,
                 heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
                 db_host=None, db_name=None, db_user=None, db_password=None, db_port=5432):
        
        # Load configuration
        if config_file:
            self.config = LogMonitoringConfig(config_file)
            # Override with config file values if not provided
            api_url = api_url or self.config.api_url
            node_id = node_id or self.config.node_id
            self.log_files = self.config.get_all_files()
        elif log_file:
            # Single file mode (backward compatible)
            self.log_files = [{
                'path': os.path.abspath(log_file),
                'label': 'main',
                'priority': 'high'
            }]
            self.config = None
        else:
            raise ValueError("Either log_file or config_file must be provided")
        
        # Store configuration
        self.api_url = api_url.rstrip("/") if api_url else None
        self.ws_port = int(ws_port)
        self.telemetry_ws_port = int(telemetry_ws_port)
        self.node_id = node_id or get_node_id()
        self.interval = interval
        self.tail_lines = tail_lines
        self.telemetry_interval = telemetry_interval
        self.heartbeat_interval = heartbeat_interval
        self._stop_flag = threading.Event()
        self._monitor_threads = []  # List of monitoring threads
        self._heartbeat_thread = None
        self._live_proc = None
        self._telemetry_proc = None
        self._live_lock = threading.Lock()
        self._telemetry_lock = threading.Lock()
        
        # compiled keyword regex
        kw = "|".join(re.escape(k) for k in ERROR_KEYWORDS)
        self._err_re = re.compile(rf"\b({kw})\b", re.IGNORECASE)
        
        # Database and suppression checker setup (same as before)
        # ... existing code ...
        
        logger.info(f"Daemon initialized to monitor {len(self.log_files)} log file(s)")

    def start(self):
        """Start monitoring threads for all configured log files"""
        logger.info(f"Starting log monitoring for {len(self.log_files)} file(s)")
        
        # Start a thread for each log file
        for log_file_config in self.log_files:
            thread = threading.Thread(
                target=self._monitor_loop,
                args=(log_file_config,),
                daemon=True,
                name=f"Monitor-{log_file_config['label']}"
            )
            thread.start()
            self._monitor_threads.append(thread)
            logger.info(f"Started monitoring: {log_file_config['path']} [{log_file_config['label']}]")
        
        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info(f"Heartbeat started (interval: {self.heartbeat_interval}s)")
    
    def stop(self):
        """Stop all monitoring threads"""
        self._stop_flag.set()
        
        # Wait for all monitor threads
        for thread in self._monitor_threads:
            if thread:
                thread.join(timeout=2)
        
        # Stop heartbeat
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)
        
        # Stop subprocesses
        self.stop_livelogs()
        self.stop_telemetry()
        
        # Close database
        if self.db_connection:
            try:
                self.db_connection.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
    
    def _monitor_loop(self, log_file_config: Dict):
        """
        Monitor a single log file.
        This runs in its own thread.
        
        Args:
            log_file_config: Dict with 'path', 'label', 'priority'
        """
        log_file_path = log_file_config['path']
        label = log_file_config['label']
        priority = log_file_config['priority']
        
        # Wait until file exists
        while not os.path.exists(log_file_path) and not self._stop_flag.is_set():
            logger.warning(f"Waiting for log file: {log_file_path}")
            time.sleep(5)
        
        if self._stop_flag.is_set():
            return
        
        logger.info(f"Log file found, starting monitoring: {log_file_path}")
        
        try:
            with open(log_file_path, "r", errors="ignore") as f:
                # Go to EOF
                f.seek(0, os.SEEK_END)
                logger.info(f"Monitoring started [{label}]: {log_file_path}")
                
                while not self._stop_flag.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(self.interval)
                        continue
                    
                    if self._err_re.search(line):
                        severity = detect_severity(line)
                        ts = parse_timestamp(line)
                        payload = {
                            "timestamp": ts,
                            "system_ip": self.node_id,
                            "log_path": log_file_path,
                            "log_label": label,  # NEW: Add label
                            "application": label,
                            "log_line": line.rstrip("\n"),
                            "severity": severity,
                            "priority": priority  # NEW: Add priority
                        }
                        
                        logger.info(f"Issue detected [{severity}] in {label}: {line.strip()[:100]}")
                        
                        # Check suppression rules
                        if self.suppression_checker:
                            try:
                                should_suppress, matched_rule = self.suppression_checker.should_suppress(
                                    line.rstrip("\n"),
                                    self.node_id
                                )
                                
                                if should_suppress:
                                    logger.info(
                                        f"[SUPPRESSED] [{label}] Error suppressed by rule: {matched_rule['name']} (ID: {matched_rule['id']})"
                                    )
                                    continue
                            except Exception as e:
                                logger.error(f"[SUPPRESSED] Error checking suppression rules: {e}")
                        
                        # Send to RabbitMQ
                        if self.api_url:
                            success = send_to_rabbitmq(payload)
                            if success:
                                logger.info(f"✅ [{label}] Log entry sent to RabbitMQ")
                            else:
                                logger.error(f"❌ [{label}] Failed to send log to RabbitMQ")
                        else:
                            logger.info(f"No API configured, logging locally: {json.dumps(payload)}")
        
        except Exception as e:
            logger.error(f"Monitor loop exception for {log_file_path}: {e}", exc_info=True)
```

**Update parse_args():**

```python
def parse_args():
    parser = argparse.ArgumentParser(description="Log Collector Daemon")
    
    # Configuration options (mutually exclusive)
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument("--log-file", "-l", help="Path to single log file to monitor")
    config_group.add_argument("--config", "-c", help="Path to YAML configuration file")
    
    parser.add_argument("--api-url", "-a", help="Central API URL to send logs")
    parser.add_argument("--control-port", "-p", type=int, default=DEFAULT_CONTROL_PORT)
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    parser.add_argument("--telemetry-ws-port", type=int, default=DEFAULT_TELEMETRY_WS_PORT)
    parser.add_argument("--node-id", "-n", help="optional node identifier")
    parser.add_argument("--telemetry-interval", "-t", type=int, default=DEFAULT_TELEMETRY_INTERVAL)
    parser.add_argument("--heartbeat-interval", type=int, default=DEFAULT_HEARTBEAT_INTERVAL)
    
    # Database configuration
    parser.add_argument("--db-host", help="Database host for suppression rules")
    parser.add_argument("--db-name", help="Database name for suppression rules")
    parser.add_argument("--db-user", help="Database user for suppression rules")
    parser.add_argument("--db-password", help="Database password for suppression rules")
    parser.add_argument("--db-port", type=int, default=5432)
    
    return parser.parse_args()
```

**Update main():**

```python
if __name__ == "__main__":
    args = parse_args()
    logger.info("="*60)
    logger.info("Resolvix Daemon Starting")
    logger.info("="*60)
    
    daemon = LogCollectorDaemon(
        log_file=args.log_file,
        config_file=args.config,
        api_url=args.api_url,
        ws_port=args.ws_port,
        telemetry_ws_port=args.telemetry_ws_port,
        node_id=args.node_id,
        telemetry_interval=args.telemetry_interval,
        heartbeat_interval=args.heartbeat_interval,
        db_host=args.db_host,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
        db_port=args.db_port
    )
    
    daemon.start()
    app = make_app(daemon)
    
    # Log startup info
    if args.config:
        logger.info(f"Configuration file: {args.config}")
    else:
        logger.info(f"Single file mode: {args.log_file}")
    
    logger.info(f"Control HTTP endpoint: http://0.0.0.0:{args.control_port}")
    # ... rest of startup logging ...
```

### Step 3: Create Example Configuration File

**File:** `resolvix_config.example.yaml`

```yaml
# Resolvix Daemon Configuration
# Copy this file and customize for your environment

# API Configuration
api:
  url: "http://13.235.113.192:3000/api/ticket"
  node_id: null  # Auto-detect if null

# Database Configuration (for suppression rules)
database:
  host: "140.238.255.110"
  name: "resolvix_db"
  user: "resolvix_user"
  password: "changeme"
  port: 5432

# Log Monitoring Configuration
log_monitoring:
  mode: custom  # Options: auto, custom
  
  files:
    # System logs
    - path: /var/log/syslog
      label: system
      priority: high
      enabled: true
    
    # Apache error logs
    - path: /var/log/apache2/error.log
      label: apache_errors
      priority: critical
      enabled: true
    
    # Apache access logs (if needed)
    - path: /var/log/apache2/access.log
      label: apache_access
      priority: low
      enabled: false
    
    # Nginx logs (all files in directory)
    - path: /var/log/nginx/*.log
      label: nginx
      priority: high
      enabled: true
      glob: true
    
    # MySQL logs
    - path: /var/log/mysql/
      label: mysql
      priority: high
      enabled: true
      recursive: false
    
    # Application logs (recursive)
    - path: /var/log/myapp/
      label: application
      priority: high
      enabled: true
      recursive: true
      exclude:
        - debug.log
        - trace.log

# Telemetry Configuration
telemetry:
  interval: 60  # Collection interval in seconds
  ws_port: 8756

# Control Configuration
control:
  port: 8754
  ws_port: 8755
  heartbeat_interval: 30
```

### Step 4: Update Installation Script

**File:** `install.sh` (add config file setup)

```bash
# ... existing installation steps ...

# Create config directory
sudo mkdir -p /etc/resolvix
sudo chmod 755 /etc/resolvix

# Copy example config
cp resolvix_config.example.yaml /etc/resolvix/config.yaml
sudo chown $(whoami):$(whoami) /etc/resolvix/config.yaml
sudo chmod 644 /etc/resolvix/config.yaml

echo "[Installer] Created config file at /etc/resolvix/config.yaml"
echo "[Installer] Please edit this file to customize your log monitoring"

# Update systemd service to use config file
ExecStart=${PYTHON_PATH} ${WORK_DIR}/log_collector_daemon.py --config /etc/resolvix/config.yaml
```

### Step 5: Add Get Status Endpoint Enhancement

**Add to Flask app in `make_app()`:**

```python
@app.route("/api/status", methods=["GET"])
def status():
    status_data = daemon.get_status()
    
    # Add monitored files info
    if hasattr(daemon, 'log_files'):
        status_data["monitored_files"] = {
            "count": len(daemon.log_files),
            "files": [
                {
                    "path": f["path"],
                    "label": f["label"],
                    "priority": f["priority"]
                }
                for f in daemon.log_files
            ]
        }
    
    return jsonify(status_data), HTTPStatus.OK
```

### Step 6: Add Requirements

**File:** `requirements.txt` (add)

```
PyYAML>=5.4.0
```

### Step 7: Testing

**Test config file:**

```bash
# Create test config
python3 -c "from log_config import LogMonitoringConfig; LogMonitoringConfig.create_default_config('test_config.yaml')"

# Edit test_config.yaml with your paths

# Test daemon with config
python3 log_collector_daemon.py --config test_config.yaml

# Check status
curl http://localhost:8754/api/status | jq .monitored_files
```

---

## Option A: Backend Developer Guide

### What You Need to Do

#### 1. Update Error Log Schema

**Add new fields to error logs table/collection:**

```sql
-- If using PostgreSQL
ALTER TABLE error_logs ADD COLUMN log_label VARCHAR(100);
ALTER TABLE error_logs ADD COLUMN priority VARCHAR(50);

-- Create index for better querying
CREATE INDEX idx_error_logs_label ON error_logs(log_label);
CREATE INDEX idx_error_logs_priority ON error_logs(priority);
```

**Or if using MongoDB:**

```javascript
db.error_logs.createIndex({ "log_label": 1 });
db.error_logs.createIndex({ "priority": 1 });
```

#### 2. Update API Endpoint to Accept New Fields

**Endpoint:** `POST /api/ticket` or `POST /api/logs`

**Updated request body schema:**

```json
{
  "timestamp": "2025-12-18T10:30:45Z",
  "system_ip": "192.168.1.100",
  "log_path": "/var/log/apache2/error.log",
  "log_label": "apache_errors",     // NEW FIELD
  "application": "apache_errors",
  "log_line": "Error: Connection timeout",
  "severity": "error",
  "priority": "critical"             // NEW FIELD
}
```

**Example backend code (Node.js/Express):**

```javascript
// POST /api/ticket
app.post('/api/ticket', async (req, res) => {
  const {
    timestamp,
    system_ip,
    log_path,
    log_label,    // NEW
    application,
    log_line,
    severity,
    priority      // NEW
  } = req.body;
  
  // Validate
  if (!timestamp || !system_ip || !log_line) {
    return res.status(400).json({ error: 'Missing required fields' });
  }
  
  // Store in database
  const ticket = await db.tickets.create({
    timestamp: new Date(timestamp),
    system_ip,
    log_path,
    log_label: log_label || 'unlabeled',    // Default if not provided
    application: application || log_label,
    log_line,
    severity: severity || 'info',
    priority: priority || 'medium',         // Default if not provided
    status: 'open',
    created_at: new Date()
  });
  
  res.status(201).json({
    success: true,
    ticket_id: ticket.id
  });
});
```

#### 3. Create API Endpoints for Configuration Management

**NEW ENDPOINT:** `GET /api/nodes/{node_ip}/config`

Get current configuration for a node:

```javascript
app.get('/api/nodes/:node_ip/config', async (req, res) => {
  const { node_ip } = req.params;
  
  // Get config from database
  const config = await db.node_configs.findOne({ node_ip });
  
  if (!config) {
    return res.status(404).json({ error: 'Node not found' });
  }
  
  res.json({
    node_ip,
    monitored_files: config.monitored_files,
    updated_at: config.updated_at
  });
});
```

**NEW ENDPOINT:** `POST /api/nodes/{node_ip}/config`

Update node configuration:

```javascript
app.post('/api/nodes/:node_ip/config', async (req, res) => {
  const { node_ip } = req.params;
  const { monitored_files } = req.body;
  
  // Validate monitored_files structure
  if (!Array.isArray(monitored_files)) {
    return res.status(400).json({ error: 'monitored_files must be an array' });
  }
  
  // Update or create config
  const config = await db.node_configs.upsert({
    node_ip,
    monitored_files,
    updated_at: new Date()
  });
  
  res.json({
    success: true,
    message: 'Configuration updated',
    config
  });
});
```

**NEW ENDPOINT:** `GET /api/nodes/{node_ip}/status`

Enhanced status including monitored files:

```javascript
app.get('/api/nodes/:node_ip/status', async (req, res) => {
  const { node_ip } = req.params;
  
  // Get status from node (make HTTP request to node's daemon)
  const nodeStatus = await axios.get(`http://${node_ip}:8754/api/status`);
  
  res.json({
    node_ip,
    status: nodeStatus.data,
    monitored_files: nodeStatus.data.monitored_files || {},
    timestamp: new Date()
  });
});
```

#### 4. Database Schema for Node Configurations

**Table:** `node_configs`

```sql
CREATE TABLE node_configs (
    id SERIAL PRIMARY KEY,
    node_ip VARCHAR(50) UNIQUE NOT NULL,
    config_yaml TEXT,  -- Store the entire YAML config
    monitored_files JSONB,  -- Store monitored files as JSON
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_node_configs_ip ON node_configs(node_ip);
```

**Example row:**

```json
{
  "node_ip": "192.168.1.100",
  "monitored_files": [
    {
      "path": "/var/log/syslog",
      "label": "system",
      "priority": "high",
      "enabled": true
    },
    {
      "path": "/var/log/apache2/error.log",
      "label": "apache_errors",
      "priority": "critical",
      "enabled": true
    }
  ],
  "updated_at": "2025-12-18T10:30:00Z"
}
```

#### 5. Update Statistics/Dashboard Queries

**Example: Errors by log source**

```sql
SELECT 
    log_label,
    priority,
    COUNT(*) as error_count,
    MAX(timestamp) as last_error
FROM error_logs
WHERE system_ip = '192.168.1.100'
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY log_label, priority
ORDER BY error_count DESC;
```

**Example: High priority errors**

```sql
SELECT *
FROM error_logs
WHERE priority IN ('critical', 'high')
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC
LIMIT 100;
```

#### 6. API Documentation Updates

Update your API docs to include new fields:

**Swagger/OpenAPI example:**

```yaml
paths:
  /api/ticket:
    post:
      summary: Create error log ticket
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required:
                - timestamp
                - system_ip
                - log_line
              properties:
                timestamp:
                  type: string
                  format: date-time
                system_ip:
                  type: string
                log_path:
                  type: string
                log_label:
                  type: string
                  description: "Label identifying the log source (e.g., 'apache_errors', 'system')"
                application:
                  type: string
                log_line:
                  type: string
                severity:
                  type: string
                  enum: [critical, error, warn, info]
                priority:
                  type: string
                  enum: [critical, high, medium, low]
                  description: "Priority level of the log source"
```

---

## Option A: Frontend Developer Guide

### What You Need to Implement

#### 1. Node Configuration Management UI

**Create a new page: "Node Configuration"**

**Features needed:**
- View current monitored files for each node
- Add new log files to monitor
- Edit existing file configurations
- Enable/disable specific log files
- Set priority levels
- Save configuration

**Example UI mockup:**

```
┌─────────────────────────────────────────────────────────┐
│ Node: 192.168.1.100                    [Edit] [Refresh] │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Monitored Log Files (5)                                 │
│                                                          │
│ ┌────────────────────────────────────────────────────┐  │
│ │ ✓ /var/log/syslog                     [system]    │  │
│ │   Priority: High          Last Error: 2 min ago   │  │
│ │   Errors Today: 23        [Edit] [Disable]        │  │
│ └────────────────────────────────────────────────────┘  │
│                                                          │
│ ┌────────────────────────────────────────────────────┐  │
│ │ ✓ /var/log/apache2/error.log  [apache_errors]    │  │
│ │   Priority: Critical      Last Error: 5 min ago   │  │
│ │   Errors Today: 156       [Edit] [Disable]        │  │
│ └────────────────────────────────────────────────────┘  │
│                                                          │
│ [+ Add Log File]                                        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**React Component Example:**

```jsx
import React, { useState, useEffect } from 'react';
import { Card, Button, Badge, Table } from 'react-bootstrap';

function NodeConfiguration({ nodeIp }) {
  const [monitoredFiles, setMonitoredFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetchNodeStatus();
  }, [nodeIp]);
  
  const fetchNodeStatus = async () => {
    try {
      const response = await fetch(`/api/nodes/${nodeIp}/status`);
      const data = await response.json();
      
      if (data.status.monitored_files) {
        setMonitoredFiles(data.status.monitored_files.files);
      }
    } catch (error) {
      console.error('Error fetching node status:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const getPriorityBadge = (priority) => {
    const variants = {
      critical: 'danger',
      high: 'warning',
      medium: 'info',
      low: 'secondary'
    };
    return <Badge bg={variants[priority] || 'secondary'}>{priority}</Badge>;
  };
  
  return (
    <Card>
      <Card.Header>
        <h5>Monitored Log Files</h5>
        <Button variant="primary" size="sm" onClick={fetchNodeStatus}>
          Refresh
        </Button>
      </Card.Header>
      <Card.Body>
        {loading ? (
          <p>Loading...</p>
        ) : (
          <Table hover>
            <thead>
              <tr>
                <th>Path</th>
                <th>Label</th>
                <th>Priority</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {monitoredFiles.map((file, idx) => (
                <tr key={idx}>
                  <td><code>{file.path}</code></td>
                  <td>{file.label}</td>
                  <td>{getPriorityBadge(file.priority)}</td>
                  <td>
                    <Button variant="outline-primary" size="sm">
                      Edit
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card.Body>
    </Card>
  );
}

export default NodeConfiguration;
```

#### 2. Log Source Filter in Dashboard

**Add dropdown filter to error logs dashboard:**

```jsx
function ErrorLogsDashboard() {
  const [logSource, setLogSource] = useState('all');
  const [errors, setErrors] = useState([]);
  
  const logSources = [
    { value: 'all', label: 'All Sources' },
    { value: 'system', label: 'System Logs' },
    { value: 'apache_errors', label: 'Apache Errors' },
    { value: 'nginx', label: 'Nginx' },
    { value: 'application', label: 'Application' }
  ];
  
  const fetchErrors = async () => {
    const url = logSource === 'all' 
      ? '/api/errors' 
      : `/api/errors?log_label=${logSource}`;
    
    const response = await fetch(url);
    const data = await response.json();
    setErrors(data);
  };
  
  return (
    <div>
      <div className="filters">
        <label>Log Source:</label>
        <select value={logSource} onChange={(e) => setLogSource(e.target.value)}>
          {logSources.map(src => (
            <option key={src.value} value={src.value}>
              {src.label}
            </option>
          ))}
        </select>
      </div>
      
      <ErrorLogTable errors={errors} />
    </div>
  );
}
```

#### 3. Priority-based Visualization

**Add priority indicators to error list:**

```jsx
function ErrorLogRow({ error }) {
  const priorityIcons = {
    critical: '🔴',
    high: '🟠',
    medium: '🟡',
    low: '⚪'
  };
  
  const priorityColors = {
    critical: '#dc3545',
    high: '#fd7e14',
    medium: '#ffc107',
    low: '#6c757d'
  };
  
  return (
    <tr style={{ borderLeft: `4px solid ${priorityColors[error.priority]}` }}>
      <td>
        <span className="priority-icon">
          {priorityIcons[error.priority]}
        </span>
      </td>
      <td><Badge>{error.log_label}</Badge></td>
      <td>{error.timestamp}</td>
      <td>{error.log_line}</td>
      <td>{error.severity}</td>
    </tr>
  );
}
```

#### 4. Statistics by Log Source

**Add charts showing errors by source:**

```jsx
import { Pie, Bar } from 'react-chartjs-2';

function ErrorStatsBySource({ nodeIp }) {
  const [stats, setStats] = useState({});
  
  useEffect(() => {
    fetchStats();
  }, [nodeIp]);
  
  const fetchStats = async () => {
    const response = await fetch(`/api/nodes/${nodeIp}/stats/by-source`);
    const data = await response.json();
    setStats(data);
  };
  
  const chartData = {
    labels: Object.keys(stats),
    datasets: [{
      label: 'Errors by Source',
      data: Object.values(stats),
      backgroundColor: [
        '#FF6384',
        '#36A2EB',
        '#FFCE56',
        '#4BC0C0',
        '#9966FF'
      ]
    }]
  };
  
  return (
    <Card>
      <Card.Header>Errors by Log Source (24h)</Card.Header>
      <Card.Body>
        <Pie data={chartData} />
      </Card.Body>
    </Card>
  );
}
```

#### 5. Configuration Editor Modal

**Allow editing log file configuration:**

```jsx
function EditLogFileModal({ file, onSave, onClose }) {
  const [formData, setFormData] = useState({
    path: file.path,
    label: file.label,
    priority: file.priority,
    enabled: file.enabled
  });
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Save configuration
    await fetch(`/api/nodes/${nodeIp}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        monitored_files: [formData]
      })
    });
    
    onSave();
  };
  
  return (
    <Modal show={true} onHide={onClose}>
      <Modal.Header closeButton>
        <Modal.Title>Edit Log File Configuration</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Form onSubmit={handleSubmit}>
          <Form.Group>
            <Form.Label>File Path</Form.Label>
            <Form.Control 
              type="text" 
              value={formData.path}
              onChange={(e) => setFormData({...formData, path: e.target.value})}
            />
          </Form.Group>
          
          <Form.Group>
            <Form.Label>Label</Form.Label>
            <Form.Control 
              type="text" 
              value={formData.label}
              onChange={(e) => setFormData({...formData, label: e.target.value})}
            />
          </Form.Group>
          
          <Form.Group>
            <Form.Label>Priority</Form.Label>
            <Form.Select 
              value={formData.priority}
              onChange={(e) => setFormData({...formData, priority: e.target.value})}
            >
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </Form.Select>
          </Form.Group>
          
          <Form.Group>
            <Form.Check 
              type="checkbox"
              label="Enabled"
              checked={formData.enabled}
              onChange={(e) => setFormData({...formData, enabled: e.target.checked})}
            />
          </Form.Group>
          
          <Button type="submit">Save</Button>
        </Form>
      </Modal.Body>
    </Modal>
  );
}
```

#### 6. Node Overview Enhancement

**Show monitored file count on node list:**

```jsx
function NodeCard({ node }) {
  return (
    <Card>
      <Card.Body>
        <h5>{node.ip}</h5>
        <p>Status: <Badge bg="success">Online</Badge></p>
        <p>Monitored Files: <strong>{node.monitored_files_count}</strong></p>
        <p>Errors Today: <strong>{node.errors_today}</strong></p>
        <Button href={`/nodes/${node.ip}/config`}>
          Configure
        </Button>
      </Card.Body>
    </Card>
  );
}
```

#### 7. API Integration Summary

**API Calls you'll need:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/nodes/{ip}/status` | GET | Get monitored files and status |
| `/api/nodes/{ip}/config` | GET | Get current configuration |
| `/api/nodes/{ip}/config` | POST | Update configuration |
| `/api/errors?log_label={label}` | GET | Filter errors by log source |
| `/api/nodes/{ip}/stats/by-source` | GET | Get error statistics by source |

---

# Option B: Multiple --log-file Implementation (Quick Fix)

## Option B: Daemon Developer Guide

This is a simpler, faster implementation that allows multiple `--log-file` arguments.

### Step 1: Modify parse_args()

**File:** `log_collector_daemon.py`

```python
def parse_args():
    parser = argparse.ArgumentParser(description="Log Collector Daemon")
    
    # Allow multiple --log-file arguments
    parser.add_argument("--log-file", "-l", action='append', dest='log_files',
                       help="Path to log file to monitor (can be specified multiple times)")
    parser.add_argument("--api-url", "-a", required=True, help="Central API URL")
    parser.add_argument("--control-port", "-p", type=int, default=DEFAULT_CONTROL_PORT)
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    parser.add_argument("--telemetry-ws-port", type=int, default=DEFAULT_TELEMETRY_WS_PORT)
    parser.add_argument("--node-id", "-n", help="optional node identifier")
    parser.add_argument("--telemetry-interval", "-t", type=int, default=DEFAULT_TELEMETRY_INTERVAL)
    parser.add_argument("--heartbeat-interval", type=int, default=DEFAULT_HEARTBEAT_INTERVAL)
    
    # Database configuration
    parser.add_argument("--db-host", help="Database host")
    parser.add_argument("--db-name", help="Database name")
    parser.add_argument("--db-user", help="Database user")
    parser.add_argument("--db-password", help="Database password")
    parser.add_argument("--db-port", type=int, default=5432)
    
    args = parser.parse_args()
    
    # Validate at least one log file
    if not args.log_files:
        parser.error("At least one --log-file must be specified")
    
    return args
```

### Step 2: Modify LogCollectorDaemon.__init__()

```python
class LogCollectorDaemon:
    def __init__(self, log_files, api_url, ws_port=DEFAULT_WS_PORT, 
                 telemetry_ws_port=DEFAULT_TELEMETRY_WS_PORT, node_id=None, 
                 interval=1, tail_lines=200, telemetry_interval=DEFAULT_TELEMETRY_INTERVAL,
                 heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL,
                 db_host=None, db_name=None, db_user=None, db_password=None, db_port=5432):
        
        # Store log files as list of dicts
        self.log_files = []
        for i, log_file in enumerate(log_files):
            self.log_files.append({
                'path': os.path.abspath(log_file),
                'label': f'log_{i+1}',  # Simple label
                'priority': 'high'
            })
        
        # Rest of initialization
        self.api_url = api_url.rstrip("/") if api_url else None
        self.ws_port = int(ws_port)
        self.telemetry_ws_port = int(telemetry_ws_port)
        self.node_id = node_id or get_node_id()
        self.interval = interval
        self.tail_lines = tail_lines
        self.telemetry_interval = telemetry_interval
        self.heartbeat_interval = heartbeat_interval
        self._stop_flag = threading.Event()
        self._monitor_threads = []
        self._heartbeat_thread = None
        # ... rest of init ...
        
        logger.info(f"Daemon initialized to monitor {len(self.log_files)} log file(s)")
```

### Step 3: Modify start() and _monitor_loop()

**Same as Option A** - Use the multi-threaded approach with one thread per file.

### Step 4: Update main()

```python
if __name__ == "__main__":
    args = parse_args()
    logger.info("="*60)
    logger.info("Resolvix Daemon Starting")
    logger.info("="*60)
    
    daemon = LogCollectorDaemon(
        log_files=args.log_files,  # Pass the list
        api_url=args.api_url,
        ws_port=args.ws_port,
        telemetry_ws_port=args.telemetry_ws_port,
        node_id=args.node_id,
        telemetry_interval=args.telemetry_interval,
        heartbeat_interval=args.heartbeat_interval,
        db_host=args.db_host,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
        db_port=args.db_port
    )
    
    daemon.start()
    app = make_app(daemon)
    
    logger.info(f"Monitoring {len(args.log_files)} log file(s):")
    for log_file in args.log_files:
        logger.info(f"  - {log_file}")
    
    # ... rest of startup ...
```

### Step 5: Update systemd service

```ini
ExecStart=/path/to/venv/bin/python3 /path/to/log_collector_daemon.py \
  --log-file "/var/log/syslog" \
  --log-file "/var/log/apache2/error.log" \
  --log-file "/var/log/nginx/error.log" \
  --api-url "http://backend:3000/api/ticket"
```

### Usage Examples

```bash
# Monitor multiple files
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --log-file /var/log/nginx/error.log \
  --api-url http://backend:3000/api/ticket

# Still works with single file (backward compatible)
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://backend:3000/api/ticket
```

---

## Option B: Backend Developer Guide

### What You Need to Do (Minimal Changes)

#### 1. Update Schema (Optional but Recommended)

Same as Option A - add `log_label` and `priority` fields.

But since Option B doesn't have proper labels, the `log_label` will be generic like "log_1", "log_2", etc.

```sql
ALTER TABLE error_logs ADD COLUMN log_label VARCHAR(100);
```

#### 2. Update API to Accept log_label (Optional)

The daemon will send `log_label: 'log_1'` etc. You can store it or ignore it.

```javascript
app.post('/api/ticket', async (req, res) => {
  const { log_label, ...otherFields } = req.body;
  
  // Store log_label if provided
  await db.tickets.create({
    ...otherFields,
    log_label: log_label || 'unknown'
  });
  
  res.status(201).json({ success: true });
});
```

**That's it!** Option B requires minimal backend changes.

---

## Option B: Frontend Developer Guide

### What You Need to Do (Minimal Changes)

#### 1. Show Monitored Files Count

Display how many files are being monitored:

```jsx
function NodeStatus({ node }) {
  const [status, setStatus] = useState(null);
  
  useEffect(() => {
    fetch(`http://${node.ip}:8754/api/status`)
      .then(res => res.json())
      .then(data => setStatus(data));
  }, [node.ip]);
  
  return (
    <div>
      <h3>Node: {node.ip}</h3>
      {status?.monitored_files && (
        <p>Monitoring {status.monitored_files.count} log files</p>
      )}
    </div>
  );
}
```

#### 2. Display File List (Optional)

Show which files are being monitored:

```jsx
function MonitoredFilesList({ nodeIp }) {
  const [files, setFiles] = useState([]);
  
  useEffect(() => {
    fetch(`http://${nodeIp}:8754/api/status`)
      .then(res => res.json())
      .then(data => {
        if (data.monitored_files) {
          setFiles(data.monitored_files.files);
        }
      });
  }, [nodeIp]);
  
  return (
    <ul>
      {files.map((file, idx) => (
        <li key={idx}>{file.path}</li>
      ))}
    </ul>
  );
}
```

**That's it!** Option B requires minimal frontend changes.

---

# Migration Path

## From Current → Option B → Option A

### Phase 1: Deploy Option B (Week 1)

1. **Daemon Team:** Implement Option B (30 minutes)
2. **Backend Team:** Optional schema updates (1 hour)
3. **Frontend Team:** Show file count (30 minutes)
4. **Deploy to Dev:** Test with multiple files
5. **Deploy to Production:** Update systemd service

### Phase 2: Deploy Option A (Week 2-3)

1. **Daemon Team:** Implement Option A (2 hours)
2. **Backend Team:** Full implementation (4 hours)
3. **Frontend Team:** Full UI (8 hours)
4. **Create default configs:** For common setups
5. **Update documentation:** User guides
6. **Deploy to Production:** Gradual rollout

### Migration Script for Users

**From single file to config file:**

```python
#!/usr/bin/env python3
"""
Migrate from single file to config file
"""
import yaml
import sys

def create_config_from_args(log_files, api_url, output_file):
    config = {
        'api': {
            'url': api_url,
            'node_id': None
        },
        'log_monitoring': {
            'mode': 'custom',
            'files': []
        }
    }
    
    for i, log_file in enumerate(log_files):
        config['log_monitoring']['files'].append({
            'path': log_file,
            'label': f'log_{i+1}',
            'priority': 'high',
            'enabled': True
        })
    
    with open(output_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print(f"Created config file: {output_file}")
    print(f"Monitoring {len(log_files)} files")

if __name__ == "__main__":
    log_files = [
        '/var/log/syslog',
        '/var/log/apache2/error.log'
    ]
    api_url = 'http://backend:3000/api/ticket'
    
    create_config_from_args(log_files, api_url, 'resolvix_config.yaml')
```

---

# Testing Strategy

## Option A Testing

### Unit Tests

```python
# test_log_config.py
import unittest
from log_config import LogFileConfig, LogMonitoringConfig

class TestLogConfig(unittest.TestCase):
    
    def test_single_file_resolution(self):
        config = LogFileConfig({'path': '/var/log/syslog', 'label': 'system'})
        files = config.resolve_files()
        self.assertTrue(len(files) > 0)
    
    def test_glob_pattern(self):
        config = LogFileConfig({
            'path': '/var/log/*.log',
            'label': 'all_logs',
            'glob': True
        })
        files = config.resolve_files()
        self.assertTrue(len(files) > 0)
    
    def test_config_file_loading(self):
        config = LogMonitoringConfig('test_config.yaml')
        self.assertIsNotNone(config.api_url)
        self.assertTrue(len(config.log_files) > 0)
```

### Integration Tests

```bash
# Test with config file
python3 log_collector_daemon.py --config test_config.yaml &
DAEMON_PID=$!

# Wait for startup
sleep 2

# Check status
curl http://localhost:8754/api/status | jq .monitored_files

# Generate test errors in multiple files
echo "ERROR: Test error in syslog" | sudo tee -a /var/log/syslog
echo "ERROR: Test error in apache" | sudo tee -a /var/log/apache2/error.log

# Check logs
grep "Issue detected" /var/log/resolvix.log

# Cleanup
kill $DAEMON_PID
```

## Option B Testing

```bash
# Test with multiple files
python3 log_collector_daemon.py \
  --log-file /var/log/syslog \
  --log-file /var/log/apache2/error.log \
  --api-url http://localhost:3000/api/ticket &

DAEMON_PID=$!
sleep 2

# Check status
curl http://localhost:8754/api/status | jq .monitored_files

# Generate errors
echo "ERROR: Multi-file test 1" | sudo tee -a /var/log/syslog
echo "ERROR: Multi-file test 2" | sudo tee -a /var/log/apache2/error.log

# Verify both are caught
grep "Issue detected" /var/log/resolvix.log | tail -5

kill $DAEMON_PID
```

---

# Recommendation

## Choose Option A If:
- ✅ You want a professional, production-ready solution
- ✅ You have 2 hours for implementation
- ✅ You want flexibility for future features
- ✅ You want to match industry standards
- ✅ Users need to manage many log files

## Choose Option B If:
- ✅ You need a quick fix NOW
- ✅ You have limited development time
- ✅ Users typically monitor 2-3 files max
- ✅ You'll implement Option A later

## My Recommendation:
**Implement Option B this week, then Option A next sprint.**

This gives you:
1. Immediate improvement for users
2. Time to fully design Option A
3. Real-world feedback from Option B
4. Smooth migration path

---

**Questions? Need clarification? Let me know and I'll help implement either option!** 🚀
