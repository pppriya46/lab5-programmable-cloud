#!/usr/bin/env python3

# Adapted from the Google Cloud Python samples:
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/compute/api/create_instance.py
# Copyright 2015 Google Inc. All Rights Reserved. Licensed under the Apache License, Version 2.0.

import argparse
import time

import googleapiclient.discovery
import google.auth

# Note: the default machine type is f1-micro. If f1-micro is out of stock in
# us-west1-b (ZONE_RESOURCE_POOL_EXHAUSTED), run with --machine-type e2-micro,
# which the assignment allows ("f1-micro or e2 family").
ZONE = 'us-west1-b'
TAG = 'allow-5000'

STARTUP_SCRIPT = """#!/bin/bash
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


def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result.get('items', [])


def wait_for_operation(compute, project, zone, operation):
    print('Waiting for operation to finish...')
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return result
        time.sleep(1)


def create_firewall_rule(compute, project):
    """Create the allow-5000 rule unless it already exists."""
    existing = compute.firewalls().list(project=project).execute()
    if any(rule['name'] == TAG for rule in existing.get('items', [])):
        print('Firewall rule %s already exists.' % TAG)
        return

    body = {
        'name': TAG,
        'network': 'global/networks/default',
        'direction': 'INGRESS',
        'allowed': [{'IPProtocol': 'tcp', 'ports': ['5000']}],
        'sourceRanges': ['0.0.0.0/0'],
        'targetTags': [TAG],
    }
    op = compute.firewalls().insert(project=project, body=body).execute()
    print('Creating firewall rule %s...' % TAG)
    while True:
        result = compute.globalOperations().get(
            project=project, operation=op['name']).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(1)


def create_instance(compute, project, zone, name, machine_type):
    image_response = compute.images().getFromFamily(
        project='ubuntu-os-cloud', family='ubuntu-2204-lts').execute()
    source_disk_image = image_response['selfLink']

    config = {
        'name': name,
        'machineType': 'zones/%s/machineTypes/%s' % (zone, machine_type),
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {'sourceImage': source_disk_image},
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ],
        }],
        'metadata': {
            'items': [{'key': 'startup-script', 'value': STARTUP_SCRIPT}]
        },
    }
    return compute.instances().insert(
        project=project, zone=zone, body=config).execute()


def set_tags(compute, project, zone, name):
    instance = compute.instances().get(
        project=project, zone=zone, instance=name).execute()
    body = {
        'items': [TAG],
        'fingerprint': instance['tags']['fingerprint'],
    }
    return compute.instances().setTags(
        project=project, zone=zone, instance=name, body=body).execute()


def get_external_ip(compute, project, zone, name):
    instance = compute.instances().get(
        project=project, zone=zone, instance=name).execute()
    return instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']


def main(name, machine_type):
    credentials, project = google.auth.default()
    compute = googleapiclient.discovery.build(
        'compute', 'v1', credentials=credentials)

    create_firewall_rule(compute, project)

    print('Creating instance %s...' % name)
    op = create_instance(compute, project, ZONE, name, machine_type)
    wait_for_operation(compute, project, ZONE, op['name'])

    op = set_tags(compute, project, ZONE, name)
    wait_for_operation(compute, project, ZONE, op['name'])

    ip = get_external_ip(compute, project, ZONE, name)
    print('\nInstance %s is running.' % name)
    print('Give the startup script a few minutes to install Flask, then visit:')
    print('\n    http://%s:5000\n' % ip)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', default='flask-vm', help='Instance name.')
    parser.add_argument('--machine-type', default='f1-micro',
                        help='Machine type (use e2-medium while developing).')
    args = parser.parse_args()
    main(args.name, args.machine_type)
