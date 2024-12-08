import time
import sys
import asyncio
from download_manager.logger.color_formatter import logger


class ProgressTracker:
    def __init__(self, total_size):
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()
        self.last_update = 0
        self.update_interval = 0.5  # Update every 500ms
        self.update_callback = None
        self.download_id = None
        self.url = None
        self.filename = None

    def set_update_callback(self, callback, download_id, url, filename):
        """Set the callback function for WebSocket updates."""
        self.update_callback = callback
        self.download_id = download_id
        self.url = url
        self.filename = filename

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
            f"% {self.current_progress_percent()}"
        )

        # Clear line and print update
        sys.stdout.write('\033[K' + progress_msg)
        sys.stdout.flush()
        self.last_update = current_time

        # Send progress update via WebSocket
        if self.update_callback and self.download_id:
            progress_percent = int(
                (self.downloaded_size / self.total_size) * 100)
            asyncio.create_task(self.update_callback(
                self.download_id,
                'downloading',
                progress_percent,
                None
            ))

    def log_message(self, message, level="info"):
        sys.stdout.write('\n')
        sys.stdout.flush()

        if level == "error":
            logger.error(message)
        elif level == "success":
            logger.success(message)
        else:
            logger.info(message)

    def current_progress_percent(self):
        return int((self.downloaded_size / self.total_size) * 100) if self.total_size > 0 else 0
