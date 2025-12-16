#!/usr/bin/env python3
"""
Suppression Rule Checker
Checks if errors should be suppressed based on database rules.
"""

import psycopg2
from datetime import datetime
from typing import Tuple, Optional, Dict, List
import logging

# Set up logging
logger = logging.getLogger('resolvix.suppression')


class SuppressionRuleChecker:
    """
    Checks if errors should be suppressed based on suppression rules.
    
    Features:
    - Caches rules for 60 seconds to reduce database queries
    - Case-insensitive text matching
    - Node-specific or global rules
    - Updates match statistics when rules trigger
    """
    
    def __init__(self, db_connection, cache_ttl: int = 60):
        """
        Initialize the suppression checker.
        
        Args:
            db_connection: psycopg2 database connection
            cache_ttl: Cache time-to-live in seconds (default: 60)
        """
        self.db = db_connection
        self._rules_cache: Optional[List[Dict]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = cache_ttl
        
        # Statistics
        self.total_checks = 0
        self.total_suppressed = 0
        
        logger.info("SuppressionRuleChecker initialized with cache TTL: %d seconds", cache_ttl)
    
    def should_suppress(self, error_message: str, node_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if an error should be suppressed.
        
        Args:
            error_message: The error message text to check
            node_id: The node ID (system IP) where the error occurred
        
        Returns:
            Tuple of (should_suppress: bool, matched_rule: dict or None)
            
        Example:
            suppressed, rule = checker.should_suppress("Disk space low", "192.168.1.100")
            if suppressed:
                print(f"Suppressed by rule: {rule['name']}")
        """
        self.total_checks += 1
        
        # Refresh cache if needed
        if self._should_refresh_cache():
            self._load_rules()
        
        # If no rules loaded, don't suppress
        if not self._rules_cache:
            return False, None
        
        # Check each rule
        for rule in self._rules_cache:
            if self._matches_rule(error_message, node_id, rule):
                # Update statistics in database
                self._increment_match_count(rule['id'])
                
                # Update local statistics
                self.total_suppressed += 1
                
                logger.info(
                    "Error suppressed by rule ID %d: '%s' (node_id=%s)",
                    rule['id'],
                    rule['name'],
                    node_id
                )
                
                return True, rule
        
        # No rule matched
        return False, None
    
    def _should_refresh_cache(self) -> bool:
        """
        Check if the rules cache needs to be refreshed.
        
        Returns:
            True if cache should be refreshed, False otherwise
        """
        # Cache never loaded
        if self._rules_cache is None:
            return True
        
        # Cache timestamp not set
        if self._cache_timestamp is None:
            return True
        
        # Check if TTL expired
        elapsed = (datetime.now() - self._cache_timestamp).total_seconds()
        if elapsed >= self._cache_ttl:
            logger.debug("Cache expired (%.1f seconds old), refreshing...", elapsed)
            return True
        
        return False
    
    def _load_rules(self):
        """
        Load active, non-expired suppression rules from database.
        
        This method is called automatically when the cache expires.
        Loads only rules where:
        - enabled = true
        - expires_at is NULL (forever) OR expires_at > NOW()
        """
        try:
            cursor = self.db.cursor()
            
            query = """
                SELECT
                    id,
                    name,
                    match_text,
                    node_ip,
                    duration_type,
                    expires_at
                FROM suppression_rules
                WHERE enabled = true
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY id
            """
            
            cursor.execute(query)
            
            # Convert rows to dictionaries
            self._rules_cache = []
            for row in cursor.fetchall():
                self._rules_cache.append({
                    'id': row[0],
                    'name': row[1],
                    'match_text': row[2],
                    'node_ip': row[3],
                    'duration_type': row[4],
                    'expires_at': row[5]
                })
            
            self._cache_timestamp = datetime.now()
            cursor.close()
            
            logger.info("Loaded %d active suppression rules", len(self._rules_cache))
            
            # Log each rule for debugging
            for rule in self._rules_cache:
                logger.debug(
                    "Rule ID %d: '%s' - match_text='%s', node_ip=%s",
                    rule['id'],
                    rule['name'],
                    rule['match_text'],
                    rule['node_ip'] or 'ALL'
                )
        
        except Exception as e:
            logger.error("Error loading suppression rules: %s", e)
            # Keep old cache if load fails
            if self._rules_cache is None:
                self._rules_cache = []
    
    def _matches_rule(self, error_message: str, node_id: str, rule: Dict) -> bool:
        """
        Check if an error matches a specific rule.
        
        Args:
            error_message: The error message text
            node_id: The node ID (system IP) where error occurred
            rule: The rule dictionary to check against
        
        Returns:
            True if error matches rule, False otherwise
        """
        # Check 1: Node filtering
        # If rule has node_ip set, error must be from that node
        # If rule.node_ip is None, it applies to all nodes
        if rule['node_ip'] is not None and rule['node_ip'] != node_id:
            return False
        
        # Check 2: Text matching (case-insensitive)
        match_text_lower = rule['match_text'].lower()
        error_message_lower = error_message.lower()
        
        if match_text_lower not in error_message_lower:
            return False
        
        # All checks passed - this rule matches!
        return True
    
    def _increment_match_count(self, rule_id: int):
        """
        Update rule statistics when a match occurs.
        
        Increments match_count and sets last_matched_at timestamp.
        This runs in background - errors are logged but don't stop processing.
        
        Args:
            rule_id: The ID of the rule that matched
        """
        try:
            cursor = self.db.cursor()
            
            update_query = """
                UPDATE suppression_rules
                SET
                    match_count = match_count + 1,
                    last_matched_at = NOW()
                WHERE id = %s
            """
            
            cursor.execute(update_query, (rule_id,))
            self.db.commit()
            cursor.close()
            
            logger.debug("Updated match statistics for rule ID %d", rule_id)
        
        except Exception as e:
            logger.error("Error updating match count for rule %d: %s", rule_id, e)
            # Rollback but continue - stats update failure shouldn't break daemon
            try:
                self.db.rollback()
            except:
                pass
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about suppression activity.
        
        Returns:
            Dictionary with statistics:
            - total_checks: Total errors checked
            - total_suppressed: Total errors suppressed
            - suppression_rate: Percentage suppressed
            - cached_rules: Number of rules in cache
        """
        suppression_rate = 0.0
        if self.total_checks > 0:
            suppression_rate = (self.total_suppressed / self.total_checks) * 100
        
        return {
            'total_checks': self.total_checks,
            'total_suppressed': self.total_suppressed,
            'suppression_rate': suppression_rate,
            'cached_rules': len(self._rules_cache) if self._rules_cache else 0
        }
    
    def force_reload(self):
        """
        Force an immediate reload of rules from database.
        
        Useful for testing or when you know rules have changed.
        """
        logger.info("Forcing reload of suppression rules")
        self._load_rules()
