#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

from __future__ import annotations

import argparse
import os
import subprocess
import typing as t
import urllib.parse
import re
import github
import shutil
import sys

import azure.devops.connection
import azure.devops.v6_0.build.build_client
import azure.devops.v6_0.build.models
import azure.devops.v6_0.core.core_client
import azure.devops.v6_0.core.models
import azure.devops.v6_0.pipelines.models
import azure.devops.v6_0.pipelines.pipelines_client
import msrest.authentication

try:
    import argcomplete
except ImportError:
    argcomplete = None


def get_azure_devops_key() -> str:
    with open(os.path.expanduser('~/.config/ansible-azp-tools/azure-devops.key')) as key_file:
        return key_file.read().strip()


def get_github_token() -> str:
    with open(os.path.expanduser('~/.config/ansible-azp-tools/github.key')) as key_file:
        return key_file.read().strip()


def get_connection() -> azure.devops.connection.Connection:
    base_url = 'https://dev.azure.com/ansible'

    creds = msrest.authentication.BasicAuthentication('', get_azure_devops_key())
    connection = azure.devops.connection.Connection(base_url=base_url, creds=creds)

    return connection


def get_projects(
        core_client: azure.devops.v6_0.core.core_client.CoreClient,
) -> t.List[azure.devops.v6_0.core.models.TeamProjectReference]:
    return core_client.get_projects()


def get_pipelines(
        pipelines_client: azure.devops.v6_0.pipelines.pipelines_client.PipelinesClient,
        project: str,
) -> t.List[azure.devops.v6_0.pipelines.models.Pipeline]:
    return pipelines_client.list_pipelines(project)


def get_definition(
        build_client: azure.devops.v6_0.build.build_client.BuildClient,
        project: str,
        definition_id: int,
) -> azure.devops.v6_0.build.models.BuildDefinition:
    return build_client.get_definition(project, definition_id)


def find_repos() -> t.Dict[str, t.List[str]]:
    connection = get_connection()

    core_client = connection.clients_v6_0.get_core_client()
    pipelines_client = connection.clients_v6_0.get_pipelines_client()
    build_client = connection.clients_v6_0.get_build_client()

    repo_names = []
    unhandled_projects = {}

    collection_github_orgs = (
        'ansible-collections',
        'redhat-cop',
    )

    for project in get_projects(core_client):
        repositories = []

        for pipeline in get_pipelines(pipelines_client, project.name):
            # noinspection PyProtectedMember
            web_href = urllib.parse.urlparse(pipeline._links.additional_properties['web']['href'])
            definition_id = int(urllib.parse.parse_qs(web_href.query)['definitionId'][0])
            definition = get_definition(build_client, project.name, definition_id)
            repository: azure.devops.v6_0.build.models.BuildRepository = definition.repository

            repositories.append(repository)

        if not repositories:
            continue

        if len(repositories) != 1:
            raise Exception(f'{project.name}: {repositories}')

        repository = repositories[0]

        if repository.url == 'https://github.com/ansible/ansible.git':
            repo_names.append('ansible/ansible')
            continue

        handled = False

        for github_org in collection_github_orgs:
            match = re.search(rf'^https://github.com/{github_org}/(?P<collection>.*)\.git$', repository.url)

            if match:
                collection = match.group('collection')

                if project.name != collection:
                    raise Exception(f'{project.name} != {collection}')

                repo_names.append(f'{github_org}/{collection}')
                handled = True
                break

        if handled:
            continue

        if '.' not in project.name:
            continue  # ignore projects without a dot, under the assumption they're not a collection

        unhandled_projects[project.name] = repository.url

    if unhandled_projects:
        raise Exception(f'Unhandled projects: {unhandled_projects}')

    gh = github.Github(login_or_token=get_github_token())
    repos = {}

    for repo_name in sorted(repo_names):
        try:
            repo = gh.get_repo(repo_name)
        except github.GithubException:
            # handle private repositories here (if any)
            raise

        branches = list(repo.get_branches())

        all_branch_names = sorted(b.name for b in branches)

        if repo_name == 'ansible/ansible':
            stable_matches = [m.group('version').split('.') for m in [re.search('stable-(?P<version>[0-9]+.[0-9]+)', b) for b in all_branch_names] if m]
            stable_versions = sorted([(int(m[0]), int(m[1])) for m in stable_matches], reverse=True)
            latest_versions = stable_versions[:4]
            filtered_branch_names = ['devel'] + [f'stable-{v[0]}.{v[1]}' for v in latest_versions]
        else:
            filtered_branch_names = [b for b in all_branch_names if re.search('^(devel|main|master|stable-.*)$', b)]

        repos[repo_name] = sorted(filtered_branch_names)

    return repos


def update_repos(base_path: str, repos: t.Dict[str, t.List[str]]) -> None:
    for repo, branches in repos.items():
        print(f'{repo}:')

        for branch in branches:
            print(f'  {branch}')

            path = os.path.join(base_path, repo, branch)

            if repo != 'ansible/ansible':
                path = os.path.join(path, 'ansible_collections', repo.split('/')[1].replace('.', '/'))  # make collections usable in place

            stderr = sys.stderr.buffer

            if os.path.exists(path):
                subprocess.run(['git', 'checkout', '.'], stdout=stderr, check=True, cwd=path)
                subprocess.run(['git', 'clean', '-fxd'], stdout=stderr, check=True, cwd=path)
                subprocess.run(['git', 'pull'], stdout=stderr, check=True, cwd=path)
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                subprocess.run(['git', 'clone', f'https://github.com/{repo}', '--branch', branch, path], stdout=stderr, check=True)

        existing_branches = os.listdir(os.path.join(base_path, repo))
        purge_branches = set(existing_branches) - set(branches)

        for branch in purge_branches:
            print(f'  {branch} - purge')

            path = os.path.join(base_path, repo, branch)
            shutil.rmtree(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--find', action='store_true')
    parser.add_argument('--update', action='store_true')

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    base_dir = os.path.expanduser('~/.ansible/azp-tools/repos')

    if args.find:
        repos = find_repos()

        for repo, branches in repos.items():
            print(f'{repo}:')

            for branch in branches:
                print(f'  {branch}')
    else:
        orgs = sorted(os.listdir(base_dir))
        projects = sorted(f'{org}/{project}' for org in orgs for project in os.listdir(os.path.join(base_dir, org)))
        repos = {name: sorted(os.listdir(os.path.join(base_dir, name))) for name in projects}

    if args.update:
        os.makedirs(base_dir, exist_ok=True)
        update_repos(base_dir, repos)


if __name__ == '__main__':
    main()
