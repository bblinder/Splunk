#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import requests
import os, sys
from time import sleep
from flask import Flask, render_template, request
from dotenv import load_dotenv


load_dotenv()
    
realm = 'us1' # change to reflect your SignalFx Realm


app = Flask(__name__)

# putting these in single quotes for now, as for some reason double quotes aren't working.
list_of_tweets = [
    'WTF is this? I cant order my special editions! #JustDoIt',
    'Argh! Site is down again! #cantdoit',
    'Lol did #JustDoIt hire the guys from Old Balance? Site is draaagggggging...',
    'Im so happy I cant order my special editions! #JustDoIt"',
    'OMG Im gonna miss my running club! #JustDoIt',
    'Bought AdDDos instead #sandalscandal',
    'Guess Im gonna have to set my bunions free. Major #JustDoIt fail',
    'Γιατί δεν λειτουργεί ο ιστότοπος #JustDoIt fail!',
    'Δεν λειτουργεί ο ιστότοπος #JustDoIt fail!',
    'Im finally cutting out the logos out of my #JustDoIt pillow case!',
    'What the hell, #JustDoIt! This is the 4th fail this month!',
    'Tu terribilis es, #JustDoIt!',
    'Non iterum! Ordinem meum addere non possum!'
]

def send_tweet():
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
    print('Please set your realm and org_access_token in .env')
    sys.exit(1)
else:
    app.run(host="0.0.0.0", port="8080", debug=True)
