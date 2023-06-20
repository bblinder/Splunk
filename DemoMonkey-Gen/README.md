# DemoMonkey Config Generator

A tool to rapidly create tailored static demos for prospects, using DemoMonkey.

The Python utility generates a DemoMonkey configuration file, using existing APM service names retrieved via the [Service Topology API](https://dev.splunk.com/observability/reference/api/apm_service_topology/latest), and replaces them with randomly generated fake microservices.

Additionally, the application provides a Web interface (via Streamlit) where users can select existing templates, or generate a config file based on user inputs.

## Requirements

- Python 3.6 or higher
- [DemoMonkey](https://chrome.google.com/webstore/detail/demomonkey/jgbhioialphpgjgofopnplfibkeehgjd) (Chrome extension)
- [Splunk Observability Cloud token](https://docs.splunk.com/Observability/admin/authentication-tokens/tokens.html#nav-Create-and-manage-authentication-tokens), with **API permissions enabled**
- [The SignalFlow CLI](https://github.com/signalfx/signalflow-cli)
- [Streamlit](https://streamlit.io/)

## Available Templates

| Template  | Documentation/Scripts |
| ------------- | ------------- |
| Energy  | TBD |
| FSI Investment Banking  | [Docs](https://docs.google.com/document/d/1nLQFvKBgLAz7HweonBoHoFJcE88BdbHEgm4mov5ZdLQ/edit)  |
| Private Banking | TBD  |


## Overview

The tool can either be run via a **Web app** (Streamlit) or via the **command line**.

The CLI tool’s available options can be shown by running `python3 generate_demomonkey.py -h`:

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
                        Observability Cloud environment (e.g. pmrum-shop)
  -d BASE_DOMAIN, --base-domain BASE_DOMAIN
                        Base domain for the fake microservices (e.g.
                        splunk.com). Blank by default.
```

By default, the service names and RUM workflow names retrieved via API/SignalFlow are cached for 10 minutes.

## Usage

### Setting up our environment
1. Clone this repo: `git clone https://github.com/bblinder/Splunk.git`
2. `cd Splunk/DemoMonkey-Gen`
3. `python3 -m venv venv`
4. `source venv/bin/activate`

### Installing dependencies

1. Install dependencies: `./setup.sh`


### Running the Web app (Streamlit)

1. `streamlit run demomonkey_streamlit.py`

This will start a local web server and open a browser window. You should see a screen like this:

![](images%2F2023-06-20%20at%2016.33.57.png)

You can then select a template from the dropdown menu, or provide your own values. If providing your own values, enter them and click on the `Generate` button. This will generate a DemoMonkey config file with random microservices names and automatically copy it to your clipboard.


### Running the CLI tool

Once dependencies are installed, you can run the script. You’ll need the following arguments:

- `--token`: your O11y Cloud token with API permissions enabled (**optional**: you can also set the `SFX_TOKEN` environment variable).
- `--environment`: your O11y Cloud environment (ex: `pmrum-shop`).
- `--realm`: (**Optional**). The O11y realm corresponding to your Org. Defaults to `us1`.
- `-d`/`--base-domain`: (**Optional**). The domain name of your prospect (ex: `splunk.com`). If provided, will be included in the full microservice name

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

You can upload it directly to DemoMonkey, or copy/paste its contents: the script automatically copies the output to your clipboard (via `pyperclip`). Alternatatively, you can also do this is via `pbcopy` on MacOS:

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


## TODO

- Fix the `--token` argument for the CLI. Currently, it doesn’t work if you pass in a token via the command line. You need to set the `SFX_TOKEN` environment variable instead.
- Use the `signalflow` Python library instead of the CLI. This will make the script more portable.