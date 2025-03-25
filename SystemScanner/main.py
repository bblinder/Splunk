#!/usr/bin/env python3

"""
SystemScanner
Version 0.3
Author: Brandon Blinderman
"""

import argparse
import json
from typing import Dict, Any
from os_info import get_os_info
from runtime_versions import RuntimeFactory
from utils import ContextLogger
from health import HealthCheck
from validators import sanitize_command_output, validate_path
from datetime import datetime
from string import Template  # Using string.Template for text formatting

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="System Scanner")
    parser.add_argument(
        "--output",
        type=str,
        choices=["json", "text"],
        default="text",
        help="Output format (json or text)",
    )
    parser.add_argument(
        "--health-check", action="store_true", help="Perform system health check"
    )
    return parser.parse_args()

def format_output(data: Dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(data, indent=2)
    return generate_text_report(data)

def generate_text_report(data: Dict[str, Any]) -> str:
    template = """
==================================================
SYSTEM SCANNER REPORT
Generated: ${timestamp}
==================================================

OPERATING SYSTEM INFORMATION:
--------------------------------------------------
System: ${os_system}
Version: ${os_version}
Architecture: ${os_architecture}
Flavor: ${os_flavor}
--------------------------------------------------

RUNTIME VERSIONS:
--------------------------------------------------
${runtime_versions}
--------------------------------------------------

OPENTELEMETRY COLLECTOR INFORMATION:
--------------------------------------------------
Version: ${otel_version}
Path: ${otel_path}
--------------------------------------------------
${kubernetes_info}

${health_check}
"""

    report_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "os_system": sanitize_command_output(data["os_info"].get("system", "")),
        "os_version": sanitize_command_output(data["os_info"].get("version", "")),
        "os_architecture": sanitize_command_output(data["os_info"].get("architecture", "")),
        "os_flavor": sanitize_command_output(data["os_info"].get("flavor", "")),
        "runtime_versions": "\n".join(
            f"  {runtime}: {sanitize_command_output(version)}"
            for runtime, version in data.get("runtime_versions", {}).items()
        ),
        "otel_version": sanitize_command_output(data["otel_collector"].get("version", "")),
        "otel_path": validate_path(data["otel_collector"].get("path")) if data["otel_collector"].get("path") else "Not found",
        "kubernetes_info": generate_kubernetes_section(data.get("kubernetes_info")),
        "health_check": generate_health_check_section(data.get("health_check")),
    }

    return Template(template).substitute(report_data)

def generate_kubernetes_section(k8s_info):
    if not k8s_info:
        return ""

    template = """
KUBERNETES INFORMATION:
--------------------------------------------------
OpenTelemetry ConfigMaps found: ${otel_configmaps_count}
${configmaps_list}
"""

    configmaps_list = "\n".join(
        f"  - {cm['namespace']}/{cm['name']}" for cm in k8s_info.get("otel_configmaps", [])
    )

    return Template(template).substitute({
        "otel_configmaps_count": len(k8s_info.get("otel_configmaps", [])),
        "configmaps_list": configmaps_list,
    })

def generate_health_check_section(health_check):
    if not health_check:
        return ""

    template = """
SYSTEM HEALTH:
--------------------------------------------------
${health_checks}
"""

    health_checks = "\n".join(
        f"  {check}: {'✓' if status else '✗'}"
        for check, status in health_check.items()
    )

    return Template(template).substitute({
        "health_checks": health_checks,
    })

def main():
    args = parse_arguments()
    logger = ContextLogger(__name__)

    with logger.operation_context("System Scan"):
        data = {}

        # Collect OS Information
        try:
            with logger.operation_context("OS Information Retrieval"):
                os_name, os_version, os_architecture, os_flavor = get_os_info()
                data["os_info"] = {
                    "system": sanitize_command_output(os_name),
                    "version": sanitize_command_output(os_version),
                    "architecture": sanitize_command_output(os_architecture),
                    "flavor": sanitize_command_output(os_flavor),
                }
        except Exception as e:
            logger.error(f"Error retrieving OS information: {str(e)}", exc_info=True)

        # Collect Runtime Versions
        try:
            with logger.operation_context("Runtime Versions Retrieval"):
                factory = RuntimeFactory()
                data["runtime_versions"] = {
                    "Java": sanitize_command_output(factory.get_version("java")),
                    "Python": sanitize_command_output(factory.get_version("python")),
                    "Node.js": sanitize_command_output(factory.get_version("node")),
                }
        except Exception as e:
            logger.error(f"Error retrieving runtime versions: {str(e)}", exc_info=True)

        # Collect OpenTelemetry Collector Information
        try:
            with logger.operation_context("OpenTelemetry Collector Retrieval"):
                otel_version, otel_path = factory.get_otel_collector_info()
                data["otel_collector"] = {
                    "version": sanitize_command_output(otel_version),
                    "path": validate_path(otel_path) if otel_path else None,
                }
        except Exception as e:
            logger.error(f"Error retrieving OpenTelemetry Collector information: {str(e)}", exc_info=True)

        # Collect Kubernetes Information
        try:
            with logger.operation_context("Kubernetes Retrieval"):
                if factory.is_running_in_kubernetes():
                    data["kubernetes_info"] = {"otel_configmaps": factory.get_otel_configmaps()}
        except Exception as e:
            logger.error(f"Error retrieving Kubernetes information: {str(e)}", exc_info=True)

        # Perform Health Checks
        try:
            with logger.operation_context("Health Check"):
                if args.health_check:
                    health_checker = HealthCheck()
                    data["health_check"] = health_checker.check_system_resources()
        except Exception as e:
            logger.error(f"Error during health check: {str(e)}", exc_info=True)

        # Output results
        output = format_output(data, args.output)
        print(output)

if __name__ == "__main__":
    main()
