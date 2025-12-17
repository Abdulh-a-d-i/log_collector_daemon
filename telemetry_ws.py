#!/usr/bin/env python3
# telemetry_ws.py
"""
WebSocket server for streaming telemetry data to connected clients.
Similar to livelogs.py but for system telemetry metrics.
"""
import asyncio
import websockets
import json
import signal
import sys
import argparse
from datetime import datetime
import psutil
import time
import socket
import uuid

# Import AlertManager with fallback
try:
    from alert_manager import AlertManager
    ALERT_MANAGER_AVAILABLE = True
except ImportError:
    ALERT_MANAGER_AVAILABLE = False
    print("[telemetry-ws] Warning: Alert manager not available - alerts disabled")

class TelemetryCollector:
    """Collects system telemetry metrics"""
    def __init__(self, api_url, node_id, interval=60):
        self.api_url = api_url
        self.node_id = node_id
        self.interval = interval
        self._last_net = None
        self._last_disk = None
        self._last_time = None
        self.daemon_ref = None  # Reference to daemon for queue access
        
        # Generate machine UUID from MAC address (consistent across restarts)
        self.machine_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
        
        # Initialize Alert Manager
        if ALERT_MANAGER_AVAILABLE and api_url:
            try:
                self.alert_manager = AlertManager(
                    backend_url=api_url,
                    hostname=socket.gethostname(),
                    ip_address=node_id
                )
                print("[telemetry-ws] Alert manager enabled")
            except Exception as e:
                print(f"[telemetry-ws] Failed to initialize alert manager: {e}")
                self.alert_manager = None
        else:
            self.alert_manager = None
        
    def collect_all_metrics(self):
        """Collect all system metrics"""
        try:
            cpu = self._collect_cpu()
            memory = self._collect_memory()
            disk = self._collect_disk()
            network = self._collect_network()
            processes = self._collect_processes()
            
            # Check alerts if manager is available
            if self.alert_manager:
                try:
                    self.alert_manager.check_cpu_alert(cpu['cpu_usage_percent'])
                    self.alert_manager.check_memory_alert(memory['memory_usage_percent'])
                    
                    # Check root disk partition
                    if '/' in disk['disk_usage']:
                        self.alert_manager.check_disk_alert(disk['disk_usage']['/']['usage_percent'])
                    
                    # Check process count
                    self.alert_manager.check_process_count(processes['process_count'])
                    
                    # Check network spikes
                    self.alert_manager.check_network_spike(
                        network['bytes_sent_mb_per_sec'],
                        network['bytes_recv_mb_per_sec']
                    )
                except Exception as e:
                    print(f"[telemetry-ws] Alert check error: {e}")
            
            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node_id": self.node_id,
                "metrics": {
                    "cpu": cpu,
                    "memory": memory,
                    "disk": disk,
                    "network": network,
                    "processes": processes
                }
            }
        except Exception as e:
            print(f"[telemetry] ERROR: {e}")
            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node_id": self.node_id,
                "error": str(e),
                "metrics": {}
            }
    
    def _collect_cpu(self):
        """Collect CPU metrics"""
        load_avg = psutil.getloadavg()
        return {
            "cpu_usage_percent": psutil.cpu_percent(interval=0.1),
            "cpu_per_core_percent": psutil.cpu_percent(interval=0.1, percpu=True),
            "load_avg_1min": load_avg[0],
            "load_avg_5min": load_avg[1],
            "load_avg_15min": load_avg[2]
        }
    
    def _collect_memory(self):
        """Collect memory metrics"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "memory_total_gb": round(mem.total / (1024**3), 2),
            "memory_used_gb": round(mem.used / (1024**3), 2),
            "memory_available_gb": round(mem.available / (1024**3), 2),
            "memory_usage_percent": mem.percent,
            "swap_total_gb": round(swap.total / (1024**3), 2),
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "swap_usage_percent": swap.percent
        }
    
    def _collect_disk(self):
        """Collect disk metrics"""
        disk_usage = {}
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_usage[partition.mountpoint] = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "usage_percent": usage.percent
                }
            except:
                pass
        
        # Calculate disk I/O rates
        disk_io = psutil.disk_io_counters()
        current_time = time.time()
        
        if self._last_disk and self._last_time:
            time_delta = current_time - self._last_time
            read_mb_per_sec = (disk_io.read_bytes - self._last_disk.read_bytes) / (1024**2) / time_delta
            write_mb_per_sec = (disk_io.write_bytes - self._last_disk.write_bytes) / (1024**2) / time_delta
        else:
            read_mb_per_sec = 0
            write_mb_per_sec = 0
        
        self._last_disk = disk_io
        self._last_time = current_time
        
        return {
            "disk_usage": disk_usage,
            "disk_io": {
                "read_mb_per_sec": round(read_mb_per_sec, 2),
                "write_mb_per_sec": round(write_mb_per_sec, 2)
            }
        }
    
    def _collect_network(self):
        """Collect network metrics"""
        try:
            net_io = psutil.net_io_counters()
            current_time = time.time()
            
            if self._last_net and self._last_time:
                time_delta = current_time - self._last_time
                bytes_sent_per_sec = (net_io.bytes_sent - self._last_net.bytes_sent) / (1024**2) / time_delta
                bytes_recv_per_sec = (net_io.bytes_recv - self._last_net.bytes_recv) / (1024**2) / time_delta
            else:
                bytes_sent_per_sec = 0
                bytes_recv_per_sec = 0
            
            self._last_net = net_io
            
            # Get connection count safely
            try:
                conn_count = len(psutil.net_connections())
            except (psutil.AccessDenied, PermissionError):
                conn_count = 0
            
            return {
                "bytes_sent_mb_per_sec": round(bytes_sent_per_sec, 2),
                "bytes_recv_mb_per_sec": round(bytes_recv_per_sec, 2),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "active_connections": conn_count
            }
        except Exception as e:
            print(f"[telemetry] Error collecting network metrics: {e}")
            return {
                "bytes_sent_mb_per_sec": 0,
                "bytes_recv_mb_per_sec": 0,
                "packets_sent": 0,
                "packets_recv": 0,
                "active_connections": 0
            }
    
    def _collect_processes(self):
        """Collect process metrics"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "memory_percent": round(proc.info['memory_percent'], 2)
                })
            except:
                pass
        
        # Sort by memory usage and get top 5
        top_processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:5]
        
        return {
            "process_count": len(processes),
            "top_memory_processes": top_processes
        }
    
    def _transform_to_api_format(self, ws_metrics):
        """
        Transform WebSocket format to API POST format.
        
        Args:
            ws_metrics: Metrics in WebSocket format
            
        Returns:
            dict: Metrics in API format
        """
        metrics = ws_metrics.get('metrics', {})
        
        # Get primary disk usage (usually "/")
        disk_usage = metrics.get('disk', {}).get('disk_usage', {})
        primary_disk = disk_usage.get('/', disk_usage.get(list(disk_usage.keys())[0] if disk_usage else '/'))
        
        # Calculate uptime
        try:
            uptime_seconds = int(time.time() - psutil.boot_time())
        except:
            uptime_seconds = 0
        
        return {
            'machine_id': self.machine_id,  # UUID format for backend
            'timestamp': ws_metrics.get('timestamp', datetime.utcnow().isoformat() + 'Z'),
            'cpu_percent': float(metrics.get('cpu', {}).get('cpu_usage_percent', 0)),
            'memory_percent': float(metrics.get('memory', {}).get('memory_usage_percent', 0)),
            'memory_used_mb': int(metrics.get('memory', {}).get('memory_used_gb', 0) * 1024),
            'memory_total_mb': int(metrics.get('memory', {}).get('memory_total_gb', 0) * 1024),
            'disk_percent': float(primary_disk.get('usage_percent', 0) if primary_disk else 0),
            'disk_used_gb': float(primary_disk.get('used_gb', 0) if primary_disk else 0),
            'disk_total_gb': float(primary_disk.get('total_gb', 0) if primary_disk else 0),
            'network_rx_bytes': int(metrics.get('network', {}).get('packets_recv', 0)),
            'network_tx_bytes': int(metrics.get('network', {}).get('packets_sent', 0)),
            'network_rx_rate_mbps': float(metrics.get('network', {}).get('bytes_recv_mb_per_sec', 0)),
            'network_tx_rate_mbps': float(metrics.get('network', {}).get('bytes_sent_mb_per_sec', 0)),
            'uptime_seconds': uptime_seconds,
            'process_count': int(metrics.get('processes', {}).get('process_count', 0)),
            'active_connections': int(metrics.get('network', {}).get('active_connections', 0)),
            'load_avg_1m': float(metrics.get('cpu', {}).get('load_avg_1min', 0)),
            'load_avg_5m': float(metrics.get('cpu', {}).get('load_avg_5min', 0)),
            'load_avg_15m': float(metrics.get('cpu', {}).get('load_avg_15min', 0))
        }


class TelemetryWebSocketServer:
    def __init__(self, node_id: str, port: int, interval: int = 60):
        self.node_id = node_id
        self.port = port
        self.interval = interval
        self.clients = set()
        self.collector = None
        self.running = False
        self.broadcast_task = None
        
    async def register(self, websocket):
        """Register a new client connection"""
        self.clients.add(websocket)
        print(f"[telemetry-ws] Client connected. Total clients: {len(self.clients)}")
        
    async def unregister(self, websocket):
        """Unregister a client connection"""
        self.clients.discard(websocket)
        print(f"[telemetry-ws] Client disconnected. Total clients: {len(self.clients)}")
        
    async def send_to_client(self, websocket, message):
        """Send message to a specific client with error handling"""
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            await self.unregister(websocket)
        except Exception as e:
            print(f"[telemetry-ws] Error sending to client: {e}")
            await self.unregister(websocket)
            
    async def broadcast_telemetry(self):
        """Continuously collect and broadcast telemetry to all connected clients"""
        print(f"[telemetry-ws] Broadcast started (interval: {self.interval}s)")
        
        while self.running:
            try:
                # Collect metrics
                metrics = self.collector.collect_all_metrics()
                message = json.dumps(metrics)
                
                # Broadcast to WebSocket clients
                if self.clients:
                    await asyncio.gather(
                        *[self.send_to_client(client, message) for client in self.clients],
                        return_exceptions=True
                    )
                
                # Enqueue for HTTP POST (new functionality)
                if hasattr(self, 'telemetry_queue') and self.telemetry_queue:
                    try:
                        # Transform to API format
                        api_payload = self.collector._transform_to_api_format(metrics)
                        
                        # Enqueue for HTTP POST
                        self.telemetry_queue.enqueue(api_payload)
                        print("[telemetry-ws] Enqueued snapshot for HTTP POST")
                    except Exception as e:
                        print(f"[telemetry-ws] Error enqueueing for HTTP POST: {e}")
                        # Don't fail - WebSocket should continue working
                
                # Wait for next interval
                await asyncio.sleep(self.interval)
                
            except Exception as e:
                print(f"[telemetry-ws] Broadcast error: {e}")
                await asyncio.sleep(5)
                
    async def handler(self, websocket):
        """Handle individual WebSocket connections"""
        print(f"[telemetry-ws] Client connected: {websocket.remote_address}")
        
        try:
            await self.register(websocket)
            
            # Send initial connection confirmation
            try:
                welcome = {
                    "type": "connection",
                    "status": "connected",
                    "node_id": self.node_id,
                    "interval": self.interval,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
                await websocket.send(json.dumps(welcome))
            except Exception as e:
                print(f"[telemetry-ws] Welcome error: {e}")
                await self.unregister(websocket)
                return
            
            # Keep connection alive and handle incoming messages
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        # Handle client commands
                        if data.get("command") == "get_metrics":
                            metrics = self.collector.collect_all_metrics()
                            await websocket.send(json.dumps(metrics))
                            
                        elif data.get("command") == "ping":
                            pong = {
                                "type": "pong",
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }
                            await websocket.send(json.dumps(pong))
                            
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        print(f"[telemetry-ws] Message error: {e}")
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                print(f"[telemetry-ws] Connection error: {e}")
                    
        except Exception as e:
            print(f"[telemetry-ws] Handler error: {e}")
        finally:
            await self.unregister(websocket)
            
    async def start_server(self):
        """Start the WebSocket server"""
        self.running = True
        
        # Initialize telemetry collector (without auto-sending to API)
        self.collector = TelemetryCollector(
            api_url="",  # No API URL needed for WS mode
            node_id=self.node_id,
            interval=self.interval
        )
        
        # Try to initialize telemetry queue for HTTP POST
        try:
            from telemetry_queue import TelemetryQueue
            self.telemetry_queue = TelemetryQueue(
                db_path='/var/lib/resolvix/telemetry_queue.db',
                max_size=1000
            )
            print("[telemetry-ws] Telemetry queue initialized for HTTP POST")
        except Exception as e:
            print(f"[telemetry-ws] Could not initialize telemetry queue: {e}")
            self.telemetry_queue = None
        
        # Start the broadcast task
        self.broadcast_task = asyncio.create_task(self.broadcast_telemetry())
        
        # Start WebSocket server
        async with websockets.serve(self.handler, "0.0.0.0", self.port, ping_interval=20, ping_timeout=10):
            print(f"[telemetry-ws] Server started on ws://0.0.0.0:{self.port}")
            print(f"[telemetry-ws] Node ID: {self.node_id}")
            print(f"[telemetry-ws] Broadcast interval: {self.interval}s")
            
            # Run forever
            await asyncio.Future()  # Run forever
            
    def stop(self):
        """Stop the server"""
        print("[telemetry-ws] Shutting down...")
        self.running = False
        if self.broadcast_task:
            self.broadcast_task.cancel()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("\n[telemetry-ws] Received shutdown signal")
    sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="WebSocket server for streaming telemetry data"
    )
    parser.add_argument(
        "node_id",
        help="Node identifier"
    )
    parser.add_argument(
        "port",
        type=int,
        help="WebSocket port to listen on"
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=60,
        help="Telemetry collection interval in seconds (default: 60)"
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start server
    server = TelemetryWebSocketServer(
        node_id=args.node_id,
        port=args.port,
        interval=args.interval
    )
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\n[telemetry-ws] Interrupted by user")
    except Exception as e:
        print(f"[telemetry-ws] Fatal error: {e}")
    finally:
        server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[telemetry-ws] Exiting...")
        sys.exit(0)
