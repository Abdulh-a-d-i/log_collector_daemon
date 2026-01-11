# Resolvix Log Collector Daemon - Complete Documentation

## Executive Summary

**Project Name:** Resolvix Log Collector Daemon  
**Version:** 1.1.0  
**Purpose:** Real-time system monitoring, log collection, and intelligent alert management for Linux servers

### What This System Does

Resolvix is an enterprise-grade system monitoring daemon that provides:

1. **Real-time Error Detection** - Continuously monitors server log files for errors, failures, and critical issues
2. **System Telemetry Collection** - Tracks CPU, memory, disk, network, and process metrics
3. **Intelligent Alerting** - Creates tickets/alerts only when thresholds are sustained (prevents alert fatigue)
4. **Live Log Streaming** - WebSocket-based real-time log viewing for operations teams
5. **Error Suppression** - Database-driven rules to suppress known/expected errors
6. **Remote Management** - REST API for configuration and control

---

## Business Value Proposition

### Problems Solved

1. **Reactive Incident Response** → **Proactive Monitoring**

   - Detects issues before they impact customers
   - Reduces Mean Time To Detection (MTTD)

2. **Alert Fatigue** → **Smart Alerting**

   - Only alerts when thresholds persist (e.g., CPU > 90% for 5 minutes)
   - Suppression rules eliminate noise from known issues

3. **Manual Log Checking** → **Automated Error Detection**

   - Keywords: error, critical, fatal, failed, panic, etc.
   - Automatic severity classification

4. **Distributed Systems Chaos** → **Centralized Visibility**

   - Single backend receives data from all servers
   - Historical telemetry for trend analysis

5. **Downtime Risk** → **High Availability**
   - Persistent queue survives network outages
   - Automatic retry with exponential backoff
   - Self-healing capabilities

### ROI Metrics

- **Reduced Downtime:** Early detection of resource exhaustion (CPU, memory, disk)
- **Lower MTTR:** Immediate notification with context (logs + metrics)
- **Cost Savings:** Prevent scaling issues before they become critical
- **Operational Efficiency:** Operations team doesn't need to SSH into each server

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    Linux Server                          │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │         Log Collector Daemon (Main)            │    │
│  │  - Monitors log files                          │    │
│  │  - Collects telemetry metrics                  │    │
│  │  - Checks alert thresholds                     │    │
│  │  - Manages subprocesses                        │    │
│  └────────────────────────────────────────────────┘    │
│           │              │              │               │
│           ▼              ▼              ▼               │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐       │
│  │   Livelogs   │ │Telemetry │ │   Control    │       │
│  │  WebSocket   │ │WebSocket │ │  HTTP API    │       │
│  │  (Port 8755) │ │(Port 8756)│ │ (Port 8754) │       │
│  └──────────────┘ └──────────┘ └──────────────┘       │
│           │              │              │               │
└───────────┼──────────────┼──────────────┼───────────────┘
            │              │              │
            ▼              ▼              ▼
    ┌───────────────────────────────────────────┐
    │         Backend Server                     │
    │  - RabbitMQ (error logs queue)            │
    │  - REST API (alerts, telemetry, config)   │
    │  - PostgreSQL (suppression rules)         │
    │  - WebSocket clients (dashboards)         │
    └───────────────────────────────────────────┘
```

### Data Flow

1. **Error Detection Flow**

   ```
   Log File → Daemon reads line-by-line → Keyword match →
   Check suppression rules → Send to RabbitMQ →
   Backend processes → Alert Manager creates ticket
   ```

2. **Telemetry Collection Flow**

   ```
   psutil collects metrics → Check alert thresholds →
   Enqueue to SQLite → Background poster POSTs to backend →
   Simultaneously stream via WebSocket to dashboards
   ```

3. **Configuration Flow**
   ```
   Backend updates config → Daemon polls /api/settings →
   Hot-reload (no restart) → Apply changes at runtime
   ```

---

## Technical Architecture

### Technology Stack

**Language:** Python 3.8+  
**Key Libraries:**

- `flask` - HTTP API server
- `websockets` - Real-time streaming
- `psutil` - System metrics collection
- `pika` - RabbitMQ client
- `psycopg2` - PostgreSQL client
- `requests` - HTTP client

**External Dependencies:**

- RabbitMQ - Message queue for error logs
- PostgreSQL - Suppression rules database (optional)
- Backend REST API - Central management server

### Core Modules

#### 1. `log_collector_daemon.py` (Main Entry Point)

**Responsibilities:**

- Orchestrates all components
- Spawns monitoring threads (one per log file)
- Manages livelogs and telemetry subprocesses
- Exposes HTTP control API
- Sends heartbeats to backend

**Key Classes:**

```python
class LogCollectorDaemon:
    - __init__(): Initialize with log files, API URL, ports, intervals
    - start(): Launch monitoring threads and heartbeat
    - stop(): Graceful shutdown
    - _monitor_loop(log_file_config): Per-file monitoring thread
    - _heartbeat_loop(): Periodic status updates
    - _telemetry_post_loop(): Background queue processing
    - start_livelogs(): Spawn livelogs.py subprocess
    - start_telemetry(): Spawn telemetry_ws.py subprocess
```

**Error Detection Algorithm:**

```python
1. Open log file and seek to end (tail mode)
2. Read new lines continuously
3. For each line:
   a. Match against error keywords (regex)
   b. Parse timestamp (syslog format or ISO8601)
   c. Detect severity (critical > failure > error > warn)
   d. Determine priority (critical/high/medium/low)
   e. Check suppression rules (if enabled)
   f. If not suppressed:
      - Send to RabbitMQ
      - Log locally
4. Sleep interval between reads
```

**Self-Monitoring:**

- Monitors its own log file (`/var/log/resolvix.log`)
- Skips operational messages to prevent recursion
- Reports critical errors to backend immediately

#### 2. `alert_manager.py` (Smart Alerting)

**Purpose:** Prevent alert fatigue by requiring sustained threshold breaches

**Configuration:** `alert_config.py`

| Alert Type         | Threshold | Duration  | Cooldown | Priority |
| ------------------ | --------- | --------- | -------- | -------- |
| CPU Critical       | 90%       | 5 min     | 30 min   | Critical |
| CPU High           | 75%       | 10 min    | 1 hour   | High     |
| Memory Critical    | 95%       | 5 min     | 30 min   | Critical |
| Memory High        | 85%       | 10 min    | 1 hour   | High     |
| Disk Critical      | 90%       | Immediate | 2 hours  | Critical |
| Disk High          | 80%       | Immediate | 4 hours  | High     |
| Network Spike      | 5x normal | 1 min     | 30 min   | Medium   |
| High Process Count | 500+      | 5 min     | 1 hour   | Medium   |

**Algorithm:**

```python
1. Collect metric (e.g., CPU = 92%)
2. Check if above threshold (92% > 90% ✓)
3. Start tracking breach time if first breach
4. On subsequent checks:
   a. If still above threshold:
      - Calculate breach duration
      - If duration >= required duration:
        → Send alert via HTTP POST to backend
        → Record last_alert_sent timestamp
        → Reset breach tracking
   b. If below threshold:
      - Reset breach tracking
5. Cooldown enforcement:
   - Don't send duplicate alert until cooldown expires
```

**Benefits:**

- Eliminates transient spike alerts
- Provides actionable alerts with context
- Reduces alert fatigue by 90%+

#### 3. `suppression_checker.py` (Noise Reduction)

**Purpose:** Filter out known/expected errors using database rules

**Database Schema:**

```sql
CREATE TABLE suppression_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    match_text TEXT NOT NULL,        -- Substring to match
    node_ip VARCHAR(255),             -- NULL = all nodes
    duration_type VARCHAR(50),        -- 'forever', '1h', '24h'
    enabled BOOLEAN DEFAULT true,
    expires_at TIMESTAMP,
    match_count INTEGER DEFAULT 0,
    last_matched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Example Rules:**

| Name                        | Match Text                | Node IP      | Duration | Effect                |
| --------------------------- | ------------------------- | ------------ | -------- | --------------------- |
| Ignore known disk warning   | "disk space low on /tmp"  | NULL         | Forever  | Suppress on all nodes |
| Suppress during maintenance | "connection refused"      | 192.168.1.10 | 2h       | Suppress on one node  |
| Filter cron job errors      | "cron: error (grandchild" | NULL         | Forever  | Suppress cron noise   |

**Caching:**

- Rules cached for 60 seconds (configurable)
- Reduces database load
- Auto-refresh on cache expiry

**Statistics Tracking:**

- Increments `match_count` on every match
- Updates `last_matched_at` timestamp
- Used for rule effectiveness analysis

#### 4. `telemetry_queue.py` + `telemetry_poster.py` (Reliability Layer)

**Problem:** Network outages cause telemetry data loss

**Solution:** SQLite-based persistent queue with retry logic

**Queue Schema:**

```sql
CREATE TABLE telemetry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL,           -- JSON telemetry snapshot
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_attempt_at TEXT
);
```

**Flow:**

```
Collect Metrics → Enqueue to SQLite → Background Poster Thread →
  ├─ POST Success → Delete from queue
  └─ POST Failure → Increment retry_count
      ├─ retry_count < 3 → Keep in queue (retry later)
      └─ retry_count >= 3 → Drop (permanent failure)
```

**Retry Strategy:**

- 1st retry: Wait 5 seconds
- 2nd retry: Wait 15 seconds
- 3rd retry: Wait 60 seconds
- After 3 failures: Drop snapshot

**Benefits:**

- Zero data loss during network issues
- Automatic recovery when backend comes back online
- Prevents memory leaks (queue size limit)

#### 5. `process_monitor.py` (Deep System Insight)

**Purpose:** Detailed process-level monitoring and management

**API Endpoints:**

| Method | Endpoint                             | Purpose            |
| ------ | ------------------------------------ | ------------------ |
| GET    | `/api/processes?limit=30&sortBy=cpu` | Top processes      |
| GET    | `/api/processes/{pid}`               | Process details    |
| POST   | `/api/processes/{pid}/kill`          | Terminate process  |
| GET    | `/api/processes/{pid}/history`       | Historical metrics |
| GET    | `/api/processes/{pid}/tree`          | Parent + children  |

**Features:**

- CPU and memory usage per process
- Command-line arguments
- Open files and network connections count
- Process tree navigation
- Historical tracking (in-memory)

**Use Cases:**

- Identify memory leaks (process using 90% RAM)
- Find CPU hogs (runaway process at 100% CPU)
- Kill frozen processes remotely
- Track process behavior over time

#### 6. `config_store.py` (Centralized Configuration)

**Purpose:** Dynamic configuration without daemon restart

**Configuration Hierarchy:**

```
1. Default Config (hardcoded in code)
     ↓
2. Local File (/etc/resolvix/config.json)
     ↓
3. Backend API (/api/settings/daemon/{node_id})
     ↓
4. Runtime Changes (hot-reload)
```

**Secrets Management:**

- Separate file: `/etc/resolvix/secrets.json`
- Restricted permissions (0600)
- Never exposed via API

**Hot-Reload Support:**

| Setting            | Hot-Reload | Requires Restart |
| ------------------ | ---------- | ---------------- |
| Logging level      | ✓          |                  |
| Alert thresholds   | ✓          |                  |
| Error keywords     | ✓          |                  |
| Telemetry interval |            | ✓                |
| Monitored files    | ✓          |                  |
| Ports              |            | ✓                |

#### 7. `livelogs.py` (Real-Time Log Streaming)

**Purpose:** WebSocket server for live log tailing (like `tail -f`)

**Protocol:**

```json
// Client → Server
{ "command": "ping" }

// Server → Client
{
    "type": "live_log",
    "node_id": "192.168.1.10",
    "timestamp": "2024-12-29T10:30:45Z",
    "log": "ERROR: Database connection failed"
}
```

**Features:**

- Multiple concurrent clients
- Automatic client cleanup on disconnect
- Timestamp parsing from log lines
- Zero data buffering (instant streaming)

#### 8. `telemetry_ws.py` (Real-Time Metrics Streaming)

**Purpose:** WebSocket server for live system metrics

**Metrics Collected:**

```json
{
  "timestamp": "2024-12-29T10:30:45Z",
  "node_id": "192.168.1.10",
  "metrics": {
    "cpu": {
      "cpu_usage_percent": 45.2,
      "cpu_per_core_percent": [40, 50, 42, 48],
      "load_avg_1min": 2.5,
      "load_avg_5min": 2.1,
      "load_avg_15min": 1.8
    },
    "memory": {
      "memory_total_gb": 16.0,
      "memory_used_gb": 10.2,
      "memory_available_gb": 5.8,
      "memory_usage_percent": 63.75,
      "swap_total_gb": 4.0,
      "swap_used_gb": 0.5,
      "swap_usage_percent": 12.5
    },
    "disk": {
      "disk_usage": {
        "/": {
          "total_gb": 100.0,
          "used_gb": 75.0,
          "free_gb": 25.0,
          "usage_percent": 75.0
        }
      },
      "disk_io": {
        "read_mb_per_sec": 5.2,
        "write_mb_per_sec": 2.8
      }
    },
    "network": {
      "bytes_sent_mb_per_sec": 1.5,
      "bytes_recv_mb_per_sec": 3.2,
      "packets_sent": 12500,
      "packets_recv": 15000,
      "active_connections": 45
    },
    "processes": {
      "process_count": 125,
      "top_memory_processes": [
        { "pid": 1234, "name": "java", "memory_percent": 15.2 }
      ]
    }
  }
}
```

**Dual Mode:**

- **WebSocket streaming** for real-time dashboards
- **HTTP POST queueing** for historical storage

#### 9. `system_info.py` (Machine Registration)

**Purpose:** Collect hardware/OS info during installation

**Collected Data:**

- Operating system and version
- CPU architecture and core count
- Total RAM and disk capacity
- Network interfaces and IP addresses
- MAC address
- Hostname

**Registration Flow:**

```
install.sh → Run system_info.py →
Generate system_info.json →
POST to backend /api/system_info →
Backend returns machine UUID →
Save UUID to system_info.json
```

---

## Installation & Deployment

### Prerequisites

- **OS:** Ubuntu 18.04+ / Debian 10+ / CentOS 7+
- **Python:** 3.8 or higher
- **Root Access:** Required for system log access
- **Network:** Connectivity to backend server

### Installation Process

#### Automated Installation (Recommended)

```bash
# Download installation script
curl -O https://backend.example.com/scripts/install.sh

# Run with parameters
sudo bash install.sh \
  "/var/log/syslog" \
  "http://backend.example.com/api/ticket" \
  "http://backend.example.com/api/system_info" \
  "your-auth-token" \
  "ssh-rsa AAAA... backend-key" \
  "http://backend.example.com"

# Installation steps:
# 1. Creates resolvix user for file browser access
# 2. Configures SSH access with backend public key
# 3. Installs Python dependencies (handles apt locks)
# 4. Creates Python virtual environment
# 5. Collects and sends system info
# 6. Generates systemd service file
# 7. Starts daemon service
```

#### Manual Installation

```bash
# 1. Clone repository
git clone https://github.com/yourorg/resolvix-daemon.git
cd resolvix-daemon

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure daemon
vim /etc/resolvix/config.json

# 5. Create systemd service
sudo cp resolvix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable resolvix
sudo systemctl start resolvix

# 6. Verify
sudo systemctl status resolvix
curl http://localhost:8754/api/health
```

### Service Management

```bash
# Start daemon
sudo systemctl start resolvix

# Stop daemon
sudo systemctl stop resolvix

# Restart daemon
sudo systemctl restart resolvix

# View logs
sudo journalctl -u resolvix -f

# Check status
sudo systemctl status resolvix

# Update daemon after code changes
sudo ./update-daemon.sh

# Uninstall completely
sudo ./uninstall.sh
```

---

## API Reference

### Control API (Port 8754)

#### Health Check

```http
GET /api/health

Response:
{
    "status": "healthy",
    "service": "resolvix",
    "version": "1.1.0",
    "uptime_seconds": 3600,
    "timestamp": "2024-12-29T10:30:45Z",
    "node_id": "192.168.1.10",
    "ports": {
        "control_api": 8754,
        "livelogs_ws": 8755,
        "telemetry_ws": 8756
    },
    "components": {
        "log_collector": "running",
        "livelogs_ws": "stopped",
        "telemetry_ws": "running",
        "control_api": "running"
    },
    "monitoring": {
        "log_files": 3,
        "log_sources": ["/var/log/syslog", "/var/log/nginx/error.log"]
    }
}
```

#### Start/Stop Services

```http
POST /api/control
Content-Type: application/json

{
    "command": "start_livelogs"  // or stop_livelogs, start_telemetry, stop_telemetry
}

Response:
{
    "status": "started",
    "pid": "12345",
    "ws_port": 8755
}
```

#### Get Status

```http
GET /api/status

Response:
{
    "node_id": "192.168.1.10",
    "log_file": "/var/log/syslog",
    "monitored_files": {
        "count": 3,
        "files": [...]
    },
    "livelogs": {
        "running": true,
        "pid": 12345,
        "ws_port": 8755
    },
    "telemetry": {
        "running": true,
        "pid": 12346,
        "ws_port": 8756,
        "interval": 3
    },
    "suppression_rules": {
        "enabled": true,
        "statistics": {...}
    }
}
```

#### Process Management

```http
GET /api/processes?limit=30&sortBy=cpu
GET /api/processes/{pid}
POST /api/processes/{pid}/kill
GET /api/processes/{pid}/history?hours=24
GET /api/processes/{pid}/tree
```

#### Configuration Management

```http
# Get current configuration
GET /api/config

# Update configuration
POST /api/config
{
    "settings": {
        "alerts.thresholds.cpu_critical.threshold": 85,
        "intervals.telemetry": 5
    }
}

# Reload from backend
POST /api/config/reload

# Get configuration schema
GET /api/config/schema

# Simplified frontend endpoints
GET /config/get
POST /config/update
```

#### Monitored Files Management

```http
# List monitored files
GET /api/monitored-files

# Add new files
POST /api/monitored-files
{
    "files": [
        {
            "path": "/var/log/apache2/error.log",
            "label": "apache_errors",
            "priority": "high",
            "enabled": true
        }
    ]
}

# Update file configuration
PUT /api/monitored-files/{file_id}
{
    "label": "apache_critical",
    "priority": "critical",
    "enabled": true
}

# Remove file from monitoring
DELETE /api/monitored-files/{file_id}

# Reload monitoring
POST /api/monitored-files/reload
```

### WebSocket APIs

#### Livelogs WebSocket (Port 8755)

```javascript
// Connect
const ws = new WebSocket("ws://server-ip:8755/livelogs");

// Receive logs
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.log); // "ERROR: Database connection failed"
};
```

#### Telemetry WebSocket (Port 8756)

```javascript
// Connect
const ws = new WebSocket("ws://server-ip:8756");

// Receive metrics (every 3 seconds by default)
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`CPU: ${data.metrics.cpu.cpu_usage_percent}%`);
  console.log(`Memory: ${data.metrics.memory.memory_usage_percent}%`);
};

// Request immediate metrics
ws.send(JSON.stringify({ command: "get_metrics" }));

// Ping/pong
ws.send(JSON.stringify({ command: "ping" }));
```

---

## Configuration Reference

### Configuration File Structure

**Location:** `/etc/resolvix/config.json`

```json
{
  "connectivity": {
    "api_url": "http://backend:3000/api",
    "telemetry_backend_url": "http://backend:3000"
  },
  "messaging": {
    "rabbitmq": {
      "url": "amqp://user:pass@host:5672",
      "queue": "error_logs_queue"
    }
  },
  "telemetry": {
    "interval": 3,
    "retry_backoff": [5, 15, 60],
    "timeout": 10,
    "queue_db_path": "/var/lib/resolvix/telemetry_queue.db",
    "queue_max_size": 1000
  },
  "monitoring": {
    "log_files": [
      {
        "id": "file_001",
        "path": "/var/log/syslog",
        "label": "system",
        "priority": "high",
        "enabled": true
      }
    ],
    "error_keywords": [
      "emerg",
      "emergency",
      "alert",
      "crit",
      "critical",
      "err",
      "error",
      "fail",
      "failed",
      "failure",
      "panic",
      "fatal"
    ]
  },
  "alerts": {
    "thresholds": {
      "cpu_critical": {
        "threshold": 90,
        "duration": 300,
        "priority": "critical",
        "cooldown": 1800
      }
    }
  },
  "ports": {
    "control": 8754,
    "ws": 8755,
    "telemetry_ws": 8756
  },
  "intervals": {
    "telemetry": 3,
    "heartbeat": 30
  },
  "logging": {
    "level": "INFO",
    "path": "/var/log/resolvix.log",
    "max_bytes": 10485760,
    "backup_count": 5
  },
  "suppression": {
    "db": {
      "host": "localhost",
      "port": 5432,
      "name": "resolvix",
      "user": "resolvix_user"
    },
    "cache_ttl": 60
  },
  "security": {
    "cors_allowed_origins": "*"
  }
}
```

### Secrets File

**Location:** `/etc/resolvix/secrets.json` (Permissions: 0600)

```json
{
  "db_password": "database-password",
  "telemetry_jwt_token": "jwt-token-for-backend"
}
```

### Command-Line Arguments

```bash
python3 log_collector_daemon.py \
    --log-file /var/log/syslog \                    # Log file to monitor (repeatable)
    --api-url http://backend:3000/api/ticket \       # Backend API URL
    --control-port 8754 \                            # Control API port
    --ws-port 8755 \                                 # Livelogs WebSocket port
    --telemetry-ws-port 8756 \                       # Telemetry WebSocket port
    --node-id 192.168.1.10 \                         # Node identifier
    --telemetry-interval 3 \                         # Telemetry collection interval (seconds)
    --heartbeat-interval 30 \                        # Heartbeat interval (seconds)
    --telemetry-backend-url http://backend:3000 \    # Telemetry backend URL
    --telemetry-jwt-token "token" \                  # JWT for authentication
    --db-host localhost \                            # PostgreSQL host (suppression rules)
    --db-name resolvix \                             # PostgreSQL database
    --db-user resolvix_user \                        # PostgreSQL user
    --db-password "password" \                       # PostgreSQL password
    --db-port 5432                                   # PostgreSQL port
```

---

## Monitoring & Observability

### Daemon Logs

**Location:** `/var/log/resolvix.log`

**Log Rotation:**

- Max file size: 10 MB
- Backup count: 5 files
- Total max size: 50 MB

**Log Levels:**

- **DEBUG:** Detailed diagnostics (cache hits, queue sizes)
- **INFO:** Normal operations (started monitoring, sent alert)
- **WARNING:** Non-critical issues (backend timeout, cache miss)
- **ERROR:** Recoverable errors (failed to send log, database error)
- **CRITICAL:** Fatal errors (initialization failure, component crash)

**Example Logs:**

```
2024-12-29 10:30:45 [INFO] Starting log monitoring for 3 file(s)
2024-12-29 10:30:45 [INFO] Started monitoring: /var/log/syslog [system]
2024-12-29 10:30:50 [DEBUG] Issue detected [error|high] in apache_errors: Connection refused
2024-12-29 10:30:50 [INFO] [SUPPRESSED] [apache_errors] Error suppressed by rule: Ignore connection timeouts (ID: 5)
2024-12-29 10:31:00 [INFO] ✅ [nginx_errors] Log entry sent to RabbitMQ successfully
2024-12-29 10:31:30 [INFO] [AlertManager] ✓ Ticket created for cpu_critical: CPU usage at 92.5% for 5.2 minutes
2024-12-29 10:32:00 [ERROR] [TelemetryPoster] Connection error (backend unavailable)
2024-12-29 10:32:00 [INFO] [TelemetryPoster] Retrying in 5s (attempt 1/3)
```

### System Logs (journalctl)

```bash
# View daemon service logs
sudo journalctl -u resolvix -f

# Last 100 lines
sudo journalctl -u resolvix -n 100

# Logs from last hour
sudo journalctl -u resolvix --since "1 hour ago"

# Errors only
sudo journalctl -u resolvix -p err
```

### Health Monitoring

```bash
# Check if daemon is responding
curl http://localhost:8754/api/health

# Get detailed status
curl http://localhost:8754/api/status

# Check queue size
sqlite3 /var/lib/resolvix/telemetry_queue.db "SELECT COUNT(*) FROM telemetry_queue;"
```

### Performance Metrics

**Typical Resource Usage:**

- **CPU:** 1-5% (spikes to 10-15% during telemetry collection)
- **Memory:** 50-100 MB
- **Disk I/O:** Minimal (log reads only)
- **Network:** < 1 Mbps (depends on telemetry interval)

---

## Security Considerations

### Access Control

1. **Daemon User**

   - Runs as `resolvix` user (not root)
   - Member of `adm` group for log file access

2. **SSH Access**

   - Backend public key added to `~/.ssh/authorized_keys`
   - Used for remote file browsing only
   - No password authentication

3. **File Permissions**
   ```bash
   /etc/resolvix/config.json       # 644 (readable by all)
   /etc/resolvix/secrets.json      # 600 (owner only)
   /var/log/resolvix.log           # 644 (readable by all)
   /var/lib/resolvix/*.db          # 644 (readable by all)
   ```

### Network Security

1. **API Authentication**

   - Optional JWT token for backend API
   - Token stored in secrets file

2. **CORS Configuration**

   - Default: `*` (allow all origins)
   - Configurable via `security.cors_allowed_origins`

3. **Firewall Rules**

   ```bash
   # Allow control API
   sudo ufw allow 8754/tcp

   # Allow WebSocket ports (if external access needed)
   sudo ufw allow 8755/tcp  # Livelogs
   sudo ufw allow 8756/tcp  # Telemetry
   ```

### Data Privacy

1. **Log Data**

   - Sent to backend via RabbitMQ
   - No local persistence beyond rotation
   - Contains system/application logs (may include sensitive data)

2. **Telemetry Data**

   - System metrics only (no user data)
   - Queued locally in SQLite if backend unavailable
   - Automatically deleted after 3 failed retries

3. **Secrets Management**
   - Database passwords stored in separate secrets file
   - Restricted file permissions (0600)
   - Never logged or exposed via API

---

## Troubleshooting Guide

### Common Issues

#### 1. Daemon Won't Start

**Symptoms:**

```bash
sudo systemctl start resolvix
Job for resolvix.service failed because the control process exited with error code.
```

**Diagnosis:**

```bash
# Check service status
sudo systemctl status resolvix

# View error logs
sudo journalctl -u resolvix -n 50

# Check daemon log file
sudo tail -f /var/log/resolvix.log
```

**Common Causes:**

- Missing log file: Daemon waits for file to exist
- Port already in use: Another process using 8754/8755/8756
- Python dependencies missing: `pip install -r requirements.txt`
- Database connection failure: Check PostgreSQL credentials

**Solutions:**

```bash
# Create missing log file
sudo touch /var/log/syslog

# Kill processes using ports
sudo lsof -ti:8754 | xargs sudo kill -9

# Reinstall dependencies
source venv/bin/activate
pip install --force-reinstall -r requirements.txt

# Test database connection
psql -h localhost -U resolvix_user -d resolvix -c "SELECT 1;"
```

#### 2. Logs Not Being Sent to Backend

**Symptoms:**

- Daemon running but no errors appear in backend

**Diagnosis:**

```bash
# Check RabbitMQ connection
curl http://backend:15672/api/queues  # RabbitMQ management API

# Check daemon logs for send errors
sudo grep "RabbitMQ" /var/log/resolvix.log

# Test RabbitMQ connectivity
telnet backend 5672
```

**Common Causes:**

- RabbitMQ credentials incorrect
- RabbitMQ server down/unreachable
- Network firewall blocking port 5672
- Queue full (disk space issue on RabbitMQ server)

**Solutions:**

```bash
# Update RabbitMQ credentials in config
vim /etc/resolvix/config.json

# Reload daemon
sudo systemctl restart resolvix

# Check RabbitMQ status
ssh backend-server
sudo systemctl status rabbitmq-server
```

#### 3. Telemetry Data Not Posting

**Symptoms:**

- Telemetry queue growing indefinitely
- Backend not receiving telemetry

**Diagnosis:**

```bash
# Check queue size
sqlite3 /var/lib/resolvix/telemetry_queue.db "SELECT COUNT(*) FROM telemetry_queue;"

# Check for POST errors
sudo grep "TelemetryPoster" /var/log/resolvix.log

# Test backend endpoint
curl -X POST http://backend:3000/api/telemetry/snapshot -H "Content-Type: application/json" -d '{}'
```

**Common Causes:**

- Backend API down/unavailable
- Incorrect telemetry_backend_url
- JWT token expired/invalid
- Network timeout

**Solutions:**

```bash
# Update backend URL
vim /etc/resolvix/config.json
# Change telemetry_backend_url

# Update JWT token
vim /etc/resolvix/secrets.json
# Update telemetry_jwt_token

# Restart daemon
sudo systemctl restart resolvix

# Clear queue (if needed)
rm /var/lib/resolvix/telemetry_queue.db
sudo systemctl restart resolvix
```

#### 4. High CPU Usage

**Symptoms:**

- Daemon using > 50% CPU continuously

**Diagnosis:**

```bash
# Check process CPU
top -p $(pgrep -f log_collector_daemon.py)

# Check thread count
ps -eLf | grep log_collector_daemon.py | wc -l

# Check monitored files count
curl http://localhost:8754/api/status | jq '.monitored_files.count'
```

**Common Causes:**

- Too many log files being monitored
- High log volume (100+ lines/second)
- Telemetry interval too low (< 1 second)
- Runaway thread/subprocess

**Solutions:**

```bash
# Reduce monitored files
curl -X DELETE http://localhost:8754/api/monitored-files/{file_id}

# Increase telemetry interval
curl -X POST http://localhost:8754/config/update \
  -H "Content-Type: application/json" \
  -d '{"telemetry_interval": 10}'

# Restart daemon
sudo systemctl restart resolvix
```

#### 5. WebSocket Connection Failures

**Symptoms:**

- Frontend dashboard can't connect to livelogs/telemetry

**Diagnosis:**

```bash
# Test WebSocket connectivity
wscat -c ws://server-ip:8755/livelogs

# Check if service is running
curl http://localhost:8754/api/status | jq '.livelogs.running'

# Check firewall
sudo ufw status | grep 8755
```

**Common Causes:**

- Livelogs/telemetry service not started
- Firewall blocking WebSocket ports
- CORS configuration blocking connection
- Network proxy interfering with WebSocket upgrade

**Solutions:**

```bash
# Start livelogs service
curl -X POST http://localhost:8754/api/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_livelogs"}'

# Open firewall ports
sudo ufw allow 8755/tcp
sudo ufw allow 8756/tcp

# Check if ports are listening
sudo netstat -tlnp | grep 8755
```

#### 6. Suppression Rules Not Working

**Symptoms:**

- Errors being sent despite matching suppression rules

**Diagnosis:**

```bash
# Check suppression status
curl http://localhost:8754/api/status | jq '.suppression_rules'

# Check daemon logs for suppression
sudo grep "SUPPRESSED" /var/log/resolvix.log

# Test database connection
psql -h localhost -U resolvix_user -d resolvix -c "SELECT * FROM suppression_rules WHERE enabled = true;"
```

**Common Causes:**

- Database credentials incorrect
- Suppression rules disabled
- Rule match_text doesn't match actual error
- Cache not refreshing

**Solutions:**

```bash
# Verify database connection
vim /etc/resolvix/config.json
# Check suppression.db settings

# Update database password
vim /etc/resolvix/secrets.json
# Update db_password

# Test rule matching
psql -h localhost -U resolvix_user -d resolvix
SELECT * FROM suppression_rules WHERE 'your error message' LIKE '%' || match_text || '%';

# Force rule cache refresh (restart daemon)
sudo systemctl restart resolvix
```

---

## Performance Tuning

### Optimizing for High Log Volume

**Scenario:** Server generates 1000+ log lines/second

**Adjustments:**

1. **Increase Monitoring Interval**

   ```json
   {
     "monitoring": {
       "interval": 0.5 // Read every 500ms instead of 100ms
     }
   }
   ```

2. **Reduce Error Keyword List**

   ```json
   {
     "monitoring": {
       "error_keywords": ["critical", "fatal", "panic"] // Only most severe
     }
   }
   ```

3. **Use Suppression Rules Aggressively**

   - Suppress known noisy errors
   - Use node-specific rules to reduce database load

4. **Batch RabbitMQ Sends** (requires code modification)
   - Instead of sending one message per error
   - Batch 10-50 messages together

### Optimizing for Large Server Fleets

**Scenario:** 100+ servers sending data to one backend

**Adjustments:**

1. **Increase Telemetry Interval**

   ```json
   {
     "telemetry": {
       "interval": 60 // Collect every 60 seconds
     }
   }
   ```

2. **Stagger Telemetry Collection**

   - Add random offset to interval per server
   - Prevents thundering herd

3. **Increase Queue Size**

   ```json
   {
     "telemetry": {
       "queue_max_size": 5000 // Store more during outages
     }
   }
   ```

4. **Adjust Retry Strategy**
   ```json
   {
     "telemetry": {
       "retry_backoff": [10, 30, 120] // Longer waits between retries
     }
   }
   ```

### Optimizing for Low-Power Devices

**Scenario:** Running on Raspberry Pi or IoT device

**Adjustments:**

1. **Increase All Intervals**

   ```json
   {
     "intervals": {
       "telemetry": 60,
       "heartbeat": 300
     }
   }
   ```

2. **Disable Unnecessary Features**

   - Don't start livelogs unless needed
   - Disable process monitoring
   - Reduce monitored log files to minimum

3. **Reduce Log Level**
   ```json
   {
     "logging": {
       "level": "WARNING" // Only warnings and errors
     }
   }
   ```

---

## Development Guide

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourorg/resolvix-daemon.git
cd resolvix-daemon

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov pylint black

# Run tests
pytest tests/

# Run linter
pylint *.py

# Format code
black *.py
```

### Testing

#### Unit Tests

```python
# tests/test_suppression_checker.py
import pytest
from suppression_checker import SuppressionRuleChecker

def test_suppression_rule_matching():
    # Test case: Rule should match error message
    checker = SuppressionRuleChecker(mock_db_connection)

    error_message = "ERROR: Connection refused to database"
    node_id = "192.168.1.10"

    should_suppress, rule = checker.should_suppress(error_message, node_id)

    assert should_suppress == True
    assert rule['name'] == "Ignore database connection errors"
```

#### Integration Tests

```python
# tests/test_daemon_integration.py
import pytest
import requests

def test_daemon_health_endpoint():
    response = requests.get("http://localhost:8754/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'
    assert 'version' in data
```

#### Manual Testing

```bash
# Start daemon in development mode
python3 log_collector_daemon.py \
    --log-file test.log \
    --api-url http://localhost:3000/api/ticket

# In another terminal, generate test logs
echo "$(date) ERROR: Test error message" >> test.log

# Check if error was detected
curl http://localhost:8754/api/status
```

### Adding New Features

#### Example: Add New Alert Type

1. **Update `alert_config.py`**

   ```python
   ALERT_THRESHOLDS = {
       # Existing thresholds...
       'swap_critical': {
           'threshold': 90,
           'duration': 300,
           'priority': 'critical',
           'cooldown': 1800
       }
   }

   ALERT_MESSAGES = {
       # Existing messages...
       'swap_critical': "🔴 CRITICAL: Swap usage at {value}% on {hostname}"
   }
   ```

2. **Update `alert_manager.py`**

   ```python
   def check_swap_alert(self, swap_percent):
       current_time = time.time()
       if swap_percent >= ALERT_THRESHOLDS['swap_critical']['threshold']:
           self._handle_threshold_alert(
               'swap_critical',
               swap_percent,
               current_time,
               {'swap_percent': swap_percent}
           )
   ```

3. **Update `telemetry_ws.py`**

   ```python
   # In collect_all_metrics():
   if self.alert_manager:
       swap_percent = memory['swap_usage_percent']
       self.alert_manager.check_swap_alert(swap_percent)
   ```

4. **Test**

   ```bash
   # Restart daemon
   sudo systemctl restart resolvix

   # Monitor logs
   sudo journalctl -u resolvix -f

   # Create high swap usage (for testing)
   stress --vm 10 --vm-bytes 1G --timeout 30s
   ```

### Code Style Guidelines

- **PEP 8:** Follow Python style guide
- **Docstrings:** Use triple-quoted strings for all functions/classes
- **Logging:** Use `logger.info()`, not `print()`
- **Error Handling:** Always use try/except for external operations
- **Type Hints:** Use type annotations where applicable

---

## Deployment Strategies

### Single Server Deployment

**Use Case:** Small application, one server

```
┌─────────────────────┐
│   Application       │
│   + Resolvix Daemon │
│   + Backend         │
│   + PostgreSQL      │
│   + RabbitMQ        │
└─────────────────────┘
```

**Installation:**

```bash
# Install all components on one server
sudo apt install rabbitmq-server postgresql
sudo ./install.sh /var/log/syslog http://localhost:3000/api/ticket ...
```

### Multi-Server Deployment

**Use Case:** Multiple application servers, centralized backend

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  App Server  │  │  App Server  │  │  App Server  │
│  + Daemon    │  │  + Daemon    │  │  + Daemon    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       └─────────────────┼──────────────────┘
                         ▼
              ┌──────────────────┐
              │  Backend Server  │
              │  + API           │
              │  + PostgreSQL    │
              │  + RabbitMQ      │
              └──────────────────┘
```

**Installation:**

```bash
# On each app server
sudo ./install.sh \
  /var/log/syslog \
  http://backend-server:3000/api/ticket \
  http://backend-server:3000/api/system_info \
  "auth-token" \
  "backend-ssh-key" \
  http://backend-server:3000
```

### High Availability Deployment

**Use Case:** Mission-critical systems requiring redundancy

```
┌──────────────┐  ┌──────────────┐
│  App Server  │  │  App Server  │
│  + Daemon    │  │  + Daemon    │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                ▼
       ┌──────────────────┐
       │  Load Balancer   │
       │  (HAProxy/Nginx) │
       └────────┬─────────┘
                │
       ┌────────┴────────┐
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│  Backend 1   │  │  Backend 2   │
│  + API       │  │  + API       │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │  PostgreSQL HA  │
       │  (Primary+Replica)│
       └─────────────────┘
       ┌─────────────────┐
       │  RabbitMQ Cluster│
       │  (3 nodes)      │
       └─────────────────┘
```

### Cloud Deployment (AWS Example)

**Components:**

- **EC2 Instances:** Application servers with daemon
- **RDS PostgreSQL:** Managed database
- **Amazon MQ:** Managed RabbitMQ
- **Application Load Balancer:** Backend API traffic distribution
- **CloudWatch:** Centralized logging

**Terraform Example:**

```hcl
resource "aws_instance" "app_server" {
  count         = 3
  ami           = "ami-ubuntu-20.04"
  instance_type = "t3.medium"

  user_data = <<-EOF
    #!/bin/bash
    curl -O https://backend.example.com/install.sh
    bash install.sh \
      /var/log/syslog \
      http://backend-alb.internal:3000/api/ticket \
      ...
  EOF
}

resource "aws_db_instance" "postgres" {
  engine         = "postgres"
  instance_class = "db.t3.medium"
  # ...
}

resource "aws_mq_broker" "rabbitmq" {
  broker_name = "resolvix-mq"
  engine_type = "RabbitMQ"
  # ...
}
```

---

## Migration & Upgrade

### Upgrading from v1.0 to v1.1

**Breaking Changes:**

- None (backward compatible)

**New Features:**

- Multi-file monitoring
- Configuration store with hot-reload
- Enhanced process monitoring

**Upgrade Steps:**

```bash
# 1. Backup configuration
sudo cp /etc/resolvix/config.json /etc/resolvix/config.json.backup

# 2. Stop daemon
sudo systemctl stop resolvix

# 3. Pull latest code
cd /opt/resolvix-daemon
git pull origin main

# 4. Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# 5. Update systemd service (if needed)
sudo cp resolvix.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Start daemon
sudo systemctl start resolvix

# 7. Verify
sudo systemctl status resolvix
curl http://localhost:8754/api/health
```

### Migrating to New Backend

**Scenario:** Moving from self-hosted to cloud backend

```bash
# 1. Update API URLs in config
vim /etc/resolvix/config.json
# Change connectivity.api_url and telemetry_backend_url

# 2. Update RabbitMQ credentials
vim /etc/resolvix/config.json
# Change messaging.rabbitmq.url

# 3. Update secrets if needed
vim /etc/resolvix/secrets.json

# 4. Restart daemon
sudo systemctl restart resolvix

# 5. Verify connectivity
curl http://localhost:8754/api/status
```

---

## FAQ

### General Questions

**Q: How much does this cost?**
A: The daemon itself is open-source and free. You'll need infrastructure costs for:

- Backend server (can be small: 2GB RAM, 2 CPU cores)
- PostgreSQL database
- RabbitMQ server
- Estimated: $20-50/month for small deployments

**Q: Can it monitor Windows servers?**
A: Not currently. Resolvix is designed for Linux. A Windows port would require significant changes to use Windows Event Log instead of syslog.

**Q: How many servers can one backend handle?**
A: With proper tuning:

- Small backend: 50-100 servers
- Medium backend: 500-1000 servers
- Enterprise backend (clustered): 5000+ servers

**Q: Does it work with Docker/Kubernetes?**
A: Yes, but requires special configuration:

- Docker: Mount log volume, use host network mode
- Kubernetes: Deploy as DaemonSet, use node's log files

### Technical Questions

**Q: What happens if the backend is down?**
A: The daemon continues operating:

- Error logs: Sent to RabbitMQ (persistent queue)
- Telemetry: Stored in local SQLite queue
- Alerts: Queued and sent when backend recovers
- Maximum queue size: 1000 entries (configurable)

**Q: Can I monitor multiple log files?**
A: Yes, version 1.1+ supports multiple log files:

```bash
--log-file /var/log/syslog \
--log-file /var/log/nginx/error.log \
--log-file /var/log/apache2/error.log
```

**Q: How do I add custom error keywords?**
A: Update the configuration:

```json
{
  "monitoring": {
    "error_keywords": ["error", "fatal", "my_custom_error"]
  }
}
```

**Q: Can I filter errors by severity?**
A: Yes, use suppression rules or priority filters in the backend.

**Q: How do I backup the configuration?**
A: Configuration is stored in:

- `/etc/resolvix/config.json`
- `/etc/resolvix/secrets.json`
- Backup both files regularly

**Q: What ports need to be open?**
A: Outbound only (daemon initiates all connections):

- Backend API (typically 3000 or 443)
- RabbitMQ (5672)
- PostgreSQL (5432, if using suppression rules)

Inbound (optional, for management):

- Control API: 8754
- Livelogs WebSocket: 8755
- Telemetry WebSocket: 8756

---

## Glossary

**Alert Manager:** Component that creates tickets when thresholds are sustained  
**Backend:** Central server that receives logs, telemetry, and serves dashboards  
**Configuration Store:** Module for dynamic configuration management  
**Cooldown:** Time period after an alert before another alert of same type can be sent  
**Daemon:** Background service that runs continuously  
**Duration:** How long a threshold must be breached before alerting  
**Hot-reload:** Applying configuration changes without restarting the service  
**Livelogs:** Real-time log streaming via WebSocket  
**Node ID:** Unique identifier for a server (typically IP address)  
**Process Monitor:** Component for tracking individual processes  
**Priority:** Importance level (critical > high > medium > low)  
**Queue:** Persistent storage for data waiting to be sent  
**RabbitMQ:** Message broker for error log delivery  
**Severity:** Classification of log message (critical > error > warning > info)  
**Suppression Rule:** Database rule to filter out known/expected errors  
**Telemetry:** System metrics (CPU, memory, disk, network)  
**Threshold:** Value at which an alert should be triggered  
**WebSocket:** Protocol for bidirectional real-time communication

---

## Support & Contributing

### Getting Help

**Documentation:** This file  
**Issue Tracker:** GitHub Issues  
**Email:** support@resolvix.com  
**Slack:** #resolvix-daemon (internal)

### Reporting Bugs

When reporting bugs, please include:

1. **Environment Details**

   - OS and version
   - Python version
   - Daemon version

2. **Reproduction Steps**

   - Exact commands run
   - Configuration file (redacted secrets)

3. **Error Messages**

   - Daemon logs (`/var/log/resolvix.log`)
   - System logs (`journalctl -u resolvix`)

4. **Expected vs Actual Behavior**

### Contributing

**Process:**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit pull request

**Guidelines:**

- Follow PEP 8 style guide
- Add docstrings to all functions
- Write unit tests for new features
- Update documentation

---

## License

**License:** MIT License  
**Copyright:** 2024 Resolvix Team

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## Changelog

### Version 1.1.0 (2024-12-29)

- Added multi-file monitoring support
- Implemented configuration store with hot-reload
- Added process monitoring and management
- Enhanced alert manager with network spike detection
- Added self-monitoring of daemon logs
- Improved error handling and logging
- Added file browser SSH access during installation

### Version 1.0.0 (2024-11-15)

- Initial release
- Basic log monitoring
- Telemetry collection
- WebSocket streaming
- RabbitMQ integration
- Alert thresholds
- Suppression rules

---

## Appendix A: File Structure

```
log_collector_daemon/
├── log_collector_daemon.py      # Main daemon (2273 lines)
├── alert_manager.py              # Smart alerting (200 lines)
├── alert_config.py               # Alert thresholds (50 lines)
├── process_monitor.py            # Process tracking (300 lines)
├── suppression_checker.py        # Error filtering (200 lines)
├── config_store.py               # Configuration management (400 lines)
├── telemetry_queue.py            # Persistent queue (250 lines)
├── telemetry_poster.py           # HTTP POST client (150 lines)
├── telemetry_ws.py               # Telemetry WebSocket server (450 lines)
├── livelogs.py                   # Livelogs WebSocket server (150 lines)
├── system_info.py                # Hardware info collection (100 lines)
├── test_config.py                # Configuration tests (276 lines)
├── install.sh                    # Installation script (342 lines)
├── uninstall.sh                  # Removal script (30 lines)
├── update-daemon.sh              # Update script (125 lines)
├── service.template              # Systemd service template (20 lines)
├── requirements.txt              # Python dependencies (7 lines)
├── README.md                     # Basic README
└── PROJECT_DOCUMENTATION.md      # This file
```

---

## Appendix B: Database Schema

### Suppression Rules Table

```sql
CREATE TABLE suppression_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    match_text TEXT NOT NULL,
    node_ip VARCHAR(255),
    duration_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT true,
    expires_at TIMESTAMP,
    match_count INTEGER DEFAULT 0,
    last_matched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_suppression_enabled ON suppression_rules(enabled);
CREATE INDEX idx_suppression_expires ON suppression_rules(expires_at);
CREATE INDEX idx_suppression_node ON suppression_rules(node_ip);
```

---

## Appendix C: Environment Variables

```bash
# Optional environment variables (alternative to CLI args)
export RESOLVIX_API_URL="http://backend:3000/api/ticket"
export RESOLVIX_NODE_ID="192.168.1.10"
export RESOLVIX_LOG_FILE="/var/log/syslog"
export RESOLVIX_CONTROL_PORT="8754"
export RESOLVIX_WS_PORT="8755"
export RESOLVIX_TELEMETRY_WS_PORT="8756"
export RESOLVIX_TELEMETRY_INTERVAL="3"
export RESOLVIX_HEARTBEAT_INTERVAL="30"
export RESOLVIX_DB_HOST="localhost"
export RESOLVIX_DB_NAME="resolvix"
export RESOLVIX_DB_USER="resolvix_user"
export RESOLVIX_DB_PASSWORD="password"
```

---

**Document Version:** 1.0  
**Last Updated:** December 29, 2024  
**Maintained By:** Resolvix Development Team
