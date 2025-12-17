# 🚀 QUICK DEPLOYMENT REFERENCE

## Files to Deploy (4 files):

```
✅ telemetry_queue.py
✅ telemetry_poster.py
✅ log_collector_daemon.py
✅ telemetry_ws.py
```

## Quick Deploy Commands:

```bash
# 1. Copy files
scp telemetry_*.py log_collector_daemon.py telemetry_ws.py bitnami@NODE_IP:/home/bitnami/log-horizon-daemon/

# 2. Create directory
ssh bitnami@NODE_IP "sudo mkdir -p /var/lib/resolvix && sudo chown bitnami:bitnami /var/lib/resolvix"

# 3. Edit service (ADD THESE TWO LINES to ExecStart):
sudo nano /etc/systemd/system/resolvix-daemon.service
```

**Add to ExecStart:**

```
--telemetry-backend-url http://localhost:3000 \
--telemetry-jwt-token YOUR_JWT_TOKEN_HERE
```

```bash
# 4. Restart
sudo systemctl daemon-reload
sudo systemctl restart resolvix-daemon

# 5. Verify (should see telemetry messages)
sudo journalctl -u resolvix-daemon -f | grep -i telemetry
```

## Quick Checks:

```bash
# Queue stats
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_stats())"

# Queue size (should be 0-5)
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_queue_size())"

# Latest logs
sudo journalctl -u resolvix-daemon --since "2 minutes ago"

# Test backend
curl -X POST http://localhost:3000/api/telemetry/snapshot \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"test","cpu_percent":50,"memory_percent":60,"disk_percent":70}'
```

## Expected Log Output:

```
✅ [Daemon] Telemetry queue initialized
✅ [Daemon] Telemetry poster initialized (backend=http://localhost:3000)
✅ [Daemon] Telemetry POST thread started
✅ [TelemetryPoster] POST loop started
✅ [telemetry-ws] Telemetry queue initialized for HTTP POST
✅ [telemetry-ws] Enqueued snapshot for HTTP POST
✅ [TelemetryPoster] Processing 1 queued snapshots
✅ [TelemetryPoster] Successfully posted snapshot
```

## Rollback (if needed):

```bash
sudo systemctl stop resolvix-daemon
cp log_collector_daemon.py.backup log_collector_daemon.py
cp telemetry_ws.py.backup telemetry_ws.py
sudo systemctl start resolvix-daemon
```

---

**Full Documentation:** See `DEPLOYMENT_GUIDE.md`
