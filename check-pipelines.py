#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""A simple script to check for out-of-date Azure Pipelines configurations testing against ansible-core devel branch."""

from __future__ import annotations

import abc
import argparse
import contextlib
import os
import re
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

                with contextlib.suppress(FileNotFoundError):
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
        expected_image = 'quay.io/ansible/azure-pipelines-test-container:3.0.0'

        boilerplate = f'''
### Azure Pipelines Test Container Update

Projects using Azure Pipelines should use the current test container for all branches.

The current container is: `{expected_image}`

A report on each project's status can be found below.

#### Checklist
'''

        print(boilerplate)

        for config in self.settings.configs:
            variables = {item['name']: item['value'] for item in config.yaml.get('variables', [])}
            containers = {item['container']: item['image'] for item in config.yaml.get('resources', {}).get('containers', [])}
            default_image = containers.get('default') or variables.get('defaultContainer')

            checkmark = 'X' if default_image == expected_image else ' '

            print(f'- [{checkmark}] {config}')


class CheckMatrix:
    def __init__(self, args: argparse.Namespace, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> None:
        checklist = ''

        for config in self.settings.configs:
            if config.namespace == 'ansible' and config.name == 'ansible' and config.branch != 'devel':
                continue

            checklist += self.process_matrix(config)

        if not checklist:
            return

        print(f'''
### Azure Pipelines Test Matrix Updates

The following collections tested with the `devel` branch of `ansible-core` should be updated:

{checklist.strip()}
'''.strip())

    def process_matrix(self, config: Config) -> str:
        namespace, name, branch, path = config
    
        stages = config.yaml['stages']

        # Every platform/version combination known to ansible-test in the devel branch should be listed below.
        # The key is the value used for --remote or --docker.
        # The value is a list of the entries which it replaces (if any). The values can be removed once they're no longer in any matrix.
        # This is the only place updates should be required when adding/removing platforms.
        # Be sure to add a new platform *and* define what it replaces at the same time.
        platforms = {
            'alpine3': [],
            'centos7': [],
            'fedora37': [],
            'opensuse15': [],
            'ubuntu2004': [],
            'ubuntu2204': [],
            'alpine/3.17': [],
            'fedora/37': [],
            'freebsd/12.4': [],
            'freebsd/13.2': ['freebsd/13.1'],
            'macos/13.2': [],
            'rhel/7.9': [],
            'rhel/8.7': [],
            'rhel/9.1': [],
            'ubuntu/20.04': [],
            'ubuntu/22.04': [],
            '': [],  # obsolete entries with no replacement go here
        }

        expected = set(platforms)
        deprecated: dict[str, str] = {}

        for platform, deprecated_platforms in platforms.items():
            for deprecated_platform in deprecated_platforms:
                if replacement := deprecated.get(deprecated_platform):
                    raise RuntimeError(f'"{deprecated_platform}" is listed as replaced by both "{replacement}" and "{platform}"')

                if deprecated_platform in platforms:
                    raise RuntimeError(f'"{platform}" is listed as both a current and deprecated platform')

                deprecated[deprecated_platform] = platform

        # Entries here are currently used in the ansible-core matrix, but are not recommended for collections.
        special = {
            'ios/csr1000v',
            'vyos/1.1.8',
        }

        tests: list[tuple[str, str | None]] = []

        for stage in stages:
            jobs = stage['jobs']
            stage_display_name = stage.get('displayName', stage['stage'])

            if stage_display_name == 'Dependencies':
                continue  # community.windows uses this to setup dependencies, not run tests

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
                            tests.append((test, stage_display_name))
                else:
                    for target in targets:
                        raw_test = target.get('test', target.get('name'))
                        test = test_format.format(raw_test)
                        tests.append((test, stage_display_name))
    
        tests_found = set()
        known_ansible_branches = ('devel', '2.9', '2.10', '2.11', '2.12', '2.13', '2.14', '2.15')

        for test, stage_display_name in tests:
            parts = test.split('@')[0].split('/')
    
            if namespace == 'ansible' and name == 'ansible':
                ansible_branch = 'devel'
                test_parts = parts
            else:
                if parts[0] not in known_ansible_branches:
                    raise Exception(f'Unexpected branch found in: {test}')
    
                ansible_branch = parts[0]
                test_parts = parts[1:]

                if (
                        any(supported_ansible_branch in stage_display_name for supported_ansible_branch in known_ansible_branches) and
                        ansible_branch not in stage_display_name
                ):
                    print(f'- [ ] {namespace}.{name}:{branch} - Branch "{ansible_branch}" does not match stage "{stage_display_name}"')
    
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
            elif test_type in ('freebsd', 'osx', 'macos', 'rhel', 'ios', 'vyos', 'alpine', 'fedora', 'ubuntu'):
                test_name = f'{test_type}/{test_parts[1]}'
            else:
                test_name = None
    
            if not test_name:
                if test_parts[0] == 'linux-community':
                    continue

                if test_parts[0] == 'lint':
                    continue  #  used by osbuild.composer / infra.osbuild

                raise Exception(f'Test name not extracted: {test}')

            test_name = re.sub('-pypi-latest$', '', test_name)  # work-around for community.docker collection

            tests_found.add(test_name)
    
        unknown = tests_found - expected - set(deprecated) - special
    
        if unknown:
            raise Exception(f'[{config.path}] Unknown test name: {unknown}')

        result = ''

        for test_found in tests_found:
            replacement = deprecated.get(test_found)

            if replacement is None:
                continue

            if replacement and replacement not in tests_found:
                result += f'  - [ ] Replace `{test_found}` with `{replacement}`\n'
            else:
                result += f'  - [ ] Remove `{test_found}`\n'

        if result:
            result = f'- [ ] {namespace}.{name}:{branch}\n{result}'

        return result


if __name__ == '__main__':
    main()
