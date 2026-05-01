# 🚀 Splunk On-Call Configuration Discovery Tool

This is a dedicated utility for extracting all discoverable configurations from a Splunk On-Call (VictorOps) environment into standardized JSON files. These serve as the data source for generating Infrastructure as Code (IaC), typically for tools like Terraform.

Think of this as the "data dump": everything you need to codify the current state of your system.

---

## ⚙️ Getting Started

### 💾 Prerequisites

*   **Python:** 3.10+
*   **Dependency:** `requests`

```bash
pip3 install requests
```

### 🔒 Configuration

The script requires three environment variables:

| Variable | Purpose | Example |
| :--- | :--- | :--- |
| `SOURCE_SPLUNK_ONCALL_API_ID` | Your API identifier. | `your-api-id` |
| `SOURCE_SPLUNK_ONCALL_API_KEY` | Your secret API key. | `your-api-key` |
| `SOURCE_SPLUNK_ONCALL_ORG_SLUG` | The On-Call organization slug. | `your-org-slug` |

**Setup Example (Linux/macOS):**
```bash
export SOURCE_SPLUNK_ONCALL_API_ID="your-api-id"
export SOURCE_SPLUNK_ONCALL_API_KEY="your-api-key"
export SOURCE_SPLUNK_ONCALL_ORG_SLUG="your-org-slug"
```

### 🏃 Usage

Run the script from your terminal:

```bash
python3 discovery.py
```

---

## ✨ Key Features

*   **Comprehensive Coverage:** Fetches global resources (Users, Teams, Rules) and complex, scoped resources (User Paging Policies, Team Escalations, Schedules).
*   **Robust API Handling:** Utilizes native `urllib3` adapters to gracefully handle **rate limiting (429)**, server errors (50x), exponential backoff, and automatic pagination detection.
*   **Filtering:** Automatically detects and filters out expired on-call scheduled overrides, ensuring the output inventory only reflects current and future states.
*   **Output Structure:** All data is placed in a dedicated `inventory/` directory, ready for use by IaC tools.

## 📂 Inventory Structure

All extracted data is placed in the `inventory/` directory. Each file is a standalone, structured JSON object, representing a distinct set of resources.

### 📁 Directory Contents

| File Name | Data Contained | Scope | Description |
| :--- | :--- | :--- | :--- |
| `users_inventory.json` | List of all user accounts. | Global | Basic user records. |
| `teams_inventory.json` | List of all teams. | Global | Team details and slugs. |
| `routing_keys_inventory.json` | Global routing keys. | Global | Keys for routing alerts. |
| `alert_rules_inventory.json` | All active alert rules. | Global | Ordered rules defined in On-Call. |
| `integrations_inventory.json` | Connected APIs/services. | Global | Integration configuration. |
| `outbound_webhooks_inventory.json` | Webhook definitions. | Global | Webhook endpoints. |
| `contact_methods_inventory.json` | User contact details. | Per-User | Details like phone/email mappings. |
| `paging_policies_inventory.json` | User paging policies. | Per-User | Rules defining how/when users are paged. |
| `escalation_policies_inventory.json` | Team escalation policies. | Per-Team | Step-by-step alert escalation rules. |
| `schedules_inventory.json` | On-Call schedules/rotations. | Per-Team | Shift schedules for every team. |
| `scheduled_overrides_inventory.json` | Active scheduled overrides. | Per-Team | Current and future override definitions. |

***

### 💡 Developer Note

The script includes helper functions (`api_get`, `fetch_per_entity`) to safely manage varied API responses (whether the data is in a bare list, wrapped in a dictionary, or requires looping through individual parent entities). 

It is a _read-only_ discovery tool. It does not modify any data in the Splunk On-Call environment.
