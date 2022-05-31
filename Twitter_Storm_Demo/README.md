# Twitter Storm demo

A flask app that fires off a list of pre-written "tweets" as custom events. Overlay with the event feed in the CICD demo for best effect.

The script can be run locally or in a cloud instance. Update the [canary deployment script](https://cd.splunkdev.com/observability-sales-engineering/field-demos/-/blob/main/CICD%20Automation%20Demo/Readme.md) to include a `curl` to the flask endpoint.

## Pre-work

1. Retrieve your O11y cloud/SignalFx token. **Ensure it has ingest permissions.**
1. Edit the `Tweets.txt` file to include the tweets you want to send. Some examples are included.
2. Run `pip install -r requirements.txt` to ensure dependencies are met.
3. Include `SIGNALFX_ORG_ACCESS_TOKEN` and `REALM` in either the `.env` file or as environmental variables
    - Ex: `export SIGNALFX_ORG_ACCESS_TOKEN=xxxx`


## Running the demo

1. Run `python3 Twitter_Storm.py` to kick off the script.
     - If running from a cloud instance, it's recommended you use `nohup` to separate the running script from your terminal process. This ensures that it continues running if you lose connection to your instance.
2. Note the IP and port it exposes (usually `127.0.0.1:8080`), though this can be a public-facing cloud instance.
3. Open the URL in a browser, or use a GET request (`curl http://{URL_OF_ENDPOINT}:8080`) to trigger the tweet storm.
   - Optional: include the curl request as a line in the `canary.sh` script so it triggers as part of the CICD demo.
