#!/usr/bin/env python3
# test_alerts.py
"""
Test script for alert manager functionality
Run this to verify alerts are working correctly
"""

import time
import sys
from alert_manager import AlertManager

def test_cpu_alert():
    """Test CPU alert triggering"""
    print("="*60)
    print("Testing CPU Alert System")
    print("="*60)
    
    alert_mgr = AlertManager(
        backend_url="http://localhost:3000",
        hostname="test-server",
        ip_address="192.168.1.100"
    )
    
    print("\n[TEST] Simulating high CPU (95%) for 6 minutes...")
    print("[TEST] Alert should trigger after 5 minutes (300 seconds)")
    print("[TEST] Press Ctrl+C to stop\n")
    
    for i in range(360):  # 6 minutes
        alert_mgr.check_cpu_alert(95.5)
        elapsed = i + 1
        print(f"[TEST] Elapsed: {elapsed}s - CPU at 95.5%", end='\r')
        time.sleep(1)
    
    print("\n[TEST] CPU alert test completed")

def test_memory_alert():
    """Test memory alert triggering"""
    print("\n" + "="*60)
    print("Testing Memory Alert System")
    print("="*60)
    
    alert_mgr = AlertManager(
        backend_url="http://localhost:3000",
        hostname="test-server",
        ip_address="192.168.1.100"
    )
    
    print("\n[TEST] Simulating high memory (96%) for 6 minutes...")
    print("[TEST] Alert should trigger after 5 minutes (300 seconds)")
    print("[TEST] Press Ctrl+C to stop\n")
    
    for i in range(360):
        alert_mgr.check_memory_alert(96.2)
        elapsed = i + 1
        print(f"[TEST] Elapsed: {elapsed}s - Memory at 96.2%", end='\r')
        time.sleep(1)
    
    print("\n[TEST] Memory alert test completed")

def test_disk_alert():
    """Test disk alert triggering (immediate)"""
    print("\n" + "="*60)
    print("Testing Disk Alert System")
    print("="*60)
    
    alert_mgr = AlertManager(
        backend_url="http://localhost:3000",
        hostname="test-server",
        ip_address="192.168.1.100"
    )
    
    print("\n[TEST] Simulating critical disk usage (92%)...")
    print("[TEST] Alert should trigger immediately (no duration requirement)\n")
    
    alert_mgr.check_disk_alert(92.5)
    time.sleep(2)
    
    print("[TEST] Disk alert test completed")

def test_process_count_alert():
    """Test process count alert"""
    print("\n" + "="*60)
    print("Testing Process Count Alert System")
    print("="*60)
    
    alert_mgr = AlertManager(
        backend_url="http://localhost:3000",
        hostname="test-server",
        ip_address="192.168.1.100"
    )
    
    print("\n[TEST] Simulating high process count (550) for 6 minutes...")
    print("[TEST] Alert should trigger after 5 minutes (300 seconds)")
    print("[TEST] Press Ctrl+C to stop\n")
    
    for i in range(360):
        alert_mgr.check_process_count(550)
        elapsed = i + 1
        print(f"[TEST] Elapsed: {elapsed}s - Process count: 550", end='\r')
        time.sleep(1)
    
    print("\n[TEST] Process count alert test completed")

def test_cooldown():
    """Test cooldown functionality"""
    print("\n" + "="*60)
    print("Testing Alert Cooldown System")
    print("="*60)
    
    alert_mgr = AlertManager(
        backend_url="http://localhost:3000",
        hostname="test-server",
        ip_address="192.168.1.100"
    )
    
    print("\n[TEST] Triggering disk alert twice...")
    print("[TEST] Second alert should be suppressed by cooldown\n")
    
    # First alert
    print("[TEST] Sending first alert...")
    alert_mgr.check_disk_alert(92.5)
    time.sleep(2)
    
    # Second alert (should be suppressed)
    print("[TEST] Sending second alert (should be in cooldown)...")
    alert_mgr.check_disk_alert(93.0)
    time.sleep(2)
    
    print("[TEST] Cooldown test completed")

def main():
    """Run all tests"""
    print("Alert Manager Test Suite")
    print("="*60)
    print("This will test the alert system with simulated data")
    print("Make sure your backend is running on http://localhost:3000")
    print("="*60)
    print("\nAvailable tests:")
    print("1. CPU Alert (5 min duration)")
    print("2. Memory Alert (5 min duration)")
    print("3. Disk Alert (immediate)")
    print("4. Process Count Alert (5 min duration)")
    print("5. Cooldown Test")
    print("6. Run all tests")
    print("0. Exit")
    
    while True:
        try:
            choice = input("\nSelect test (0-6): ").strip()
            
            if choice == '0':
                print("Exiting...")
                sys.exit(0)
            elif choice == '1':
                test_cpu_alert()
            elif choice == '2':
                test_memory_alert()
            elif choice == '3':
                test_disk_alert()
            elif choice == '4':
                test_process_count_alert()
            elif choice == '5':
                test_cooldown()
            elif choice == '6':
                test_disk_alert()
                test_cooldown()
                print("\n[INFO] Long-running tests (CPU, Memory, Process) skipped.")
                print("[INFO] Run them individually to test duration-based alerts.")
            else:
                print("Invalid choice. Please select 0-6.")
                
        except KeyboardInterrupt:
            print("\n\n[TEST] Interrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"\n[ERROR] Test failed: {e}")

if __name__ == "__main__":
    main()
