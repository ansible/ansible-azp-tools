# ansible-azp-tools
Tools for working with Ansible projects using Azure Pipelines.

## Set up
1. Install Python dependencies needed to run scripts from this repository to a preferred location using `pip install -r requirements.txt`.
2. Populate `~/.config/ansible-azp-tools/azure-devops.key` and `~/.config/ansible-azp-tools/github.key` with Personal Access Tokens for Azure Pipelines and Github, respectively.
3. Run `./sync.py --find --update` to clone the repositories/branches needed for the scripts to check the configurations of the repositories.

## check-pipelines.py
* `./check-pipelines.py matrix` - checks for out-of-date Azure Pipelines configuration matrix testing against ansible-core devel branch
* `./check-pipelines.py container` - check for out-of-date `quay.io/ansible/azure-pipelines-test-container` versions

## pipelines-sanity.py
TBD

## pipelines-yaml.py
TBD
