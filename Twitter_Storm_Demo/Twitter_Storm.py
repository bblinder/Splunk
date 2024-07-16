#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Variables to set:
    REALM: The SignalFx realm to use (e.g. us0, us1, etc.) Defaults to us1.
    SIGNALFX_ORG_ACCESS_TOKEN: The SignalFx organization access token.

Variables should be set in the .env file or as environment variables.
Don't hardcode them in the script!

Example:
    `export REALM=us1`
    `export SIGNALFX_ORG_ACCESS_TOKEN=<SignalFx Org Access Token>`
"""

import os
import random
from time import sleep
import requests
from flask import Flask, abort
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()  # Pre-load environment variables

# Load and cache words and tweets
WORDS = [word.strip() for word in open("words.txt").readlines()]
TWEETS = [tweet.strip().replace("'", "") for tweet in open("Tweets.txt").readlines()]

class Config:
    REALM = os.getenv("REALM", "us1") # Default to us1 if not set
    SIGNALFX_ORG_ACCESS_TOKEN = os.getenv("SIGNALFX_ORG_ACCESS_TOKEN")
    if not SIGNALFX_ORG_ACCESS_TOKEN:
        raise ValueError("SIGNALFX_ORG_ACCESS_TOKEN must be set as an environment variable.")

def generate_username():
    """Generates a random username."""
    return random.choice(WORDS) + str(random.randint(0, len(WORDS) - 1))

def send_tweets():
    """Sends tweets as custom events."""
    endpoint = f"https://ingest.{Config.REALM}.signalfx.com/v2/event"
    headers = {"Content-Type": "application/json", "X-SF-TOKEN": Config.SIGNALFX_ORG_ACCESS_TOKEN}
    
    for tweet_text in TWEETS:
        username = generate_username()
        data = [{"category": "USER_DEFINED", "eventType": f"twitter: {tweet_text} - @{username}", "dimensions": {"feed": "twitter"}}]
        try:
            response = requests.post(url=endpoint, headers=headers, json=data)
            print(response.status_code)
            sleep(1)  # Throttle requests
        except requests.RequestException as e:
            print(f"Request failed: {e}")

@app.route("/", methods=["GET"])
def index():
    """Root endpoint."""
    try:
        send_tweets()
        return "<h1>Tweets sent!</h1>"
    except Exception as e:
        print(f"Error sending tweets: {e}")
        return abort(500)

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port="8080")
    except ValueError as e:
        print(e)
        sys.exit(1)
