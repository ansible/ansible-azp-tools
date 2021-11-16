#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""A simple script to check for out-of-date Azure Pipelines configurations testing against ansible-core devel branch."""

from __future__ import annotations

import abc
import argparse
import os
import typing as t

try:
    import argcomplete
except ImportError:
    argcomplete = None

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(metavar='command', dest='command', required=True)

    matrix_parser = subparsers.add_parser('matrix', help='check matrix configurations')
    matrix_parser.set_defaults(command=CheckMatrix)

    matrix_parser.add_argument(
        '--minimal',
        action='store_true',
        help='omit current and skipped projects',
    )

    actions = ['add', 'remove', 'consider']
    matrix_parser.add_argument(
        '--action',
        dest='actions',
        action='append',
        choices=actions,
        help=f'action(s) to show: {", ".join(actions)}',
    )

    container_parser = subparsers.add_parser('container', help='check default containers')
    container_parser.set_defaults(command=CheckContainer)

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    settings = Settings()

    command: Command = args.command(args, settings)
    command.run()


class Config:
    def __init__(self, namespace: str, name: str, branch: str, path: str) -> None:
        self.namespace = namespace
        self.name = name
        self.branch = branch
        self.path = path

        with open(path) as yaml_file:
            self.yaml = yaml.load(yaml_file, Loader=yaml.SafeLoader)

    def __iter__(self) -> t.Tuple[str, str, str, str]:
        for item in self.namespace, self.name, self.branch, self.path:
            yield item

    def __str__(self):
        return f'{self.namespace}.{self.name}:{self.branch}'


class Settings:
    def __init__(self):
        self.base_path = os.path.expanduser('~/.ansible/azp-tools/repos')
        self.collections_path = os.path.join(self.base_path, 'ansible-collections')
        self.ansible_path = os.path.join(self.base_path, 'ansible/ansible')
        self.collections = os.listdir(self.collections_path)
        self.collection_branches = {collection: os.listdir(os.path.join(self.collections_path, collection)) for collection in self.collections}
        self.ansible_branches = os.listdir(self.ansible_path)
        self.configs = []

        for collection, branches in self.collection_branches.items():
            namespace, name = collection.split('.')

            for branch in branches:
                path = os.path.join(self.collections_path, collection, branch, 'ansible_collections', namespace, name, '.azure-pipelines/azure-pipelines.yml')

                self.configs.append(Config(namespace, name, branch, path))

        for branch in self.ansible_branches:
            path = os.path.join(self.ansible_path, branch, '.azure-pipelines/azure-pipelines.yml')

            self.configs.append(Config('ansible', 'ansible', branch, path))


class Command(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def run(self) -> None:
        pass


class CheckContainer:
    def __init__(self, args: argparse.Namespace, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> None:
        expected_image = 'quay.io/ansible/azure-pipelines-test-container:1.9.0'

        boilerplate = f'''
### Azure Pipelines Test Container Update

Projects using Azure Pipelines should use the current test container for all branches.

The current container is: `{expected_image}`

A report on each project's status can be found below.

#### Checklist
'''

        print(boilerplate)

        for config in self.settings.configs:
            containers = config.yaml['resources']['containers']
            default_container = [c for c in containers if c['container'] == 'default'][0]
            default_image = default_container['image']

            checkmark = 'X' if default_image == expected_image else ' '

            print(f'- [{checkmark}] {config}')


class CheckMatrix:
    def __init__(self, args: argparse.Namespace, settings: Settings) -> None:
        self.actions: t.List[str] = args.actions or ['add', 'remove', 'consider']
        self.minimal: bool = args.minimal
        self.settings = settings

    def run(self) -> None:
        self.matrix_boilerplate()

        for config in self.settings.configs:
            if config.namespace == 'ansible' and config.name == 'ansible' and config.branch != 'devel':
                continue

            self.process_matrix(config)

    def matrix_boilerplate(self) -> None:
        actions = dict(
            add='The platform is already tested by the project, but the version is not. Add the version to the matrix.',
            remove='The platform and version are deprecated and will be removed from `ansible-test` in the future. Remove the version from the matrix.',
            consider='The platform is not yet tested by the project. Consider adding the version to the matrix.',
        )

        action_text = '\n'.join(f'- {action.title()} - {description}' for action, description in actions.items() if action in self.actions)

        statuses = dict(
            skipped='The project was skipped because it does not use platforms that were evaluated. No action is necessary.',
            current='The project uses platforms that were evaluated, and all are current. No action is necessary.',
            update='The project uses platforms that were evaluated, and one or more changes are indicated.',
        )

        status_text = '\n'.join(f'- {status.title()} - {description}' for status, description in statuses.items() if status == 'update' or not self.minimal)

        print(f'''
### Azure Pipelines Test Matrix Updates

Projects using Azure Pipelines to test against the `ansible-core` `devel` branch have been checked to verify their test matrix is up-to-date.

A report on each project's status, as well as the required and recommended actions are explained below.

#### Using the Checklist  

Each project is given a status as follows:

{status_text}

The types of changes are as follows:

{action_text}

> IMPORTANT: These changes should **only** be made for the portion of the test matrix tested against the `devel` branch of `ansible-core`.

#### Checklist
''')

    def process_matrix(self, config: Config) -> None:
        namespace, name, branch, path = config
    
        stages = config.yaml['stages']
        tests = []
    
        # Every platform/version combination known to ansible-test in the devel branch should be listed in one of the two lists below.
        # The key is the value used for --remote or --docker.
        # The value is the platform group the target is part of.
        # The platform groups are used to distinguish between "Add" and "Consider" when generating the checklist.
    
        # Entries here are currently used in the ansible-core test matrix.
        expected = {
            'alpine3': 'alpine',
            'centos7': 'centos',
            'fedora34': 'fedora',
            'fedora35': 'fedora',
            'opensuse15': 'opensuse',
            'opensuse15py2': 'opensuse',
            'ubuntu1804': 'ubuntu',
            'ubuntu2004': 'ubuntu',
            'freebsd/12.2': 'freebsd',
            'freebsd/13.0': 'freebsd',
            'macos/11.1': 'macos',
            'rhel/7.9': 'rhel',
            'rhel/8.5': 'rhel',
            'rhel/9.0b': 'rhel',
        }
    
        # Entries here are deprecated and will be removed from ansible-test in the future.
        deprecated = {
            'centos6': 'centos',
            'centos8': 'centos',
            'fedora30': 'fedora',
            'fedora31': 'fedora',
            'fedora32': 'fedora',
            'fedora33': 'fedora',
            'ubuntu1604': 'ubuntu',
            'freebsd/11.1': 'freebsd',
            'freebsd/11.4': 'freebsd',
            'freebsd/12.1': 'freebsd',
            'osx/10.11': 'macos',
            'macos/10.15': 'macos',
            'rhel/7.6': 'rhel',
            'rhel/7.8': 'rhel',
            'rhel/8.1': 'rhel',
            'rhel/8.2': 'rhel',
            'rhel/8.3': 'rhel',
            'rhel/8.4': 'rhel',
        }
    
        # Entries here are currently used in the ansible-core matrix, but are not recommended for collections.
        special = {
            'ios/csr1000v': 'ios',
            'vyos/1.1.8': 'vyos',
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
            parts = test.split('@')[0].split('/')
    
            if namespace == 'ansible' and name == 'ansible':
                ansible_branch = 'devel'
                test_parts = parts
            else:
                if parts[0] not in ('devel', '2.9', '2.10', '2.11', '2.12'):
                    raise Exception(f'Unexpected branch found in: {test}')
    
                ansible_branch = parts[0]
                test_parts = parts[1:]
    
            if ansible_branch != 'devel':
                continue
    
            test_type = test_parts[0]
    
            if test_type == 'i':
                test_parts = test_parts[1:]
                test_type = test_parts[0]
    
            if test_type in ('sanity', 'units', 'aws', 'cloud', 'hcloud', 'windows', 'galaxy', 'generic'):
                continue
    
            if test_type == 'linux':
                test_name = test_parts[1]
            elif test_type in ('freebsd', 'osx', 'macos', 'rhel', 'ios', 'vyos'):
                test_name = f'{test_type}/{test_parts[1]}'
            else:
                test_name = None
    
            if not test_name:
                raise Exception(f'Test name not extracted: {test}')
    
            tests_found.add(test_name)
    
        unknown = tests_found - set(expected.keys()) - set(deprecated.keys()) - set(special.keys())
    
        if unknown:
            raise Exception(f'Unknown test name: {unknown}')
    
        platforms = {test_name: expected.get(test_name) or deprecated.get(test_name) or special.get(test_name) for test_name in tests_found}
    
        if None in platforms.values():
            raise Exception(f'Missing platform information: {platforms}')
    
        platforms_used = sorted(platforms.values())
    
        if not platforms_used:
            if not self.minimal:
                print(f'- [X] {namespace}.{name}:{branch} - Skipped')

            return

        to_remove = (set(deprecated.keys()) & tests_found
                     if 'remove' in self.actions else set())

        to_add = (set([name for name, platform in expected.items() if platform in platforms_used]) - tests_found
                  if 'add' in self.actions else set())

        to_consider = (set([name for name, platform in expected.items() if platform not in platforms_used]) - tests_found
                       if 'consider' in self.actions else set())
    
        if not to_add and not to_consider and not to_remove:
            if not self.minimal:
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
