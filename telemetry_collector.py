#!/usr/bin/env python3
# telemetry_collector.py
import threading
import time
import psutil
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import json

class TelemetryCollector:
    """
    Collects system telemetry metrics and sends them to a central API endpoint.
    Runs in a background thread to avoid blocking the main daemon.
    """
    
    def __init__(
        self, 
        api_url: str, 
        node_id: str, 
        interval: int = 60,
        collect_network: bool = True,
        collect_disk_io: bool = True
    ):
        """
        Args:
            api_url: Central API endpoint for telemetry data
            node_id: Unique identifier for this node
            interval: Collection interval in seconds (default: 60)
            collect_network: Whether to collect network metrics
            collect_disk_io: Whether to collect disk I/O metrics
        """
        self.api_url = api_url.rstrip("/")
        self.node_id = node_id
        self.interval = interval
        self.collect_network = collect_network
        self.collect_disk_io = collect_disk_io
        
        self._stop_flag = threading.Event()
        self._thread = None
        
        # Store previous values for rate calculations
        self._prev_net_io = None
        self._prev_disk_io = None
        self._prev_time = None
        
    def start(self):
        """Start the telemetry collection thread"""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._thread.start()
        print(f"[telemetry] Started collection (interval: {self.interval}s)")
        
    def stop(self):
        """Stop the telemetry collection thread"""
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=5)
        print("[telemetry] Stopped collection")
        
    def _collect_cpu_metrics(self) -> Dict[str, Any]:
        """Collect CPU-related metrics"""
        cpu_percent = psutil.cpu_percent(interval=1, percpu=False)
        cpu_percent_per_core = psutil.cpu_percent(interval=0, percpu=True)
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
        
        return {
            "cpu_usage_percent": round(cpu_percent, 2),
            "cpu_per_core_percent": [round(x, 2) for x in cpu_percent_per_core],
            "load_avg_1min": round(load_avg[0], 2),
            "load_avg_5min": round(load_avg[1], 2),
            "load_avg_15min": round(load_avg[2], 2),
            "cpu_count_logical": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False)
        }
        
    def _collect_memory_metrics(self) -> Dict[str, Any]:
        """Collect memory-related metrics"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "memory_total_gb": round(mem.total / (1024**3), 2),
            "memory_used_gb": round(mem.used / (1024**3), 2),
            "memory_available_gb": round(mem.available / (1024**3), 2),
            "memory_usage_percent": round(mem.percent, 2),
            "swap_total_gb": round(swap.total / (1024**3), 2),
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "swap_usage_percent": round(swap.percent, 2)
        }
        
    def _collect_disk_metrics(self) -> Dict[str, Any]:
        """Collect disk-related metrics"""
        disk_usage = {}
        disk_io_stats = {}
        
        # Disk usage for all partitions
        partitions = psutil.disk_partitions(all=False)
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                mount = partition.mountpoint
                disk_usage[mount] = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "usage_percent": round(usage.percent, 2)
                }
            except PermissionError:
                continue
        
        # Disk I/O rates (if enabled)
        if self.collect_disk_io:
            current_disk_io = psutil.disk_io_counters(perdisk=False)
            current_time = time.time()
            
            if self._prev_disk_io and self._prev_time:
                time_delta = current_time - self._prev_time
                if time_delta > 0:
                    read_bytes_per_sec = (current_disk_io.read_bytes - self._prev_disk_io.read_bytes) / time_delta
                    write_bytes_per_sec = (current_disk_io.write_bytes - self._prev_disk_io.write_bytes) / time_delta
                    
                    disk_io_stats = {
                        "read_mb_per_sec": round(read_bytes_per_sec / (1024**2), 2),
                        "write_mb_per_sec": round(write_bytes_per_sec / (1024**2), 2),
                        "read_count": current_disk_io.read_count,
                        "write_count": current_disk_io.write_count
                    }
            
            self._prev_disk_io = current_disk_io
            self._prev_time = current_time
        
        return {
            "disk_usage": disk_usage,
            "disk_io": disk_io_stats
        }
        
    def _collect_network_metrics(self) -> Dict[str, Any]:
        """Collect network-related metrics"""
        if not self.collect_network:
            return {}
        
        current_net_io = psutil.net_io_counters()
        current_time = time.time()
        net_stats = {}
        
        # Calculate rates if we have previous data
        if self._prev_net_io and self._prev_time:
            time_delta = current_time - self._prev_time
            if time_delta > 0:
                bytes_sent_per_sec = (current_net_io.bytes_sent - self._prev_net_io.bytes_sent) / time_delta
                bytes_recv_per_sec = (current_net_io.bytes_recv - self._prev_net_io.bytes_recv) / time_delta
                
                net_stats = {
                    "bytes_sent_mb_per_sec": round(bytes_sent_per_sec / (1024**2), 2),
                    "bytes_recv_mb_per_sec": round(bytes_recv_per_sec / (1024**2), 2),
                    "packets_sent": current_net_io.packets_sent,
                    "packets_recv": current_net_io.packets_recv,
                    "errors_in": current_net_io.errin,
                    "errors_out": current_net_io.errout,
                    "drops_in": current_net_io.dropin,
                    "drops_out": current_net_io.dropout
                }
        
        # Connection count
        try:
            connections = len(psutil.net_connections())
            net_stats["active_connections"] = connections
        except (PermissionError, psutil.AccessDenied):
            # May need root permissions
            pass
        
        self._prev_net_io = current_net_io
        
        return {"network": net_stats}
        
    def _collect_process_metrics(self) -> Dict[str, Any]:
        """Collect process-related metrics"""
        try:
            process_count = len(psutil.pids())
            
            # Get top 5 processes by memory
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'memory_percent': round(proc.info['memory_percent'], 2)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            top_memory = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:5]
            
            return {
                "process_count": process_count,
                "top_memory_processes": top_memory
            }
        except Exception as e:
            print(f"[telemetry] Error collecting process metrics: {e}")
            return {"process_count": 0}
    
    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all telemetry metrics"""
        metrics = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "node_id": self.node_id,
            "metrics": {}
        }
        
        try:
            metrics["metrics"]["cpu"] = self._collect_cpu_metrics()
        except Exception as e:
            print(f"[telemetry] Error collecting CPU metrics: {e}")
            
        try:
            metrics["metrics"]["memory"] = self._collect_memory_metrics()
        except Exception as e:
            print(f"[telemetry] Error collecting memory metrics: {e}")
            
        try:
            disk_metrics = self._collect_disk_metrics()
            metrics["metrics"]["disk"] = disk_metrics
        except Exception as e:
            print(f"[telemetry] Error collecting disk metrics: {e}")
            
        try:
            net_metrics = self._collect_network_metrics()
            if net_metrics:
                metrics["metrics"].update(net_metrics)
        except Exception as e:
            print(f"[telemetry] Error collecting network metrics: {e}")
            
        try:
            metrics["metrics"]["processes"] = self._collect_process_metrics()
        except Exception as e:
            print(f"[telemetry] Error collecting process metrics: {e}")
        
        return metrics
        
    def _send_metrics(self, metrics: Dict[str, Any]) -> bool:
        """Send metrics to the central API"""
        try:
            response = requests.post(
                f"{self.api_url}/telemetry",
                json=metrics,
                timeout=10
            )
            
            if response.status_code >= 400:
                print(f"[telemetry] API returned status {response.status_code}")
                return False
            
            return True
            
        except requests.exceptions.Timeout:
            print("[telemetry] Request timeout")
            return False
        except requests.exceptions.ConnectionError:
            print("[telemetry] Connection error")
            return False
        except Exception as e:
            print(f"[telemetry] Error sending metrics: {e}")
            return False
            
    def _collection_loop(self):
        """Main collection loop"""
        print("[telemetry] Collection loop started")
        
        # Initial delay to allow system to stabilize
        if not self._stop_flag.wait(5):
            pass
        
        while not self._stop_flag.is_set():
            try:
                # Collect metrics
                metrics = self.collect_all_metrics()
                
                # Send to API
                success = self._send_metrics(metrics)
                
                if success:
                    print(f"[telemetry] Metrics sent successfully at {metrics['timestamp']}")
                else:
                    # Optionally save locally if send fails
                    print(f"[telemetry] Failed to send metrics, will retry next interval")
                    
            except Exception as e:
                print(f"[telemetry] Error in collection loop: {e}")
            
            # Wait for next interval
            self._stop_flag.wait(self.interval)
            
        print("[telemetry] Collection loop ended")


# Example standalone usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Telemetry Collector")
    parser.add_argument("--api-url", required=True, help="Central API URL for telemetry")
    parser.add_argument("--node-id", required=True, help="Node identifier")
    parser.add_argument("--interval", type=int, default=60, help="Collection interval in seconds")
    args = parser.parse_args()
    
    collector = TelemetryCollector(
        api_url=args.api_url,
        node_id=args.node_id,
        interval=args.interval
    )
    
    collector.start()
    
    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        collector.stop()
