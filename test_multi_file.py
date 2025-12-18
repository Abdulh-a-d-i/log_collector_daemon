#!/usr/bin/env python3
"""
Test script for Option B: Multiple --log-file implementation
Tests that the daemon can monitor multiple log files simultaneously
"""

import subprocess
import time
import os
import requests
import json

def test_multi_file_monitoring():
    print("=" * 60)
    print("Testing Option B: Multiple Log File Monitoring")
    print("=" * 60)
    
    # Create test log files
    test_files = [
        "test_log1.log",
        "test_log2.log",
        "test_log3.log"
    ]
    
    print("\n1. Creating test log files...")
    for log_file in test_files:
        with open(log_file, 'w') as f:
            f.write(f"# Test log file: {log_file}\n")
        print(f"   ✓ Created {log_file}")
    
    # Start daemon with multiple files
    print("\n2. Starting daemon with multiple log files...")
    cmd = [
        "python3",
        "log_collector_daemon.py",
        "--log-file", test_files[0],
        "--log-file", test_files[1],
        "--log-file", test_files[2],
        "--api-url", "http://13.235.113.192:3000/api/ticket",
        "--control-port", "8754"
    ]
    
    print(f"   Command: {' '.join(cmd)}")
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"   ✓ Daemon started (PID: {proc.pid})")
        
        # Wait for daemon to initialize
        print("\n3. Waiting for daemon to initialize...")
        time.sleep(3)
        
        # Check status endpoint
        print("\n4. Checking status endpoint...")
        try:
            response = requests.get("http://localhost:8754/api/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                print(f"   ✓ Status endpoint working")
                print(f"\n   Status Response:")
                print(json.dumps(status, indent=2))
                
                # Verify monitored files
                if 'monitored_files' in status:
                    monitored = status['monitored_files']
                    print(f"\n   ✅ Monitoring {monitored['count']} files:")
                    for file in monitored['files']:
                        print(f"      - {file['path']} [{file['label']}] ({file['priority']})")
                else:
                    print("   ❌ monitored_files not found in status")
            else:
                print(f"   ❌ Status endpoint returned {response.status_code}")
        except Exception as e:
            print(f"   ❌ Error checking status: {e}")
        
        # Write test errors to each file
        print("\n5. Writing test errors to log files...")
        test_errors = [
            "ERROR: Test error in file 1 - connection failed",
            "CRITICAL: Test critical error in file 2 - database down",
            "FAILURE: Test failure in file 3 - service crashed"
        ]
        
        for i, (log_file, error_msg) in enumerate(zip(test_files, test_errors)):
            with open(log_file, 'a') as f:
                f.write(f"{error_msg}\n")
            print(f"   ✓ Wrote error to {log_file}")
            time.sleep(1)
        
        # Wait for processing
        print("\n6. Waiting for daemon to process errors...")
        time.sleep(3)
        
        # Check daemon logs
        print("\n7. Checking daemon logs...")
        if os.path.exists("/var/log/resolvix.log"):
            print("   Daemon log output (last 20 lines):")
            with open("/var/log/resolvix.log", 'r') as f:
                lines = f.readlines()
                for line in lines[-20:]:
                    if "Issue detected" in line or "Monitor-" in line:
                        print(f"   {line.strip()}")
        else:
            print("   Note: /var/log/resolvix.log not accessible (may need sudo)")
        
        print("\n8. Shutting down daemon...")
        proc.terminate()
        proc.wait(timeout=5)
        print("   ✓ Daemon stopped")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        if 'proc' in locals():
            proc.terminate()
    
    finally:
        # Cleanup test files
        print("\n9. Cleaning up test files...")
        for log_file in test_files:
            if os.path.exists(log_file):
                os.remove(log_file)
                print(f"   ✓ Removed {log_file}")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_multi_file_monitoring()
