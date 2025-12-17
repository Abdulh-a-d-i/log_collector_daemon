# 🚀 TELEMETRY DEPLOYMENT GUIDE

**Last Updated:** December 17, 2025  
**Status:** Ready for Production Deployment

---

## 📦 WHAT TO DEPLOY

### Files to Copy to Server:
1. ✅ `telemetry_queue.py` - SQLite queue manager
2. ✅ `telemetry_poster.py` - HTTP POST client
3. ✅ `log_collector_daemon.py` - Updated main daemon
4. ✅ `telemetry_ws.py` - Updated WebSocket server

---

## 🔧 DEPLOYMENT STEPS

### 1. Copy Files to Server

```bash
# Replace with your server IP
NODE_IP="192.168.100.27"

scp telemetry_queue.py bitnami@$NODE_IP:/home/bitnami/log-horizon-daemon/
scp telemetry_poster.py bitnami@$NODE_IP:/home/bitnami/log-horizon-daemon/
scp log_collector_daemon.py bitnami@$NODE_IP:/home/bitnami/log-horizon-daemon/
scp telemetry_ws.py bitnami@$NODE_IP:/home/bitnami/log-horizon-daemon/
```

### 2. Create Queue Directory

```bash
ssh bitnami@$NODE_IP
sudo mkdir -p /var/lib/resolvix
sudo chown bitnami:bitnami /var/lib/resolvix
sudo chmod 755 /var/lib/resolvix
```

### 3. Update Systemd Service

Edit the service file:
```bash
sudo nano /etc/systemd/system/resolvix-daemon.service
```

**ADD** these two flags to the `ExecStart` line:
```ini
--telemetry-backend-url http://localhost:3000 \
--telemetry-jwt-token YOUR_JWT_TOKEN_HERE
```

**Example service file:**
```ini
[Unit]
Description=Resolvix Log Collector Daemon
After=network.target

[Service]
Type=simple
User=bitnami
WorkingDirectory=/home/bitnami/log-horizon-daemon
ExecStart=/usr/bin/python3 /home/bitnami/log-horizon-daemon/log_collector_daemon.py \
    --log-file /var/log/syslog \
    --api-url http://your-backend:5001 \
    --control-port 8754 \
    --ws-port 8755 \
    --telemetry-ws-port 8756 \
    --telemetry-interval 60 \
    --telemetry-backend-url http://localhost:3000 \
    --telemetry-jwt-token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Important parameters:**
- `--telemetry-backend-url`: Your backend URL (e.g., `http://localhost:3000`)
- `--telemetry-jwt-token`: Your JWT authentication token
- `--telemetry-interval`: Snapshot frequency in seconds (default: 60)

### 4. Reload and Restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart resolvix-daemon
```

### 5. Verify Daemon Started

```bash
sudo systemctl status resolvix-daemon
```

**Should show:** `Active: active (running)`

---

## ✅ VERIFICATION STEPS

### 1. Check Logs for Initialization

```bash
sudo journalctl -u resolvix-daemon -f
```

**Look for these lines:**
```
[Daemon] Telemetry queue initialized
[Daemon] Telemetry poster initialized (backend=http://localhost:3000)
[Daemon] Telemetry POST thread started
[TelemetryPoster] POST loop started
[telemetry-ws] Telemetry queue initialized for HTTP POST
[telemetry-ws] Enqueued snapshot for HTTP POST
```

### 2. Check Queue Database Created

```bash
ls -lh /var/lib/resolvix/telemetry_queue.db
```

**Should show:** File exists with size > 0

### 3. Check Queue Statistics

```bash
cd /home/bitnami/log-horizon-daemon
python3 -c "from telemetry_queue import TelemetryQueue; import json; q = TelemetryQueue(); print(json.dumps(q.get_stats(), indent=2))"
```

**Expected output:**
```json
{
  "total": 5,
  "by_retry_count": {
    "0": 5
  },
  "oldest_timestamp": "2025-12-17T10:00:00.000Z"
}
```

### 4. Monitor Real-Time Logs

```bash
sudo journalctl -u resolvix-daemon -f | grep -E 'Telemetry|POST'
```

**Should see every ~60 seconds:**
```
[telemetry-ws] Enqueued snapshot for HTTP POST
[TelemetryPoster] Processing 1 queued snapshots
[TelemetryPoster] Successfully posted snapshot
```

### 5. Verify Backend Receiving Data

On your backend server, check the database:

```sql
SELECT 
    node_id, 
    COUNT(*) as snapshots,
    MAX(timestamp) as latest_snapshot
FROM telemetry_history
WHERE timestamp >= NOW() - INTERVAL '10 minutes'
GROUP BY node_id;
```

Or check backend logs:
```bash
# If using pm2
pm2 logs | grep telemetry

# If using systemd
sudo journalctl -u your-backend-service -f | grep telemetry
```

---

## 🔍 TROUBLESHOOTING

### Issue: Daemon won't start

**Check logs:**
```bash
sudo journalctl -u resolvix-daemon -n 50
```

**Common fixes:**
- Missing Python modules: `pip3 install requests psutil`
- Wrong file permissions: `chmod +x /home/bitnami/log-horizon-daemon/log_collector_daemon.py`
- Syntax errors: `python3 -m py_compile log_collector_daemon.py`

### Issue: Queue growing but nothing being POSTed

**Check backend connectivity:**
```bash
curl -X POST http://localhost:3000/api/telemetry/snapshot \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"test","cpu_percent":50,"memory_percent":60,"disk_percent":70}'
```

**Common causes:**
- Backend not running: `systemctl status your-backend-service`
- Wrong backend URL in service file
- Invalid/expired JWT token
- Firewall blocking connection

### Issue: 401 Unauthorized errors

**Cause:** Invalid or expired JWT token

**Fix:**
1. Get a new JWT token from your auth endpoint
2. Update service file with new token
3. Restart daemon: `sudo systemctl restart resolvix-daemon`

### Issue: Queue too large

**Check size:**
```bash
python3 -c "from telemetry_queue import TelemetryQueue; print(f'Queue size: {TelemetryQueue().get_queue_size()}')"
```

**If too large (>100), clear it:**
```bash
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('/var/lib/resolvix/telemetry_queue.db')
conn.execute('DELETE FROM telemetry_queue')
conn.commit()
conn.close()
print("Queue cleared")
EOF
```

### Issue: WebSocket not working anymore

**Test WebSocket:**
```bash
wscat -c ws://localhost:8756
```

**Should see:** Metrics streaming every 60 seconds

**If broken:**
- Check if telemetry_ws.py process is running: `ps aux | grep telemetry_ws`
- Restart daemon: `sudo systemctl restart resolvix-daemon`

---

## 📊 MONITORING

### Commands to Run Regularly

**Check daemon status:**
```bash
sudo systemctl status resolvix-daemon
```

**Check queue size:**
```bash
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_queue_size())"
```

**Check latest logs:**
```bash
sudo journalctl -u resolvix-daemon --since "5 minutes ago" | tail -50
```

**Check POST activity:**
```bash
sudo journalctl -u resolvix-daemon --since "5 minutes ago" | grep -i "POST\|telemetry"
```

### What to Monitor:

✅ **Queue size** - Should be 0-5 normally  
✅ **POST success rate** - Check for "Successfully posted" messages  
✅ **Backend receiving data** - Verify in database  
✅ **WebSocket still working** - Test with wscat  
✅ **Disk space** - Queue database grows if backend down  

---

## 🎯 SUCCESS CRITERIA

After deployment, verify:

- [ ] Daemon starts without errors
- [ ] Queue database exists at `/var/lib/resolvix/telemetry_queue.db`
- [ ] Logs show telemetry initialization messages
- [ ] Logs show "Enqueued snapshot" every 60 seconds
- [ ] Logs show "Successfully posted snapshot" every ~60 seconds
- [ ] Queue size remains low (0-5)
- [ ] Backend database has new telemetry entries
- [ ] WebSocket still streams metrics
- [ ] Heartbeat still working

---

## 📝 EXAMPLE: COMPLETE DEPLOYMENT

```bash
# 1. Connect to server
ssh bitnami@192.168.100.27

# 2. Navigate to daemon directory
cd /home/bitnami/log-horizon-daemon

# 3. Backup existing files
cp log_collector_daemon.py log_collector_daemon.py.backup.$(date +%Y%m%d)
cp telemetry_ws.py telemetry_ws.py.backup.$(date +%Y%m%d)

# 4. Upload new files (run from local machine)
# scp telemetry_*.py log_collector_daemon.py telemetry_ws.py bitnami@192.168.100.27:/home/bitnami/log-horizon-daemon/

# 5. Create queue directory
sudo mkdir -p /var/lib/resolvix
sudo chown bitnami:bitnami /var/lib/resolvix

# 6. Edit service file
sudo nano /etc/systemd/system/resolvix-daemon.service
# Add: --telemetry-backend-url http://localhost:3000 --telemetry-jwt-token YOUR_TOKEN

# 7. Restart
sudo systemctl daemon-reload
sudo systemctl restart resolvix-daemon

# 8. Verify
sudo journalctl -u resolvix-daemon -f | grep -i telemetry
# Should see initialization messages

# 9. Check queue
python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_stats())"
# Should show entries

# 10. Wait 2 minutes, check again
# Queue should be processing and sending to backend
```

---

## 🔗 RELATED FILES

- **Implementation Guide:** `DAEMON_TELEMETRY_IMPLEMENTATION.md`
- **Implementation Summary:** `IMPLEMENTATION_COMPLETE.md`
- **Test Script:** `test_telemetry_post.py`
- **Deployment Script:** `deploy_telemetry.sh`

---

## 🆘 SUPPORT

If issues persist:

1. **Collect logs:** `sudo journalctl -u resolvix-daemon > daemon-logs.txt`
2. **Check queue:** `python3 -c "from telemetry_queue import TelemetryQueue; print(TelemetryQueue().get_stats())"`
3. **Test backend:** `curl http://localhost:3000/api/telemetry/snapshot`
4. **Check Python errors:** `python3 -c "from telemetry_queue import TelemetryQueue; from telemetry_poster import TelemetryPoster; print('OK')"`

---

**Deployment Status:** ✅ Ready  
**Estimated Time:** 10-15 minutes  
**Rollback Available:** Yes (restore .backup files)
