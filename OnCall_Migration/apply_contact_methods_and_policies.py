#!/usr/bin/env python3
"""
Apply deferred user settings: contact methods and paging policies.

Run after apply.py has provisioned users in the target org.
Dry-run by default. Pass --apply to execute writes.

Usage:
    python3 apply_contact_methods_and_policies.py
    python3 apply_contact_methods_and_policies.py -h
    python3 apply_contact_methods_and_policies.py --apply --inventory inventory --remapping inventory/remapping.json
"""

from __future__ import annotations

import argparse
import sys

from utils.cli import print_help_and_exit_if_requested


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply deferred Splunk On-Call user settings (contact methods and paging policies).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true", help="Execute writes (default is dry-run).")
    parser.add_argument("--inventory", default="inventory", help="Inventory directory path.")
    parser.add_argument("--remapping", default="inventory/remapping.json", help="Remapping file path.")
    return parser


if __name__ == "__main__":
    print_help_and_exit_if_requested(_build_arg_parser)

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apply import RemappingContext
from utils import load_dotenv, load_json
from utils.http_client import BaseVictorOpsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


class DeferredMigrationClient(BaseVictorOpsClient):
    """Client for applying contact methods and paging policies to the target org."""

    def __init__(self, api_id: str, api_key: str, org_slug: str, dry_run: bool = True):
        super().__init__(
            api_id,
            api_key,
            org_slug,
            retry_total=3,
            retry_backoff=1,
            allowed_methods=["GET", "POST"],
            extra_headers={"Content-Type": "application/json"},
        )
        self.dry_run = dry_run

    def get(self, endpoint: str) -> Tuple[Optional[Any], int]:
        url = self._url(endpoint, self.base_v1)
        self.rate_limiter.wait()
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 404:
            return None, 404
        if resp.status_code != 200:
            log.error(f"GET {url} -> {resp.status_code}: {resp.text[:200]}")
            return None, resp.status_code
        return resp.json(), resp.status_code

    def get_emails(self, username: str) -> Tuple[Optional[Any], int]:
        return self.get(f"user/{username}/contact-methods/emails")

    def get_phones(self, username: str) -> Tuple[Optional[Any], int]:
        return self.get(f"user/{username}/contact-methods/phones")

    def get_paging_steps(self, username: str) -> Tuple[Optional[Any], int]:
        return self.get(f"user/{username}/policies/primary/steps")

    def post(self, endpoint: str, payload: Dict[str, Any]) -> Tuple[Optional[Any], int]:
        url = self._url(endpoint, self.base_v1)
        self.rate_limiter.wait()
        if self.dry_run:
            log.info(f"DRY-RUN POST {url} payload={payload}")
            return {"dry_run": True, "endpoint": endpoint, "payload": payload}, 200
        resp = self.session.post(url, json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            log.error(f"POST {url} -> {resp.status_code}: {resp.text[:200]}")
            return None, resp.status_code
        try:
            return resp.json(), resp.status_code
        except ValueError:
            return {}, resp.status_code

    def post_email(self, username: str, payload: Dict[str, Any]) -> Tuple[Optional[Any], int]:
        return self.post(f"user/{username}/contact-methods/emails", payload)

    def post_phone(self, username: str, payload: Dict[str, Any]) -> Tuple[Optional[Any], int]:
        return self.post(f"user/{username}/contact-methods/phones", payload)

    def post_paging_policy_step(self, username: str, payload: Dict[str, Any]) -> Tuple[Optional[Any], int]:
        return self.post(f"user/{username}/policies/primary/steps", payload)


class DeferredPipeline:
    def __init__(
        self,
        client: DeferredMigrationClient,
        inventory_dir: Path,
        remapping: RemappingContext,
    ):
        self.client = client
        self.inventory_dir = inventory_dir
        self.remapping = remapping
        self.stats: Dict[str, Dict[str, int]] = {}

    def _bump(self, category: str, outcome: str) -> None:
        self.stats.setdefault(category, {"created": 0, "skipped": 0, "failed": 0, "warned": 0})
        self.stats[category][outcome] += 1

    @staticmethod
    def _contact_methods(category: Any) -> List[Any]:
        if not isinstance(category, dict):
            return []
        methods = category.get("contactMethods")
        return methods if isinstance(methods, list) else []

    @staticmethod
    def _extract_contact_values(raw: Any, value_keys: Tuple[str, ...]) -> set:
        if isinstance(raw, dict):
            items = raw.get("contactMethods")
            if not isinstance(items, list):
                items = []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        values: set = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in value_keys:
                if item.get(key):
                    values.add(item[key])
                    break
        return values

    def _existing_for_user(self, target_user: str) -> Tuple[set, set, set]:
        """Return (emails, phones, paging_signatures) already present on the target user.

        Skipped entirely in dry-run so a preview run performs no target GETs.
        """
        if self.client.dry_run:
            return set(), set(), set()
        emails_raw, _ = self.client.get_emails(target_user)
        phones_raw, _ = self.client.get_phones(target_user)
        paging_raw, _ = self.client.get_paging_steps(target_user)
        existing_emails = self._extract_contact_values(emails_raw, ("emailAddress", "value"))
        existing_phones = self._extract_contact_values(phones_raw, ("phoneNumber", "value"))
        existing_paging = {
            (step.get("timeout"), step.get("contactType"))
            for step in self._paging_steps(paging_raw or [], target_user)
            if isinstance(step, dict)
        }
        return existing_emails, existing_phones, existing_paging

    @staticmethod
    def _paging_steps(raw: Any, source_user: str) -> List[Any]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("steps", "primary", "policies"):
                candidate = raw.get(key)
                if isinstance(candidate, list):
                    return candidate
                if isinstance(candidate, dict):
                    nested = candidate.get("steps")
                    if isinstance(nested, list):
                        return nested
            log.warning(f"Could not parse paging policy steps for user '{source_user}'; skipping.")
            return []
        if raw:
            log.warning(f"Unexpected paging policy format for user '{source_user}'; skipping.")
        return []

    def run(self) -> None:
        log.info("Loading inventory files...")
        contact_methods = load_json(self.inventory_dir / "contact_methods_inventory.json", default={})
        paging_policies = load_json(self.inventory_dir / "paging_policies_inventory.json", default={})

        if not contact_methods:
            log.warning("Contact methods inventory is empty or not found.")

        if not isinstance(contact_methods, dict):
            contact_methods = {}
        if not isinstance(paging_policies, dict):
            paging_policies = {}

        source_users = sorted(set(contact_methods.keys()) | set(paging_policies.keys()))
        for source_user in source_users:
            methods = contact_methods.get(source_user)
            if not isinstance(methods, dict):
                methods = {}

            if self.remapping.is_skipped("users", source_user):
                log.info(f"Skipping user '{source_user}' (set to null in remapping).")
                self._bump("users", "skipped")
                continue
            target_user = self.remapping.map_value("users", source_user)

            log.info(f"Processing deferred items for target user: {target_user}")

            existing_emails, existing_phones, existing_paging = self._existing_for_user(target_user)

            for email_obj in self._contact_methods(methods.get("emails")):
                if not isinstance(email_obj, dict):
                    continue
                source_email = email_obj.get("value")
                if not source_email:
                    continue
                target_email = self.remapping.map_value("emails", source_email)
                if target_email is None:
                    self._bump("emails", "skipped")
                    continue
                if target_email in existing_emails:
                    log.info(f"  SKIP email exists for {target_user}: {target_email}")
                    self._bump("emails", "skipped")
                    continue

                payload = {
                    "emailAddress": target_email,
                    "label": email_obj.get("label", "Default"),
                }
                _, status = self.client.post_email(target_user, payload)
                if status in (200, 201):
                    existing_emails.add(target_email)
                    self._bump("emails", "created")
                else:
                    self._bump("emails", "failed")

            for phone_obj in self._contact_methods(methods.get("phones")):
                if not isinstance(phone_obj, dict):
                    continue
                phone_number = phone_obj.get("value")
                if not phone_number:
                    continue
                if phone_number in existing_phones:
                    log.info(f"  SKIP phone exists for {target_user}: {phone_number}")
                    self._bump("phones", "skipped")
                    continue
                payload = {
                    "phoneNumber": phone_number,
                    "label": phone_obj.get("label", "Phone"),
                }
                _, status = self.client.post_phone(target_user, payload)
                if status in (200, 201):
                    existing_phones.add(phone_number)
                    self._bump("phones", "created")
                else:
                    self._bump("phones", "failed")

            log.debug(
                "Skipping devices for %s — push devices require user login and cannot be migrated via API.",
                target_user,
            )

            for step in self._paging_steps(paging_policies.get(source_user), source_user):
                if not isinstance(step, dict):
                    continue
                contact_type = step.get("contactType")
                step_signature = (step.get("timeout", 1), contact_type)
                if step_signature in existing_paging:
                    log.info(f"  SKIP paging step exists for {target_user}: {step_signature}")
                    self._bump("paging_steps", "skipped")
                    continue
                payload = {
                    "timeout": step.get("timeout", 1),
                    "contactType": contact_type,
                }
                _, status = self.client.post_paging_policy_step(target_user, payload)
                if status in (200, 201):
                    existing_paging.add(step_signature)
                    self._bump("paging_steps", "created")
                elif contact_type == "push":
                    log.warning(
                        "Expected failure for push contactType on %s "
                        "(devices cannot be migrated via API). Skipping step.",
                        target_user,
                    )
                    self._bump("paging_steps", "warned")
                else:
                    self._bump("paging_steps", "failed")

        for category, counts in sorted(self.stats.items()):
            log.info(
                "%s: created=%d skipped=%d failed=%d warned=%d",
                category,
                counts.get("created", 0),
                counts.get("skipped", 0),
                counts.get("failed", 0),
                counts.get("warned", 0),
            )
        log.info("Deferred migration processing complete.")


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)

    load_dotenv()

    required = {
        "TARGET_SPLUNK_ONCALL_API_ID": os.getenv("TARGET_SPLUNK_ONCALL_API_ID"),
        "TARGET_SPLUNK_ONCALL_API_KEY": os.getenv("TARGET_SPLUNK_ONCALL_API_KEY"),
        "TARGET_SPLUNK_ONCALL_ORG_SLUG": os.getenv("TARGET_SPLUNK_ONCALL_ORG_SLUG"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        log.critical("Missing target org credentials:")
        for name in missing:
            log.critical(f"  - {name}")
        log.critical(
            "Add TARGET_SPLUNK_ONCALL_API_ID, TARGET_SPLUNK_ONCALL_API_KEY, and "
            "TARGET_SPLUNK_ONCALL_ORG_SLUG to your .env (see .env.example)."
        )
        sys.exit(1)

    remapping_path = Path(args.remapping)
    if not remapping_path.exists():
        log.critical(f"Remapping file not found: {remapping_path}")
        sys.exit(1)

    remapping_data = load_json(remapping_path, default={})
    client = DeferredMigrationClient(
        required["TARGET_SPLUNK_ONCALL_API_ID"],
        required["TARGET_SPLUNK_ONCALL_API_KEY"],
        required["TARGET_SPLUNK_ONCALL_ORG_SLUG"],
        dry_run=not args.apply,
    )
    pipeline = DeferredPipeline(
        client,
        Path(args.inventory),
        RemappingContext(remapping_data),
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    log.info(f"Starting deferred apply pipeline ({mode}) for org '{required['TARGET_SPLUNK_ONCALL_ORG_SLUG']}'")
    pipeline.run()


if __name__ == "__main__":
    main()
