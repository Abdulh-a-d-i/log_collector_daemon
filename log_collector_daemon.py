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
        self.first_run = True
        
        os.makedirs(save_dir, exist_ok=True)
        self.output_file = os.path.join(save_dir, "latest_logs.tar.gz")
        logger.info(f"Initialized with log_file_path={log_file_path}, save_dir={save_dir}, api_url={api_url}")

    def parse_log_timestamp(self, line):
        try:
            if line.startswith('20'):
                log_time_str = line[:26]
                return datetime.strptime(log_time_str, '%Y-%m-%d %H:%M:%S.%f %z')
            else:
                log_time_str = line[:15]
                return datetime.strptime(log_time_str, '%b %d %H:%M:%S')
        except (ValueError, IndexError):
            logger.warning(f"Failed to parse timestamp in line: {line[:50]}...")
            return None

    def get_initial_logs(self):
        try:
            with open(self.log_file_path, 'r') as f:
                logs = tailer.tail(f, self.initial_lines)
                logger.info(f"Read {len(logs)} initial logs")
                return logs
        except Exception as e:
            logger.error(f"Error reading initial logs: {e}")
            return []

    def get_logs_last_minute(self):
        current_time = datetime.now()
        one_minute_ago = current_time - timedelta(minutes=1)
        
        try:
            # Read last 500 lines (you can adjust this if logs are sparse/dense)
            with open(self.log_file_path, 'r') as f:
                recent_lines = tailer.tail(f, 50)
    
            logs = []
            for line in recent_lines:
                log_time = self.parse_log_timestamp(line)
                if log_time:
                    # Adjust if log time has no year info
                    if log_time.year == 1900:
                        log_time = log_time.replace(year=current_time.year)
                    if one_minute_ago <= log_time <= current_time:
                        logs.append(line)
            
            logger.info(f"Collected {len(logs)} logs from last minute at {current_time}")
            return logs
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            return []

    def create_tar_gz(self, logs):
        try:
            if os.path.exists(self.output_file):
                os.remove(self.output_file)
                logger.info(f"Removed old {self.output_file}")

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as temp_file:
                temp_file.write(''.join(logs))
                temp_file_path = temp_file.name

            with tarfile.open(self.output_file, "w:gz") as tar:
                tar.add(temp_file_path, arcname="logs.log")
            
            os.remove(temp_file_path)
            file_size = os.path.getsize(self.output_file)
            logger.info(f"Created tar.gz file at {self.output_file} with size {file_size} bytes at {datetime.now()}")
        except Exception as e:
            logger.error(f"Error creating tar.gz: {e}")

    def send_to_api(self):
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
        logger.info("Starting Log Collector Daemon")
        while True:
            try:
                logs = self.get_logs_last_minute()
                if logs:
                    self.create_tar_gz(logs)
                    if self.api_url:
                        self.send_to_api()
                else:
                    logger.info(f"No new logs found at {datetime.now()}")
                time.sleep(60)
            except Exception as e:
                logger.error(f"Daemon error: {e} at {datetime.now()}")
                time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python log_collector_daemon.py <log_file_path> <save_dir> [api_url]")
        sys.exit(1)
    
    log_file_path = sys.argv[1]
    save_dir = sys.argv[2]
    api_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    daemon = LogCollectorDaemon(log_file_path, save_dir, api_url)
    daemon.run()
