import time


class BandwidthMonitor:
    def __init__(self, window_size: int = 5):
        self.transfer_logs = []
        self.window_size = window_size
        self.start_time = time.time()

    def log_transfer(self, bytes_transferred: int):
        current_time = time.time()
        self.transfer_logs.append((current_time, bytes_transferred))

        # Clean old logs
        cutoff = current_time - self.window_size
        self.transfer_logs = [(t, b)
                              for t, b in self.transfer_logs if t > cutoff]

    def get_speed(self) -> float:
        """Get current speed in bytes/second"""
        if not self.transfer_logs:
            return 0.0
        total_bytes = sum(b for _, b in self.transfer_logs)
        time_diff = max(time.time() - self.start_time, 0.001)
        return total_bytes / time_diff
