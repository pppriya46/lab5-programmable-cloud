#!/usr/bin/env python3

# Adapted from the Google Cloud Python samples:
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/compute/api/create_instance.py
# Copyright 2015 Google Inc. All Rights Reserved. Licensed under the Apache License, Version 2.0.

import argparse
import os
import time
from pprint import pprint

import googleapiclient.discovery
import google.auth
import google.oauth2.service_account as service_account

#
# Use Google Service Account - See https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html#module-google.oauth2.service_account
#
credentials = service_account.Credentials.from_service_account_file(filename='service-credentials.json')
project = os.getenv('GOOGLE_CLOUD_PROJECT') or 'lab5-510220'
service = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

ZONE = 'us-west1-b'
HERE = os.path.dirname(os.path.abspath(__file__))

# Startup script for VM-2: installs and starts the Flask app (same as Part 1).
VM2_STARTUP_SCRIPT = """#!/bin/bash
apt-get update
apt-get install -y python3 python3-pip git
mkdir -p /srv
cd /srv
git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
cd flask-tutorial
python3 setup.py install
pip3 install -e .
export FLASK_APP=flaskr
flask init-db
nohup flask run -h 0.0.0.0 &
"""

# Startup script for VM-1: pulls its files out of instance metadata and runs
# the program that launches VM-2.
VM1_STARTUP_SCRIPT = """#!/bin/bash
MD=http://metadata/computeMetadata/v1/instance/attributes
apt-get update
apt-get install -y python3-pip
mkdir -p /srv
cd /srv
curl -s $MD/vm2-startup-script -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -s $MD/service-credentials -H "Metadata-Flavor: Google" > service-credentials.json
curl -s $MD/vm1-launch-vm2-code -H "Metadata-Flavor: Google" > vm1-launch-vm2-code.py
export GOOGLE_CLOUD_PROJECT=$(curl -s $MD/project -H "Metadata-Flavor: Google")
pip3 install --upgrade google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib
python3 ./vm1-launch-vm2-code.py
"""


def wait_for_operation(compute, project, zone, operation):
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(1)


def read(filename):
    with open(os.path.join(HERE, filename)) as f:
        return f.read()


def create_vm1(compute, name, machine_type):
    image = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2204-lts').execute()
    config = {
        'name': name,
        'machineType': 'zones/%s/machineTypes/%s' % (ZONE, machine_type),
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': image['selfLink']},
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],
        'metadata': {
            'items': [
                {'key': 'startup-script', 'value': VM1_STARTUP_SCRIPT},
                {'key': 'vm2-startup-script', 'value': VM2_STARTUP_SCRIPT},
                {'key': 'service-credentials', 'value': read('service-credentials.json')},
                {'key': 'vm1-launch-vm2-code', 'value': read('vm1-launch-vm2-code.py')},
                {'key': 'project', 'value': project},
            ]
        },
    }
    return compute.instances().insert(
        project=project, zone=ZONE, body=config).execute()


def main(name, machine_type):
    print('Creating VM-1 (%s)...' % name)
    op = create_vm1(service, name, machine_type)
    wait_for_operation(service, project, ZONE, op['name'])
    print('VM-1 is up. Its startup script will now launch VM-2 (flask-vm2).')
    print('Give it a few minutes, then check:')
    print('  gcloud compute instances list')
    print('and visit the VM-2 URL (http://<VM-2 external IP>:5000).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='vm1-launcher', help='Name for VM-1.')
    parser.add_argument('--machine-type', default='e2-micro')
    args = parser.parse_args()
    main(args.name, args.machine_type)
