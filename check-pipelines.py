#!/usr/bin/env python
"""A simple script to check for out-of-date Azure Pipelines configurations testing against ansible-core devel branch."""

from __future__ import annotations

import os

import yaml


def main():
    base_path = os.path.expanduser('~/.ansible/azp-tools/repos')
    collections_path = os.path.join(base_path, 'ansible-collections')
    collections = os.listdir(collections_path)
    collection_branches = {collection: os.listdir(os.path.join(collections_path, collection)) for collection in collections}

    boilerplate()

    for collection, branches in collection_branches.items():
        namespace, name = collection.split('.')

        for branch in branches:
            yaml_path = os.path.join(collections_path, collection, branch, 'ansible_collections', namespace, name, '.azure-pipelines', 'azure-pipelines.yml')

            process(namespace, name, branch, yaml_path)

    process('ansible', 'ansible', 'devel', os.path.join(base_path, 'ansible/ansible/devel/.azure-pipelines/azure-pipelines.yml'))


def boilerplate():
    print('''
### Azure Pipelines Test Matrix Updates

Projects using Azure Pipelines to test against the `ansible-core` `devel` branch have been checked to verify their test matrix is up-to-date.

A report on each project's status, as well as the required and recommended actions are explained below.

#### Using the Checklist  

Each project is given a status as follows:

- `Skipped` - The project was skipped because it does not use platforms that were evaluated. No action is necessary.
- `Current` - The project uses platforms that were evaluated, and all are current. No action is necessary.
- `Update` - The project uses platforms that were evaluated, and one or more changes are indicated.

The types of changes are as follows:

- `Add` - The platform is already tested by the project, but the version is not. Add the version to the matrix.
- `Remove` - The platform and version are deprecated and will be removed from `ansible-test` in the future. Remove the version from the matrix.
- `Consider` - The platform is not yet tested by the project. Consider adding the version to the matrix.

> IMPORTANT: These changes should **only** be made for the portion of the test matrix tested against the `devel` branch of `ansible-core`.

#### Checklist
''')


def process(namespace, name, branch, yaml_path):
    with open(yaml_path) as yaml_file:
        config = yaml.load(yaml_file, Loader=yaml.SafeLoader)

    stages = config['stages']
    tests = []

    # Every platform/version combination known to ansible-test in the devel branch should be listed in one of the two lists below.
    # The key is the value used for --remote or --docker.
    # The value is the platform group the target is part of.
    # The platform groups are used to distinguish between "Add" and "Consider" when generating the checklist.

    # Entries here are currently used in the ansible-core test matrix.
    expected = {
        'alpine3': 'alpine',
        'centos6': 'centos',
        'centos7': 'centos',
        'centos8': 'centos',
        'fedora32': 'fedora',
        'fedora33': 'fedora',
        'opensuse15': 'opensuse',
        'opensuse15py2': 'opensuse',
        'ubuntu1804': 'ubuntu',
        'ubuntu2004': 'ubuntu',
        'freebsd/11.4': 'freebsd',
        'freebsd/12.2': 'freebsd',
        'macos/11.1': 'macos',
        'rhel/7.9': 'rhel',
        'rhel/8.3': 'rhel',
    }

    # Entries here are deprecated and will be removed from ansible-test in the future.
    deprecated = {
        'fedora30': 'fedora',
        'fedora31': 'fedora',
        'ubuntu1604': 'ubuntu',
        'freebsd/11.1': 'freebsd',
        'freebsd/12.1': 'freebsd',
        'osx/10.11': 'macos',
        'macos/10.15': 'macos',
        'rhel/7.6': 'rhel',
        'rhel/7.8': 'rhel',
        'rhel/8.1': 'rhel',
        'rhel/8.2': 'rhel',
    }

    for stage in stages:
        jobs = stage['jobs']

        for job in jobs:
            template = job['template']

            if template == 'templates/coverage.yml':
                continue

            if template != 'templates/matrix.yml':
                raise Exception(f'Unexpected template: {template}')

            parameters = job['parameters']
            test_format = parameters.get('testFormat', '{0}')
            targets = parameters['targets']
            groups = parameters.get('groups')

            if groups:
                for group in groups:
                    for target in targets:
                        raw_test = target.get('test', target.get('name'))
                        test = test_format.format(raw_test, group)
                        tests.append(test)
            else:
                for target in targets:
                    raw_test = target.get('test', target.get('name'))
                    test = test_format.format(raw_test)
                    tests.append(test)

    tests_found = set()

    for test in tests:
        parts = test.split('/')

        if namespace == 'ansible' and name == 'ansible':
            ansible_branch = 'devel'
            test_parts = parts
        else:
            if parts[0] not in ('devel', '2.9', '2.10'):
                raise Exception(f'Unexpected branch found in: {test}')

            ansible_branch = parts[0]
            test_parts = parts[1:]

        if ansible_branch != 'devel':
            continue

        test_type = test_parts[0]

        if test_type in ('sanity', 'units', 'aws', 'cloud', 'hcloud', 'windows', 'galaxy', 'generic', 'i'):
            continue

        if test_type == 'linux':
            test_name = test_parts[1]
        elif test_type in ('freebsd', 'osx', 'macos', 'rhel'):
            test_name = f'{test_type}/{test_parts[1]}'
        else:
            test_name = None

        if not test_name:
            raise Exception(f'Test name not extracted: {test_type}')

        tests_found.add(test_name)

    unknown = tests_found - set(expected.keys()) - set(deprecated.keys())

    if unknown:
        raise Exception(f'Unknown test name: {unknown}')

    platforms = {test_name: expected.get(test_name) or deprecated.get(test_name) for test_name in tests_found}

    if None in platforms.values():
        raise Exception(f'Missing platform information: {platforms}')

    platforms_used = sorted(platforms.values())

    if not platforms_used:
        print(f'- [X] {namespace}.{name}:{branch} - Skipped')
        return

    to_remove = set(deprecated.keys()) & tests_found
    to_add = set([name for name, platform in expected.items() if platform in platforms_used]) - tests_found
    to_consider = set([name for name, platform in expected.items() if platform not in platforms_used]) - tests_found

    if not to_add and not to_consider and not to_remove:
        print(f'- [X] {namespace}.{name}:{branch} - Current')
        return

    print(f'- [ ] {namespace}.{name}:{branch} - Update')

    for item in sorted(to_remove):
        print(f'  - [ ] Remove: {item}')

    for item in sorted(to_add):
        print(f'  - [ ] Add: {item}')

    for item in sorted(to_consider):
        print(f'  - [ ] Consider: {item}')


if __name__ == '__main__':
    main()
