import time

from download_manager.logger.color_formatter import logger

class ProgressTracker:
    def __init__(self, total_size):
        self.total_size = total_size
        self.downloaded_size = 0
        self.start_time = time.time()

    def update(self, chunk_size):
        self.downloaded_size += chunk_size
        elapsed_time = time.time() - self.start_time
        download_speed = self.downloaded_size / elapsed_time
        remaining_time = (self.total_size - self.downloaded_size) / \
            download_speed if download_speed > 0 else 0
        logger.info(
            f"Downloading... {
                self.downloaded_size / (1024 * 1024):.1f}/{self.total_size / (1024 * 1024):.1f} MB "
            f"{download_speed / (1024 * 1024):.1f} MB/s {
                time.strftime('%H:%M:%S', time.gmtime(remaining_time))}"
        )

    def log_message(self, message, level="info"):
        if level == "error":
            logger.error(message)
        elif level == "success":
            logger.success(message)
        else:
            logger.info(message)
