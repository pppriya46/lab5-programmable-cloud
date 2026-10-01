#!/usr/bin/env python3

# Adapted from the Google Cloud Python samples:
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/compute/api/create_instance.py
# Copyright 2015 Google Inc. All Rights Reserved. Licensed under the Apache License, Version 2.0.

import argparse
import time

import googleapiclient.discovery
import googleapiclient.errors
import google.auth

ZONE = 'us-west1-b'
TAG = 'allow-5000'

# The Flask install is already baked into the disk. Clones only need to start it.
CLONE_STARTUP_SCRIPT = """#!/bin/bash
cd /srv/flask-tutorial
export FLASK_APP=flaskr
nohup flask run -h 0.0.0.0 &
"""


def wait_for_zone_operation(compute, project, zone, operation):
    while True:
        result = compute.zoneOperations().get(
            project=project, zone=zone, operation=operation).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(1)


def wait_for_global_operation(compute, project, operation):
    while True:
        result = compute.globalOperations().get(
            project=project, operation=operation).execute()
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(1)


def resource_exists(getter):
    try:
        getter.execute()
        return True
    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 404:
            return False
        raise


def create_snapshot(compute, project, zone, instance_name, snapshot_name):
    """Snapshot the boot disk of the instance."""
    instance = compute.instances().get(
        project=project, zone=zone, instance=instance_name).execute()
    disk_name = instance['disks'][0]['source'].split('/')[-1]

    if resource_exists(compute.snapshots().get(
            project=project, snapshot=snapshot_name)):
        print('Snapshot %s already exists.' % snapshot_name)
        return instance['machineType'].split('/')[-1]

    print('Creating snapshot %s from disk %s...' % (snapshot_name, disk_name))
    op = compute.disks().createSnapshot(
        project=project, zone=zone, disk=disk_name,
        body={'name': snapshot_name}).execute()
    wait_for_zone_operation(compute, project, zone, op['name'])
    return instance['machineType'].split('/')[-1]


def create_image(compute, project, snapshot_name, image_name):
    if resource_exists(compute.images().get(project=project, image=image_name)):
        print('Image %s already exists.' % image_name)
        return

    print('Creating image %s from snapshot %s...' % (image_name, snapshot_name))
    op = compute.images().insert(project=project, body={
        'name': image_name,
        'sourceSnapshot': 'global/snapshots/%s' % snapshot_name,
    }).execute()
    wait_for_global_operation(compute, project, op['name'])


def create_clone(compute, project, zone, name, machine_type, image_name):
    config = {
        'name': name,
        'machineType': 'zones/%s/machineTypes/%s' % (zone, machine_type),
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {
                'sourceImage': 'global/images/%s' % image_name,
            },
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ],
        }],
        'tags': {'items': [TAG]},
        'metadata': {
            'items': [{'key': 'startup-script', 'value': CLONE_STARTUP_SCRIPT}]
        },
    }
    return compute.instances().insert(
        project=project, zone=zone, body=config).execute()


def main(instance_name, machine_type_override=None):
    credentials, project = google.auth.default()
    compute = googleapiclient.discovery.build(
        'compute', 'v1', credentials=credentials)

    snapshot_name = 'base-snapshot-%s' % instance_name
    image_name = 'base-image-%s' % instance_name

    machine_type = create_snapshot(
        compute, project, ZONE, instance_name, snapshot_name)
    # Clones default to the source VM's type; override if that type is out of stock.
    machine_type = machine_type_override or machine_type
    create_image(compute, project, snapshot_name, image_name)

    timings = []
    for i in range(1, 4):
        name = '%s-clone-%d' % (instance_name, i)
        start = time.time()
        op = create_clone(
            compute, project, ZONE, name, machine_type, image_name)
        wait_for_zone_operation(compute, project, ZONE, op['name'])
        elapsed = time.time() - start
        timings.append((name, elapsed))
        print('%s created in %.2f seconds' % (name, elapsed))

    with open('TIMING.md', 'w') as f:
        f.write('# Instance creation times\n\n')
        f.write('Created from image `%s` (built from snapshot `%s`).\n\n'
                % (image_name, snapshot_name))
        f.write('| Instance | Time (seconds) |\n|---|---|\n')
        for name, elapsed in timings:
            f.write('| %s | %.2f |\n' % (name, elapsed))
    print('Wrote TIMING.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', default='flask-vm',
                        help='Name of the Part 1 instance to snapshot.')
    parser.add_argument('--machine-type', default=None,
                        help='Machine type for the clones (default: same as source).')
    args = parser.parse_args()
    main(args.name, args.machine_type)
