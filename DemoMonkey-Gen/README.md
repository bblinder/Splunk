# DemoMonkey Config Generator

A tool to rapidly create tailored static demos for prospects, using DemoMonkey.

The Python script generates a DemoMonkey configuration file, using existing APM service names retrieved via the [Service Topology API](https://dev.splunk.com/observability/reference/api/apm_service_topology/latest), and replaces them with randomly generated fake microservices.

## Requirements

- Python 3.6 or higher
- [DemoMonkey](https://chrome.google.com/webstore/detail/demomonkey/jgbhioialphpgjgofopnplfibkeehgjd) (Chrome extension)
- [Splunk Observability Cloud token](https://docs.splunk.com/Observability/admin/authentication-tokens/tokens.html#nav-Create-and-manage-authentication-tokens), with **API permissions enabled**
- [The SignalFlow CLI](https://github.com/signalfx/signalflow-cli)

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
1. Clone this repo: `git clone https://github.com/bblinder/Splunk.git`
2. `cd Splunk/DemoMonkey-Gen`
3. Run `python3 -m venv venv`
4. Run `source venv/bin/activate`

### Installing dependencies

1. Install dependencies: `pip3 install -r requirements.txt --upgrade`

2. Install the latest version of the SignalFlow CLI: `pip3 install git+https://github.com/signalfx/signalflow-cli`

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
2023-04-26 12:21:11,158 Retrieved 16 nodes from O11y API.
2023-04-26 12:21:11,263 Generated 12 fake microservices.
2023-04-26 12:21:11,263 Mapped 12 domains to services.
2023-04-26 12:21:11,264 DemoMonkey config written to /Users/bblinderman/Github/Splunk/DemoMonkey-Gen/demomonkey_config.mnky
```

Look for a configuration file called `demomonkey_config.mnky`. The script should output the full path to the config file.

You can upload it directly to DemoMonkey, or copy/paste its contents. A quick way to do this is via `pbcopy` on MacOS:

```bash
cat demomonkey_config.mnky | pbcopy
```

You can then paste the contents directly into DemoMonkey:

![](images/2023-04-26%20at%2011.43.21.png)

Next, activate your DemoMonkey config for the changes to take effect.

## Result

Your demo should go from looking like this:

![](images/2023-04-26%20at%2011.40.58.png)

To this:

![](images/2023-04-26%20at%2011.41.39.png)
