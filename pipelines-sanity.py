#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""Run sanity tests against the default branch of each collection in Azure Pipelines."""

from __future__ import annotations

import argparse
import glob
import os
import subprocess

try:
    import argcomplete
except ImportError:
    argcomplete = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='stop on sanity test failure')
    parser.add_argument('--docker', action='store_true', help='run tests using docker')
    parser.add_argument('--test', action='append', default=[], help='run only specified test(s)')

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    base_path = '~/.ansible/azp-tools/repos'

    paths = glob.glob(os.path.expanduser(os.path.join(base_path, 'ansible-collections/*/*/ansible_collections/*/*')))
    paths = [path for path in paths if path.split(os.path.sep)[-4] in ('main', 'master')]

    cmd = ['ansible-test', 'sanity', '-v']

    if args.docker:
        cmd.append('--docker')

    for test in args.test:
        cmd.extend(['--test', test])

    for path in paths:
        print(f'---[ {path} ]---')
        subprocess.run(cmd, cwd=path, check=args.check)
        print(f'---[ {path} ]---')


if __name__ == '__main__':
    main()
