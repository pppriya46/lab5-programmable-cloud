#!/usr/bin/env python3

# Runs ON VM-1. Uses the service account credentials that part3.py copied
# to this VM (via instance metadata) to launch VM-2 running the Flask app.
#
# Adapted from the Google Cloud Python samples:
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/compute/api/create_instance.py
# Copyright 2015 Google Inc. All Rights Reserved. Licensed under the Apache License, Version 2.0.

import os
import time

import googleapiclient.discovery
import googleapiclient.errors
import google.oauth2.service_account as service_account

ZONE = 'us-west1-b'
TAG = 'allow-5000'
VM2_NAME = 'flask-vm2'
MACHINE_TYPE = 'e2-micro'

credentials = service_account.Credentials.from_service_account_file(
    filename='service-credentials.json')
project = os.environ['GOOGLE_CLOUD_PROJECT']
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

with open('vm2-startup-script.sh') as f:
    vm2_startup_script = f.read()


def wait_for_operation(getter):
    while True:
        result = getter().execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(1)


def firewall_exists():
    rules = compute.firewalls().list(project=project).execute()
    return any(r['name'] == TAG for r in rules.get('items', []))


def create_firewall_rule():
    body = {
        'name': TAG,
        'network': 'global/networks/default',
        'direction': 'INGRESS',
        'allowed': [{'IPProtocol': 'tcp', 'ports': ['5000']}],
        'sourceRanges': ['0.0.0.0/0'],
        'targetTags': [TAG],
    }
    op = compute.firewalls().insert(project=project, body=body).execute()
    wait_for_operation(lambda: compute.globalOperations().get(
        project=project, operation=op['name']))


def instance_exists(name):
    try:
        compute.instances().get(project=project, zone=ZONE, instance=name).execute()
        return True
    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 404:
            return False
        raise


def create_vm2():
    image = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2204-lts').execute()
    config = {
        'name': VM2_NAME,
        'machineType': 'zones/%s/machineTypes/%s' % (ZONE, MACHINE_TYPE),
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': image['selfLink']},
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}],
        }],
        'tags': {'items': [TAG]},
        'metadata': {
            'items': [{'key': 'startup-script', 'value': vm2_startup_script}]
        },
    }
    op = compute.instances().insert(project=project, zone=ZONE, body=config).execute()
    wait_for_operation(lambda: compute.zoneOperations().get(
        project=project, zone=ZONE, operation=op['name']))


if not firewall_exists():
    print('Creating firewall rule %s' % TAG)
    create_firewall_rule()

if instance_exists(VM2_NAME):
    print('%s already exists.' % VM2_NAME)
else:
    print('Creating %s...' % VM2_NAME)
    create_vm2()

instance = compute.instances().get(
    project=project, zone=ZONE, instance=VM2_NAME).execute()
ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
print('VM-2 is running. Flask will be available in a few minutes at http://%s:5000' % ip)
