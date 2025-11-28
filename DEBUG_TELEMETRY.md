# Debug Telemetry WebSocket Error 1011

## Step 1: Stop the Service
```bash
sudo systemctl stop resolvix
```

## Step 2: Upload Updated Files
Make sure these files are updated on the server:
- `telemetry_ws.py` (with extensive debug logging)
- `test_telemetry.sh` (test script)

```bash
# Make test script executable
chmod +x test_telemetry.sh
```

## Step 3: Run Manually with Debug Output
```bash
cd /root/log_collector_daemon
./test_telemetry.sh
```

Or run directly:
```bash
cd /root/log_collector_daemon
source venv/bin/activate
python3 telemetry_ws.py $(hostname -I | awk '{print $1}') 8756 --interval 60
```

## Step 4: Connect from Backend
While the manual server is running, connect from your backend and watch the output.

## What to Look For

### Success Output:
```
[telemetry-ws] Server started on ws://0.0.0.0:8756
[telemetry-ws] ===== NEW CONNECTION =====
[telemetry-ws] Client connected: ('192.168.56.1', 54321)
[telemetry-ws] Registering client...
[telemetry-ws] Client registered successfully
[telemetry-ws] Creating welcome message...
[telemetry-ws] Sending welcome message...
[telemetry-ws] Welcome message sent successfully
[telemetry-ws] Entering message loop...
[telemetry] Collecting CPU metrics...
[telemetry] CPU: OK
[telemetry] Collecting memory metrics...
[telemetry] Memory: OK
```

### Error Output (What We Need to See):
```
[telemetry-ws] ===== NEW CONNECTION =====
[telemetry-ws] Client connected: ('192.168.56.1', 54321)
[telemetry-ws] ERROR sending welcome: <ERROR MESSAGE HERE>
Traceback (most recent call last):
  ...
```

## Common Issues and Fixes

### Issue 1: Permission Error on net_connections()
```
PermissionError: [Errno 13] Permission denied
```
**Fix:** Run as root or the error is already caught and handled

### Issue 2: Missing psutil
```
ModuleNotFoundError: No module named 'psutil'
```
**Fix:**
```bash
source venv/bin/activate
pip install psutil websockets
```

### Issue 3: Port Already in Use
```
OSError: [Errno 98] Address already in use
```
**Fix:**
```bash
sudo netstat -tulpn | grep 8756
sudo kill <PID>
```

### Issue 4: CPU Metrics Hanging
If it hangs at "Collecting CPU metrics...", the issue is `psutil.cpu_percent(interval=1)` blocking.

**Fix:** Change interval to 0.1 or use non-blocking mode

## Step 5: Check Specific Metrics

Test each metric individually:
```bash
python3 << 'EOF'
import psutil
import traceback

print("Testing CPU...")
try:
    cpu = psutil.cpu_percent(interval=0.1)
    print(f"✅ CPU: {cpu}%")
except Exception as e:
    print(f"❌ CPU Error: {e}")
    traceback.print_exc()

print("\nTesting Memory...")
try:
    mem = psutil.virtual_memory()
    print(f"✅ Memory: {mem.percent}%")
except Exception as e:
    print(f"❌ Memory Error: {e}")
    traceback.print_exc()

print("\nTesting Disk...")
try:
    disk = psutil.disk_usage('/')
    print(f"✅ Disk: {disk.percent}%")
except Exception as e:
    print(f"❌ Disk Error: {e}")
    traceback.print_exc()

print("\nTesting Network...")
try:
    net = psutil.net_io_counters()
    print(f"✅ Network: {net.bytes_sent} bytes sent")
except Exception as e:
    print(f"❌ Network Error: {e}")
    traceback.print_exc()

print("\nTesting Connections...")
try:
    conn = psutil.net_connections()
    print(f"✅ Connections: {len(conn)}")
except Exception as e:
    print(f"⚠️ Connections Error (expected): {e}")

print("\nTesting Processes...")
try:
    procs = list(psutil.process_iter(['pid', 'name', 'memory_percent']))
    print(f"✅ Processes: {len(procs)}")
except Exception as e:
    print(f"❌ Process Error: {e}")
    traceback.print_exc()

print("\n✅ All tests complete")
EOF
```

## Step 6: Test WebSocket Connection

From another terminal:
```bash
# Install websocat if not installed
# Ubuntu: sudo apt install websocat
# Or use Python:

python3 << 'EOF'
import asyncio
import websockets

async def test():
    try:
        print("Connecting to ws://localhost:8756...")
        async with websockets.connect('ws://localhost:8756') as ws:
            print("✅ Connected!")
            msg = await ws.recv()
            print(f"Received: {msg}")
            
            # Keep connection alive
            await asyncio.sleep(5)
            print("✅ Connection stable")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
EOF
```

## Step 7: Send Me the Output

Copy and send the FULL output from Step 3 when your backend connects, especially:
1. The exact error message
2. The full traceback
3. Which metric collection step it fails at

## Quick Fix: Reduce CPU Interval

If CPU collection is the issue, edit `telemetry_ws.py`:

```python
def _collect_cpu(self):
    """Collect CPU metrics"""
    load_avg = psutil.getloadavg()
    return {
        "cpu_usage_percent": psutil.cpu_percent(interval=0.1),  # Changed from 1 to 0.1
        "cpu_per_core_percent": psutil.cpu_percent(interval=0.1, percpu=True),  # Changed
        "load_avg_1min": load_avg[0],
        "load_avg_5min": load_avg[1],
        "load_avg_15min": load_avg[2]
    }
```

## After Finding the Issue

Once we identify the problem from the debug output, we'll fix it and restart the service:
```bash
sudo systemctl start resolvix
sudo systemctl status resolvix
```
