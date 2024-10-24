"""
SystemScanner: Runtime Versions Module

This module is responsible for detecting and reporting versions
of various runtime environments installed on the system, such as
Java, Python, and Node.js.

It uses a factory pattern to manage different runtime version checks.
"""

import os
import sys
import subprocess


class RuntimeFactory:
    def __init__(self):
        self.executors = {
            "java": ["java", "-version"],
            "node": ["node", "-v"],
            "python": lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }

    def get_version(self, runtime_name):
        command = self.executors.get(runtime_name)
        if callable(command):
            return command()
        elif command:
            return self.execute_command(command)
        return f"{runtime_name} not supported"

    def execute_command(self, command):
        try:
            result = subprocess.run(
                command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, check=True
            )
            return result.stdout.decode().strip()
        except subprocess.CalledProcessError as e:
            return f"Command failed: {e}"
        except FileNotFoundError:
            return f"{command[0]} not found"

    def get_otel_collector_info(self):
        otelcol_path = None
        version_result = None

        if os.name == "nt":  # Windows
            result = subprocess.run(
                ["where", "otelcol"], capture_output=True, text=True
            )
            if result.returncode == 0:
                otelcol_path = result.stdout.strip().split("\n")[0]
                version_result = self.execute_command([otelcol_path, "--version"])
        else:  # Unix-like systems
            otelcol_path = "/usr/bin/otelcol"
            if not os.path.exists(otelcol_path):
                try:
                    result = subprocess.run(
                        ["which", "otelcol"], capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        otelcol_path = result.stdout.strip().split("\n")[0]
                except Exception as e:
                    return f"Error finding OpenTelemetry Collector: {str(e)}"

            version_result = self.execute_command([otelcol_path, "--version"])

        if not otelcol_path:
            return "OpenTelemetry Collector not found", None

        # Check if the result contains both the version and path
        parts = version_result.split('\n')
        for part in parts:
            if 'OpenTelemetry Collector' in part:
                version_info, path_info = part.strip().split(':')
                return version_info.strip(), path_info.strip()

        return (
            f"Unable to determine OpenTelemetry Collector version",
            None,
        )
