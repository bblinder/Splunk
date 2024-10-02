"""
SystemScanner: Logging Configuration Module

This module sets up the logging configuration for the SystemScanner project.
It provides a centralized way to configure logging levels and formats.
"""

import logging


def configure_logging():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger(__name__)
