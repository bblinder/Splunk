#!/usr/bin/env python3

"""
Version 0.1
Author: Brandon Blinderman
"""

import subprocess
from os_info import get_os_info
from runtime_versions import RuntimeFactory
from dotnet_framework import get_dotnet_versions
from logger_config import configure_logging

def otel_collector_version(os_name):
    try:
        if os_name == "Windows":
            # For Windows, we might need to adjust the path or command
            result = subprocess.run(["where", "otelcol"], capture_output=True, text=True)
            if result.returncode == 0:
                otelcol_path = result.stdout.strip().split('\n')[0]
                version_result = subprocess.run([otelcol_path, "--version"], capture_output=True, text=True)
            else:
                return "OpenTelemetry Collector not found"
        else:
            # For Linux and macOS
            version_result = subprocess.run(["/bin/otelcol", "--version"], capture_output=True, text=True)

        if version_result.returncode == 0:
            # The version info might be in stdout or stderr, depending on the collector's output
            version_info = version_result.stdout or version_result.stderr
            return version_info.strip()
        else:
            return "Unable to determine OpenTelemetry Collector version"
    except FileNotFoundError:
        return "OpenTelemetry Collector not found"
    except Exception as e:
        return f"Error checking OpenTelemetry Collector version: {str(e)}"

def main():
    logger = configure_logging()

    os_name, os_version = get_os_info()
    logger.info(f"Operating System: {os_name}")
    logger.info(f"OS Version: {os_version}")

    factory = RuntimeFactory()

    java_version = factory.get_version("java")
    logger.info(f"Java Version: {java_version}")

    python_version = factory.get_version("python")
    logger.info(f"Python Version: {python_version}")

    node_version = factory.get_version("node")
    logger.info(f"Node.js Version: {node_version}")

    otel_version = otel_collector_version(os_name)
    logger.info(f"OpenTelemetry Collector Version: {otel_version}")

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
