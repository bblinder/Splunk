#!/usr/bin/env python3

import argparse
import json
import logging
import os
import pickle
import re
import subprocess
import sys
import pyperclip as pc
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import faker_microservice
import requests
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

CACHE_FILE = "service_names_cache.pickle"
CACHE_TIMEOUT = timedelta(minutes=10)

SIGNALFLOW_CACHE_FILE = "signalflow_cache.pickle"
SIGNALFLOW_CACHE_TIMEOUT = timedelta(minutes=10)

PROGRAM = (
    "E = (C).publish(label='E', enable=False)\n"
    "A = data('rum.workflow.count', filter=filter('workflow.name', '*')).sum(by=['workflow.name']).publish(label='A', enable=False)\n"
    "B = data('rum.workflow.time.ns.p75', filter=filter('workflow.name', '*'), rollup='average').mean(by=['sf_operation']).top(count=30).publish(label='B')\n"
    "C = (B/1000000000).percentile(pct=75, by=['workflow.name']).publish(label='C', enable=False)\n"
    "D = (A*C).publish(label='D', enable=False)\n")


def run_signalflow_program(sfx_token, program):
    """
    Runs the Signalflow CLI to extract RUM workflow names.
    """
    command = ["signalflow", "--token", sfx_token, "--start=-5m", "--stop=-1m"]
    process = subprocess.Popen(command,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               text=True)

    try:
        stdout, stderr = process.communicate(input=program, timeout=15)
    except subprocess.TimeoutExpired:
        logging.error("SignalFlow program took too long to run.")
        return None

    if process.returncode != 0:
        logging.error(f"Error running SignalFlow program: {stderr}")
        return None

    extracted_values = []
    for line in stdout.splitlines():
        match = re.search(r"([A-Za-z0-9_\s]+):\s+\[", line)
        if match:
            extracted_values.append(match.group(1).strip())

    # Create a Counter object from the extracted values
    value_counts = Counter(extracted_values)

    # Get the top 50 most common workflow names
    top_workflows = value_counts.most_common(50)

    # Extract the workflow names to a list
    top_workflow_names = [workflow[0] for workflow in top_workflows]

    logging.info(
        f"Extracted {len(top_workflow_names)} workflow names from SignalFlow.")
    return top_workflow_names


def cache_signalflow_output(extracted_values):
    """Cache extracted values from SignalFlow output."""
    try:
        with open(SIGNALFLOW_CACHE_FILE, "wb") as cache_file:
            pickle.dump(
                {
                    "timestamp": datetime.utcnow(),
                    "extracted_values": extracted_values
                },
                cache_file,
            )
    except Exception as e:
        logging.error(f"Error caching SignalFlow output: {e}")


def load_signalflow_output_from_cache():
    """Load extracted values from SignalFlow output cache."""
    try:
        if not Path(SIGNALFLOW_CACHE_FILE).is_file():
            return None
        with open(SIGNALFLOW_CACHE_FILE, "rb") as cache_file:
            cached_data = pickle.load(cache_file)
        if datetime.utcnow(
        ) - cached_data["timestamp"] > SIGNALFLOW_CACHE_TIMEOUT:
            return None
        return cached_data["extracted_values"]
    except Exception as e:
        logging.error(f"Error loading SignalFlow output from cache: {e}")
        return None


def get_service_names(sfx_token, sfx_realm, o11y_environment):
    """
    Get service names from O11y Cloud's APM topology API.
    """
    url = f"https://api.{sfx_realm}.signalfx.com/v2/apm/topology"

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    time_range = f"{one_hour_ago.isoformat()}Z/{now.isoformat()}Z"

    payload = json.dumps({
        "timeRange":
        time_range,
        "tagFilters": [{
            "name": "sf_environment",
            "operator": "equals",
            "scope": "global",
            "value": o11y_environment,
        }],
    })
    headers = {"Content-Type": "application/json", "X-SF-Token": sfx_token}

    try:
        response = requests.post(url,
                                 headers=headers,
                                 data=payload,
                                 timeout=15)

        if not response.ok:
            logging.error(f"Error {response.status_code}: {response.text}")
            return []

        response_data = response.json()
        logging.info(
            f"Retrieved {len(response_data['data']['nodes'])} nodes from O11y API."
        )

        service_names = [
            node["serviceName"] for node in response_data["data"]["nodes"]
            if node["type"] == "service"
        ]
        return service_names

    except requests.exceptions.RequestException as e:
        logging.error(f"Error retrieving service names from O11y API: {e}")
        return []


def cache_service_names(service_names):
    """Cache service names to a file."""
    with open(CACHE_FILE, "wb") as cache_file:
        pickle.dump(
            {
                "timestamp": datetime.utcnow(),
                "service_names": service_names
            }, cache_file)


def load_service_names_from_cache():
    """Load service names from cache"""
    if not Path(CACHE_FILE).is_file():
        return None
    with open(CACHE_FILE, "rb") as cache_file:
        cached_data = pickle.load(cache_file)
    if datetime.utcnow() - cached_data["timestamp"] > CACHE_TIMEOUT:
        return None
    return cached_data["service_names"]


def generate_fake_microservices(service_names, base_domain=None):
    """
    Generate fake microservices using the Faker library.
    """
    fake = Faker()
    fake.add_provider(faker_microservice.Provider)
    microservices = []

    for _ in range(len(service_names)):
        microservice = fake.microservice()
        # microservice_domain = f"{microservice}.{base_domain}"
        microservice_domain = f"{microservice}"
        microservices.append(microservice_domain)
    logging.info(f"Generated {len(microservices)} fake microservices.")
    return microservices


def map_domains_to_services(service_names, microservices):
    """
    Map domain names to service names.
    """
    service_microservice_map = dict(zip(service_names, microservices))
    logging.info(
        f"Mapped {len(service_microservice_map)} domains to services.")
    return service_microservice_map


def write_demomonkey_config(service_names,
                            base_domain=None,
                            extracted_values=None):
    """
    Writes a DemoMonkey config file.
    Args:
        service_names (list): The list of service names to use in the config file.
        base_domain (str, optional): The prospect's domain name to use for each microservice.
        extracted_values (list, optional): The extracted values from a SignalFlow program's output.
    Returns:
        str: The contents of the DemoMonkey config file.
    """
    microservices = generate_fake_microservices(service_names, base_domain)
    service_microservice_map = map_domains_to_services(service_names,
                                                       microservices)

    if base_domain:
        replacements = "\n".join(
            f"{service} = {microservice}.$domain"
            for service, microservice in service_microservice_map.items())
        domain_line = f"$domain={base_domain}//Set the main domain of your prospect. This will be used in the User Experience Section"
    else:
        replacements = "\n".join(
            f"{service} = {microservice}"
            for service, microservice in service_microservice_map.items())
        domain_line = "; $domain=//Set the main domain of your prospect. This will be used in the User Experience Section"

    if extracted_values:
        if base_domain:
            extracted_values_line = "\n".join(f"; {value} = $domain/<url/path>"
                                              for value in extracted_values)
        else:
            extracted_values_line = "\n".join(f"; {value} = </url/path>"
                                              for value in extracted_values)
    else:
        extracted_values_line = ""

    demomonkey_config = f"""; [Options]
; ; This configuration is set to run on all websites with a wildcard pattern
; @include[] = /^https?.*$/

; [Replacements]

[Options]
@include[] = /^https?://.*signalfx\.com/.*$/
!querySelector(.platform-notification-message-error , style.display) = none
@namespace[] = splunk

[Variables]
{domain_line}

{replacements}

;; Top RUM workflow names from SignalFlow (use command/ctrl + "/" to bulk uncomment).
;; Can be matched with prospect domains/URL paths.

{extracted_values_line}
"""
    with open("demomonkey_config.mnky", "w") as file:
        file.write(demomonkey_config)
    logging.info(
        f"DemoMonkey config written to {Path.cwd() / 'demomonkey_config.mnky'}"
    )
    return "demomonkey_config.mnky"


def main(realm, token, environment, base_domain=None):
    service_names = load_service_names_from_cache()

    if service_names:
        logging.info("Using cached service names.")
    else:
        service_names = get_service_names(token, realm, environment)
        cache_service_names(service_names)

    if not service_names:
        logging.error("No service names retrieved.")
        return

    extracted_values = load_signalflow_output_from_cache()

    if extracted_values:
        logging.info("Using cached SignalFlow output.")
    else:
        program = PROGRAM
        extracted_values = run_signalflow_program(token, program)
        cache_signalflow_output(extracted_values)

    demomonkey_config_file = write_demomonkey_config(service_names,
                                                     base_domain,
                                                     extracted_values)

    with open(demomonkey_config_file, "r") as file:
        demomonkey_config = file.read()
        # copy demomonkey_config to clipboard
        pc.copy(demomonkey_config)
        logging.info("DemoMonkey config copied to clipboard.")

    return service_names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=
        "Generate DemoMonkey config with SignalFx service names and custom domain names"
    )
    parser.add_argument("--realm",
                        default="us0",
                        help="SignalFx realm (e.g. us0, us1, etc.)")
    parser.add_argument(
        "--token",
        required=False,
        help=
        "SignalFx API token (optional if using environment variable SFX_TOKEN)",
    )
    parser.add_argument(
        "--environment",
        required=True,
        help="Observability environment (e.g. pmrum-shop)",
    )
    parser.add_argument(
        "-d",
        "--base-domain",
        required=False,
        help=
        "Base domain for the fake microservices (e.g. splunk.com). Blank by default.",
    )

    args = parser.parse_args()

    token = args.token or os.environ.get("SFX_TOKEN")
    if not token:
        logging.error(
            "SignalFx API token is required. Please provide it using --token or set the SFX_TOKEN environment variable."
        )
        sys.exit(1)

    main(args.realm, args.token, args.environment, args.base_domain)
