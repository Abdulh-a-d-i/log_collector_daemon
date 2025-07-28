import os
import sys
import time
import tarfile
import requests
from datetime import datetime, timedelta
import tailer
import logging
import tempfile

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LogCollectorDaemon:
    def __init__(self, log_file_path, save_dir, api_url=None, initial_lines=100):
        self.log_file_path = log_file_path
        self.save_dir = save_dir
        self.api_url = api_url
        self.initial_lines = initial_lines
        self.last_processed_time = None
        
        # Ensure save directory exists
        os.makedirs(save_dir, exist_ok=True)
        self.output_file = os.path.join(save_dir, "latest_logs.tar.gz")
        self.first_run = True

    def parse_log_timestamp(self, line):
        """Parse timestamp from log line, supporting both formats"""
        try:
            # Try ISO format (e.g., 2025-07-27 22:41:18.533 +05:00)
            if line.startswith('20'):
                log_time_str = line[:26]  # Up to the first space after time
                return datetime.strptime(log_time_str, '%Y-%m-%d %H:%M:%S.%f %z')
            # Try syslog format (e.g., Jul 27 22:41:17)
            else:
                log_time_str = line[:15]  # Up to the first space after time
                return datetime.strptime(log_time_str, '%b %d %H:%M:%S')
        except (ValueError, IndexError):
            return None

    def get_initial_logs(self):
        """Read last N lines on first run"""
        try:
            with open(self.log_file_path, 'r') as f:
                return tailer.tail(f, self.initial_lines)
        except Exception as e:
            logger.error(f"Error reading initial logs: {e}")
            return []

    def get_logs_last_minute(self):
        """Read logs generated in the last minute"""
        current_time = datetime.now()
        one_minute_ago = current_time - timedelta(minutes=1)
        
        if self.first_run:
            self.first_run = False
            return self.get_initial_logs()
        
        if not self.last_processed_time:
            self.last_processed_time = one_minute_ago
        
        logs = []
        try:
            with open(self.log_file_path, 'r') as f:
                for line in f:
                    log_time = self.parse_log_timestamp(line)
                    if log_time and self.last_processed_time < log_time <= current_time:
                        logs.append(line)
            self.last_processed_time = current_time
            return logs
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            return []

    def create_tar_gz(self, logs):
        """Create compressed tar.gz file from logs, overwriting existing file"""
        try:
            # Remove old file if exists
            if os.path.exists(self.output_file):
                os.remove(self.output_file)

            # Write logs to temporary file and compress
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as temp_file:
                temp_file.write(''.join(logs))
                temp_file_path = temp_file.name

            with tarfile.open(self.output_file, "w:gz") as tar:
                tar.add(temp_file_path, arcname="logs.log")
            
            os.remove(temp_file_path)
            logger.info(f"Created tar.gz file at {self.output_file} with size {os.path.getsize(self.output_file)} bytes")
        except Exception as e:
            logger.error(f"Error creating tar.gz: {e}")

    def send_to_api(self):
        """Send compressed file to API endpoint"""
        if not self.api_url:
            return
        
        try:
            with open(self.output_file, 'rb') as f:
                files = {'file': ('latest_logs.tar.gz', f)}
                response = requests.post(self.api_url, files=files, timeout=10)
                if response.status_code == 200:
                    logger.info("Successfully sent logs to API")
                else:
                    logger.error(f"API request failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending to API: {e}")

    def run(self):
        """Main daemon loop"""
        logger.info("Starting Log Collector Daemon")
        while True:
            try:
                # Get logs
                logs = self.get_logs_last_minute()
                
                if logs:
                    # Create compressed file
                    self.create_tar_gz(logs)
                    
                    # Send to API if URL is provided
                    if self.api_url:
                        self.send_to_api()
                else:
                    logger.info("No new logs found")
                
                # Wait for 1 minute
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Shutting down Log Collector Daemon")
                break
            except Exception as e:
                logger.error(f"Daemon error: {e}")
                time.sleep(60)  # Continue running even on errors

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python log_collector_daemon.py <log_file_path> <save_dir> [api_url]")
        sys.exit(1)
    
    log_file_path = sys.argv[1]
    save_dir = sys.argv[2]
    api_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    daemon = LogCollectorDaemon(log_file_path, save_dir, api_url)
    daemon.run()
