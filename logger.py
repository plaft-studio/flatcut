"""
Logging utility for Blender addon development
Provides both file and console logging with debug mode support
"""

import logging
import os
from datetime import datetime
from pathlib import Path


class BlenderAddonLogger:
    """Logger for Blender addon with file and console output"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.logger = logging.getLogger("craft-addon")
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if self.logger.handlers:
            return

        # Create logs directory. Prefer a user-writable location managed by
        # Blender's extension system (the add-on's own install directory may
        # be read-only or wiped on update when distributed as an extension);
        # fall back to the legacy in-place "logs" folder for dev installs.
        log_dir = None
        try:
            import bpy
            log_dir = Path(bpy.utils.extension_path_user(__package__, path="logs", create=True))
        except Exception:
            log_dir = None
        if log_dir is None:
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(exist_ok=True)

        # File handler - detailed logs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"craft_addon_{timestamp}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(funcName)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler - important messages only
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '[Craft] %(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Keep reference to latest log file
        latest_link = log_dir / "latest.log"
        if latest_link.exists():
            latest_link.unlink()
        try:
            latest_link.symlink_to(log_file.name)
        except:
            pass  # Symlink might fail on some systems

        self._initialized = True
        self.logger.info(f"Logger initialized. Log file: {log_file}")

    def debug(self, message):
        """Debug level logging (verbose)"""
        self.logger.debug(message)

    def info(self, message):
        """Info level logging"""
        self.logger.info(message)

    def warning(self, message):
        """Warning level logging"""
        self.logger.warning(message)

    def error(self, message, exc_info=False):
        """Error level logging"""
        self.logger.error(message, exc_info=exc_info)

    def critical(self, message, exc_info=True):
        """Critical error logging"""
        self.logger.critical(message, exc_info=exc_info)

    def set_debug_mode(self, enabled=True):
        """Enable/disable debug mode for console output"""
        for handler in self.logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(logging.DEBUG if enabled else logging.INFO)
        self.info(f"Debug mode: {'enabled' if enabled else 'disabled'}")


# Global logger instance
_logger = None


def get_logger():
    """Get the global logger instance"""
    global _logger
    if _logger is None:
        _logger = BlenderAddonLogger()
    return _logger


def log_operator_call(operator_name, context_info=None):
    """Decorator to log operator calls"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger()
            logger.debug(f"Operator called: {operator_name}")
            if context_info:
                logger.debug(f"Context: {context_info}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Operator finished: {operator_name} -> {result}")
                return result
            except Exception as e:
                logger.error(f"Operator failed: {operator_name}", exc_info=True)
                raise
        return wrapper
    return decorator


# Convenience functions
def debug(msg):
    get_logger().debug(msg)

def info(msg):
    get_logger().info(msg)

def warning(msg):
    get_logger().warning(msg)

def error(msg, exc_info=False):
    get_logger().error(msg, exc_info=exc_info)

def critical(msg, exc_info=True):
    get_logger().critical(msg, exc_info=exc_info)
