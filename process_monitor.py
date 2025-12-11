#!/usr/bin/env python3
# process_monitor.py
"""
Process-level monitoring module for detailed system process tracking
Provides top processes by CPU/RAM, process management, and historical data
"""

import psutil
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger('resolvix')

class ProcessMonitor:
    """Monitors and manages system processes"""
    
    def __init__(self, history_size=1000):
        """
        Initialize process monitor
        
        Args:
            history_size: Number of historical snapshots to keep per process
        """
        self.history_size = history_size
        self.process_history = defaultdict(list)  # pid -> list of snapshots
        self.last_collection_time = None
        
    def get_process_metrics(self):
        """
        Collect top 10 processes by CPU and RAM usage
        Returns detailed process information
        """
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 
                                        'memory_percent', 'memory_info', 'create_time', 
                                        'status', 'cmdline', 'num_threads']):
            try:
                pinfo = proc.info
                
                # Calculate CPU percent with short interval
                try:
                    cpu_percent = proc.cpu_percent(interval=0.1)
                except:
                    cpu_percent = pinfo.get('cpu_percent', 0) or 0
                
                process_data = {
                    'pid': pinfo['pid'],
                    'name': pinfo['name'] or 'Unknown',
                    'username': pinfo.get('username', 'Unknown'),
                    'cpu_percent': round(cpu_percent, 2),
                    'memory_percent': round(pinfo.get('memory_percent', 0) or 0, 2),
                    'memory_mb': round(pinfo['memory_info'].rss / 1024 / 1024, 2) if pinfo.get('memory_info') else 0,
                    'status': pinfo.get('status', 'unknown'),
                    'started_at': datetime.fromtimestamp(pinfo['create_time']).isoformat() if pinfo.get('create_time') else None,
                    'cmdline': ' '.join(pinfo['cmdline']) if pinfo.get('cmdline') else (pinfo.get('name') or 'Unknown'),
                    'num_threads': pinfo.get('num_threads', 0) or 0
                }
                
                processes.append(process_data)
                
                # Store snapshot for history
                self._add_to_history(pinfo['pid'], {
                    'timestamp': datetime.now().isoformat(),
                    'cpu_percent': process_data['cpu_percent'],
                    'memory_percent': process_data['memory_percent'],
                    'memory_mb': process_data['memory_mb']
                })
                
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                logger.debug(f"Issue collecting process data: {e}")
        
        # Sort by CPU (top 10) and RAM (top 10)
        top_cpu = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        top_ram = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:10]
        
        self.last_collection_time = datetime.now()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'top_cpu': top_cpu,
            'top_ram': top_ram,
            'total_processes': len(processes),
            'zombie_count': sum(1 for p in processes if p['status'] == 'zombie')
        }
    
    def get_process_details(self, pid):
        """
        Get detailed information about a specific process
        
        Args:
            pid: Process ID
            
        Returns:
            dict with detailed process info or error
        """
        try:
            proc = psutil.Process(pid)
            
            # Get connections (may fail on some systems)
            try:
                connections = len(proc.connections())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                connections = 0
            
            # Get open files count
            try:
                open_files = len(proc.open_files())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                open_files = 0
            
            return {
                'success': True,
                'pid': pid,
                'name': proc.name(),
                'username': proc.username(),
                'cpu_percent': round(proc.cpu_percent(interval=0.1), 2),
                'memory_percent': round(proc.memory_percent(), 2),
                'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 2),
                'status': proc.status(),
                'started_at': datetime.fromtimestamp(proc.create_time()).isoformat(),
                'cmdline': ' '.join(proc.cmdline()) if proc.cmdline() else proc.name(),
                'cwd': proc.cwd() if hasattr(proc, 'cwd') else None,
                'num_threads': proc.num_threads(),
                'num_fds': proc.num_fds() if hasattr(proc, 'num_fds') else None,
                'connections': connections,
                'open_files': open_files,
                'parent_pid': proc.ppid() if proc.ppid() else None,
                'nice': proc.nice() if hasattr(proc, 'nice') else None
            }
        except psutil.NoSuchProcess:
            return {
                'success': False,
                'error': 'Process not found',
                'pid': pid
            }
        except psutil.AccessDenied:
            return {
                'success': False,
                'error': 'Permission denied',
                'pid': pid
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'pid': pid
            }
    
    def kill_process(self, pid, force=False):
        """
        Kill a process by PID
        
        Args:
            pid: Process ID to kill
            force: Use SIGKILL instead of SIGTERM
            
        Returns:
            dict with success status and message
        """
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            proc_user = proc.username()
            
            logger.info(f"[ProcessMonitor] Attempting to {'force kill' if force else 'terminate'} process: {proc_name} (PID: {pid}, User: {proc_user})")
            
            if force:
                proc.kill()  # SIGKILL
            else:
                proc.terminate()  # SIGTERM
            
            # Wait up to 3 seconds for process to terminate
            try:
                proc.wait(timeout=3)
                logger.info(f"[ProcessMonitor] Successfully terminated process: {proc_name} (PID: {pid})")
                
                return {
                    'success': True,
                    'message': f'Process {proc_name} (PID: {pid}) terminated successfully',
                    'pid': pid,
                    'name': proc_name,
                    'forced': force
                }
            except psutil.TimeoutExpired:
                # If terminate didn't work, try kill
                if not force:
                    logger.warning(f"[ProcessMonitor] Process {pid} didn't terminate, forcing kill")
                    proc.kill()
                    proc.wait(timeout=2)
                    
                    return {
                        'success': True,
                        'message': f'Process {proc_name} (PID: {pid}) force killed after timeout',
                        'pid': pid,
                        'name': proc_name,
                        'forced': True
                    }
                else:
                    raise
                    
        except psutil.NoSuchProcess:
            logger.warning(f"[ProcessMonitor] Process not found: PID {pid}")
            return {
                'success': False,
                'error': 'Process not found or already terminated',
                'pid': pid
            }
        except psutil.AccessDenied:
            logger.error(f"[ProcessMonitor] Permission denied killing process: PID {pid}")
            return {
                'success': False,
                'error': 'Permission denied - insufficient privileges (may need root)',
                'pid': pid
            }
        except Exception as e:
            logger.error(f"[ProcessMonitor] Failed to kill process {pid}: {e}")
            return {
                'success': False,
                'error': f'Failed to kill process: {str(e)}',
                'pid': pid
            }
    
    def get_process_history(self, pid, hours=24):
        """
        Get historical data for a specific process
        
        Args:
            pid: Process ID
            hours: Number of hours of history to return
            
        Returns:
            dict with historical metrics
        """
        if pid not in self.process_history:
            return {
                'pid': pid,
                'history': [],
                'message': 'No history available for this process'
            }
        
        # Filter history by time window
        cutoff_time = datetime.now() - timedelta(hours=hours)
        history = self.process_history[pid]
        
        filtered_history = [
            entry for entry in history
            if datetime.fromisoformat(entry['timestamp']) > cutoff_time
        ]
        
        # Calculate statistics
        if filtered_history:
            cpu_values = [h['cpu_percent'] for h in filtered_history]
            mem_values = [h['memory_percent'] for h in filtered_history]
            
            stats = {
                'avg_cpu': round(sum(cpu_values) / len(cpu_values), 2),
                'max_cpu': round(max(cpu_values), 2),
                'avg_memory': round(sum(mem_values) / len(mem_values), 2),
                'max_memory': round(max(mem_values), 2)
            }
        else:
            stats = None
        
        return {
            'pid': pid,
            'hours': hours,
            'history': filtered_history,
            'statistics': stats,
            'data_points': len(filtered_history)
        }
    
    def _add_to_history(self, pid, snapshot):
        """
        Add snapshot to process history with size limit
        
        Args:
            pid: Process ID
            snapshot: Metrics snapshot dict
        """
        if pid not in self.process_history:
            self.process_history[pid] = []
        
        self.process_history[pid].append(snapshot)
        
        # Keep only last N snapshots
        if len(self.process_history[pid]) > self.history_size:
            self.process_history[pid] = self.process_history[pid][-self.history_size:]
    
    def cleanup_old_history(self, hours=48):
        """
        Remove history for processes older than specified hours
        
        Args:
            hours: Age threshold for cleanup
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        pids_to_remove = []
        
        for pid, history in self.process_history.items():
            if not history:
                pids_to_remove.append(pid)
                continue
            
            # Remove old entries
            self.process_history[pid] = [
                entry for entry in history
                if datetime.fromisoformat(entry['timestamp']) > cutoff_time
            ]
            
            # If no entries left, mark for removal
            if not self.process_history[pid]:
                pids_to_remove.append(pid)
        
        # Clean up empty histories
        for pid in pids_to_remove:
            del self.process_history[pid]
        
        if pids_to_remove:
            logger.info(f"[ProcessMonitor] Cleaned up history for {len(pids_to_remove)} processes")
    
    def get_process_tree(self, pid):
        """
        Get process tree (parent and children) for a process
        
        Args:
            pid: Process ID
            
        Returns:
            dict with parent and children info
        """
        try:
            proc = psutil.Process(pid)
            
            # Get parent
            try:
                parent = proc.parent()
                parent_info = {
                    'pid': parent.pid,
                    'name': parent.name(),
                    'status': parent.status()
                } if parent else None
            except:
                parent_info = None
            
            # Get children
            children = []
            try:
                for child in proc.children(recursive=True):
                    children.append({
                        'pid': child.pid,
                        'name': child.name(),
                        'status': child.status(),
                        'cpu_percent': round(child.cpu_percent(interval=0.1), 2),
                        'memory_mb': round(child.memory_info().rss / 1024 / 1024, 2)
                    })
            except:
                pass
            
            return {
                'success': True,
                'pid': pid,
                'name': proc.name(),
                'parent': parent_info,
                'children': children,
                'total_children': len(children)
            }
        except psutil.NoSuchProcess:
            return {
                'success': False,
                'error': 'Process not found',
                'pid': pid
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'pid': pid
            }
