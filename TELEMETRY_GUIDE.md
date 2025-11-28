# Telemetry WebSocket Guide

## What Code Was Created

### `telemetry_ws.py`
A WebSocket server that streams live system telemetry data to connected clients.

**Components:**
1. **TelemetryCollector Class** - Collects system metrics using `psutil`:
   - CPU: usage %, per-core %, load averages
   - Memory: total, used, available, swap
   - Disk: usage per partition, I/O rates (MB/sec)
   - Network: throughput (MB/sec), packets, active connections
   - Processes: count, top 5 memory consumers

2. **TelemetryWebSocketServer Class** - WebSocket server that:
   - Listens on port 8756
   - Broadcasts metrics to all connected clients
   - Sends data at configured interval (default: 60 seconds)

## How to Start Live Telemetry

### Step 1: Start the Telemetry WebSocket Server

```bash
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "start_telemetry"}'
```

**Response:**
```json
{
  "status": "started",
  "pid": "12345",
  "ws_port": 8756,
  "interval": 60
}
```

### Step 2: Connect to the WebSocket

**WebSocket URL:** `ws://<node-ip>:8756`

## Client Examples

### JavaScript/Browser
```javascript
const ws = new WebSocket('ws://192.168.1.100:8756');

ws.onopen = () => {
  console.log('Connected to telemetry stream');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Telemetry:', data);
  
  // Access metrics
  console.log('CPU Usage:', data.metrics.cpu.cpu_usage_percent + '%');
  console.log('Memory Usage:', data.metrics.memory.memory_usage_percent + '%');
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

### Python
```python
import asyncio
import websockets
import json

async def stream_telemetry():
    uri = "ws://192.168.1.100:8756"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            print(f"Node: {data['node_id']}")
            print(f"CPU: {data['metrics']['cpu']['cpu_usage_percent']}%")
            print(f"Memory: {data['metrics']['memory']['memory_usage_percent']}%")
            print("---")

asyncio.run(stream_telemetry())
```

### Node.js
```javascript
const WebSocket = require('ws');

const ws = new WebSocket('ws://192.168.1.100:8756');

ws.on('open', () => {
  console.log('Connected to telemetry stream');
});

ws.on('message', (data) => {
  const telemetry = JSON.parse(data);
  console.log('CPU:', telemetry.metrics.cpu.cpu_usage_percent + '%');
  console.log('Memory:', telemetry.metrics.memory.memory_usage_percent + '%');
});
```

## Stop Telemetry Stream

```bash
curl -X POST http://localhost:8754/control \
  -H "Content-Type: application/json" \
  -d '{"command": "stop_telemetry"}'
```

## Check Status

```bash
curl http://localhost:8754/status
```

**Response:**
```json
{
  "node_id": "192.168.1.100",
  "log_file": "/var/log/syslog",
  "livelogs": {
    "running": false,
    "pid": null,
    "ws_port": 8755
  },
  "telemetry": {
    "running": true,
    "pid": 12345,
    "ws_port": 8756,
    "interval": 60
  }
}
```

## Sample Telemetry Data

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "node_id": "192.168.1.100",
  "metrics": {
    "cpu": {
      "cpu_usage_percent": 45.2,
      "cpu_per_core_percent": [50.1, 40.3, 45.8, 44.9],
      "load_avg_1min": 2.5,
      "load_avg_5min": 2.1,
      "load_avg_15min": 1.8
    },
    "memory": {
      "memory_total_gb": 16.0,
      "memory_used_gb": 8.5,
      "memory_available_gb": 7.5,
      "memory_usage_percent": 53.1,
      "swap_total_gb": 4.0,
      "swap_used_gb": 0.5,
      "swap_usage_percent": 12.5
    },
    "disk": {
      "disk_usage": {
        "/": {
          "total_gb": 100.0,
          "used_gb": 60.0,
          "free_gb": 40.0,
          "usage_percent": 60.0
        }
      },
      "disk_io": {
        "read_mb_per_sec": 5.2,
        "write_mb_per_sec": 2.1
      }
    },
    "network": {
      "bytes_sent_mb_per_sec": 1.5,
      "bytes_recv_mb_per_sec": 3.2,
      "packets_sent": 1234567,
      "packets_recv": 2345678,
      "active_connections": 45
    },
    "processes": {
      "process_count": 234,
      "top_memory_processes": [
        {"pid": 1234, "name": "chrome", "memory_percent": 15.2},
        {"pid": 5678, "name": "python3", "memory_percent": 8.5}
      ]
    }
  }
}
```

## Troubleshooting

### Telemetry not starting
```bash
# Check if telemetry_ws.py exists
ls -la telemetry_ws.py

# Make it executable
chmod +x telemetry_ws.py

# Check daemon logs
sudo journalctl -u resolvix -f
```

### Port already in use
```bash
# Check what's using port 8756
sudo netstat -tulpn | grep 8756

# Kill the process if needed
sudo kill <PID>
```
