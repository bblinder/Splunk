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
    # Get current timestamp
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = []
    report.append("=" * 50)
    report.append("SYSTEM SCANNER REPORT")
    report.append(f"Generated: {current_time}")
    report.append("=" * 50)
    report.append("")

    # Runtime Versions
    report.append("RUNTIME VERSIONS:")
    for runtime, version in data["runtime_versions"].items():
        report.append(f"  {runtime}: {version}")

    report.append("-" * 50)

    # OpenTelemetry Collector Information
    report.append("OPENTELEMETRY COLLECTOR INFORMATION:")
    report.append(f"  Version: {data['otel_collector']['version']}")
    path_display = (
        data["otel_collector"]["path"]
        if data["otel_collector"]["path"]
        else "Not found"
    )
    report.append(f"  Path: {path_display}")
    report.append("-" * 50)

    # K8S Information
    if "kubernetes_info" in data:
        report.append("KUBERNETES INFORMATION:")
        if "otel_configmaps" in data["kubernetes_info"]:
            otel_maps = data["kubernetes_info"]["otel_configmaps"]
            if isinstance(otel_maps, list):
                report.append(f"  OpenTelemetry ConfigMaps found: {len(otel_maps)}")
                for cm in otel_maps:
                    report.append(f"  - {cm['namespace']}/{cm['name']}")
            else:
                report.append(f"  OpenTelemetry ConfigMaps: {otel_maps}")
        report.append("-" * 50)

    # Health Check if available
    if "health_check" in data:
        report.append("SYSTEM HEALTH:")
        for check, status in data["health_check"].items():
            status_str = "✓" if status else "✗"
            report.append(f"  {check}: {status_str}")
        report.append("-" * 50)

    return "\n".join(report)


def main():
    args = parse_arguments()
    logger = ContextLogger(__name__)

    with logger.operation_context("System Scan"):
        # Initialize health check
        health_checker = HealthCheck()

        # Collect system information
        data = {}

        # Add timestamp
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # OS Information
        os_name, os_version, os_architecture, os_flavor = get_os_info()
        data["os_info"] = {
            "system": sanitize_command_output(os_name),
            "version": sanitize_command_output(os_version),
            "architecture": sanitize_command_output(os_architecture),
            "flavor": sanitize_command_output(os_flavor),
        }

        # Runtime Versions
        factory = RuntimeFactory()
        data["runtime_versions"] = {
            "Java": sanitize_command_output(factory.get_version("java")),
            "Python": sanitize_command_output(factory.get_version("python")),
            "Node.js": sanitize_command_output(factory.get_version("node")),
        }

        # OpenTelemetry Collector Information
        otel_version, otel_path = factory.get_otel_collector_info()
        data["otel_collector"] = {
            "version": sanitize_command_output(otel_version),
            "path": validate_path(otel_path) if otel_path else None,
        }

        # K8S Information
        if factory.is_running_in_kubernetes():
            data["kubernetes_info"] = {"otel_configmaps": factory.get_otel_configmaps()}

        # Health Check if requested
        if args.health_check:
            data["health_check"] = health_checker.check_system_resources()

        # Output results
        output = format_output(data, args.output)
        print(output)


if __name__ == "__main__":
    main()
