#!/usr/bin/env python3
"""
Test script to immediately POST telemetry to backend
Run this to verify backend connectivity
"""

import requests
import psutil
import time
import socket
from datetime import datetime
import uuid

# CONFIGURATION - Update these values
BACKEND_URL = "http://localhost:3000/api/telemetry/snapshot"
JWT_TOKEN = None  # Set your JWT token here or leave None
NODE_ID = socket.gethostname()  # Or use a UUID

def collect_metrics():
    """Collect system metrics matching backend spec"""
    try:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net_io = psutil.net_io_counters()
        
        # Load average (Windows doesn't have this)
        try:
            load = psutil.getloadavg()
        except:
            load = (0, 0, 0)
        
        # Network connections count
        try:
            conn_count = len(psutil.net_connections())
        except:
            conn_count = 0
        
        return {
            "node_id": NODE_ID,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "cpu_percent": round(cpu, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_used_mb": int(memory.used / (1024 * 1024)),
            "memory_total_mb": int(memory.total / (1024 * 1024)),
            "disk_percent": round(disk.percent, 2),
            "disk_used_gb": round(disk.used / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "network_rx_bytes": net_io.bytes_recv,
            "network_tx_bytes": net_io.bytes_sent,
            "network_rx_rate_mbps": 0,  # Rate calculated in daemon
            "network_tx_rate_mbps": 0,
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "process_count": len(psutil.pids()),
            "active_connections": conn_count,
            "load_avg_1m": round(load[0], 2) if load else 0,
            "load_avg_5m": round(load[1], 2) if load else 0,
            "load_avg_15m": round(load[2], 2) if load else 0
        }
    except Exception as e:
        print(f"❌ Error collecting metrics: {e}")
        return None

def send_telemetry():
    """Send telemetry snapshot to backend"""
    print(f"\n{'='*60}")
    print(f"🔄 Collecting metrics...")
    
    metrics = collect_metrics()
    if not metrics:
        return False
    
    print(f"✅ Metrics collected:")
    print(f"   CPU: {metrics['cpu_percent']}%")
    print(f"   Memory: {metrics['memory_percent']}%")
    print(f"   Disk: {metrics['disk_percent']}%")
    print(f"   Processes: {metrics['process_count']}")
    
    print(f"\n📤 Sending to: {BACKEND_URL}")
    print(f"   Node ID: {metrics['node_id']}")
    print(f"   Timestamp: {metrics['timestamp']}")
    
    try:
        headers = {
            "Content-Type": "application/json"
        }
        if JWT_TOKEN:
            headers["Authorization"] = f"Bearer {JWT_TOKEN}"
        
        response = requests.post(
            BACKEND_URL,
            json=metrics,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✅ SUCCESS! Telemetry sent")
            print(f"   Status: {response.status_code}")
            try:
                print(f"   Response: {response.json()}")
            except:
                print(f"   Response: {response.text[:200]}")
            return True
        else:
            print(f"❌ FAILED! Status: {response.status_code}")
            print(f"   Error: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ CONNECTION ERROR: Backend not reachable")
        print(f"   Is the backend running at {BACKEND_URL}?")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ TIMEOUT: Request took longer than 5 seconds")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("TELEMETRY POST TEST")
    print("=" * 60)
    print(f"Backend: {BACKEND_URL}")
    print(f"JWT Token: {'Configured' if JWT_TOKEN else 'Not configured (may cause 401)'}")
    print(f"Node ID: {NODE_ID}")
    
    # Single test
    print("\n🧪 Test 1: Single POST")
    success = send_telemetry()
    
    if success:
        # Ask if want to run continuous
        print("\n" + "=" * 60)
        response = input("✅ Test successful! Run continuous loop? (y/n): ")
        
        if response.lower() == 'y':
            print("\n🔄 Starting continuous loop (every 60 seconds)")
            print("   Press Ctrl+C to stop\n")
            
            count = 0
            try:
                while True:
                    count += 1
                    print(f"\n📊 Snapshot #{count}")
                    send_telemetry()
                    print(f"\n⏳ Waiting 60 seconds...")
                    time.sleep(60)
            except KeyboardInterrupt:
                print(f"\n\n✋ Stopped by user after {count} snapshots")
    else:
        print("\n" + "=" * 60)
        print("❌ Test failed - check configuration:")
        print("   1. Is backend running at", BACKEND_URL, "?")
        print("   2. Is JWT_TOKEN configured correctly?")
        print("   3. Check firewall/network settings")
        print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Exiting...")
