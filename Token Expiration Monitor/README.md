# Splunk Observability Token Expiration Monitor

Python script to monitor Splunk Observability Cloud token expiration. Fetches tokens, calculates expiry, and sends `token.days_until_expiration` metrics.

## Prerequisites

*   [`uv`](https://github.com/astral-sh/uv) installed.
*   The script uses the `uv run --script` header to manage its dependencies automatically.
*   Make the script executable: `chmod +x splunk_o11y_token_health.py`.

## Configuration

Configure via environment variables or CLI arguments. CLI arguments take precedence.

**Required:**

*   **Realm:** Splunk Observability realm (e.g., `us0`, `us1`).
    *   Env: `SPLUNK_REALM`
    *   CLI: `--realm` (Default: `us1`)

*   **Authentication:**
    **Session Token:** Requires Email, Password, Org ID. **API endpoint will not work if SSO is enabled.** Caches token for ~55 mins (`.session_token_cache.json`).
        *   Env: `SPLUNK_EMAIL`, `SPLUNK_PASSWORD`, `SPLUNK_ORG_ID`
        *   CLI: `--use-session`, `--email`, `--password`, `--org-id` (Use `$SPLUNK_PASSWORD` env var for safety)

        > **Note:** If SSO is enabled, you'll need to manually obtain a session token from the Splunk Observability Cloud UI.

*   **Ingest Token:** Splunk Observability Ingest token (requires ingest permissions).
    *   Env: `SPLUNK_INGEST_TOKEN`
    *   CLI: `--ingest-token` (Not needed if using `--dry-run`)

**Optional:**

*   `--page-size`: Tokens per API request (Default: 100).
*   `--dry-run`: Process data and show planned metrics, but do not send them.

## Usage

Ensure the script is executable (`chmod +x script_name.py`). Since the script uses the `uv run --script` header, `uv` will handle the environment and dependencies when you execute it directly.

**1. Using API Token (Recommended):**
```
# Set required environment variables

export SPLUNK_REALM="us1"
export SPLUNK_API_TOKEN="YOUR_API_ACCESS_TOKEN"
export SPLUNK_INGEST_TOKEN="YOUR_INGEST_TOKEN"

# Execute the script directly

./splunk_o11y_token_health.py
```

**2. Using Session Token (Non-SSO Org, Env Vars):**
```
# Set required environment variables

export SPLUNK_REALM="eu0"
export SPLUNK_EMAIL="your.email@example.com"
export SPLUNK_PASSWORD='your_secret_password' # Use env var!
export SPLUNK_ORG_ID="YOUR_ORG_ID"
export SPLUNK_INGEST_TOKEN="YOUR_INGEST_TOKEN"

# Execute the script with the session flag

./splunk_o11y_token_health.py --use-session
```
*(Note: If a valid cached session token exists, it will be used, and credentials won't be needed for that run.)*

**3. Dry Run:**
```
# Assumes required auth env vars are set

./splunk_o11y_token_health.py --dry-run
```

## Output Metric

Sends a gauge metric to Splunk Observability Cloud:

*   **`token.days_until_expiration`**: Days until token expiry (negative if expired).
    *   *Dimensions:* `token_name`, `token_id`, `token_type`, `expiration_date`, `auth_scopes`

## Session Token Caching

When using `--use-session`, a successfully created session token is cached in `.session_token_cache.json` for approximately 55 minutes. Subsequent runs with `--use-session` within this period will reuse the cached token. API token authentication (`--api-token`) does not use this cache.

## Exit Codes

*   `0`: Success (metrics sent, or dry run completed, or no relevant tokens found).
*   `1`: Failure (configuration error, API error, metric sending failed).
