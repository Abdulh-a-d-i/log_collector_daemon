# Telemetry WebSocket Data Format

## Message Types

### 1. Welcome Message (First message after connection)
```typescript
{
  type: "connection",
  status: "connected",
  node_id: "192.168.100.27",
  interval: 60,
  timestamp: "2025-11-28T11:32:04.657416Z"
}
```

### 2. Telemetry Data (Sent every 60 seconds)
```typescript
{
  timestamp: "2025-11-28T11:32:04.657416Z",
  node_id: "192.168.100.27",
  metrics: {
    cpu: {
      cpu_usage_percent: 45.2,
      cpu_per_core_percent: [50.1, 40.3, 45.8, 44.9],
      load_avg_1min: 2.5,
      load_avg_5min: 2.1,
      load_avg_15min: 1.8
    },
    memory: {
      memory_total_gb: 16.0,
      memory_used_gb: 8.5,
      memory_available_gb: 7.5,
      memory_usage_percent: 53.1,
      swap_total_gb: 4.0,
      swap_used_gb: 0.5,
      swap_usage_percent: 12.5
    },
    disk: {
      disk_usage: {
        "/": {
          total_gb: 100.0,
          used_gb: 60.0,
          free_gb: 40.0,
          usage_percent: 60.0
        },
        "/home": {
          total_gb: 200.0,
          used_gb: 80.0,
          free_gb: 120.0,
          usage_percent: 40.0
        }
      },
      disk_io: {
        read_mb_per_sec: 5.2,
        write_mb_per_sec: 2.1
      }
    },
    network: {
      bytes_sent_mb_per_sec: 1.5,
      bytes_recv_mb_per_sec: 3.2,
      packets_sent: 1234567,
      packets_recv: 2345678,
      active_connections: 45
    },
    processes: {
      process_count: 234,
      top_memory_processes: [
        { pid: 1234, name: "chrome", memory_percent: 15.2 },
        { pid: 5678, name: "python3", memory_percent: 8.5 },
        { pid: 9012, name: "node", memory_percent: 6.3 },
        { pid: 3456, name: "mysql", memory_percent: 5.1 },
        { pid: 7890, name: "nginx", memory_percent: 2.8 }
      ]
    }
  }
}
```

## TypeScript Interface

```typescript
interface WelcomeMessage {
  type: "connection";
  status: "connected";
  node_id: string;
  interval: number;
  timestamp: string;
}

interface TelemetryData {
  timestamp: string;
  node_id: string;
  metrics: {
    cpu: {
      cpu_usage_percent: number;
      cpu_per_core_percent: number[];
      load_avg_1min: number;
      load_avg_5min: number;
      load_avg_15min: number;
    };
    memory: {
      memory_total_gb: number;
      memory_used_gb: number;
      memory_available_gb: number;
      memory_usage_percent: number;
      swap_total_gb: number;
      swap_used_gb: number;
      swap_usage_percent: number;
    };
    disk: {
      disk_usage: {
        [mountpoint: string]: {
          total_gb: number;
          used_gb: number;
          free_gb: number;
          usage_percent: number;
        };
      };
      disk_io: {
        read_mb_per_sec: number;
        write_mb_per_sec: number;
      };
    };
    network: {
      bytes_sent_mb_per_sec: number;
      bytes_recv_mb_per_sec: number;
      packets_sent: number;
      packets_recv: number;
      active_connections: number;
    };
    processes: {
      process_count: number;
      top_memory_processes: Array<{
        pid: number;
        name: string;
        memory_percent: number;
      }>;
    };
  };
}

type WebSocketMessage = WelcomeMessage | TelemetryData;
```

## Frontend Usage Example

```typescript
const ws = new WebSocket('ws://192.168.100.27:8756');

ws.onmessage = (event) => {
  const data: WebSocketMessage = JSON.parse(event.data);
  
  // Check if it's a welcome message
  if ('type' in data && data.type === 'connection') {
    console.log('Connected to node:', data.node_id);
    console.log('Telemetry interval:', data.interval, 'seconds');
    return;
  }
  
  // It's telemetry data
  if ('metrics' in data) {
    // CPU Usage
    const cpuUsage = data.metrics.cpu.cpu_usage_percent;
    
    // Memory Usage
    const memoryUsage = data.metrics.memory.memory_usage_percent;
    const memoryUsedGB = data.metrics.memory.memory_used_gb;
    const memoryTotalGB = data.metrics.memory.memory_total_gb;
    
    // Disk Usage (root partition)
    const rootDisk = data.metrics.disk.disk_usage["/"];
    const diskUsage = rootDisk?.usage_percent || 0;
    const diskUsedGB = rootDisk?.used_gb || 0;
    const diskTotalGB = rootDisk?.total_gb || 0;
    
    // Disk I/O
    const diskReadMB = data.metrics.disk.disk_io.read_mb_per_sec;
    const diskWriteMB = data.metrics.disk.disk_io.write_mb_per_sec;
    
    // Network
    const networkSentMB = data.metrics.network.bytes_sent_mb_per_sec;
    const networkRecvMB = data.metrics.network.bytes_recv_mb_per_sec;
    const activeConnections = data.metrics.network.active_connections;
    
    // Processes
    const processCount = data.metrics.processes.process_count;
    const topProcesses = data.metrics.processes.top_memory_processes;
    
    // Update your UI
    setTelemetryData({
      cpu: cpuUsage,
      memory: memoryUsage,
      disk: diskUsage,
      network: { sent: networkSentMB, recv: networkRecvMB },
      processes: processCount,
      timestamp: data.timestamp
    });
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('WebSocket closed:', event.code, event.reason);
};
```

## React Component Example

```typescript
import { useEffect, useState } from 'react';

interface TelemetryState {
  cpu: number;
  memory: number;
  disk: number;
  network: { sent: number; recv: number };
  processes: number;
  timestamp: string;
}

function NodeTelemetry({ nodeIp }: { nodeIp: string }) {
  const [telemetry, setTelemetry] = useState<TelemetryState | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(`ws://${nodeIp}:8756`);

    ws.onopen = () => {
      console.log('Connected to telemetry');
      setConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // Skip welcome message
      if (data.type === 'connection') return;

      // Process telemetry data
      if (data.metrics) {
        const rootDisk = data.metrics.disk.disk_usage["/"] || {};
        
        setTelemetry({
          cpu: data.metrics.cpu.cpu_usage_percent,
          memory: data.metrics.memory.memory_usage_percent,
          disk: rootDisk.usage_percent || 0,
          network: {
            sent: data.metrics.network.bytes_sent_mb_per_sec,
            recv: data.metrics.network.bytes_recv_mb_per_sec
          },
          processes: data.metrics.processes.process_count,
          timestamp: data.timestamp
        });
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      setConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [nodeIp]);

  if (!connected) return <div>Connecting...</div>;
  if (!telemetry) return <div>Waiting for data...</div>;

  return (
    <div>
      <h3>System Telemetry</h3>
      <p>CPU: {telemetry.cpu.toFixed(1)}%</p>
      <p>Memory: {telemetry.memory.toFixed(1)}%</p>
      <p>Disk: {telemetry.disk.toFixed(1)}%</p>
      <p>Network: ↑{telemetry.network.sent.toFixed(2)} MB/s ↓{telemetry.network.recv.toFixed(2)} MB/s</p>
      <p>Processes: {telemetry.processes}</p>
      <p>Last Update: {new Date(telemetry.timestamp).toLocaleTimeString()}</p>
    </div>
  );
}
```

## Common Mistakes to Avoid

❌ **Wrong:**
```typescript
data.usage  // undefined
data.cpu    // undefined
data.memory // undefined
```

✅ **Correct:**
```typescript
data.metrics.cpu.cpu_usage_percent
data.metrics.memory.memory_usage_percent
data.metrics.disk.disk_usage["/"].usage_percent
```

## Notes

- First message is always a welcome message with `type: "connection"`
- Telemetry data is sent every 60 seconds (configurable)
- Disk usage is an object with mountpoints as keys (e.g., "/", "/home")
- Always check if disk mountpoint exists before accessing
- Network connections count may be 0 if running without root permissions
- Keep the WebSocket connection open to receive continuous updates
