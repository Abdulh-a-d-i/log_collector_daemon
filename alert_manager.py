#!/usr/bin/env python3
# alert_manager.py
"""
Smart Alert Manager - Monitors thresholds and creates tickets
"""

import time
import requests
from collections import defaultdict
from datetime import datetime, timedelta
from alert_config import ALERT_THRESHOLDS, ALERT_MESSAGES
import logging

logger = logging.getLogger('resolvix')

class AlertManager:
    def __init__(self, backend_url, hostname, ip_address):
        self.backend_url = backend_url.rstrip("/") if backend_url else None
        self.hostname = hostname
        self.ip_address = ip_address
        
        # Track alert state
        self.alert_start_times = defaultdict(lambda: None)
        self.last_alert_sent = defaultdict(lambda: None)
        self.baseline_network = {'sent': 0, 'recv': 0, 'samples': 0}
        
        logger.info(f"[AlertManager] Initialized for {hostname} ({ip_address})")
        
    def check_cpu_alert(self, cpu_percent):
        """Check CPU usage against thresholds"""
        current_time = time.time()
        
        # Check critical threshold
        if cpu_percent >= ALERT_THRESHOLDS['cpu_critical']['threshold']:
            self._handle_threshold_alert(
                'cpu_critical', 
                cpu_percent, 
                current_time,
                {'cpu_percent': cpu_percent}
            )
        # Check high threshold
        elif cpu_percent >= ALERT_THRESHOLDS['cpu_high']['threshold']:
            self._handle_threshold_alert(
                'cpu_high', 
                cpu_percent, 
                current_time,
                {'cpu_percent': cpu_percent}
            )
        else:
            # Reset alert state if back to normal
            self._reset_alert('cpu_critical')
            self._reset_alert('cpu_high')
    
    def check_memory_alert(self, memory_percent):
        """Check memory usage against thresholds"""
        current_time = time.time()
        
        if memory_percent >= ALERT_THRESHOLDS['memory_critical']['threshold']:
            self._handle_threshold_alert(
                'memory_critical', 
                memory_percent, 
                current_time,
                {'memory_percent': memory_percent}
            )
        elif memory_percent >= ALERT_THRESHOLDS['memory_high']['threshold']:
            self._handle_threshold_alert(
                'memory_high', 
                memory_percent, 
                current_time,
                {'memory_percent': memory_percent}
            )
        else:
            self._reset_alert('memory_critical')
            self._reset_alert('memory_high')
    
    def check_disk_alert(self, disk_percent):
        """Check disk usage against thresholds"""
        current_time = time.time()
        
        if disk_percent >= ALERT_THRESHOLDS['disk_critical']['threshold']:
            self._handle_threshold_alert(
                'disk_critical', 
                disk_percent, 
                current_time,
                {'disk_percent': disk_percent}
            )
        elif disk_percent >= ALERT_THRESHOLDS['disk_high']['threshold']:
            self._handle_threshold_alert(
                'disk_high', 
                disk_percent, 
                current_time,
                {'disk_percent': disk_percent}
            )
        else:
            self._reset_alert('disk_critical')
            self._reset_alert('disk_high')
    
    def check_network_spike(self, bytes_sent, bytes_recv):
        """Detect unusual network traffic spikes"""
        # Build baseline (average of samples)
        self.baseline_network['sent'] += bytes_sent
        self.baseline_network['recv'] += bytes_recv
        self.baseline_network['samples'] += 1
        
        if self.baseline_network['samples'] < 20:
            return  # Not enough data yet
        
        avg_sent = self.baseline_network['sent'] / self.baseline_network['samples']
        avg_recv = self.baseline_network['recv'] / self.baseline_network['samples']
        
        multiplier = ALERT_THRESHOLDS['network_spike']['threshold_multiplier']
        
        if bytes_sent > avg_sent * multiplier or bytes_recv > avg_recv * multiplier:
            spike_value = max(bytes_sent / avg_sent if avg_sent > 0 else 0, 
                            bytes_recv / avg_recv if avg_recv > 0 else 0)
            self._handle_threshold_alert(
                'network_spike',
                spike_value,
                time.time(),
                {'bytes_sent': bytes_sent, 'bytes_recv': bytes_recv, 'spike': spike_value}
            )
    
    def check_process_count(self, process_count):
        """Check if too many processes are running"""
        current_time = time.time()
        
        if process_count >= ALERT_THRESHOLDS['high_process_count']['threshold']:
            self._handle_threshold_alert(
                'high_process_count',
                process_count,
                current_time,
                {'process_count': process_count}
            )
        else:
            self._reset_alert('high_process_count')
    
    def _handle_threshold_alert(self, alert_type, value, current_time, metadata):
        """Handle threshold-based alerts with duration and cooldown"""
        config = ALERT_THRESHOLDS[alert_type]
        
        # Check if we're in cooldown period
        if self.last_alert_sent[alert_type]:
            time_since_last = current_time - self.last_alert_sent[alert_type]
            if time_since_last < config['cooldown']:
                return  # Still in cooldown, don't spam
        
        # Start tracking if this is first breach
        if not self.alert_start_times[alert_type]:
            self.alert_start_times[alert_type] = current_time
            logger.info(f"[ALERT] {alert_type} threshold breached: {value}")
            return  # Wait for duration requirement
        
        # Check if duration requirement is met
        breach_duration = current_time - self.alert_start_times[alert_type]
        
        if breach_duration >= config['duration']:
            # Duration met - send alert!
            self._send_alert(alert_type, value, breach_duration, metadata)
            self.last_alert_sent[alert_type] = current_time
            self.alert_start_times[alert_type] = None  # Reset
    
    def _reset_alert(self, alert_type):
        """Reset alert state when metrics return to normal"""
        if self.alert_start_times[alert_type]:
            logger.info(f"[ALERT] {alert_type} returned to normal")
            self.alert_start_times[alert_type] = None
    
    def _send_alert(self, alert_type, value, duration, metadata):
        """Create ticket in backend for this alert"""
        if not self.backend_url:
            logger.warning("[ALERT] No backend URL configured, skipping alert")
            return
            
        config = ALERT_THRESHOLDS[alert_type]
        
        # Format message
        message = ALERT_MESSAGES[alert_type].format(
            value=round(value, 1),
            duration=round(duration / 60, 1),  # Convert to minutes
            hostname=self.hostname
        )
        
        # Prepare ticket data
        ticket_data = {
            'title': message,
            'description': self._generate_alert_description(alert_type, value, duration, metadata),
            'priority': config['priority'],
            'status': 'open',
            'application': 'System Monitor',
            'system_ip': self.ip_address,
            'alert_type': alert_type,
            'metric_value': value,
        }
        
        try:
            # Extract base URL and construct alert endpoint
            base_url = self.backend_url.replace('/api/ticket', '').replace('/api/logs', '')
            alert_url = f'{base_url}/api/alerts/create'
            
            response = requests.post(
                alert_url,
                json=ticket_data,
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"[ALERT] ✓ Ticket created for {alert_type}: {message}")
            else:
                logger.warning(f"[ALERT] ✗ Ticket creation failed: {response.status_code} - {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"[ALERT] ✗ Timeout sending alert for {alert_type}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"[ALERT] ✗ Connection issue sending alert: {e}")
        except Exception as e:
            logger.warning(f"[ALERT] ✗ Alert sending failed: {e}")
    
    def _generate_alert_description(self, alert_type, value, duration, metadata):
        """Generate detailed alert description"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        description = f"""
**Alert Type:** {alert_type.replace('_', ' ').title()}
**Timestamp:** {timestamp}
**Host:** {self.hostname} ({self.ip_address})
**Metric Value:** {round(value, 2)}
**Duration:** {round(duration / 60, 1)} minutes

**Threshold Configuration:**
- Threshold: {ALERT_THRESHOLDS[alert_type].get('threshold', 'N/A')}
- Required Duration: {ALERT_THRESHOLDS[alert_type]['duration']}s
- Priority: {ALERT_THRESHOLDS[alert_type]['priority']}

**Additional Metrics:**
{self._format_metadata(metadata)}

**Recommended Actions:**
{self._get_recommendations(alert_type)}
"""
        return description.strip()
    
    def _format_metadata(self, metadata):
        """Format metadata dictionary as readable text"""
        lines = []
        for key, value in metadata.items():
            if isinstance(value, float):
                lines.append(f"- {key}: {round(value, 2)}")
            else:
                lines.append(f"- {key}: {value}")
        return '\n'.join(lines) if lines else "No additional metrics"
    
    def _get_recommendations(self, alert_type):
        """Get recommended actions for each alert type"""
        recommendations = {
            'cpu_critical': "1. Check top processes: `top` or `htop`\n2. Kill unnecessary processes\n3. Consider scaling horizontally",
            'cpu_high': "1. Identify CPU-intensive processes\n2. Optimize application code\n3. Monitor trends for capacity planning",
            'memory_critical': "1. Check for memory leaks: `ps aux --sort=-%mem`\n2. Restart leaking services\n3. Consider adding more RAM",
            'memory_high': "1. Clear caches: `sync; echo 3 > /proc/sys/vm/drop_caches`\n2. Review application memory usage\n3. Plan memory upgrade",
            'disk_critical': "1. Delete old logs: `find /var/log -type f -name '*.log' -mtime +30 -delete`\n2. Clear temp files: `rm -rf /tmp/*`\n3. Identify large files: `du -h --max-depth=1 / | sort -hr`",
            'disk_high': "1. Run disk cleanup\n2. Archive old data\n3. Plan storage expansion",
            'network_spike': "1. Check active connections: `netstat -tunap`\n2. Verify no DDoS attack\n3. Review application logs",
            'high_process_count': "1. Check for zombie processes\n2. Review application spawning logic\n3. Increase process limits if needed",
        }
        return recommendations.get(alert_type, "Review system logs and metrics")
