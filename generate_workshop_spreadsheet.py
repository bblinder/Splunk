#!/usr/bin/env python3

# Author: Brandon Blinderman
# Email: bblinderman@splunk.com
# Date: 2022-08-20

import sys
import csv
import argparse
import json
from time import sleep

argparser = argparse.ArgumentParser()
argparser.add_argument('-m', '--members', help="Text file containing email addresses, one per line. Default: 'members.txt'", default='members.txt')
argparser.add_argument('-ip', '--ips', help='Text file containing EC2 IP addresses, one per line')
argparser.add_argument('-r', '--realm', help='Splunk/SignalFX realm. Default: us1', required=False, default='us1')
argparser.description = "Generate a CSV file of attendees for the Splunk Observability Workshop"
args = argparser.parse_args()

email_list = args.members
ec2_ips = args.ips
sfx_realm = args.realm


def sort_emails(email_list):
    # import 'members.txt', put into a list, and sort alphabetically
    with open(email_list) as f:
        emails = f.read().splitlines()
        emails.sort()
        # remove empty lines and commas and trailing spaces
        emails = [email for email in emails if email]
        emails = [email.replace(',', '') for email in emails]
        emails = [email.strip() for email in emails]
    return emails

    
def ExtractNames():
    # extract names from emails
    users = []
    for email in emails:
        users.append(email.split('@')[0])
    return users


    # Separate first and last names and capitalize
    # first_names = []
    # last_names = []
    # for name in names:
    #     first_names.append(name.split('.')[0].capitalize())
    #     last_names.append(name.split('.')[1].capitalize())

    # # full names
    # full_names = []
    # for i in range(len(first_names)):
    #     full_names.append(first_names[i] + ' ' + last_names[i])
    # return full_names


def IPaddresses():
    IPs = []
    # import json file containing EC2 IPs
    with open(ec2_ips) as f:
        IPs = json.load(f)
        IPs.sort()
    return IPs


def WriteCSV():
    with open('Workshop_Attendees.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['User', 'Email', 'IP address (EC2)', 'SSH Info', 'Password', 'Browser Access', 'Splunk Observability URL'])
        for i in range(len(users)):
            writer.writerow([users[i], emails[i], IPs[i], f"ssh ubuntu@{IPs[i]}", 'Observability2022!', f"http://{IPs[i]}:6501", f"http://app.{sfx_realm}.signalfx.com"])

        
        # Accounting for the remaining IPs
        extra_IPs = len(IPs) - len(emails)
        if extra_IPs > 0:
            # add extra IPs to the end of the list
            for i in range(extra_IPs):
                writer.writerow(['', '', IPs[-1], f"ssh ubuntu@{IPs[-1]}", 'Observability2022!', f"http://{IPs[-1]}:6501", f"http://app.{sfx_realm}.signalfx.com"])
                IPs.pop()


if __name__ == '__main__':
    if not args.ips:
        argparser.print_help()
        sys.exit(1)
    else:
        emails = sort_emails(email_list)
        IPs = IPaddresses()
        users = ExtractNames()

        print(f"Generating CSV file for {len(emails)} attendees...")
        sleep(1)
        WriteCSV()
        # print location of CSV file
        print(f"CSV file saved to: {sys.path[0]}/Workshop_Attendees.csv")
    