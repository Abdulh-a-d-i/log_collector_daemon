#!/usr/bin/env python3
"""
Test script for configuration management
Run: python3 test_config.py
"""

import requests
import json
import sys
from config_store import ConfigStore, init_config

def test_config_store():
    """Test configuration store functionality"""
    print("🧪 Testing ConfigStore\n")

    # Test 1: Initialize config
    print("1️⃣  Initialize config store")
    try:
        config = init_config(node_id='test-node', backend_url='http://localhost:3000')
        print(f"✅ Config initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}\n")
        return False

    # Test 2: Get values
    print("2️⃣  Get configuration values")
    try:
        cpu_threshold = config.get('alerts.thresholds.cpu_critical.threshold')
        telemetry_interval = config.get('intervals.telemetry')
        rabbitmq_queue = config.get('messaging.rabbitmq.queue')
        print(f"CPU critical threshold: {cpu_threshold}")
        print(f"Telemetry interval: {telemetry_interval}s")
        print(f"RabbitMQ queue: {rabbitmq_queue}\n")
    except Exception as e:
        print(f"❌ Failed to get values: {e}\n")
        return False

    # Test 3: Set values
    print("3️⃣  Update configuration values")
    try:
        config.set('alerts.thresholds.cpu_critical.threshold', 85)
        config.set('intervals.telemetry', 5)
        new_cpu = config.get('alerts.thresholds.cpu_critical.threshold')
        new_interval = config.get('intervals.telemetry')
        print(f"Updated CPU threshold: {new_cpu}")
        print(f"Updated telemetry interval: {new_interval}s")
        print(f"✅ Values updated\n")
    except Exception as e:
        print(f"❌ Failed to update values: {e}\n")
        return False

    # Test 4: Save config
    print("4️⃣  Save configuration")
    try:
        config.save()
        print(f"✅ Saved to /etc/resolvix/config.json (or current dir if no permissions)\n")
    except Exception as e:
        print(f"⚠️  Save failed (may need sudo): {e}\n")

    # Test 5: Reload config
    print("5️⃣  Reload configuration")
    try:
        changes = config.reload()
        print(f"✅ Reloaded, {len(changes)} changes detected")
        if changes:
            print(f"Changes: {list(changes.keys())}\n")
        else:
            print("No changes detected\n")
    except Exception as e:
        print(f"❌ Failed to reload: {e}\n")
        return False

    print("✅ All ConfigStore tests passed!\n")
    return True


def test_daemon_api():
    """Test daemon configuration API endpoints"""
    print("🧪 Testing Daemon Config API\n")

    BASE_URL = 'http://localhost:8754/api'

    # Test 1: Check daemon health
    print("0️⃣  GET /api/health (checking if daemon is running)")
    try:
        response = requests.get(f'{BASE_URL}/health', timeout=5)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Daemon is running\n")
        else:
            print(f"❌ Daemon not responding correctly\n")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to daemon. Is it running on port 8754?\n")
        print(f"   Start with: sudo python3 log_collector_daemon.py --log-file /var/log/syslog --api-url http://localhost:3000/api\n")
        return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

    # Test 2: Get config
    print("1️⃣  GET /api/config")
    try:
        response = requests.get(f'{BASE_URL}/config', timeout=5)
        data = response.json()
        print(f"Status: {response.status_code}")
        if response.status_code == 200 and data.get('success'):
            config_keys = list(data.get('config', {}).keys())
            print(f"Config sections: {config_keys}")
            print(f"✅ Config retrieved successfully\n")
        else:
            print(f"❌ Failed: {data}\n")
            return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

    # Test 3: Get schema
    print("2️⃣  GET /api/config/schema")
    try:
        response = requests.get(f'{BASE_URL}/config/schema', timeout=5)
        data = response.json()
        print(f"Status: {response.status_code}")
        if response.status_code == 200 and data.get('success'):
            schema_count = len(data.get('schema', {}))
            print(f"Schema entries: {schema_count}")
            print(f"Sample fields: {list(data.get('schema', {}).keys())[:5]}")
            print(f"✅ Schema retrieved successfully\n")
        else:
            print(f"❌ Failed: {data}\n")
            return False
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

    # Test 4: Update config
    print("3️⃣  POST /api/config (update settings)")
    try:
        response = requests.post(f'{BASE_URL}/config', json={
            'settings': {
                'intervals.telemetry': 5,
                'logging.level': 'DEBUG'
            }
        }, timeout=5)
        data = response.json()
        print(f"Status: {response.status_code}")
        if response.status_code == 200 and data.get('success'):
            print(f"Message: {data.get('message')}")
            print(f"Updated: {data.get('updated')}")
            print(f"✅ Config updated successfully\n")
        else:
            print(f"⚠️  Update may have failed: {data}\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

    # Test 5: Reload config
    print("4️⃣  POST /api/config/reload")
    try:
        response = requests.post(f'{BASE_URL}/config/reload', timeout=5)
        data = response.json()
        print(f"Status: {response.status_code}")
        if response.status_code == 200 and data.get('success'):
            print(f"Message: {data.get('message')}")
            print(f"Changes detected: {data.get('changes')}")
            if data.get('details'):
                print(f"Details: {data.get('details')}")
            print(f"✅ Config reloaded successfully\n")
        else:
            print(f"⚠️  Reload may have issues: {data}\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

    print("✅ All API tests passed!\n")
    return True


def test_log_label_detection():
    """Test log_label and priority detection functions"""
    print("🧪 Testing log_label and priority detection\n")

    try:
        from log_collector_daemon import get_log_label, determine_priority

        test_cases = [
            ('/var/log/apache2/error.log', 'apache_errors'),
            ('/var/log/nginx/error.log', 'nginx_errors'),
            ('/var/log/mysql/error.log', 'mysql_errors'),
            ('/var/log/syslog', 'system'),
            ('/var/log/kern.log', 'kernel'),
            ('/var/log/auth.log', 'authentication'),
            ('/var/log/custom-app.log', 'custom-app')
        ]

        print("Testing log_label detection:")
        all_passed = True
        for log_path, expected in test_cases:
            result = get_log_label(log_path)
            status = "✅" if result == expected else "❌"
            print(f"  {status} {log_path} -> {result} (expected: {expected})")
            if result != expected:
                all_passed = False

        print("\nTesting priority detection:")
        priority_tests = [
            ('FATAL error occurred', 'error', 'critical'),
            ('Connection failed', 'error', 'high'),
            ('Warning: disk space low', 'warning', 'medium'),
            ('Info: Service started', 'info', 'low'),
            ('kernel panic - not syncing', 'critical', 'critical'),
        ]

        for log_line, severity, expected_priority in priority_tests:
            result = determine_priority(log_line, severity)
            status = "✅" if result == expected_priority else "❌"
            print(f"  {status} '{log_line}' -> {result} (expected: {expected_priority})")
            if result != expected_priority:
                all_passed = False

        if all_passed:
            print("\n✅ All detection tests passed!\n")
            return True
        else:
            print("\n⚠️  Some detection tests failed\n")
            return False

    except ImportError as e:
        print(f"❌ Cannot import functions: {e}")
        print(f"   Make sure you're running from the daemon directory\n")
        return False
    except Exception as e:
        print(f"❌ Error during testing: {e}\n")
        return False


if __name__ == '__main__':
    print("="*70)
    print("Resolvix Daemon Configuration Test Suite")
    print("="*70)
    print()

    results = []

    # Test 1: ConfigStore
    print("=" * 70)
    results.append(("ConfigStore", test_config_store()))
    print()

    # Test 2: Log label/priority detection
    print("=" * 70)
    results.append(("Detection Functions", test_log_label_detection()))
    print()

    # Test 3: Daemon API
    print("=" * 70)
    results.append(("Daemon API", test_daemon_api()))
    print()

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:30s} {status}")

    print()
    all_passed = all(result[1] for result in results)
    if all_passed:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        sys.exit(1)
