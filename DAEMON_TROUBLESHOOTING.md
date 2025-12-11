# Daemon Connection Troubleshooting Guide

## 🔴 Current Issue
Backend timing out when connecting to daemon at `http://10.215.111.191:8754`

```
[PROCESSES] Error: timeout of 10000ms exceeded
```

---

## 📋 Quick Diagnostic Checklist

Run these commands **on the node** (`10.215.111.191`):

```bash
# 1. Check if daemon is running
sudo systemctl status resolvix

# 2. Check if port 8754 is listening
sudo ss -tulpn | grep 8754

# 3. Test daemon locally
curl http://localhost:8754/api/health

# 4. Check recent logs
sudo tail -n 100 /var/log/resolvix.log

# 5. Check for firewall blocking
sudo iptables -L -n | grep 8754
```

---

## 🔍 Step-by-Step Diagnostics

### Step 1: Verify Daemon Service Status

**On the node (10.215.111.191):**

```bash
# Check systemd service
sudo systemctl status resolvix

# Expected output:
# ● resolvix.service - Resolvix
#    Loaded: loaded (/etc/systemd/system/resolvix.service; enabled)
#    Active: active (running) since ...
```

**If service is not running:**

```bash
# Start the daemon
sudo systemctl start resolvix

# Enable auto-start on boot
sudo systemctl enable resolvix

# Check logs for errors
sudo journalctl -u resolvix -n 50 --no-pager
```

---

### Step 2: Verify Port Binding

**Check if daemon is listening on port 8754:**

```bash
# Method 1: Using ss
sudo ss -tulpn | grep 8754

# Expected output:
# tcp   LISTEN 0  128  0.0.0.0:8754  0.0.0.0:*  users:(("python3",pid=1234,...))

# Method 2: Using netstat
sudo netstat -tulpn | grep 8754

# Method 3: Using lsof
sudo lsof -i :8754
```

**If port is NOT listening:**
- Daemon is not running or crashed
- Check logs: `sudo tail -n 200 /var/log/resolvix.log`
- Check for port conflicts: `sudo lsof -i :8754`

---

### Step 3: Test Daemon Locally

**On the node:**

```bash
# Test health endpoint
curl -v http://localhost:8754/api/health

# Expected response:
# HTTP/1.1 200 OK
# {"status": "ok", "message": "Daemon is running"}

# Test processes endpoint (if implemented)
curl http://localhost:8754/api/processes | jq
```

**If curl fails:**
- Daemon crashed → Check logs
- Flask not binding properly → Check daemon configuration
- Python dependencies missing → Reinstall

---

### Step 4: Test Network Connectivity

**From your backend server (where Node.js backend runs):**

```powershell
# PowerShell: Test TCP connection
Test-NetConnection -ComputerName 10.215.111.191 -Port 8754

# Expected output:
# TcpTestSucceeded : True

# Try HTTP request
curl http://10.215.111.191:8754/api/health
```

**If connection times out:**
- Firewall blocking → See Step 5
- Wrong IP address → Verify node IP
- Network routing issue → Check VPN/network config

---

### Step 5: Check Firewall Rules

**On the node:**

```bash
# Check UFW (Ubuntu/Debian)
sudo ufw status | grep 8754

# Check iptables rules
sudo iptables -L INPUT -n -v | grep 8754

# Check if firewall is dropping packets
sudo iptables -L -n -v | grep 8754
```

**Open port 8754 if blocked:**

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 8754/tcp
sudo ufw reload

# CentOS/RHEL (firewalld)
sudo firewall-cmd --add-port=8754/tcp --permanent
sudo firewall-cmd --reload

# Direct iptables
sudo iptables -A INPUT -p tcp --dport 8754 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

---

### Step 6: Check Daemon Configuration

**Verify daemon is using port 8754:**

```bash
# Check service file
cat /etc/systemd/system/resolvix.service | grep ExecStart

# Should show:
# ExecStart=/path/to/venv/bin/python /path/to/log_collector_daemon.py ...

# Check if custom port is specified
ps aux | grep log_collector_daemon

# Check daemon logs for port binding
sudo grep -i "port\|8754" /var/log/resolvix.log
```

**Port configuration in daemon:**
- Default port: **8754** (hardcoded in `DEFAULT_CONTROL_PORT`)
- Can be overridden with `--control-port` flag
- Binds to `0.0.0.0` (all interfaces)

---

### Step 7: Test from Backend Server

**Create a test script on your backend server:**

```javascript
// test-daemon-connection.js
const axios = require('axios');

const testDaemonConnection = async (nodeIp) => {
  const daemonUrl = `http://${nodeIp}:8754/api/health`;
  
  console.log(`Testing connection to: ${daemonUrl}`);
  
  try {
    const response = await axios.get(daemonUrl, { timeout: 5000 });
    console.log('✅ SUCCESS:', response.status, response.data);
  } catch (error) {
    console.error('❌ FAILED:', error.code, error.message);
    
    if (error.code === 'ECONNREFUSED') {
      console.log('→ Daemon not running or port not open');
    } else if (error.code === 'ETIMEDOUT') {
      console.log('→ Firewall blocking or network issue');
    }
  }
};

testDaemonConnection('10.215.111.191');
```

---

## 🔧 Common Issues & Solutions

### Issue 1: Daemon Not Installed

**Symptom:** SSH to node, no daemon files found

**Solution:**
```bash
# Install daemon on the node
cd /opt
sudo git clone <daemon-repo> resolvix-daemon
cd resolvix-daemon
sudo ./install.sh /var/log/syslog http://your-backend:3000/api/ticket
```

---

### Issue 2: Daemon Service Not Created

**Symptom:** `systemctl status resolvix` → Unit not found

**Solution:**
```bash
cd /opt/resolvix-daemon

# Create service file
sudo bash -c 'cat > /etc/systemd/system/resolvix.service << EOF
[Unit]
Description=Resolvix
After=network.target

[Service]
User=root
WorkingDirectory=/opt/resolvix-daemon
ExecStart=/opt/resolvix-daemon/venv/bin/python /opt/resolvix-daemon/log_collector_daemon.py --log-file "/var/log/syslog"
Restart=always
RestartSec=10
StandardOutput=append:/var/log/resolvix.log
StandardError=append:/var/log/resolvix.log

[Install]
WantedBy=multi-user.target
EOF'

# Reload systemd and start
sudo systemctl daemon-reload
sudo systemctl enable resolvix
sudo systemctl start resolvix
```

---

### Issue 3: Python Dependencies Missing

**Symptom:** Daemon crashes immediately, logs show `ModuleNotFoundError`

**Solution:**
```bash
cd /opt/resolvix-daemon
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart resolvix
```

---

### Issue 4: Port Already in Use

**Symptom:** Daemon fails to start, logs show `Address already in use`

**Solution:**
```bash
# Find process using port 8754
sudo lsof -i :8754

# Kill the process
sudo kill -9 <PID>

# Or use a different port
sudo systemctl edit resolvix
# Add: ExecStart=/path/to/python /path/to/daemon.py --control-port 8755

sudo systemctl daemon-reload
sudo systemctl restart resolvix
```

---

### Issue 5: Daemon Running but Not Responding

**Symptom:** Port listening, but HTTP requests hang

**Solution:**
```bash
# Check if daemon is stuck
sudo strace -p $(pgrep -f log_collector_daemon) -e trace=network

# Restart daemon
sudo systemctl restart resolvix

# Check if Flask is running
ps aux | grep python | grep log_collector_daemon
```

---

## 🧪 Automated Diagnostic Script

**Save as `diagnose-daemon.sh` on the node:**

```bash
#!/bin/bash

echo "==================================="
echo "Resolvix Daemon Diagnostics"
echo "==================================="
echo ""

echo "1. Checking if daemon service exists..."
if systemctl list-unit-files | grep -q resolvix; then
    echo "   ✅ Service file exists"
else
    echo "   ❌ Service file NOT found"
fi

echo ""
echo "2. Checking daemon service status..."
systemctl is-active --quiet resolvix && echo "   ✅ Service is running" || echo "   ❌ Service is NOT running"

echo ""
echo "3. Checking if port 8754 is listening..."
if sudo ss -tulpn | grep -q 8754; then
    echo "   ✅ Port 8754 is listening"
    sudo ss -tulpn | grep 8754
else
    echo "   ❌ Port 8754 is NOT listening"
fi

echo ""
echo "4. Testing local daemon connection..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8754/api/health | grep -q 200; then
    echo "   ✅ Daemon responds to HTTP requests"
else
    echo "   ❌ Daemon does NOT respond"
fi

echo ""
echo "5. Checking recent daemon logs..."
sudo tail -n 10 /var/log/resolvix.log

echo ""
echo "6. Checking firewall rules for port 8754..."
if sudo iptables -L INPUT -n | grep -q 8754; then
    echo "   ✅ Firewall rule exists"
    sudo iptables -L INPUT -n | grep 8754
else
    echo "   ⚠️  No explicit firewall rule (may be allowed by default)"
fi

echo ""
echo "==================================="
echo "Diagnostics Complete"
echo "==================================="
```

**Run it:**
```bash
chmod +x diagnose-daemon.sh
sudo ./diagnose-daemon.sh
```

---

## 📊 Expected Daemon Endpoints

| Endpoint | Method | Purpose | Expected Response |
|----------|--------|---------|-------------------|
| `/api/health` | GET | Health check | `{"status": "ok", "node_id": "..."}` |
| `/api/status` | GET | Daemon status | `{node_id, log_file, livelogs, telemetry}` |
| `/api/control` | POST | Control daemon | `{"command": "start_livelogs/stop_livelogs"}` |
| `/api/processes` | GET | List top processes | `[{pid, name, cpu, memory...}]` |
| `/api/processes/:pid` | GET | Process details | `{pid, name, status...}` |
| `/api/processes/:pid/kill` | POST | Kill process | `{"success": true, "message": "..."}` |
| `/api/processes/:pid/history` | GET | Process history | `[{timestamp, cpu, memory...}]` |
| `/api/processes/:pid/tree` | GET | Process tree | `{parent, children: [...]}` |

---

## ✅ Verification Steps

Once daemon is running, verify **in this order:**

1. **On node:** `curl http://localhost:8754/api/health` → 200 OK
2. **From backend:** `Test-NetConnection -ComputerName 10.215.111.191 -Port 8754` → Success
3. **From backend:** `curl http://10.215.111.191:8754/api/health` → 200 OK
4. **Backend API:** Call `/api/nodes/{nodeId}/processes` → Should work
5. **Frontend:** Process monitoring loads without 503 errors

---

## 🆘 Still Not Working?

### Collect diagnostic info and share:

```bash
# Run this on the node
{
  echo "=== Service Status ==="
  systemctl status resolvix
  
  echo -e "\n=== Port Binding ==="
  sudo ss -tulpn | grep 8754
  
  echo -e "\n=== Daemon Logs (last 50 lines) ==="
  sudo tail -n 50 /var/log/resolvix.log
  
  echo -e "\n=== Process Info ==="
  ps aux | grep log_collector_daemon
  
  echo -e "\n=== Firewall Rules ==="
  sudo iptables -L INPUT -n -v | grep 8754
  
} > daemon-diagnostics.txt

cat daemon-diagnostics.txt
```

Send `daemon-diagnostics.txt` to the daemon developer.

---

## 🔐 Security Notes

- Port 8754 should only be accessible from your backend server IP
- Consider using firewall rules to restrict access:
  ```bash
  sudo iptables -A INPUT -p tcp -s <backend-ip> --dport 8754 -j ACCEPT
  sudo iptables -A INPUT -p tcp --dport 8754 -j DROP
  ```
- Use VPN or private network for daemon-backend communication
- Do NOT expose port 8754 to the public internet

---

## 📝 Installation Reference

If daemon is not installed on the node:

```bash
# SSH to node
ssh user@10.215.111.191

# Download daemon
cd /opt
sudo git clone <daemon-repo> resolvix-daemon

# Install
cd resolvix-daemon
sudo ./install.sh /var/log/syslog http://your-backend:3000/api/ticket

# Verify
sudo systemctl status resolvix
curl http://localhost:8754/api/health
```
