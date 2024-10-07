import logging
import re

class SensitiveFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.sensitive_patterns = [
            (re.compile(r'token=[^&\s]+'), 'token=[REDACTED]'),
            (re.compile(r'api_key=[^&\s]+'), 'api_key=[REDACTED]'),
        ]

    def format(self, record):
        message = super().format(record)
        for pattern, replacement in self.sensitive_patterns:
            message = pattern.sub(replacement, message)
        return message

def setup_logging(log_level, log_file='technisync.log'):
    logger = logging.getLogger()
    logger.setLevel(log_level)

    formatter = SensitiveFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)