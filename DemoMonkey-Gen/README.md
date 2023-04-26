# DemoMonkey Config Generator

A tool to rapidly create tailored static demos for prospects, using DemoMonkey.

The Python script generates a DemoMonkey configuration file, using existing APM service names retrieved via the [Service Topology API](https://dev.splunk.com/observability/reference/api/apm_service_topology/latest), and replaces them with randomly generated fake microservices.

## Requirements

- Python 3.6 or higher
- [DemoMonkey](https://chrome.google.com/webstore/detail/demomonkey/jgbhioialphpgjgofopnplfibkeehgjd) (Chrome extension)
- [Splunk Observability Cloud token](https://docs.splunk.com/Observability/admin/authentication-tokens/tokens.html#nav-Create-and-manage-authentication-tokens), with **API permissions enabled**

## Overview

The tool’s available options can be shown by running `python3 generate_demomonkey.py -h`:

```bash
usage: generate_demomonkey.py [-h] [--realm REALM] [--token TOKEN]
                              --environment ENVIRONMENT [-d BASE_DOMAIN]

Generate DemoMonkey config with SignalFx service names and custom domain names

options:
  -h, --help            show this help message and exit
  --realm REALM         SignalFx realm (e.g. us0, us1, etc.)
  --token TOKEN         SignalFx API token (optional if using environment
                        variable SFX_TOKEN)
  --environment ENVIRONMENT
                        Observability environment (e.g. pmrum-shop)
  -d BASE_DOMAIN, --base-domain BASE_DOMAIN
                        Base domain for the fake microservices (e.g.
                        splunk.com). Blank by default.
```

By default, the service names retrieved via API are cached for 10 minutes.

## Usage

### Setting up our environment
1. Run `python3 -m venv venv`
2. Run `source venv/bin/activate`

### Installing dependencies

Install dependencies in the `requirements.txt` file:

`pip3 install -r requirements.txt --upgrade`

### Running the script

Once dependencies are installed, you can run the script. You’ll need the following arguments:

- `--token`: your O11y Cloud token with API permissions
- `--environment`: your Org environment (ex: `pmrum-shop`)
- `--realm`: (**Optional**). The O11y realm corresponding to your org. Defaults to `us0`.
- `-d`/`--base-domain`: (**Optional**). The domain name of your prospect (ex: `splunk.com`). If provided, will be included in the full Microservice name.

Example:

```bash
python3 generate_demomonkey.py --realm us0 --environment bblinderman --token xxxxxxx -d splunk.com     
```

You should see an output like this:

```bash
2023-04-26 11:23:21,695 Retrieved 16 nodes from O11y API.
2023-04-26 11:23:21,801 Generated 12 fake microservices.
2023-04-26 11:23:21,802 Mapped 12 domains to services.
2023-04-26 11:23:21,803 DemoMonkey config written to demomonkey_config.mnky
```

Look for a configuration filed called `demomonkey_config.mnky` in the same directory the script was run from.

You can upload it directly to DemoMonkey from there, or copy/paste its contents instead. A quick way to do this on MacOS is by using `pbcopy`:

```bash
cat demomonkey_config.mnky | pbcopy
```

From there, you can paste the config directly into DemoMonkey:

![](images/2023-04-26%20at%2011.43.21.png)

Activate your DemoMonkey config.

## Result

Your demo should go from looking like this:

![](/images/2023-04-26%20at%2011.40.58.png)

To this:

![](/images/2023-04-26%20at%2011.41.39.png)
