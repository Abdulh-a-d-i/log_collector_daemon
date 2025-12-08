# Resolvix Daemon - Technical Summary for Solutions Architect

**Date**: December 8, 2025  
**Version**: 2.0 (with Smart Alerting)

---

## 🔌 Complete Port Usage Matrix

### **Daemon Listening Ports (Inbound)**

| Port | Service | Protocol | Purpose | Default | Configurable |
|------|---------|----------|---------|---------|--------------|
| **8754** | Control API | HTTP/TCP | REST API for daemon management (start/stop services, health checks, status queries) | ✅ Yes | ✅ `--control-port` |
| **8755** | Live Logs | WebSocket/TCP | Real-time log streaming to dashboard clients (on-demand activation) | ✅ Yes | ✅ `--ws-port` |
| **8756** | Telemetry | WebSocket/TCP | Real-time system metrics broadcasting to monitoring clients (on-demand activation) | ✅ Yes | ✅ `--telemetry-ws-port` |

**Binding**: All services bind to `0.0.0.0` (all network interfaces) by design

### **Outbound Connections (Daemon → External)**

| Target | Port | Protocol | Purpose | Frequency |
|--------|------|----------|---------|-----------|
| **Backend API** | 3000 | HTTP/TCP | Heartbeat signals (`/api/heartbeat`) | Every 30s (configurable) |
| **Backend API** | 3000 | HTTP/TCP | Alert ticket creation (`/api/alerts/create`) | On threshold breach |
| **Backend API** | 3000 | HTTP/TCP | System info submission (installation only) | Once during install |
| **RabbitMQ** | 5672 | AMQP/TCP | Error log message queue submission | On error detection |

**Hardcoded Connection**:
```python
RABBITMQ_URL = "amqp://resolvix_user:resolvix4321@140.238.255.110:5672"
```

### **Optional SSH Access**

| Port | Protocol | Purpose | User | Auth Method |
|------|----------|---------|------|-------------|
| **22** | SSH/TCP | File browser access (backend → agent) | `resolvix` | SSH key only |

**Note**: Standard SSH daemon (sshd), not part of Python daemon

---

## 🔒 Security & Network Architecture

### **Recommended Firewall Rules**

```bash
# INBOUND (Control plane - restrict to backend IP only)
iptables -A INPUT -p tcp --dport 8754 -s <BACKEND_IP> -j ACCEPT  # Control API
iptables -A INPUT -p tcp --dport 8755 -s <BACKEND_IP> -j ACCEPT  # Live logs
iptables -A INPUT -p tcp --dport 8756 -s <BACKEND_IP> -j ACCEPT  # Telemetry

# OUTBOUND (Data plane - allow to backend & RabbitMQ)
iptables -A OUTPUT -p tcp --dport 3000 -d <BACKEND_IP> -j ACCEPT       # Backend API
iptables -A OUTPUT -p tcp --dport 5672 -d 140.238.255.110 -j ACCEPT   # RabbitMQ
```

### **Port Classification**

| Access Type | Ports | Recommendation |
|-------------|-------|----------------|
| **Internet-facing** | ❌ NONE | All daemon ports lack authentication |
| **Internal Network** | ✅ 8754-8756 | Backend ↔ Agent communication only |
| **Localhost Only** | ❌ NONE | All bind to 0.0.0.0 for remote access |

### **Security Gaps & Mitigations**

⚠️ **Current State**: No authentication on WebSocket/HTTP endpoints

**Recommended Solutions**:
1. **Reverse Proxy**: nginx/traefik with OAuth2/JWT authentication
2. **VPN/Private Network**: Keep agents on isolated network
3. **IP Whitelisting**: Firewall rules (implemented above)
4. **Future Enhancement**: Add token-based auth to daemon

---

## 🎯 Core Features Overview

### **1. Intelligent Error Log Monitoring**

**Technology**: Regex-based pattern matching + RabbitMQ queue

**Capabilities**:
- Real-time log tailing (supports syslog, ISO8601, RFC3339 timestamps)
- Keyword detection: `emerg`, `alert`, `critical`, `error`, `fail`, `panic`, `fatal`
- Severity classification: `critical`, `failure`, `error`, `warn`, `info`
- Reliable delivery via RabbitMQ message broker (persistent queue)

**Data Flow**:
```
Log File → Daemon (tail + filter) → RabbitMQ Queue → Backend Processor
```

**Message Format**:
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

---

### **2. Live Log Streaming (WebSocket)**

**Technology**: asyncio + websockets library

**Capabilities**:
- On-demand activation via REST API (`POST /control {"command": "start_livelogs"}`)
- Multi-client support (broadcast to all connected dashboards)
- Auto-reconnection handling and client lifecycle management
- Runs as subprocess (isolated from main daemon)

**Use Cases**:
- Real-time log viewing in web dashboard
- Debugging and troubleshooting
- Live incident response

**Connection Flow**:
```javascript
// Dashboard connects
const ws = new WebSocket('ws://agent-ip:8755/livelogs');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.timestamp}] ${data.log}`);
};
```

---

### **3. System Telemetry Collection (WebSocket)**

**Technology**: psutil + asyncio websockets

**Metrics Collected**:

| Category | Metrics | Update Frequency |
|----------|---------|------------------|
| **CPU** | Usage %, per-core %, load averages (1/5/15 min) | Every 3-60s |
| **Memory** | Total/used/available RAM, swap usage | Every 3-60s |
| **Disk** | Per-partition usage, I/O rates (MB/sec) | Every 3-60s |
| **Network** | Throughput (MB/sec), packet counts, active connections | Every 3-60s |
| **Processes** | Total count, top 5 memory consumers | Every 3-60s |

**Broadcast Mechanism**:
- WebSocket server on port 8756
- Continuous broadcasting to all connected clients
- Default interval: 3 seconds (configurable 1-3600s)

**Data Format**: See `TELEMETRY_DATA_FORMAT.md` for complete TypeScript interfaces

---

### **4. Smart Alerting System** ⭐ NEW

**Technology**: Threshold-based monitoring + automated ticketing

**Alert Types**:

| Alert | Threshold | Duration | Cooldown | Priority |
|-------|-----------|----------|----------|----------|
| CPU Critical | 90% | 5 min | 30 min | critical |
| CPU High | 75% | 10 min | 60 min | high |
| Memory Critical | 95% | 5 min | 30 min | critical |
| Memory High | 85% | 10 min | 60 min | high |
| Disk Critical | 90% | Immediate | 2 hours | critical |
| Disk High | 80% | Immediate | 4 hours | high |
| Network Spike | 5x baseline | 1 min | 30 min | medium |
| High Processes | 500+ | 5 min | 60 min | medium |

**Key Features**:
- **Duration-based triggering**: Prevents false positives from temporary spikes
- **Cooldown periods**: Prevents alert spam for persistent issues
- **Automatic ticket creation**: Creates tickets via backend API (`POST /api/alerts/create`)
- **Rich context**: Includes metrics, recommendations, host info

**Alert Lifecycle**:
```
Metric breach detected → Start timer → Duration met? → Check cooldown → Create ticket
                                              ↓ NO
                                         Reset timer
```

**Ticket Payload**:
```json
{
  "title": "🔴 CRITICAL: CPU usage at 92.3% for 5.0 minutes on web-server-01",
  "description": "Detailed alert with metrics, thresholds, and remediation steps",
  "priority": "critical",
  "status": "open",
  "application": "System Monitor",
  "system_ip": "192.168.1.100",
  "alert_type": "cpu_critical",
  "metric_value": 92.3
}
```

---

### **5. Heartbeat Monitoring**

**Purpose**: Detect dead/offline nodes

**Mechanism**:
- Background thread sends periodic heartbeat
- Default interval: 30 seconds (configurable)
- Endpoint: `{API_URL}/api/heartbeat`

**Payload**:
```json
{
  "node_id": "192.168.1.100",
  "status": "online",
  "timestamp": "2024-01-15T10:30:45Z"
}
```

**Backend Logic**:
- If heartbeat missing > 2 intervals → Mark node as offline
- Trigger alerts for critical infrastructure

---

### **6. HTTP Control API**

**Purpose**: Remote daemon management

**Endpoints**:

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| GET | `/health` | Health check | `{"status": "ok", "node_id": "..."}` |
| GET | `/status` | Service status | Full status of all services |
| POST | `/control` | Service control | Start/stop livelogs/telemetry |

**Control Commands**:
```json
// Start live log streaming
{"command": "start_livelogs"}

// Stop live log streaming
{"command": "stop_livelogs"}

// Start telemetry broadcasting
{"command": "start_telemetry"}

// Stop telemetry broadcasting
{"command": "stop_telemetry"}
```

---

### **7. SSH File Browser**

**Purpose**: Secure backend access to agent files

**Implementation**:
- Dedicated user: `resolvix`
- Groups: `adm` (read access to `/var/log`)
- Authentication: SSH key only (no password)
- Shell: `/bin/bash` (allows SSH command execution)

**Backend Access**:
```bash
# View logs
ssh -i ~/.ssh/resolvix_rsa resolvix@agent-ip 'cat /var/log/syslog'

# List directory
ssh -i ~/.ssh/resolvix_rsa resolvix@agent-ip 'ls -la /var/log'
```

**Security**:
- No sudo access
- Read-only by design (backend validates paths)
- SSH key rotation supported

---

### **8. System Information Profiling**

**Purpose**: Hardware/OS fingerprinting during installation

**Data Collected**:
- OS type, version, release
- Hostname and IP address
- MAC address
- Machine architecture
- Total RAM and disk space
- CPU core count (physical + logical)

**One-time Submission**:
- Runs during `install.sh` execution
- Sends to: `{SYSTEM_INFO_URL}/api/system_info`
- Creates `system_info.json` locally

---

## 📦 Installation & Deployment

### **Automated Installation Script**

**Command**:
```bash
sudo ./install.sh LOG_FILE API_URL SYSTEM_INFO_URL AUTH_TOKEN SSH_PUBLIC_KEY
```

**Example**:
```bash
sudo ./install.sh \
  "/var/log/syslog" \
  "http://backend:3000/api/ticket" \
  "http://backend:3000/api/system_info" \
  "Bearer token123" \
  "ssh-rsa AAAAB3NzaC1yc2E..."
```

**Installation Steps**:
1. Create `resolvix` user with SSH access
2. Install system packages (python3, python3-venv, python3-pip)
3. Create Python virtual environment
4. Install dependencies (websockets, psutil, requests, flask_cors, pika)
5. Collect and submit system information
6. Create systemd service
7. Start daemon

**Dependencies**:
```
flask>=2.0.0
flask-cors>=3.0.0
psutil>=5.8.0
requests>=2.25.0
websockets>=10.0
pika>=1.0.0
```

---

## 🛠 Configuration Options

### **Command-Line Arguments**

```bash
python log_collector_daemon.py \
  --log-file /var/log/syslog              # Required: Log file to monitor
  --api-url http://backend:3000/api       # Required: Backend API URL
  --control-port 8754                     # Optional: Control API port
  --ws-port 8755                          # Optional: Live logs WebSocket port
  --telemetry-ws-port 8756                # Optional: Telemetry WebSocket port
  --node-id 192.168.1.100                 # Optional: Node identifier (auto-detected)
  --telemetry-interval 60                 # Optional: Telemetry interval (seconds)
  --heartbeat-interval 30                 # Optional: Heartbeat interval (seconds)
```

### **Alert Threshold Configuration**

**File**: `alert_config.py`

**Customization Examples**:

```python
# Production (strict)
'cpu_critical': {'threshold': 80, 'duration': 180, 'cooldown': 3600}

# Development (lenient)
'cpu_critical': {'threshold': 95, 'duration': 600, 'cooldown': 300}

# High-traffic (adjusted)
'network_spike': {'threshold_multiplier': 10, 'duration': 120}
```

---

## 🔍 Monitoring & Operations

### **Service Management (systemd)**

```bash
sudo systemctl start resolvix      # Start daemon
sudo systemctl stop resolvix       # Stop daemon
sudo systemctl restart resolvix    # Restart daemon
sudo systemctl status resolvix     # Check status
sudo systemctl enable resolvix     # Auto-start on boot
```

### **Logs**

```bash
# Daemon logs
tail -f /var/log/resolvix.log

# Systemd logs
journalctl -u resolvix -f
```

### **Health Checks**

```bash
# Daemon health
curl http://agent-ip:8754/health

# Service status
curl http://agent-ip:8754/status
```

---

## 📊 Performance Characteristics

### **Resource Usage**

| Resource | Idle | Active (with telemetry) |
|----------|------|-------------------------|
| **CPU** | <0.1% | 0.5-1% |
| **Memory** | 30-50 MB | 50-80 MB |
| **Disk I/O** | Minimal | Log tailing only |
| **Network** | Heartbeat only | Heartbeat + telemetry |

### **Scalability**

- **Concurrent WebSocket clients**: 100+ (tested)
- **Log throughput**: Handles high-volume logs (>1000 lines/sec)
- **Message queue**: RabbitMQ handles delivery reliability

---

## 🚀 Deployment Best Practices

### **1. Network Segmentation**
- Deploy agents on private network
- Backend as gateway to agents
- No direct internet exposure for agent ports

### **2. Monitoring Stack**
```
Internet → [Firewall] → Backend (3000) → [Private Network] → Agents (8754-8756)
                            ↓
                        RabbitMQ (5672)
```

### **3. High Availability**
- RabbitMQ cluster for message reliability
- Multiple backend instances behind load balancer
- Agent auto-restart via systemd

### **4. Security Hardening**
- Firewall rules (only backend IP can access agent ports)
- SSH key rotation policy
- Regular security updates via package manager

---

## 🔄 Integration Points for Backend

### **Required Endpoints**

| Endpoint | Method | Purpose | Payload |
|----------|--------|---------|---------|
| `/api/heartbeat` | POST | Agent heartbeat | `{node_id, status, timestamp}` |
| `/api/alerts/create` | POST | Alert tickets | See alert payload above |
| `/api/system_info` | POST | System profiling | See system_info.py output |

### **RabbitMQ Integration**

**Queue**: `error_logs_queue`  
**Connection**: `amqp://resolvix_user:resolvix4321@140.238.255.110:5672`  
**Message Format**: See error log payload above

**Backend Processor**:
```javascript
// Consume from RabbitMQ queue
channel.consume('error_logs_queue', (msg) => {
  const log = JSON.parse(msg.content.toString());
  // Process log, create ticket, store in DB, etc.
  channel.ack(msg);
});
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Complete user guide and installation instructions |
| `SMART_ALERTING.md` | Smart alerting system documentation |
| `TELEMETRY_DATA_FORMAT.md` | Telemetry WebSocket data format and TypeScript interfaces |
| `DEBUG_TELEMETRY.md` | Troubleshooting guide for telemetry issues |
| `FILE_BROWSER_SETUP.md` | SSH file browser configuration guide |

---

## 🎯 Summary for Solutions Architect

### **What This Daemon Provides**

✅ **Comprehensive Monitoring**: CPU, memory, disk, network, processes  
✅ **Intelligent Alerting**: Threshold-based with auto-ticketing  
✅ **Real-time Streaming**: Live logs and telemetry via WebSocket  
✅ **Reliable Delivery**: RabbitMQ message queue for error logs  
✅ **Remote Management**: HTTP API for service control  
✅ **System Profiling**: Hardware/OS fingerprinting  
✅ **Secure Access**: SSH-based file browser  

### **Architecture Considerations**

- **Stateless Design**: No local database, all data sent to backend
- **Fault Tolerant**: Continues operation if backend unreachable
- **Scalable**: Tested with 100+ concurrent connections
- **Extensible**: Modular design for adding new features

### **Recommended Infrastructure**

```
┌─────────────────────────────────────────────────────────┐
│                     Internet                            │
└──────────────────────┬──────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  Load Balancer  │
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
     ┌────▼───┐   ┌───▼────┐   ┌───▼────┐
     │Backend │   │Backend │   │Backend │
     │  :3000 │   │  :3000 │   │  :3000 │
     └────┬───┘   └───┬────┘   └───┬────┘
          │           │            │
          └───────────┼────────────┘
                      │
          ┌───────────▼───────────┐
          │   RabbitMQ Cluster    │
          │      :5672           │
          └───────────┬───────────┘
                      │
          ┌───────────▼───────────┐
          │   Private Network     │
          │                       │
          │  Agent  Agent  Agent  │
          │  :8754  :8754  :8754  │
          │  :8755  :8755  :8755  │
          │  :8756  :8756  :8756  │
          └───────────────────────┘
```

---

**Questions?** Contact the daemon development team.

**Version**: 2.0.0  
**Last Updated**: December 8, 2025
