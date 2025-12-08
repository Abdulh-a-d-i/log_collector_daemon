#!/usr/bin/env python3
# alert_config.py
"""
Alert threshold configuration for system monitoring
Adjust these values based on your infrastructure needs
"""

ALERT_THRESHOLDS = {
    # CPU Alerts
    'cpu_critical': {
        'threshold': 90,  # CPU usage percentage
        'duration': 300,  # Must persist for 5 minutes (300 seconds)
        'priority': 'critical',
        'cooldown': 1800,  # Don't spam - wait 30 min before re-alerting
    },
    'cpu_high': {
        'threshold': 75,
        'duration': 600,  # 10 minutes
        'priority': 'high',
        'cooldown': 3600,  # 1 hour
    },
    
    # Memory Alerts
    'memory_critical': {
        'threshold': 95,  # Memory usage percentage
        'duration': 300,
        'priority': 'critical',
        'cooldown': 1800,
    },
    'memory_high': {
        'threshold': 85,
        'duration': 600,
        'priority': 'high',
        'cooldown': 3600,
    },
    
    # Disk Alerts
    'disk_critical': {
        'threshold': 90,  # Disk usage percentage
        'duration': 0,  # Alert immediately
        'priority': 'critical',
        'cooldown': 7200,  # 2 hours
    },
    'disk_high': {
        'threshold': 80,
        'duration': 0,
        'priority': 'high',
        'cooldown': 14400,  # 4 hours
    },
    
    # Network Alerts (spike detection)
    'network_spike': {
        'threshold_multiplier': 5,  # 5x normal traffic
        'duration': 60,  # 1 minute
        'priority': 'medium',
        'cooldown': 1800,
    },
    
    # Process Alerts
    'high_process_count': {
        'threshold': 500,  # Number of processes
        'duration': 300,
        'priority': 'medium',
        'cooldown': 3600,
    },
}

# Alert message templates
ALERT_MESSAGES = {
    'cpu_critical': "🔴 CRITICAL: CPU usage at {value}% for {duration} minutes on {hostname}",
    'cpu_high': "🟠 HIGH: CPU usage at {value}% for {duration} minutes on {hostname}",
    'memory_critical': "🔴 CRITICAL: Memory usage at {value}% for {duration} minutes on {hostname}",
    'memory_high': "🟠 HIGH: Memory usage at {value}% for {duration} minutes on {hostname}",
    'disk_critical': "🔴 CRITICAL: Disk usage at {value}% on {hostname}. Immediate action required!",
    'disk_high': "🟠 WARNING: Disk usage at {value}% on {hostname}. Plan cleanup soon.",
    'network_spike': "⚠️ Network traffic spike detected: {value}x normal on {hostname}",
    'high_process_count': "⚠️ High process count: {value} processes running on {hostname}",
}
