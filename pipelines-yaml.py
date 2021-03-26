#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""Output a list of paths or a globs, for finding azure-pipelines.yml files."""

from __future__ import annotations

import argparse
import glob
import os

try:
    import argcomplete
except ImportError:
    argcomplete = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--globs', action='store_true')

    if argcomplete:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()

    base_path = '~/.ansible/azp-tools/repos'

    patterns = (
        os.path.join(base_path, 'ansible-collections/*/*/ansible_collections/*/*/.azure-pipelines/azure-pipelines.yml'),
        os.path.join(base_path, 'ansible/ansible/*/.azure-pipelines/azure-pipelines.yml'),
    )

    results = []

    if args.globs:
        results.extend(patterns)
    else:
        for pattern in patterns:
            results.extend(glob.glob(os.path.expanduser(pattern)))

    print(' '.join(results))


if __name__ == '__main__':
    main()
