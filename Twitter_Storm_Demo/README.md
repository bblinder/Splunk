# Twitter Storm Demo

A Flask app that fires off a list of pre-written "tweets" as custom events. Overlay with the event feed in the CICD demo for best effect.

The script can be run locally or in a cloud instance. Update the [canary deployment script](https://cd.splunkdev.com/observability-sales-engineering/field-demos/-/blob/main/CICD%20Automation%20Demo/Readme.md) to include a `curl` to the Flask endpoint.

## Prerequisites

1. Retrieve your O11y cloud/SignalFx token. **Ensure it has ingest permissions.**
2. Edit the `Tweets.txt` file to include the tweets you want to send (**one per line**). Some examples are included.
3. Run `pip install -r requirements.txt` to ensure dependencies are met.
4. Set the `SIGNALFX_ORG_ACCESS_TOKEN` and `REALM` environment variables, or include them in the `.env` file.
    - Example: `export SIGNALFX_ORG_ACCESS_TOKEN=xxxx`

## Running the Demo

1. Run `python3 Twitter_Storm.py` to start the script.
   - If running from a cloud instance, it's recommended you use `nohup` to separate the running script from your terminal process. This ensures that it continues running if you lose connection to your instance.
2. Note the IP and port it exposes (usually `127.0.0.1:8080`), though this can be a public-facing cloud instance.
3. Open the URL in a browser, or use a GET request (`curl http://{URL_OF_ENDPOINT}:8080`) to trigger the tweet storm.
   - Optional: include the curl request as a line in the `canary.sh` script so it triggers as part of the CICD demo.
4. Once events start coming in, they should be available in the event feed. Create an event feed (or use an existing one) and add `twitter:*` to view them. The result should look something like this:

![2022-05-31 at 14 35 07](https://user-images.githubusercontent.com/9903403/171260099-9f698767-6170-46c8-a0c0-0d912ff1484a.png)
