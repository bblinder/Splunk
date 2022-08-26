#!/usr/bin/env python3

import sys
import csv
import argparse

argparser = argparse.ArgumentParser()
argparser.add_argument('-e', '--emails', help='Text file containing email addresses, one per line')
argparser.add_argument('-ip', '--ips', help='Text file containing EC2 IP addresses, one per line')
argparser.add_argument('-r', '--realm', help='Splunk/SignalFX realm. Default: us1', required=False, default='us1')
args = argparser.parse_args()

email_list = args.emails
ec2_ips = args.ips
sfx_realm = args.realm


def sort_emails(email_list):
    # import text file and put into a list and sort alphabetically
    with open(email_list) as f:
        emails = f.read().splitlines()
        emails.sort()
        # remove empty lines and commas and trailing spaces
        emails = [email for email in emails if email]
        emails = [email.replace(',', '') for email in emails]
        emails = [email.strip() for email in emails]
    return emails

    
def ExtractNames():
# extract names from emails and put into a list
    names = []
    for email in emails:
        names.append(email.split('@')[0])

    # Separate first and last names and capitalize
    first_names = []
    last_names = []
    for name in names:
        first_names.append(name.split('.')[0].capitalize())
        last_names.append(name.split('.')[1].capitalize())

    # full names
    full_names = []
    for i in range(len(first_names)):
        full_names.append(first_names[i] + ' ' + last_names[i])
    return full_names


def IPaddresses():
    IPs = []
    with open(ec2_ips) as f:
        # remove empty lines and commas and quotes and trailing spaces
        IPs = f.read().splitlines()
        IPs = [IP for IP in IPs if IP]
        IPs = [IP.replace(',', '') for IP in IPs]
        IPs = [IP.replace('"', '') for IP in IPs]
        IPs = [IP.strip() for IP in IPs]
    return IPs


def WriteCSV():
    with open('Attendees_List.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'Email', 'IP address (EC2)', 'SSH Info', 'Password', 'Browser Access', 'Splunk Observability URL'])
        for i in range(len(full_names)):
            writer.writerow([full_names[i], emails[i], IPs[i], f"ssh ubuntu@{IPs[i]}", 'Observability2022!', f"http://{IPs[i]}:6501", f"http://app.{sfx_realm}.signalfx.com"])


if __name__ == '__main__':
    if not args.emails or not args.ips:
        argparser.print_help()
        sys.exit(1)
    else:
        emails = sort_emails(email_list)
        IPs = IPaddresses()
        full_names = ExtractNames()
        WriteCSV()
    