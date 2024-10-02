#!/usr/bin/env python3

"""
SystemScanner
Version 0.2
Author: Brandon Blinderman
"""

from os_info import get_os_info
from runtime_versions import RuntimeFactory
from dotnet_framework import get_dotnet_versions
from logger_config import configure_logging


def main():
    logger = configure_logging()

    os_name, os_version, os_architecture = get_os_info()
    logger.info(f"Operating System: {os_name}")
    logger.info(f"OS Version: {os_version}")
    logger.info(f"OS Architecture: {os_architecture}")

    factory = RuntimeFactory()

    java_version = factory.get_version("java")
    logger.info(f"Java Version: {java_version}")

    python_version = factory.get_version("python")
    logger.info(f"Python Version: {python_version}")

    node_version = factory.get_version("node")
    logger.info(f"Node.js Version: {node_version}")

    otel_version, otel_path = factory.get_otel_collector_info()
    logger.info(f"OpenTelemetry Collector Version: {otel_version}")
    if otel_path:
        logger.info(f"OpenTelemetry Collector Path: {otel_path}")
    else:
        logger.info("OpenTelemetry Collector Path: Not found")

    if os_name == "Windows":
        dotnet_versions = get_dotnet_versions()
        if isinstance(dotnet_versions, list):
            logger.info("Installed .NET Framework Versions:")
            for name, version in dotnet_versions:
                logger.info(f"{name}: {version}")
        else:
            logger.error(dotnet_versions)


if __name__ == "__main__":
    main()
