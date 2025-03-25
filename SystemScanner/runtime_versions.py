"""
SystemScanner: Runtime Versions Module

This module is responsible for detecting and reporting versions
of various runtime environments installed on the system, such as
Java, Python, and Node.js.

It uses a factory pattern to manage different runtime version checks.
"""

import os
import json
import sys
import subprocess
import logging


class CommandExecutor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, command):
        try:
            result = subprocess.run(
                command,
                stderr=subprocess.STDOUT,  # Capture both stdout and stderr
                stdout=subprocess.PIPE,
                check=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if e.stderr:
                self.logger.error(f"Command failed: {e}", exc_info=False)
                return f"Failed to run command '{' '.join(command)}': {e.stderr.strip()}"
            else:
                self.logger.error(f"Command failed without stderr: {e}", exc_info=False)
                return f"Failed to run command '{' '.join(command)}': No error message available"
        except FileNotFoundError:
            self.logger.error(f"{command[0]} not found", exc_info=False)
            return f"{command[0]} not found"
        except Exception as e:
            self.logger.error(
                f"Unexpected error during command execution: {str(e)}", exc_info=False
            )
            return f"Unexpected error during command execution: {str(e)}"
        finally:
            # Optionally log the executed command for debugging purposes
            self.logger.debug(f"Executed command: {' '.join(command)}")


class RuntimeFactory:
    def __init__(self):
        self.executors = {
            "java": ["java", "-version"],
            "node": ["node", "-v"],
            "python": lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} (Current Shell Environment)",
        }
        self.logger = logging.getLogger(__name__)
        self.command_executor = CommandExecutor()

    def get_version(self, runtime_name):
        command = self.executors.get(runtime_name)
        if callable(command):
            return command()
        elif command:
            output = self.command_executor.execute(command)
            if "java" in command[0]:
                # Extract version from the combined stdout and stderr for java -version
                import re

                match = re.search(r'"(\d+\.\d+\.\d+)"', output)
                if match:
                    return match.group(1)
                else:
                    self.logger.error(f"Failed to parse Java version from: {output}", exc_info=False)
                    return f"Failed to parse Java version"
            return output
        return f"{runtime_name} not supported"

    def get_otel_collector_info(self):
        try:
            # Check for otelcol executable
            if os.name == "nt":  # Windows
                result = subprocess.run(
                    ["where", "otelcol"], capture_output=True, text=True
                )
                if result.returncode == 0:
                    otelcol_path = result.stdout.strip().split("\n")[0]
                else:
                    return "OpenTelemetry Collector not found", None
            else:  # Unix-like systems
                if os.path.exists("/usr/bin/otelcol"):
                    otelcol_path = "/usr/bin/otelcol"
                else:
                    result = subprocess.run(
                        ["which", "otelcol"], capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        otelcol_path = result.stdout.strip()
                    else:
                        return "OpenTelemetry Collector not found", None

            # Try to get version
            try:
                version_result = subprocess.run(
                    [otelcol_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if version_result.returncode == 0:
                    # Extract just the version number
                    version_output = version_result.stdout.strip().split("\n")[0]
                    # Extract just the version part (vX.Y.Z)
                    import re

                    version_match = re.search(r"v\d+\.\d+\.\d+", version_output)
                    if version_match:
                        version = version_match.group(0)
                    else:
                        self.logger.error(
                            f"Unable to determine OpenTelemetry Collector version from: {version_output}",
                            exc_info=False
                        )
                        return "Version not found", otelcol_path
                    return version, otelcol_path
                else:
                    self.logger.error(
                        f"Error running OpenTelemetry Collector version command with output: {version_result.stderr.strip()}",
                        exc_info=False
                    )
                    return (
                        f"Error determining OpenTelemetry Collector version: {version_result.stderr.strip()}",
                        otelcol_path,
                    )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                self.logger.error(
                    "Timed out or error running the OpenTelemetry Collector version command.",
                    exc_info=False
                )
                return (
                    "Timed out or error running the OpenTelemetry Collector version command.",
                    otelcol_path,
                )

        except Exception as e:
            self.logger.error(
                f"Error getting OpenTelemetry Collector info: {str(e)}", exc_info=False
            )
            return f"Error getting OpenTelemetry Collector info: {str(e)}", None

    def is_running_in_kubernetes(self):
        """Check if we're running inside a Kubernetes environment"""
        try:
            result = subprocess.run(
                ["cat", "/var/run/secrets/kubernetes.io/serviceaccount/token"],
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0 and result.stdout.strip()
        except Exception as e:
            self.logger.error(
                f"Error checking Kubernetes environment: {str(e)}",
                exc_info=False
            )
            return False

    def get_otel_configmaps(self):
        """Get OpenTelemetry collector ConfigMaps using only standard libraries"""
        if not self.is_running_in_kubernetes():
            self.logger.warning("Not running in a Kubernetes environment")
            return []

        try:
            # Use kubectl command through subprocess
            result = subprocess.run(
                ["kubectl", "get", "configmap", "--all-namespaces", "-o", "json"],
                capture_output=True,
                text=True,
                check=True,
            )

            configmaps = json.loads(result.stdout)
            otel_configmaps = []

            # Filter for OpenTelemetry related ConfigMaps
            for item in configmaps.get("items", []):
                name = item.get("metadata", {}).get("name", "")
                namespace = item.get("metadata", {}).get("namespace", "")

                # Look for common OpenTelemetry ConfigMap naming patterns
                if any(
                    pattern in name.lower()
                    for pattern in ["otel", "opentelemetry", "collector"]
                ):
                    otel_configmaps.append(
                        {
                            "name": name,
                            "namespace": namespace,
                            "data": item.get("data", {}),
                        }
                    )

            return otel_configmaps

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error executing kubectl: {e.stderr}", exc_info=False)
            return []
        except json.JSONDecodeError:
            self.logger.error("Error parsing kubectl output", exc_info=False)
            return []
        except Exception as e:
            self.logger.error(
                f"Unexpected error during Kubernetes ConfigMap retrieval: {str(e)}",
                exc_info=False
            )
            return []
