# Resolvix

A comprehensive distributed log monitoring and telemetry collection system for Linux servers. This daemon monitors system logs in real-time, filters critical errors, streams live logs via WebSocket, and collects system telemetry metrics for centralized monitoring.

##  Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Systemd Service](#systemd-service)
- [Uninstallation](#uninstallation)
- [Troubleshooting](#troubleshooting)

##  Features

### Error Log Monitoring
- **Real-time log monitoring** - Continuously tails log files for error patterns
- **Intelligent filtering** - Detects errors, warnings, critical issues, and failures
- **Severity classification** - Automatically categorizes log entries (critical, failure, error, warn, info)
- **Timestamp parsing** - Handles multiple log timestamp formats (syslog, ISO8601, RFC3339)
- **Centralized reporting** - Sends filtered errors to central API endpoint

### Live Log Streaming
- **WebSocket server** - Streams logs in real-time to connected clients
- **On-demand activation** - Start/stop live streaming via control API
- **Multi-client support** - Multiple clients can connect simultaneously
- **Auto-reconnection** - Handles client disconnections gracefully

### System Telemetry
- **CPU metrics** - Usage percentage, per-core stats, load averages
- **Memory metrics** - RAM and swap usage statistics
- **Disk metrics** - Usage per partition, I/O rates (read/write MB/sec)
- **Network metrics** - Throughput, packet counts, errors, active connections
- **Process metrics** - Process count, top memory consumers
- **Configurable intervals** - Adjust collection frequency (default: 60 seconds)

### Control Interface
- **HTTP control API** - Start/stop live log streaming remotely
- **Health checks** - Monitor daemon status
- **On-demand telemetry** - Request current metrics via API

##  Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Resolvix                             │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Log Monitor    │  │ Telemetry    │  │ Control API     │ │
│  │ Thread         │  │ Collector    │  │ (Flask)         │ │
│  │                │  │ Thread       │  │                 │ │
│  │ - Tail logs    │  │ - CPU stats  │  │ - Start/stop    │ │
│  │ - Filter errors│  │ - Memory     │  │ - Health check  │ │
│  │ - Send to API  │  │ - Disk I/O   │  │ - Get telemetry │ │
│  │                │  │ - Network    │  │                 │ │
│  └────────────────┘  └──────────────┘  └─────────────────┘ │
│           │                  │                    │          │
└───────────┼──────────────────┼────────────────────┼──────────┘
            │                  │                    │
            ▼                  ▼                    ▼
    ┌──────────────┐  ┌──────────────┐    ┌──────────────┐
    │ Central API  │  │ Central API  │    │   Client     │
    │ /logs        │  │ /telemetry   │    │   Control    │
    └──────────────┘  └──────────────┘    └──────────────┘

         ┌──────────────────────────────────┐
         │     livelogs.py (subprocess)     │
         │                                  │
         │  WebSocket Server (port 8755)   │
         │  - Tail log file                │
         │  - Broadcast to clients         │
         │  - Real-time streaming          │
         └──────────────────────────────────┘
                        │
                        ▼
                ┌──────────────┐
                │  WebSocket   │
                │   Clients    │
                └──────────────┘
```

##  Requirements

### System Requirements
- Linux-based operating system
- Python 3.7 or higher
- Root or sudo access (for systemd service installation)

### Python Dependencies
```
flask>=2.0.0
flask-cors>=3.0.0
psutil>=5.8.0
requests>=2.25.0
websockets>=10.0
```

##  Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/resolvix.git
cd resolvix
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Installation Script

The installation script will:
- Set up the virtual environment
- Install all dependencies
- Configure systemd service
- Start the daemon

```bash
chmod +x install.sh
sudo ./install.sh
```

**During installation, you'll be prompted for:**
- Log file path to monitor (e.g., `/var/log/syslog`)
- Central API URL (e.g., `http://your-api-server.com:5000`)
- Control port (default: 8754)
- WebSocket port (default: 8755)
- Telemetry interval in seconds (default: 60)

### 5. Verify Installation

```bash
# Check service status
sudo systemctl status resolvix

# Check daemon is responding
curl http://localhost:8754/health
```

Expected response:
```json
{
  "status": "ok",
  "node_id": "192.168.1.100",
  "telemetry_enabled": true
}
```

##  Configuration

### Command Line Options

```bash
python log_collector_daemon.py [OPTIONS]

Required Arguments:
  -l, --log-file PATH        Path to log file to monitor
  -a, --api-url URL          Central API URL for logs and telemetry

Optional Arguments:
  -p, --control-port PORT    Control API port (default: 8754)
  --ws-port PORT             WebSocket port for live logs (default: 8755)
  -n, --node-id ID           Node identifier (default: auto-detected IP)
  -t, --telemetry-interval N Telemetry interval in seconds (default: 60)
  --disable-telemetry        Disable telemetry collection
```

### Environment Variables

```bash
export LIVE_WS_PORT=8755
export CONTROL_PORT=8754
export TELEMETRY_INTERVAL=60
```

### Error Keywords

The daemon filters logs containing these keywords (case-insensitive):
- `emerg`, `emergency`
- `alert`
- `crit`, `critical`
- `err`, `error`
- `fail`, `failed`, `failure`
- `panic`
- `fatal`

##  Usage

### Manual Start

```bash
# With telemetry (default)
python log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://api.example.com:5000

# Without telemetry
python log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://api.example.com:5000 \
  --disable-telemetry

# Custom intervals and ports
python log_collector_daemon.py \
  --log-file /var/log/syslog \
  --api-url http://api.example.com:5000 \
  --control-port 9000 \
  --ws-port 9001 \
  --telemetry-interval 120
```

### Start Live Log Streaming

```bash
# Start WebSocket server for live logs
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_livelogs"}'
```

Response:
```json
{
  "status": "started",
  "pid": "12345"
}
```

### Stop Live Log Streaming

```bash
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "stop_livelogs"}'
```

### Get Current Telemetry

```bash
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "get_telemetry"}'
```

### Connect to Live Logs (WebSocket)

```javascript
// JavaScript/Node.js example
const ws = new WebSocket('ws://server-ip:8755/livelogs');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.timestamp}] ${data.log}`);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

```python
# Python example
import asyncio
import websockets
import json

async def stream_logs():
    uri = "ws://server-ip:8755/livelogs"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            print(f"[{data['timestamp']}] {data['log']}")

asyncio.run(stream_logs())
```

##  API Endpoints

### Central API (Your Server)

Your central server should expose these endpoints:

#### 1. POST `/logs`
Receives filtered error logs from nodes.

**Request Body:**
```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "system_ip": "192.168.1.100",
  "log_path": "/var/log/syslog",
  "application": "system",
  "log_line": "Error: Connection timeout",
  "severity": "error"
}
```

#### 2. POST `/telemetry`
Receives system telemetry metrics from nodes.

**Request Body:**
```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "node_id": "192.168.1.100",
  "metrics": {
    "cpu": {
      "cpu_usage_percent": 45.2,
      "cpu_per_core_percent": [50.1, 40.3, 45.8, 44.9],
      "load_avg_1min": 2.5,
      "load_avg_5min": 2.1,
      "load_avg_15min": 1.8
    },
    "memory": {
      "memory_total_gb": 16.0,
      "memory_used_gb": 8.5,
      "memory_available_gb": 7.5,
      "memory_usage_percent": 53.1
    },
    "disk": {
      "disk_usage": {
        "/": {
          "total_gb": 100.0,
          "used_gb": 60.0,
          "free_gb": 40.0,
          "usage_percent": 60.0
        }
      },
      "disk_io": {
        "read_mb_per_sec": 5.2,
        "write_mb_per_sec": 2.1
      }
    },
    "network": {
      "bytes_sent_mb_per_sec": 1.5,
      "bytes_recv_mb_per_sec": 3.2,
      "active_connections": 45
    },
    "processes": {
      "process_count": 234,
      "top_memory_processes": [
        {"pid": 1234, "name": "chrome", "memory_percent": 15.2}
      ]
    }
  }
}
```

### Control API (Daemon)

#### 1. GET `/health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "node_id": "192.168.1.100",
  "telemetry_enabled": true
}
```

#### 2. POST `/control`
Control daemon operations.

**Commands:**
- `start_livelogs` - Start live log streaming
- `stop_livelogs` - Stop live log streaming
- `get_telemetry` - Get current telemetry snapshot

##  Systemd Service

### Service Management

```bash
# Start service
sudo systemctl start resolvix

# Stop service
sudo systemctl stop resolvix

# Restart service
sudo systemctl restart resolvix

# Check status
sudo systemctl status resolvix

# Enable on boot
sudo systemctl enable resolvix

# Disable on boot
sudo systemctl disable resolvix

# View logs
sudo journalctl -u resolvix -f
```

### Service Template

The `service.template` file is used during installation:

```ini
[Unit]
Description=Resolvix
After=network.target

[Service]
User={USER}
WorkingDirectory={PROJECT_DIR}
ExecStart={PROJECT_DIR}/venv/bin/python {PROJECT_DIR}/log_collector_daemon.py \
  --log-file "{LOG_FILE_PATH}" \
  --api-url "{API_URL}" \
  --control-port {CONTROL_PORT} \
  --ws-port {WS_PORT} \
  --telemetry-interval {TELEMETRY_INTERVAL}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Manual Service Installation

If you prefer manual installation:

```bash
# 1. Copy service file
sudo cp resolvix.service /etc/systemd/system/

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable and start
sudo systemctl enable resolvix
sudo systemctl start resolvix
```

##  Uninstallation

### Using Uninstall Script

```bash
chmod +x uninstall.sh
sudo ./uninstall.sh
```

The script will:
1. Stop the systemd service
2. Disable the service
3. Remove the service file
4. Optionally remove the project directory

### Manual Uninstallation

```bash
# Stop and disable service
sudo systemctl stop resolvix
sudo systemctl disable resolvix

# Remove service file
sudo rm /etc/systemd/system/resolvix.service

# Reload systemd
sudo systemctl daemon-reload

# Remove project directory
rm -rf /path/to/resolvix
```

##  Troubleshooting

### Daemon Won't Start

**Check logs:**
```bash
sudo journalctl -u resolvix -n 50
```

**Common issues:**
- Log file doesn't exist or is inaccessible
- Port already in use
- Missing Python dependencies
- Permission issues

**Solutions:**
```bash
# Check if log file exists
ls -la /var/log/syslog

# Check if ports are available
sudo netstat -tulpn | grep -E '8754|8755'

# Verify Python dependencies
source venv/bin/activate
pip list
```

### WebSocket Connection Fails

**Check if livelogs is running:**
```bash
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_livelogs"}'
```

**Test WebSocket connection:**
```bash
# Install websocat
# Ubuntu/Debian: sudo apt install websocat
# macOS: brew install websocat

websocat ws://localhost:8755/livelogs
```

### High CPU Usage

The daemon is designed to be lightweight, but if you experience high CPU:

1. **Increase monitoring interval:**
```bash
# Edit service file to increase interval
--telemetry-interval 120  # Collect every 2 minutes
```

2. **Disable unnecessary features:**
```bash
--disable-telemetry  # Disable telemetry if not needed
```

3. **Check log file size:**
```bash
# Large log files can slow down tailing
ls -lh /var/log/syslog
```

### Telemetry Not Sending

**Check API connectivity:**
```bash
curl -X POST http://your-api-url/telemetry \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

**Check daemon logs for errors:**
```bash
sudo journalctl -u resolvix | grep telemetry
```

### Permission Denied Errors

Some metrics require elevated permissions:

```bash
# Run with sudo or adjust service user
sudo systemctl edit resolvix

# Add to override file:
[Service]
User=root
```

### API Connection Timeout

**Increase timeout in code:**
Edit `log_collector_daemon.py` and `telemetry_collector.py`:
```python
# Change timeout from 5 to 30 seconds
requests.post(url, json=data, timeout=30)
```

## Monitoring Dashboard

To visualize the collected data, you can create a dashboard using:

- **Grafana** - Time-series visualization
- **Elasticsearch + Kibana** - Log analysis
- **Custom React/Vue dashboard** - Using WebSocket for live logs

### Example Grafana Queries

```sql
-- CPU Usage Over Time
SELECT time, cpu_usage_percent 
FROM telemetry 
WHERE node_id = '192.168.1.100'

-- Memory Usage Trend
SELECT time, memory_usage_percent 
FROM telemetry 
WHERE node_id = '192.168.1.100'

-- Error Count by Severity
SELECT severity, COUNT(*) 
FROM logs 
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY severity
```

## 📝 Log Formats Supported

The daemon can parse multiple timestamp formats:

### Syslog Format
```
Oct 11 22:14:15 hostname process[123]: Error message
```

### ISO8601 / RFC3339
```
2024-01-15T10:30:45Z Error message
2024-01-15T10:30:45.123456Z Error message
```

### Custom Formats
Extend the `parse_timestamp()` function in `log_collector_daemon.py` to support additional formats.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request


##  Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review troubleshooting section

## Additional Resources

- [Python psutil documentation](https://psutil.readthedocs.io/)
- [Flask documentation](https://flask.palletsprojects.com/)
- [WebSocket protocol](https://datatracker.ietf.org/doc/html/rfc6455)
- [Systemd service management](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

**Version:** 1.0.0  
**Last Updated:** January 2025  
**Author:** Your Name  
**Repository:** https://github.com/yourusername/resolvix
