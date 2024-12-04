import logging

# Custom log level for success
SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")

# ANSI escape codes for colors
class LogColors:
  RESET = "\033[0m"
  RED = "\033[91m"
  GREEN = "\033[92m"
  YELLOW = "\033[93m"


# Custom formatter for colored logs
class ColoredFormatter(logging.Formatter):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

  def format(self, record):
    if record.levelno == logging.ERROR:
      record.msg = f"{LogColors.RED}{record.msg}{LogColors.RESET}"
    elif record.levelno == logging.INFO:
      record.msg = f"{LogColors.YELLOW}{record.msg}{LogColors.RESET}"
    elif record.levelno == logging.DEBUG:
      record.msg = f"{LogColors.GREEN}{record.msg}{LogColors.RESET}"
    elif record.levelno == SUCCESS:
      record.msg = f"{LogColors.GREEN}{record.msg}{LogColors.RESET}"
    return super().format(record)


# Configure logging
formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')

handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)


def log_success(msg, *args, **kwargs):
  logger.log(SUCCESS, msg, *args, **kwargs)


# add custom success method to the logger instance
logger.success = log_success
