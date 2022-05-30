#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import random
import requests
import os, sys
from time import sleep
from flask import Flask, render_template, request
from dotenv import load_dotenv

realm = 'us1' # change to reflect your SignalFx Realm

load_dotenv() # load environment variables    
app = Flask(__name__)


# turn Tweets.txt into a list
def read_tweets():
    """
    Reads the tweets from the file and turns them into a list
    """

    with open('Tweets.txt', 'r') as f:
        list_of_tweets = f.readlines()
        # strip out apostrophes and convert to single quotes
        list_of_tweets = [tweet.strip("'").replace("'", "") for tweet in list_of_tweets] # these need to be in single quotes for now, as for some reason double quotes aren't working.
    return list_of_tweets


#print((read_tweets()))


def send_tweet():
    """
    Iterates through the list of tweets and sends them as custom events.
    Be sure to change the realm to reflect your SignalFx Realm (us1, etc.)
    """

    list_of_tweets = read_tweets()
    
    # sending tweets every 1.5 seconds
    for t in list_of_tweets:
        tweet = "twitter: " + t

        # SignalFx
        endpoint = f'https://ingest.{realm}.signalfx.com/v2/event'
        org_access_token = os.getenv('SIGNALFX_ORG_ACCESS_TOKEN')

        # Set headers
        headers = {
            'Content-Type': 'application/json',
            'X-SF-TOKEN': org_access_token
        }

        print(tweet)
        data = [{
            "category": "USER_DEFINED",
            "eventType": tweet,
            "dimensions": {
                "feed": "twitter"
            }
        }]

        print(data)
        r = requests.post(endpoint, headers=headers, json=data)
        sleep(1.5)
        print(r.status_code) # putting here for debugging purposes. Useful to see if you're getting any 'unauthorized' errors.


@app.route('/', methods=['GET'])
def index():
    send_tweet()
    return "<h1>Tweets sent!</h1>"


if not realm and not org_access_token:
    print('Please set your realm and org_access_token (either as an environment variable or in a .env file)')
    sys.exit(1)
else:
    app.run(host="0.0.0.0", port="8080", debug=True)
