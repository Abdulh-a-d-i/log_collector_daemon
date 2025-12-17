# Telemetry Deployment Update - Simplified Auth

## Changes Made

### 1. Removed JWT Token Requirement ✅
- JWT token is now **optional** (not required)
- Suitable for automated machine deployments
- Telemetry works without authentication

### 2. Updated Service Template ✅
Service file now includes telemetry backend URL:
```bash
ExecStart=... --api-url "{API_URL}" --telemetry-backend-url "{TELEMETRY_BACKEND_URL}"
```

### 3. Updated Install Script ✅
`install.sh` now:
- Accepts `TELEMETRY_BACKEND_URL` as 6th parameter
- Auto-extracts base URL from API_URL if not provided
- Generates service file with `--telemetry-backend-url` parameter

## Quick Deploy to Production

### Option 1: Update Existing Installation

On your production server:

```bash
# 1. Pull latest code
cd /root/log_collector_daemon
git pull

# 2. Edit service file manually
sudo nano /etc/systemd/system/resolvix.service

# Add to ExecStart line:
--telemetry-backend-url "http://192.168.1.2:3000"

# Full line should look like:
ExecStart=/root/log_collector_daemon/venv/bin/python /root/log_collector_daemon/log_collector_daemon.py --log-file "/var/log/syslog" --api-url "http://192.168.1.2:3000/api/ticket" --telemetry-backend-url "http://192.168.1.2:3000"

# 3. Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart resolvix

# 4. Verify telemetry loop started
sudo journalctl -u resolvix -f | grep -i telemetry
# Should see: "[LogCollectorDaemon] Starting telemetry post loop..."
# Should see: "Processing queue batch..." and "Successfully posted..."
```

### Option 2: Fresh Installation

If reinstalling:
```bash
./install.sh /var/log/syslog "http://192.168.1.2:3000/api/ticket" "http://192.168.1.2:3000/api/system_info" "" "" "http://192.168.1.2:3000"
```

Parameters:
1. LOG_FILE: `/var/log/syslog`
2. API_URL: `http://192.168.1.2:3000/api/ticket`
3. SYSTEM_INFO_URL: `http://192.168.1.2:3000/api/system_info`
4. AUTH_TOKEN: (empty - not needed)
5. BACKEND_PUBLIC_KEY: (empty - optional)
6. TELEMETRY_BACKEND_URL: `http://192.168.1.2:3000`

## Verify Queue Processing

After restart, your 1000 queued entries should start processing:

```bash
# Check queue size (should decrease from 1000)
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_queue_size())"

# Monitor logs
sudo journalctl -u resolvix -f | grep -i telemetry

# Check queue stats
python3 -c "from telemetry_queue import TelemetryQueue; import json; print(json.dumps(TelemetryQueue().get_stats(), indent=2))"
```

## Expected Behavior

1. **Daemon starts**: Creates telemetry queue and poster instances
2. **POST loop starts**: Background thread processes queue every 60 seconds
3. **First batch**: Posts oldest 10 entries to backend
4. **Success**: Entries marked as sent, removed from queue
5. **Next batch**: Continues until queue is empty
6. **New snapshots**: Enqueued as they're generated (every 5 seconds)

## Troubleshooting

### If queue not decreasing:
```bash
# Check if POST loop started
sudo journalctl -u resolvix | grep "Starting telemetry post loop"

# Check for errors
sudo journalctl -u resolvix | grep -i "error\|fail" | tail -20

# Verify backend URL in service file
grep "ExecStart" /etc/systemd/system/resolvix.service
```

### If backend not receiving data:
```bash
# Test manual POST
curl -X POST http://192.168.1.2:3000/api/telemetry/snapshot \
  -H "Content-Type: application/json" \
  -d '{"machine_id":"test","timestamp":"2025-01-01T00:00:00Z"}'

# Check backend logs
# Verify /api/telemetry/snapshot endpoint is working
```

## Architecture Summary

```
┌─────────────────────────────────────────┐
│ Telemetry Collector (every 5s)         │
│  - Collects CPU, memory, disk, network │
└──────────────┬──────────────────────────┘
               │
               ├─► WebSocket Broadcast (real-time)
               │
               └─► Queue Enqueue (persistent)
                        │
                        ▼
           ┌────────────────────────┐
           │ SQLite Queue           │
           │ Max 1000 entries FIFO  │
           │ Retry tracking         │
           └────────┬───────────────┘
                    │
                    │ (every 60s)
                    ▼
           ┌────────────────────────┐
           │ POST Loop Thread       │
           │ Batch: 10 entries      │
           │ Exponential backoff    │
           └────────┬───────────────┘
                    │
                    │ HTTP POST
                    ▼
           ┌────────────────────────┐
           │ Backend API            │
           │ /api/telemetry/snapshot│
           │ → PostgreSQL           │
           └────────────────────────┘
```

## No JWT Token Needed

- ✅ Machines can self-register and send telemetry
- ✅ No manual token provisioning required
- ✅ Suitable for automated deployments
- ⚠️ Backend should implement machine authentication if needed (API keys, IP whitelisting, etc.)
