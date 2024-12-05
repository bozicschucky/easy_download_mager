import time
import sys
from download_manager.logger.color_formatter import logger


class ProgressTracker:
    def __init__(self, total_size):
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()
        # Disable logging for progress updates
        self.last_update = 0
        self.update_interval = 0.5  # Update every 500ms

    def update(self, chunk_size):
        self.downloaded_size += chunk_size
        current_time = time.time()

        # Throttle updates to prevent too frequent refreshes
        if (current_time - self.last_update) < self.update_interval:
            return

        elapsed_time = current_time - self.start_time
        download_speed = self.downloaded_size / elapsed_time
        remaining_time = (self.total_size - self.downloaded_size) / \
            download_speed if download_speed > 0 else 0

        # Create progress message
        progress_msg = (
            f"\rDownloading... {
                self.downloaded_size / (1024 * 1024):.1f}/{self.total_size / (1024 * 1024):.1f} MB "
            f"{download_speed / (1024 * 1024):.1f} MB/s {
                time.strftime('%H:%M:%S', time.gmtime(remaining_time))}"
        )

        # Clear line and print update
        sys.stdout.write('\033[K' + progress_msg)
        sys.stdout.flush()
        self.last_update = current_time

    def log_message(self, message, level="info"):
        sys.stdout.write('\n')
        sys.stdout.flush()

        if level == "error":
            logger.error(message)
        elif level == "success":
            logger.success(message)
        else:
            logger.info(message)
