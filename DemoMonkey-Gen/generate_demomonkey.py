#!/usr/bin/env python3

import argparse
import json
import logging
import os
import pickle
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import faker_microservice
import requests
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

CACHE_FILE = "service_names_cache.pickle"
CACHE_TIMEOUT = timedelta(minutes=10)


def get_service_names(sfx_token, sfx_realm, o11y_environment):
    """
    Get service names from O11y Cloud's APM topology API.
    """
    url = f"https://api.{sfx_realm}.signalfx.com/v2/apm/topology"

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    time_range = f"{one_hour_ago.isoformat()}Z/{now.isoformat()}Z"

    payload = json.dumps(
        {
            "timeRange": time_range,
            "tagFilters": [
                {
                    "name": "sf_environment",
                    "operator": "equals",
                    "scope": "global",
                    "value": o11y_environment,
                }
            ],
        }
    )
    headers = {"Content-Type": "application/json", "X-SF-Token": sfx_token}

    response = requests.post(url, headers=headers, data=payload, timeout=15)

    if not response.ok:
        logging.error(f"Error {response.status_code}: {response.text}")
        return []

    response_data = response.json()
    logging.info(
        f"Retrieved {len(response_data['data']['nodes'])} nodes from O11y API."
    )

    service_names = [
        node["serviceName"]
        for node in response_data["data"]["nodes"]
        if node["type"] == "service"
    ]
    return service_names


def cache_service_names(service_names):
    """Cache service names to a file."""
    with open(CACHE_FILE, "wb") as cache_file:
        pickle.dump(
            {"timestamp": datetime.utcnow(), "service_names": service_names}, cache_file
        )


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
    logging.info(f"Mapped {len(service_microservice_map)} domains to services.")
    return service_microservice_map


def write_demomonkey_config(service_names, base_domain=None):
    microservices = generate_fake_microservices(service_names, base_domain)
    service_microservice_map = map_domains_to_services(service_names, microservices)

    if base_domain:
        replacements = "\n".join(
            f"{service} = {microservice}.$domain"
            for service, microservice in service_microservice_map.items()
        )
        domain_line = f"$domain={base_domain}//Set the main domain of your prospect. This will be used in the User Experience Section"
    else:
        replacements = "\n".join(
            f"{service} = {microservice}"
            for service, microservice in service_microservice_map.items()
        )
        domain_line = f"; $domain=//Set the main domain of your prospect. This will be used in the User Experience Section"

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

    write_demomonkey_config(service_names, base_domain)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate DemoMonkey config with SignalFx service names and custom domain names"
    )
    parser.add_argument(
        "--realm", default="us0", help="SignalFx realm (e.g. us0, us1, etc.)"
    )
    parser.add_argument(
        "--token",
        required=False,
        help="SignalFx API token (optional if using environment variable SFX_TOKEN)",
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
        help="Base domain for the fake microservices (e.g. splunk.com). Blank by default.",
    )

    args = parser.parse_args()

    token = args.token or os.environ.get("SFX_TOKEN")
    if not token:
        logging.error(
            "SignalFx API token is required. Please provide it using --token or set the SFX_TOKEN environment variable."
        )
        sys.exit(1)

    main(args.realm, args.token, args.environment, args.base_domain)
