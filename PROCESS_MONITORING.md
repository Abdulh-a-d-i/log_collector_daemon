# Process-Level Monitoring - Complete Documentation

## Overview

The daemon now includes **detailed process-level monitoring** capabilities that allow you to track, analyze, and manage individual processes running on monitored systems.

---

## 🎯 Features

### **1. Top Process Tracking**
- Top 10 processes by CPU usage
- Top 10 processes by RAM usage
- Real-time metrics updated every collection cycle

### **2. Detailed Process Information**
- Process ID (PID), name, and owner
- CPU and memory usage
- Process status (running, sleeping, zombie, etc.)
- Start time and command line
- Thread count, open files, network connections
- Parent-child relationships (process tree)

### **3. Historical Data**
- Track process metrics over time
- Up to 1000 snapshots per process
- Calculate average and peak usage
- Configurable time windows (1-48 hours)

### **4. Process Management**
- Terminate processes remotely
- Graceful termination (SIGTERM) or force kill (SIGKILL)
- Automatic fallback to force kill if graceful fails
- Permission-based access control

### **5. Process Tree Visualization**
- View parent process
- View all child processes (recursive)
- Identify process relationships

---

## 📡 API Endpoints

### **GET /api/processes**
Get current top processes by CPU and RAM usage

**Response:**
```json
{
  "timestamp": "2025-12-11T10:30:45.123Z",
  "top_cpu": [
    {
      "pid": 1234,
      "name": "python3",
      "username": "root",
      "cpu_percent": 85.5,
      "memory_percent": 12.3,
      "memory_mb": 512.5,
      "status": "running",
      "started_at": "2025-12-11T08:00:00Z",
      "cmdline": "python3 /app/server.py",
      "num_threads": 4
    }
    // ... 9 more
  ],
  "top_ram": [
    // Similar structure, sorted by memory_percent
  ],
  "total_processes": 234,
  "zombie_count": 0
}
```

---

### **GET /api/processes/{pid}**
Get detailed information about a specific process

**Example:** `GET /api/processes/1234`

**Response:**
```json
{
  "success": true,
  "pid": 1234,
  "name": "python3",
  "username": "root",
  "cpu_percent": 85.5,
  "memory_percent": 12.3,
  "memory_mb": 512.5,
  "status": "running",
  "started_at": "2025-12-11T08:00:00Z",
  "cmdline": "python3 /app/server.py --port 8000",
  "cwd": "/app",
  "num_threads": 4,
  "num_fds": 25,
  "connections": 10,
  "open_files": 5,
  "parent_pid": 1,
  "nice": 0
}
```

**Error Response (404):**
```json
{
  "success": false,
  "error": "Process not found",
  "pid": 1234
}
```

---

### **POST /api/processes/{pid}/kill**
Terminate a process

**Example:** `POST /api/processes/1234/kill`

**Request Body:**
```json
{
  "force": false
}
```

**Parameters:**
- `force` (boolean): Use SIGKILL (true) or SIGTERM (false, default)

**Success Response (200):**
```json
{
  "success": true,
  "message": "Process python3 (PID: 1234) terminated successfully",
  "pid": 1234,
  "name": "python3",
  "forced": false
}
```

**Error Response (400):**
```json
{
  "success": false,
  "error": "Permission denied - insufficient privileges (may need root)",
  "pid": 1234
}
```

---

### **GET /api/processes/{pid}/history**
Get historical metrics for a process

**Example:** `GET /api/processes/1234/history?hours=24`

**Query Parameters:**
- `hours` (integer): Time window in hours (default: 24)

**Response:**
```json
{
  "pid": 1234,
  "hours": 24,
  "history": [
    {
      "timestamp": "2025-12-11T10:30:00Z",
      "cpu_percent": 85.5,
      "memory_percent": 12.3,
      "memory_mb": 512.5
    },
    {
      "timestamp": "2025-12-11T10:30:05Z",
      "cpu_percent": 82.1,
      "memory_percent": 12.4,
      "memory_mb": 513.2
    }
    // ... more snapshots
  ],
  "statistics": {
    "avg_cpu": 78.3,
    "max_cpu": 95.2,
    "avg_memory": 12.5,
    "max_memory": 13.8
  },
  "data_points": 288
}
```

---

### **GET /api/processes/{pid}/tree**
Get process tree (parent and children)

**Example:** `GET /api/processes/1234/tree`

**Response:**
```json
{
  "success": true,
  "pid": 1234,
  "name": "python3",
  "parent": {
    "pid": 1,
    "name": "systemd",
    "status": "sleeping"
  },
  "children": [
    {
      "pid": 1235,
      "name": "python3",
      "status": "running",
      "cpu_percent": 5.2,
      "memory_mb": 128.5
    },
    {
      "pid": 1236,
      "name": "python3",
      "status": "sleeping",
      "cpu_percent": 0.1,
      "memory_mb": 64.2
    }
  ],
  "total_children": 2
}
```

---

## 🔧 Testing

### **Test Process Monitoring**

```bash
# Get top processes
curl http://localhost:8754/api/processes | jq

# Get details for specific process
curl http://localhost:8754/api/processes/1234 | jq

# Get process history
curl http://localhost:8754/api/processes/1234/history?hours=6 | jq

# Get process tree
curl http://localhost:8754/api/processes/1234/tree | jq

# Kill a process (graceful)
curl -X POST http://localhost:8754/api/processes/1234/kill \
  -H "Content-Type: application/json" \
  -d '{"force": false}'

# Force kill a process
curl -X POST http://localhost:8754/api/processes/1234/kill \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

---

## 🎮 Usage Examples

### **Example 1: Find CPU Hogs**

```bash
# Get top CPU consumers
curl http://localhost:8754/api/processes | jq '.top_cpu[] | {pid, name, cpu_percent}'
```

**Output:**
```json
{
  "pid": 1234,
  "name": "python3",
  "cpu_percent": 95.5
}
{
  "pid": 5678,
  "name": "node",
  "cpu_percent": 82.3
}
```

---

### **Example 2: Kill Runaway Process**

```bash
# Step 1: Find the process
PID=$(curl -s http://localhost:8754/api/processes | jq -r '.top_cpu[0].pid')

# Step 2: Get details
curl http://localhost:8754/api/processes/$PID | jq

# Step 3: Kill it (graceful first)
curl -X POST http://localhost:8754/api/processes/$PID/kill \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

---

### **Example 3: Monitor Process Over Time**

```bash
# Get 6-hour history
curl "http://localhost:8754/api/processes/1234/history?hours=6" | jq '.statistics'
```

**Output:**
```json
{
  "avg_cpu": 78.3,
  "max_cpu": 95.2,
  "avg_memory": 12.5,
  "max_memory": 13.8
}
```

---

### **Example 4: Find Zombie Processes**

```bash
# Check for zombies
curl http://localhost:8754/api/processes | jq '.zombie_count'

# Find zombie processes
curl http://localhost:8754/api/processes | jq '.top_cpu[] | select(.status == "zombie")'
```

---

## 🔒 Security Considerations

### **Process Termination Permissions**

**Who can kill processes:**
- Daemon runs as configured user (typically root)
- Can only kill processes owned by that user
- System processes may require root privileges

**Best Practices:**
1. Run daemon as dedicated user with limited privileges
2. Use sudo/root only when necessary
3. Implement authentication on API endpoints (reverse proxy)
4. Log all process termination attempts

---

### **Access Control Recommendations**

```nginx
# Example: Nginx reverse proxy with auth
location /api/processes {
    auth_request /auth;
    proxy_pass http://localhost:8754;
}

location /api/processes/*/kill {
    # Extra protection for kill endpoint
    auth_request /admin_auth;
    proxy_pass http://localhost:8754;
}
```

---

## 📊 Data Storage

### **History Retention**

- **In-Memory Storage**: Up to 1000 snapshots per process
- **Automatic Cleanup**: Removes data older than 48 hours
- **Memory Usage**: ~100 KB per 1000 snapshots

### **Persistence (Optional)**

For long-term storage, integrate with time-series database:

```python
# Example: Store to InfluxDB
import influxdb

def store_process_metrics(metrics):
    for proc in metrics['top_cpu'] + metrics['top_ram']:
        point = {
            "measurement": "process_metrics",
            "tags": {
                "pid": proc['pid'],
                "name": proc['name'],
                "username": proc['username']
            },
            "fields": {
                "cpu_percent": proc['cpu_percent'],
                "memory_percent": proc['memory_percent'],
                "memory_mb": proc['memory_mb']
            }
        }
        influx_client.write_points([point])
```

---

## 🔍 Troubleshooting

### **Process Monitoring Not Available**

**Check:**
```bash
grep "ProcessMonitor" /var/log/resolvix.log
```

**Expected:**
```
[ProcessMonitor] Process monitoring enabled
```

**If disabled:**
- Ensure `process_monitor.py` exists in daemon directory
- Restart daemon: `sudo systemctl restart resolvix`

---

### **Permission Denied Errors**

**Issue:** Cannot kill certain processes

**Solution:**
```bash
# Option 1: Run daemon as root (not recommended for production)
sudo systemctl edit resolvix
# Add: User=root

# Option 2: Give specific capabilities (better)
sudo setcap 'cap_kill=+ep' /path/to/python
```

---

### **No History Available**

**Issue:** Process history returns empty

**Causes:**
- Process monitoring recently enabled
- Process hasn't been running long enough
- Process was cleaned up (>48 hours old)

**Solution:** Wait for data collection (snapshots every 3-60 seconds based on telemetry interval)

---

## 🎯 Integration with Frontend

### **React Component Example**

```javascript
// Fetch top processes
const fetchProcesses = async () => {
  const response = await fetch('http://agent-ip:8754/api/processes');
  const data = await response.json();
  setProcesses(data.top_cpu);
};

// Kill process
const killProcess = async (pid, force = false) => {
  const response = await fetch(`http://agent-ip:8754/api/processes/${pid}/kill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force })
  });
  const result = await response.json();
  if (result.success) {
    alert(`Process ${pid} terminated`);
  } else {
    alert(`Failed: ${result.error}`);
  }
};
```

---

## 📈 Performance Impact

### **Resource Usage**

| Metric | Impact |
|--------|--------|
| CPU | <1% additional |
| Memory | ~10-50 MB (depends on process count) |
| Network | Minimal (only when API called) |

### **Collection Frequency**

- Snapshots taken during telemetry collection
- Default: Every 3 seconds
- Configurable via `--telemetry-interval`

---

## 🚀 Future Enhancements

### **Planned Features**

1. **Process Alerts**: Alert when specific process exceeds thresholds
2. **Auto-restart**: Automatically restart crashed processes
3. **Resource Limits**: Set CPU/memory limits per process
4. **Persistent Storage**: Database integration for long-term history
5. **Process Groups**: Monitor process groups/cgroups
6. **Container Support**: Docker/Kubernetes process monitoring

---

## 📚 API Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/processes` | GET | Get top processes |
| `/api/processes/{pid}` | GET | Get process details |
| `/api/processes/{pid}/kill` | POST | Kill process |
| `/api/processes/{pid}/history` | GET | Get historical data |
| `/api/processes/{pid}/tree` | GET | Get process tree |

---

**Version**: 1.0.0  
**Last Updated**: December 11, 2025  
**Module**: process_monitor.py
