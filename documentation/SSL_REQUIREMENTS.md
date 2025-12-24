# SSL & Domain Setup Requirements

## Current Unsecured Connections

### 1. **HTTP REST API Endpoints (Port 8754)**
- **Control/Config HTTP Server**: Daemon exposes REST API on `http://0.0.0.0:8754`
- **Endpoints**: `/api/health`, `/api/config`, `/api/processes`, `/api/alerts`
- **Backend connections**: Daemon POSTs telemetry to backend via HTTP
- **Heartbeat**: Daemon sends heartbeat to backend via HTTP POST

### 2. **WebSocket Servers**
- **Livelogs WebSocket** (Port 8755): `ws://0.0.0.0:8755/logs`
- **Telemetry WebSocket** (Port 8756): `ws://0.0.0.0:8756/telemetry`

### 3. **Backend Communication**
- **Telemetry POST**: `requests.post()` to backend URL (currently HTTP)
- **System info POST**: Installation sends system info to backend
- **Alert POST**: Daemon sends alerts to backend API

## Current Hardcoded URLs (in install.sh)
```
API_URL=http://13.235.113.192:3000/api/ticket
SYSTEM_INFO_URL=http://13.235.113.192:3000/api/system_info
```

## Required Changes for SSL/Domain

### Backend Domain
Replace `http://13.235.113.192:3000` with:
- **Domain**: `https://yourdomain.com`
- **API endpoints**: `/api/ticket`, `/api/system_info`

### Daemon Access
Option 1: Direct HTTPS/WSS (if exposing daemon directly)
- **HTTPS**: `https://node-domain.com:8754/api/*`
- **WSS**: `wss://node-domain.com:8755/logs` and `wss://node-domain.com:8756/telemetry`

Option 2: Backend proxy (recommended)
- Backend acts as proxy/gateway to daemon nodes
- No direct SSL on daemon needed
- Keep daemon HTTP/WS, secure backend-to-daemon via VPN/private network

## Action Items

1. **Provide to SSL/Domain Team**:
   - Backend URL to replace IP:port (must support HTTPS)
   - List of API endpoints: `/api/ticket`, `/api/system_info`, `/api/alerts`
   - WebSocket paths: `/logs`, `/telemetry`

2. **Code Updates Needed**:
   - Update `install.sh` with new HTTPS domain
   - Ensure `requests` calls use `https://` URLs
   - Update WebSocket clients to use `wss://` if exposing directly

3. **Certificate Requirements**:
   - Valid SSL certificate for backend domain
   - If exposing daemon: SSL cert for each node or wildcard cert for node subdomain

4. **Configuration**:
   - No code changes needed if only backend URL changes
   - Pass new URL via install: `./install.sh /var/log/syslog https://yourdomain.com/api/ticket`
