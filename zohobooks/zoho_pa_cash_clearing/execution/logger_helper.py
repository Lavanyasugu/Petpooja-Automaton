
import logging
import os
from datetime import datetime

class LoggerHelper:
    def __init__(self, name="zobobooks_automation"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            
            # Console handler
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
            
            # File handler
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            fh = logging.FileHandler(os.path.join(log_dir, f"execution_{datetime.now().strftime('%Y%m%d')}.log"))
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)
