"""
Logger Helper Module.

Provides a unified logging interface for the entire project, ensuring all modules
write to the same daily log file with a consistent format.
"""

import json
import datetime
import logging
from pathlib import Path
from typing import Optional, Dict, Any


class LoggerHelper:
    """
    Unified logging and state management helper for Petpooja automation.
    Implemented to ensure a single project-wide logger instance.
    """

    _logger: Optional[logging.Logger] = None

    def __init__(
        self, state_path: str = "execution/state.json", log_dir: str = "logs"
    ) -> None:
        """
        Initialize the logger helper.

        Args:
            state_path: Path to the JSON state file.
            log_dir: Directory where logs should be stored.
        """
        self.state_path = Path(state_path)
        self.log_dir = Path(log_dir)

        # Ensure directories exist
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._init_state()
        self._cleanup_old_logs()
        self._setup_logging()

    def _cleanup_old_logs(self) -> None:
        """Remove redundant and 30+ day old logs."""
        try:
            thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
            
            for log_file in self.log_dir.glob("*"):
                # Always remove 'run_log_*.log' as it's the old format
                if log_file.name.startswith("run_log_"):
                    log_file.unlink()
                    continue

                # Remove regular log files if older than 30 days
                if log_file.is_file():
                    mtime = datetime.datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < thirty_days_ago:
                        log_file.unlink()
        except Exception as e:
            # We don't want a cleanup failure to crash the whole app
            print(f"Warning: Log cleanup failed: {e}")

    def _setup_logging(self) -> None:
        """Configure project-wide logging to a daily rotating file and console."""
        # Base log filename - TimedRotatingFileHandler will append timestamps during rotation
        self.log_file = self.log_dir / "automation_run.log"

        # Static logger initialization to ensure all instances share the same logger
        if LoggerHelper._logger is None:
            logger = logging.getLogger("PetpoojaApp")
            logger.setLevel(logging.INFO)

            # Avoid duplicate handlers
            if not logger.handlers:
                from logging.handlers import TimedRotatingFileHandler

                # Daily rotation at midnight, keep 30 days of logs
                file_handler = TimedRotatingFileHandler(
                    self.log_file,
                    when="midnight",
                    interval=1,
                    backupCount=30,
                    encoding="utf-8",
                )
                # Ensure the rotated files have a clear date format
                file_handler.suffix = "%Y-%m-%d"

                # Updated format to be more professional: [YYYY-MM-DD HH:MM:SS] [LEVEL] MESSAGE
                formatter = logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)

                # Console handler
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

            LoggerHelper._logger = logger

        self.logger = LoggerHelper._logger

    def add_handler(self, handler: logging.Handler) -> None:
        """Add an external handler to the logger (e.g., for GUI)."""
        if self.logger:
            # Check if this type of handler is already added
            if not any(isinstance(h, type(handler)) for h in self.logger.handlers):
                self.logger.addHandler(handler)

    def _init_state(self) -> None:
        """Initialize the state JSON file if it doesn't exist."""
        if not self.state_path.exists():
            initial_state = {"last_processed_date": None, "processed_dates": {}}
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(initial_state, f, indent=4)

    def log_execution(self, level: str, message: str) -> None:
        """
        Log a message at the specified level.

        Args:
            level: Logging level (INFO, ERROR, WARNING, DEBUG).
            message: Message to log.
        """
        lvl = level.upper()
        if lvl == "INFO":
            self.logger.info(message)
        elif lvl == "ERROR":
            self.logger.error(message)
        elif lvl == "WARNING":
            self.logger.warning(message)
        elif lvl == "DEBUG":
            self.logger.debug(message)
        else:
            self.logger.info(message)

    def get_last_processed_date(self) -> Optional[datetime.date]:
        """
        Retrieve the last successfully processed date from state.

        Returns:
            The date object of the last processed record, or None.
        """
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                last_date_str = state.get("last_processed_date")
                if last_date_str:
                    return datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        except (json.JSONDecodeError, FileNotFoundError, ValueError):
            return None
        return None

    def mark_date_completed(
        self, report_date: datetime.date, file_path: str, download_link: str
    ) -> None:
        """
        Mark a report date as completed in the project state.

        Args:
            report_date: The date processed.
            file_path: Local path where the file was saved.
            download_link: Original download URL.
        """
        date_str = report_date.strftime("%Y-%m-%d")
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state: Dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            state = {"last_processed_date": None, "processed_dates": {}}

        state["last_processed_date"] = date_str
        state["processed_dates"][date_str] = {
            "status": "COMPLETED",
            "file_path": file_path,
            "download_link": download_link,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)


if __name__ == "__main__":
    # Test block
    helper = LoggerHelper()
    helper.log_execution("INFO", "Logger initialized in standalone test.")
