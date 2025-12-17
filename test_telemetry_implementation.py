#!/usr/bin/env python3
"""
Test script for telemetry implementation
Tests queue, poster, and integration
"""

import sys
import os
import json
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_telemetry_queue():
    """Test TelemetryQueue functionality"""
    print("\n=== Testing TelemetryQueue ===")
    
    try:
        from telemetry_queue import TelemetryQueue
        
        # Initialize queue
        queue = TelemetryQueue(db_path='test_telemetry_queue.db', max_size=10)
        print("✅ Queue initialized successfully")
        
        # Test enqueue
        test_payload = {
            'node_id': 'test-node',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'cpu_percent': 50.0,
            'memory_percent': 60.0
        }
        entry_id = queue.enqueue(test_payload)
        print(f"✅ Enqueued entry (id={entry_id})")
        
        # Test queue size
        size = queue.get_queue_size()
        print(f"✅ Queue size: {size}")
        assert size == 1, "Queue should have 1 entry"
        
        # Test dequeue
        items = queue.dequeue(limit=1)
        print(f"✅ Dequeued {len(items)} items")
        assert len(items) == 1, "Should dequeue 1 item"
        
        # Test mark sent
        queue.mark_sent(items[0][0])
        size = queue.get_queue_size()
        print(f"✅ Queue size after mark_sent: {size}")
        assert size == 0, "Queue should be empty"
        
        # Test stats
        stats = queue.get_stats()
        print(f"✅ Queue stats: {json.dumps(stats, indent=2)}")
        
        # Cleanup
        os.remove('test_telemetry_queue.db')
        print("✅ Test database cleaned up")
        
        return True
    except Exception as e:
        print(f"❌ TelemetryQueue test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_telemetry_poster():
    """Test TelemetryPoster functionality"""
    print("\n=== Testing TelemetryPoster ===")
    
    try:
        from telemetry_poster import TelemetryPoster
        
        # Initialize poster (will fail to connect, but tests imports)
        poster = TelemetryPoster(
            backend_url='http://localhost:5001',
            jwt_token='test-token',
            retry_backoff=[1, 2, 3],
            timeout=5
        )
        print("✅ Poster initialized successfully")
        
        # Test POST (will fail but shouldn't crash)
        test_payload = {
            'node_id': 'test-node',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'cpu_percent': 50.0,
            'memory_percent': 60.0
        }
        success, error_type = poster.post_snapshot(test_payload)
        print(f"✅ POST test completed (success={success}, error={error_type})")
        
        # Close session
        poster.close()
        print("✅ Poster session closed")
        
        return True
    except Exception as e:
        print(f"❌ TelemetryPoster test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration between components"""
    print("\n=== Testing Integration ===")
    
    try:
        from telemetry_queue import TelemetryQueue
        from telemetry_poster import TelemetryPoster
        
        # Create queue and poster
        queue = TelemetryQueue(db_path='test_integration.db', max_size=10)
        poster = TelemetryPoster(
            backend_url='http://localhost:5001',
            jwt_token='test-token'
        )
        
        # Enqueue some test data
        for i in range(3):
            payload = {
                'node_id': 'test-node',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'cpu_percent': 50.0 + i,
                'memory_percent': 60.0 + i
            }
            queue.enqueue(payload)
        
        print(f"✅ Enqueued 3 test snapshots")
        print(f"✅ Queue size: {queue.get_queue_size()}")
        
        # Dequeue and test posting
        snapshots = queue.dequeue(limit=3)
        print(f"✅ Dequeued {len(snapshots)} snapshots")
        
        for snapshot_id, payload, retry_count in snapshots:
            success, error = poster.post_snapshot(payload)
            if not success:
                # Mark as failed (expected since backend not running)
                still_in_queue = queue.mark_failed(snapshot_id, max_retries=3)
                print(f"✅ Snapshot {snapshot_id} marked failed (retry_count={retry_count})")
        
        print(f"✅ Final queue size: {queue.get_queue_size()}")
        
        # Cleanup
        poster.close()
        os.remove('test_integration.db')
        print("✅ Integration test cleaned up")
        
        return True
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_imports():
    """Test that all modules can be imported"""
    print("\n=== Testing Imports ===")
    
    try:
        from telemetry_queue import TelemetryQueue
        print("✅ telemetry_queue imported successfully")
        
        from telemetry_poster import TelemetryPoster
        print("✅ telemetry_poster imported successfully")
        
        # Test daemon imports (optional)
        try:
            from log_collector_daemon import LogCollectorDaemon
            print("✅ log_collector_daemon imported successfully")
        except Exception as e:
            print(f"⚠️  log_collector_daemon import failed (may need dependencies): {e}")
        
        return True
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("TELEMETRY IMPLEMENTATION TEST SUITE")
    print("=" * 60)
    
    results = {
        'Imports': test_imports(),
        'TelemetryQueue': test_telemetry_queue(),
        'TelemetryPoster': test_telemetry_poster(),
        'Integration': test_integration()
    }
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")
    
    print("=" * 60)
    
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
