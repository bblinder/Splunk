#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import requests
import os
import sys
from time import sleep
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv() # load environment variables 


realm = 'us1' # change to reflect your SignalFx Realm
org_access_token = os.getenv('SIGNALFX_ORG_ACCESS_TOKEN')
   

app = Flask(__name__)

def generate_username():
    """
    Generates a random username for the tweet.
    """

    with open('words.txt', 'r') as f:
        words = f.readlines()
        words = [word.strip() for word in words]
        random_number = random.randint(0, len(words)-1)
        username = words[random_number] + str(random_number)

    return username


# turn Tweets.txt into a list
def read_tweets():
    """
    Reads the tweets from the file and turns them into a list.
    It turns them into single quotes for now, as for some reason
    the SignalFx ingest API doesn't like double quotes.
    """

    with open('Tweets.txt', 'r') as f:
        list_of_tweets = f.readlines()
        # strip out apostrophes and convert to single quotes
        list_of_tweets = [tweet.strip("'").replace("'", "") for tweet in list_of_tweets]
    return list_of_tweets


def send_tweet():
    """
    Iterates through the list of tweets and sends them as custom events.
    Be sure to change the realm to reflect your SignalFx Realm (ex: us1, etc.)
    """

    list_of_tweets = read_tweets()
    
    # sending tweets every 1.5 seconds
    for t in list_of_tweets:
        tweet = "twitter: " + t + " - " + "@" + generate_username()

        # SignalFx
        endpoint = f'https://ingest.{realm}.signalfx.com/v2/event'

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


# don't run if org_access_token or realm is not set
if org_access_token is None or realm is None:
    print("You must set the org_access_token and realm environment variables.")
    sys.exit()
else:
    app.run(host="0.0.0.0", port="8080") # include "debug=True" if you need troubleshooting
