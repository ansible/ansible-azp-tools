# ansible-azp-tools
Tools for working with Ansible projects using Azure Pipelines.

## Set up

NOTE: Python 3.10 or 3.11 are required. The Azure DevOps SDK does not yet support Python 3.12.
1. Install Python dependencies needed to run scripts from this repository to a preferred location using `pip install -r requirements.txt`.
2. Populate `~/.config/ansible-azp-tools/azure-devops.key` and `~/.config/ansible-azp-tools/github.key` with Personal Access Tokens for Azure Pipelines and GitHub, respectively.
3. Run `./sync.py --find --update` to clone the repositories/branches needed for the scripts to check the configurations of the repositories.

## check-pipelines.py
Check for out-of-date Azure Pipelines configurations testing against ansible-core.

* `./check-pipelines.py matrix` - check for out-of-date platform references in the test matrix
* `./check-pipelines.py container` - check for out-of-date `quay.io/ansible/azure-pipelines-test-container` versions

## pipelines-sanity.py
Run sanity tests against the default branch of each collection in Azure Pipelines

## pipelines-yaml.py
Output a list of paths or a globs, for finding azure-pipelines.yml files.
