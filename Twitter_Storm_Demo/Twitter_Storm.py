#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Variables to set:
    REALM: The SignalFx realm to use (e.g. us0, us1, etc.) Defaults to us0.
    SIGNALFX_ORG_ACCESS_TOKEN: The SignalFx organization access token.

Variables should be set in the .env file or as environment variables.
Don't hardcode them in the script.

Example:
    `export REALM=us0`
    `export ORG_ACCESS_TOKEN=<SignalFx Org Access Token>`
"""

import os
import random
import sys
from time import sleep

import requests
from dotenv import load_dotenv
from flask import Flask

app = Flask(__name__)


def load_config():
    """
    Load the realm and org access token from environment variables.
    Defaults the realm to us0 if no realm is set.
    """
    load_dotenv()  # load environment variables
    realm = os.getenv(
        "REALM", "us0"
    )  # change to reflect your SignalFx Realm. Defaults to us0.
    org_access_token = os.getenv("SIGNALFX_ORG_ACCESS_TOKEN")
    return realm, org_access_token


def generate_username():
    """
    Generates a random user name from the words.txt file,
    and appends a random number to the end.
    """
    with open("words.txt", "r") as f:
        words = [word.strip() for word in f.readlines()]
        return random.choice(words) + str(random.randint(0, len(words) - 1))


def read_tweets():
    """
    Reads the tweets from the Tweets.txt file, strips out apostrophes,
    and converts them to single quotes.
    """
    with open("Tweets.txt", "r") as f:
        return [tweet.strip("'").replace("'", "") for tweet in f.readlines()]


def send_tweet(realm, org_access_token):
    """
    Sends the tweets as custom events to the SignalFx ingest API.

    Args:
        realm (str): The SignalFx realm to use (e.g. us0, us1, etc.) Defaults to us0.
        org_access_token (str): The SignalFx organization access token.

    """
    tweets = read_tweets()
    endpoint = f"https://ingest.{realm}.signalfx.com/v2/event"
    headers = {"Content-Type": "application/json", "X-SF-TOKEN": org_access_token}

    for tweet_text in tweets:
        username = generate_username()
        tweet = f"twitter: {tweet_text} - @{username}"
        data = [
            {
                "category": "USER_DEFINED",
                "eventType": tweet,
                "dimensions": {"feed": "twitter"},
            }
        ]
        print(data)
        with requests.post(url=endpoint, headers=headers, json=data) as response:
            sleep(1)  # send one tweet per second
            print(response.status_code)


@app.route("/", methods=["GET"])
def index():
    """
    Flask route for the root endpoint. Sends the tweets and returns an HTML response.

    Returns:
        str: An HTML string indicating the tweets have been sent.
    """
    realm, org_access_token = load_config()
    send_tweet(realm, org_access_token)
    return "<h1>Tweets sent!</h1>"


if __name__ == "__main__":
    realm, org_access_token = load_config()
    if org_access_token is None or realm is None:
        print("You must set the ORG_ACCESS_TOKEN and REALM.")
        print("This can be done in the '.env' file or as environment variables.")
        sys.exit(1)
    else:
        app.run(
            host="0.0.0.0", port="8080"
        )  # include "debug=True" if you need troubleshooting
