
class DownloadError(Exception):
    """Base exception for download errors"""

    def __init__(self, message: str, status_code: int = None):
      super().__init__(message)
      self.status_code = status_code
      self.message = message

    def __str__(self):
      if self.status_code:
        return f"{self.message} (Status code: {self.status_code})"
      return self.message


class NetworkError(DownloadError):
    """Network-related errors"""
    pass

    def __init__(self, message: str, status_code: int = None, retry_in: int = None):
      super().__init__(message, status_code)
      self.retry_in = retry_in

    @property
    def is_retryable(self) -> bool:
      """Check if error is retryable based on status code"""
      return self.status_code in {408, 429, 500, 502, 503, 504}

    @property
    def should_wait(self) -> bool:
      """Check if we should wait before retrying"""
      return self.retry_in is not None and self.retry_in > 0


class StorageError(DownloadError):
    """Storage-related errors"""
    pass

    def __init__(self, message: str, available_space: int = None):
      super().__init__(message)
      self.available_space = available_space

    @property
    def has_space_info(self) -> bool:
      """Check if error has available space information"""
      return self.available_space is not None

    @property
    def needed_space(self) -> int:
      """Get needed space if available from error message"""
      if 'need' in self.message.lower():
        try:
          return int(self.message.split()[-2])
        except (IndexError, ValueError):
          return None
      return None
