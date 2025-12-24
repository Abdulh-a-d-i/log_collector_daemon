# Architecture & Data Flow Documentation
**For Backend (Node.js) Developer**

---

## 1. Role of Backend: Gateway/Proxy Architecture

**Answer**: **Hybrid Approach** - Backend acts as a **data receiver/storage layer**, NOT a gateway/proxy for live data.

### Data Flow Pattern:

#### **Push Model** (Daemon → Backend):
- **Telemetry Data**: Daemon pushes metrics every 60s to `POST /api/telemetry/snapshot`
- **Alert Tickets**: Daemon creates tickets when thresholds breached → `POST /api/alerts/create`
- **System Info**: On installation, daemon sends system details → `POST /api/system_info`
- **Heartbeat**: Daemon sends periodic heartbeat → `POST /api/heartbeat`

#### **Direct Model** (Frontend → Daemon):
- **Live Logs**: Frontend connects directly to daemon WebSocket `ws://daemon-ip:8755/logs`
- **Live Telemetry**: Frontend connects directly to daemon WebSocket `ws://daemon-ip:8756/telemetry`
- **Control API**: Frontend can query daemon directly via HTTP `http://daemon-ip:8754/api/health`, `/api/config`, `/api/processes`

### Architecture Summary:
```
Frontend ──[WebSocket]──> Daemon (Live streaming)
    │                          │
    └───[HTTP REST]────────────┘ (Direct control/queries)
                               │
                               └──[HTTP POST]──> Backend (Historical data/alerts)
```

---

## 2. Daemon Communication Details

### A. **Backend ← Daemon Communication**

| Aspect | Details |
|--------|---------|
| **Protocol** | HTTP (POST requests) |
| **Direction** | Daemon **PUSHES** to Backend |
| **Endpoints** | `/api/telemetry/snapshot`, `/api/alerts/create`, `/api/heartbeat`, `/api/system_info` |
| **Frequency** | Telemetry: 60s, Heartbeat: configurable, Alerts: on threshold breach |
| **Implementation** | `requests.post()` with retry logic, exponential backoff |

**Code Reference**: [`telemetry_poster.py`](telemetry_poster.py#L63), [`alert_manager.py`](alert_manager.py#L198)

### B. **Frontend ↔ Daemon Communication**

| Aspect | Details |
|--------|---------|
| **Live Logs** | WebSocket (`ws://`) on port **8755**, path `/logs` |
| **Live Telemetry** | WebSocket (`ws://`) on port **8756**, path `/telemetry` |
| **Control API** | HTTP REST on port **8754** |
| **Direction** | Bi-directional WebSocket, Frontend-initiated HTTP requests |

**Code Reference**: [`livelogs.py`](livelogs.py#L110), [`telemetry_ws.py`](telemetry_ws.py)

### C. **Does Backend Poll Daemon?**

**No**. Backend is **passive**:
- Backend does NOT initiate connections to daemon
- Backend only **receives** data pushed by daemon
- Frontend connects **directly** to daemon for real-time streaming

---

## 3. Database & Storage

### **Information Needed from Backend Team**:

The daemon code does NOT manage databases. Backend is responsible for:

| Question | Expected Answer |
|----------|-----------------|
| **Database Type** | MongoDB / PostgreSQL / MySQL / SQLite? |
| **Location** | Same instance (localhost) OR separate DB server? |
| **Connection String** | If separate, provide host/port for architecture diagram |
| **Data Retention** | How long is telemetry/logs stored? |
| **Schema** | Tables/Collections: `telemetry`, `alerts`, `system_info`, `heartbeats`? |

### **Data Stored by Backend** (expected):
1. **Telemetry snapshots** - CPU, memory, disk, network metrics (pushed every 60s)
2. **Alert tickets** - System threshold breach records
3. **System info** - Node hardware/OS details (sent on installation)
4. **Heartbeat logs** - Node online/offline status

---

## 4. Ports Summary

### **Backend Ports**:
| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| **3000** | Node.js API | HTTP | Receive telemetry, alerts, system info |

**Question for Backend Team**: Are there any other ports? (Database port? Admin panel? Separate auth service?)

### **Daemon Ports** (per node):
| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| **8754** | Control API | HTTP | Health checks, config, process monitoring |
| **8755** | Live Logs | WebSocket | Stream log entries in real-time |
| **8756** | Telemetry Stream | WebSocket | Stream system metrics in real-time |

---

## 5. API Endpoints Reference

### **Backend Endpoints** (daemon → backend):
```
POST /api/telemetry/snapshot   # Daemon pushes metrics
POST /api/alerts/create         # Daemon creates alert tickets
POST /api/heartbeat             # Daemon sends keepalive
POST /api/system_info           # One-time system details on install
```

### **Daemon Endpoints** (frontend/backend → daemon):
```
GET  /api/health               # Health check
GET  /api/config               # Get current config
POST /api/config               # Update config
POST /api/config/reload        # Reload config
GET  /api/processes            # List monitored processes
GET  /api/alerts               # Get alert state
```

---

## 6. Production Architecture Diagram Data

### **Component Inventory**:

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Browser/App)                                     │
│  - Displays historical data from Backend                    │
│  - Connects directly to Daemon for live streaming           │
└─────────────────────────────────────────────────────────────┘
         │                                    │
         │ HTTP REST                          │ WebSocket (WS)
         │ (Historical queries)               │ (Live streaming)
         ▼                                    ▼
┌──────────────────────┐           ┌─────────────────────────┐
│  Backend (Node.js)   │◄──────────│  Daemon (Python)        │
│  Port: 3000          │  HTTP POST│  Ports: 8754/8755/8756  │
│  - REST API          │           │  - Log collection       │
│  - Database          │           │  - Telemetry gathering  │
│  - Alert storage     │           │  - Alert monitoring     │
└──────────────────────┘           └─────────────────────────┘
         │                                    │
         │                                    │
         ▼                                    ▼
┌──────────────────────┐           ┌─────────────────────────┐
│  Database            │           │  Log Files              │
│  Type: ???           │           │  /var/log/syslog        │
│  Location: ???       │           │  /var/log/application/* │
└──────────────────────┘           └─────────────────────────┘
```

### **Data Flow Directions**:
1. **Daemon → Backend**: Telemetry, alerts (HTTP POST, every 60s + on-demand)
2. **Frontend → Backend**: Historical queries (HTTP REST)
3. **Frontend → Daemon**: Live logs, live metrics (WebSocket, real-time)
4. **Backend → Daemon**: None (backend does not initiate connections)

---

## 7. Questions for Backend Developer

Please provide:

1. **Database details**:
   - Type (Mongo/Postgres/MySQL/SQLite)
   - Host and port (if separate server)
   - Schema/collections used

2. **Additional ports**:
   - Any ports besides 3000?
   - Database port?
   - Admin/monitoring tools?

3. **Authentication**:
   - JWT token required for daemon API calls?
   - How is token provisioned/renewed?

4. **Deployment topology**:
   - Backend on same instance as database?
   - Load balancer in front?
   - Separate auth service?

5. **Frontend hosting**:
   - Is frontend served by Node.js backend (port 3000)?
   - Or separate web server (nginx)?

---

**Generated**: December 22, 2025  
**Project**: Resolvix Log Collector Daemon
