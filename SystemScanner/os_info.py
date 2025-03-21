"""
SystemScanner: OS Information Module

This module provides functionality to retrieve detailed information
about the operating system on which the script is running.

It includes functions to get the system name, release version,
and architecture.
"""

import platform


def get_os_info():
    system = platform.system()
    release = platform.release()
    architecture = platform.machine()
    os_flavor = ""

    # Add OS flavor information focusing on the [0] output of platform
    if system == "Darwin":  # macOS
        os_flavor = f"macOS {platform.mac_ver()[0]}"
    elif system == "Linux":
        try:
            # Simple approach using platform.linux_distribution() if available
            # Note: This is deprecated in Python 3.8+
            if hasattr(platform, "linux_distribution"):
                distro = platform.linux_distribution()[0]
                os_flavor = f"Linux {distro}"
            else:
                # Fallback to reading /etc/os-release
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            os_flavor = line.split("=")[1].strip().strip('"')
                            break
        except:
            os_flavor = "Linux"
    elif system == "Windows":
        os_flavor = f"Windows {platform.win32_ver()[0]}"

    return system, release, architecture, os_flavor
