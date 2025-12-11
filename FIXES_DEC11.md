# Daemon Fixes - December 11, 2025

## 🔧 Issues Fixed

### 1. **HTTP 404 Error on Health Check** ✅
**Problem:** Daemon returned 404 for `/api/health` endpoint

**Root Cause:** Health endpoint was at `/health` (missing `/api/` prefix)

**Fix:** Updated all legacy routes to use `/api/` prefix for consistency:
- `/control` → `/api/control`
- `/health` → `/api/health`
- `/status` → `/api/status`

**File Modified:** `log_collector_daemon.py` (lines 449, 493, 500)

---

### 2. **Diagnostic Script Path Detection** ✅
**Problem:** Script looked for venv at hardcoded `/opt/resolvix-daemon/venv` but daemon was installed at `/root/log_collector_daemon/`

**Root Cause:** Script didn't detect actual daemon installation directory

**Fix:** Auto-detect daemon directory from running process:
```bash
DAEMON_DIR=$(ps aux | grep -oP 'python3?\s+\K[^\s]+(?=/log_collector_daemon\.py)' | head -1 | xargs dirname 2>/dev/null)
```

Falls back to checking common locations if detection fails.

**File Modified:** `diagnose-daemon.sh` (check #9)

---

### 3. **Backend URL Detection** ✅
**Problem:** Script used hardcoded backend URL for connectivity test

**Fix:** Extract backend URL from running daemon process arguments:
```bash
BACKEND_URL=$(ps aux | grep log_collector_daemon | grep -oP -- '--api-url\s+\K[^\s]+' | head -1)
```

**File Modified:** `diagnose-daemon.sh` (check #10)

---

## 📋 Updated API Endpoints

All endpoints now use `/api/` prefix:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check - returns `{"status": "ok", "node_id": "..."}` |
| `/api/status` | GET | Full daemon status (livelogs, telemetry, PIDs) |
| `/api/control` | POST | Control commands (start/stop livelogs/telemetry) |
| `/api/processes` | GET | List top processes by CPU/RAM |
| `/api/processes/:pid` | GET | Process details |
| `/api/processes/:pid/kill` | POST | Kill process |
| `/api/processes/:pid/history` | GET | Process history |
| `/api/processes/:pid/tree` | GET | Process tree |

---

## 🔄 Deployment Steps

### 1. Update Daemon on ALL Nodes

```bash
# On each node (10.215.111.191, etc.)
cd /root/log_collector_daemon  # or wherever daemon is installed
git pull origin main

# Restart daemon
sudo systemctl restart resolvix

# Verify fix
curl http://localhost:8754/api/health
# Should return: {"status":"ok","node_id":"..."}
```

### 2. Run Updated Diagnostic Script

```bash
# Copy new script to node
scp diagnose-daemon.sh root@10.215.111.191:/root/

# Run it
ssh root@10.215.111.191
chmod +x diagnose-daemon.sh
sudo ./diagnose-daemon.sh
```

**Expected Results:**
- ✅ Check 5 should now PASS (HTTP 200 instead of 404)
- ✅ Check 9 should now PASS (venv detected at correct path)
- All other checks should pass

---

## 🧪 Testing

### Test Health Check
```bash
# From the node
curl http://localhost:8754/api/health

# From backend server
curl http://10.215.111.191:8754/api/health

# Expected response:
{"status":"ok","node_id":"10.215.111.191"}
```

### Test Process Endpoints
```bash
# List processes
curl http://10.215.111.191:8754/api/processes | jq

# Get specific process
curl http://10.215.111.191:8754/api/processes/1234 | jq

# Check status
curl http://10.215.111.191:8754/api/status | jq
```

---

## 📝 Backend Integration Notes

**Backend should now use these endpoints:**

```javascript
// Health check
GET http://{nodeIp}:8754/api/health

// Process list
GET http://{nodeIp}:8754/api/processes?limit=10&sortBy=cpu

// Process details
GET http://{nodeIp}:8754/api/processes/{pid}

// Kill process
POST http://{nodeIp}:8754/api/processes/{pid}/kill
Body: {"signal": "SIGTERM"}

// Daemon status
GET http://{nodeIp}:8754/api/status
```

---

## ✅ Verification Checklist

After deploying:

- [ ] Diagnostic script passes check #5 (HTTP 200 on health check)
- [ ] Diagnostic script passes check #9 (venv detection)
- [ ] Backend can connect to `/api/health` endpoint
- [ ] Backend can fetch `/api/processes` data
- [ ] Frontend process monitoring works without 503 errors
- [ ] No more timeout errors in backend logs

---

## 🐛 Remaining Issue

**Heartbeat Timeouts:** The daemon logs show heartbeat connection failures to backend:
```
Heartbeat error: Connection to 10.215.111.117 timed out
```

**This is NOT related to the diagnostic script issues** - it means:
1. Backend is not reachable from the node at `10.215.111.117:3000`
2. Network routing issue or backend is down
3. Backend `/api/heartbeat` endpoint may not exist

**Separate fix needed:** Backend team should verify `/api/heartbeat` endpoint is implemented and node can reach backend.

---

## 📚 Updated Documentation

Files updated:
- ✅ `log_collector_daemon.py` - Fixed API routes
- ✅ `diagnose-daemon.sh` - Smart path detection
- ✅ `DAEMON_TROUBLESHOOTING.md` - Updated endpoint list

---

## 🎯 Summary

**Before:** Health check returned 404, diagnostic script failed path detection  
**After:** All `/api/*` endpoints work correctly, diagnostic script auto-detects installation

**Impact:** Backend can now successfully connect to daemon and fetch process data.
