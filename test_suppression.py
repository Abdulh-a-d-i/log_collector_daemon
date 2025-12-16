#!/usr/bin/env python3
"""
Test script for suppression rules feature
Tests the SuppressionRuleChecker class functionality
"""

import psycopg2
from suppression_checker import SuppressionRuleChecker
import time
from datetime import datetime, timedelta

# ==============================================
# CONFIGURATION - UPDATE THESE VALUES
# ==============================================
DB_CONFIG = {
    'host': 'localhost',
    'database': 'your_database',
    'user': 'your_user',
    'password': 'your_password',
    'port': 5432
}

# ==============================================
# TEST FUNCTIONS
# ==============================================

def print_test_header(test_name):
    """Print test section header"""
    print("\n" + "="*60)
    print(f"TEST: {test_name}")
    print("="*60)


def test_basic_suppression(checker, conn):
    """Test 1: Basic suppression functionality"""
    print_test_header("Basic Suppression")
    
    cursor = conn.cursor()
    
    # Clean up any existing test rules
    cursor.execute("DELETE FROM suppression_rules WHERE name LIKE 'Test %'")
    conn.commit()
    
    # Create a test rule
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, expires_at, enabled
        )
        VALUES (
            'Test Basic Rule', 'test error message', NULL, 'forever', NULL, true
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created test rule ID: {rule_id}")
    
    # Force reload rules
    checker.force_reload()
    
    # Test 1: Should suppress
    suppressed, rule = checker.should_suppress("This is a test error message", "192.168.1.100")
    assert suppressed == True, "ERROR: Should have been suppressed!"
    assert rule is not None, "ERROR: Rule should be returned!"
    print(f"✓ Test 1 PASSED: Error was suppressed by rule '{rule['name']}'")
    
    # Test 2: Should NOT suppress (different text)
    suppressed, rule = checker.should_suppress("Different error entirely", "192.168.1.100")
    assert suppressed == False, "ERROR: Should NOT have been suppressed!"
    assert rule is None, "ERROR: No rule should match!"
    print("✓ Test 2 PASSED: Error was NOT suppressed (different text)")
    
    # Test 3: Case insensitive matching
    suppressed, rule = checker.should_suppress("TEST ERROR MESSAGE", "192.168.1.100")
    assert suppressed == True, "ERROR: Case-insensitive matching failed!"
    print("✓ Test 3 PASSED: Case-insensitive matching works")
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Basic suppression tests PASSED")


def test_node_specific_rules(checker, conn):
    """Test 2: Node-specific filtering"""
    print_test_header("Node-Specific Rules")
    
    cursor = conn.cursor()
    
    # Clean up
    cursor.execute("DELETE FROM suppression_rules WHERE name LIKE 'Test %'")
    conn.commit()
    
    # Create node-specific rule
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, enabled
        )
        VALUES (
            'Test Node Specific', 'specific error', '192.168.1.5', 'forever', true
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created node-specific rule ID: {rule_id} (node: 192.168.1.5)")
    
    # Force reload
    checker.force_reload()
    
    # Test 1: Should suppress for correct node
    suppressed, rule = checker.should_suppress("specific error occurred", "192.168.1.5")
    assert suppressed == True, "ERROR: Should suppress for node 192.168.1.5!"
    print("✓ Test 1 PASSED: Suppressed for correct node (192.168.1.5)")
    
    # Test 2: Should NOT suppress for different node
    suppressed, rule = checker.should_suppress("specific error occurred", "192.168.1.10")
    assert suppressed == False, "ERROR: Should NOT suppress for node 192.168.1.10!"
    print("✓ Test 2 PASSED: NOT suppressed for different node (192.168.1.10)")
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Node-specific filtering tests PASSED")


def test_cache_refresh(checker, conn):
    """Test 3: Cache refresh mechanism"""
    print_test_header("Cache Refresh")
    
    cursor = conn.cursor()
    
    # Get initial stats
    initial_stats = checker.get_statistics()
    print(f"✓ Initial cached rules: {initial_stats['cached_rules']}")
    
    # Create a new rule
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, enabled
        )
        VALUES (
            'Test Cache Rule', 'cache test', NULL, 'forever', true
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created new rule ID: {rule_id}")
    
    # Force reload to get new rule immediately
    checker.force_reload()
    
    # Check that rule is now in cache
    new_stats = checker.get_statistics()
    assert new_stats['cached_rules'] > initial_stats['cached_rules'], "ERROR: Cache not refreshed!"
    print(f"✓ Cache refreshed: {new_stats['cached_rules']} rules now cached")
    
    # Test that new rule works
    suppressed, rule = checker.should_suppress("This is a cache test error", "192.168.1.100")
    assert suppressed == True, "ERROR: New rule should work after cache refresh!"
    print(f"✓ New rule works: '{rule['name']}'")
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Cache refresh tests PASSED")


def test_statistics_tracking(checker, conn):
    """Test 4: Statistics tracking (match_count, last_matched_at)"""
    print_test_header("Statistics Tracking")
    
    cursor = conn.cursor()
    
    # Clean up and create test rule
    cursor.execute("DELETE FROM suppression_rules WHERE name LIKE 'Test %'")
    conn.commit()
    
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, enabled, match_count, last_matched_at
        )
        VALUES (
            'Test Stats Rule', 'stats test error', NULL, 'forever', true, 0, NULL
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created test rule ID: {rule_id} (match_count=0)")
    
    # Force reload
    checker.force_reload()
    
    # Trigger suppression 5 times
    print("✓ Triggering suppression 5 times...")
    for i in range(5):
        suppressed, rule = checker.should_suppress("This is a stats test error", "192.168.1.100")
        assert suppressed == True, f"ERROR: Iteration {i+1} should be suppressed!"
        time.sleep(0.1)  # Small delay to ensure DB updates
    
    # Check database for updated count
    cursor.execute(f"SELECT match_count, last_matched_at FROM suppression_rules WHERE id = {rule_id}")
    match_count, last_matched = cursor.fetchone()
    
    print(f"✓ Database match_count: {match_count}")
    print(f"✓ Database last_matched_at: {last_matched}")
    
    assert match_count == 5, f"ERROR: Expected match_count=5, got {match_count}!"
    assert last_matched is not None, "ERROR: last_matched_at should be set!"
    print("✓ Statistics correctly updated in database")
    
    # Check local statistics
    local_stats = checker.get_statistics()
    print(f"✓ Local statistics: {local_stats}")
    assert local_stats['total_suppressed'] >= 5, "ERROR: Local stats not tracking correctly!"
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Statistics tracking tests PASSED")


def test_disabled_rules(checker, conn):
    """Test 5: Disabled rules should not suppress"""
    print_test_header("Disabled Rules")
    
    cursor = conn.cursor()
    
    # Clean up and create disabled rule
    cursor.execute("DELETE FROM suppression_rules WHERE name LIKE 'Test %'")
    conn.commit()
    
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, enabled
        )
        VALUES (
            'Test Disabled Rule', 'disabled error', NULL, 'forever', false
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created DISABLED rule ID: {rule_id}")
    
    # Force reload
    checker.force_reload()
    
    # Should NOT suppress (rule is disabled)
    suppressed, rule = checker.should_suppress("This is a disabled error", "192.168.1.100")
    assert suppressed == False, "ERROR: Disabled rule should NOT suppress!"
    print("✓ Disabled rule correctly ignored")
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Disabled rules tests PASSED")


def test_expired_rules(checker, conn):
    """Test 6: Expired rules should not suppress"""
    print_test_header("Expired Rules")
    
    cursor = conn.cursor()
    
    # Clean up and create expired rule
    cursor.execute("DELETE FROM suppression_rules WHERE name LIKE 'Test %'")
    conn.commit()
    
    # Create rule that expired 1 hour ago
    cursor.execute("""
        INSERT INTO suppression_rules (
            name, match_text, node_ip, duration_type, expires_at, enabled
        )
        VALUES (
            'Test Expired Rule', 'expired error', NULL, 'custom', NOW() - INTERVAL '1 hour', true
        )
        RETURNING id
    """)
    rule_id = cursor.fetchone()[0]
    conn.commit()
    print(f"✓ Created EXPIRED rule ID: {rule_id} (expired 1 hour ago)")
    
    # Force reload
    checker.force_reload()
    
    # Should NOT suppress (rule is expired)
    suppressed, rule = checker.should_suppress("This is an expired error", "192.168.1.100")
    assert suppressed == False, "ERROR: Expired rule should NOT suppress!"
    print("✓ Expired rule correctly ignored")
    
    # Cleanup
    cursor.execute(f"DELETE FROM suppression_rules WHERE id = {rule_id}")
    conn.commit()
    cursor.close()
    
    print("\n✅ Expired rules tests PASSED")


def print_summary(checker):
    """Print final summary"""
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    stats = checker.get_statistics()
    print(f"Total checks performed:    {stats['total_checks']}")
    print(f"Total errors suppressed:   {stats['total_suppressed']}")
    print(f"Suppression rate:          {stats['suppression_rate']:.1f}%")
    print(f"Rules currently cached:    {stats['cached_rules']}")
    print("="*60)


# ==============================================
# MAIN TEST RUNNER
# ==============================================

def main():
    print("\n" + "="*60)
    print("SUPPRESSION RULES TEST SUITE")
    print("="*60)
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("="*60)
    
    try:
        # Connect to database
        print("\n→ Connecting to database...")
        conn = psycopg2.connect(**DB_CONFIG)
        print("✓ Database connected")
        
        # Create checker
        print("→ Initializing SuppressionRuleChecker...")
        checker = SuppressionRuleChecker(conn, cache_ttl=60)
        print("✓ SuppressionRuleChecker initialized")
        
        # Run all tests
        test_basic_suppression(checker, conn)
        test_node_specific_rules(checker, conn)
        test_cache_refresh(checker, conn)
        test_statistics_tracking(checker, conn)
        test_disabled_rules(checker, conn)
        test_expired_rules(checker, conn)
        
        # Print summary
        print_summary(checker)
        
        print("\n✅ ALL TESTS PASSED! ✅\n")
        
        # Close connection
        conn.close()
        print("✓ Database connection closed")
        
        return 0
        
    except psycopg2.Error as e:
        print(f"\n❌ DATABASE ERROR: {e}")
        print("\nPlease check:")
        print("1. Database credentials in DB_CONFIG")
        print("2. Database is running and accessible")
        print("3. suppression_rules table exists")
        return 1
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
