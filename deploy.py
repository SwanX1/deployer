#!/usr/bin/env python3

import logging
import os
import shutil
import subprocess

os.chdir("/home/service")

# Tee-like logging setup
LOG_FILE = '/var/log/deploy.log'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)
logging.info("Starting deployment process...")
logging.info(f"Logging to {LOG_FILE} and console.")

REQUIRED_TOOLS = ['git', 'docker']

for tool in REQUIRED_TOOLS:
    if shutil.which(tool) is None:
        logging.error(f"Error: {tool} is not installed or not in PATH.")
        exit(1)
    if tool == 'docker':
        # Check for "docker compose" as well
        result = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True)
        if result.returncode != 0:
            logging.error("Error: Docker Compose is not available. Please ensure you have Docker Compose installed and accessible via 'docker compose'.")
            exit(1)

REPOSITORIES = [
    "https://git.martindienas.lv/Infra/Ahaz.git",
    "https://git.martindienas.lv/Infra/CTFd.git",
]

def update_repository(repo_url):
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    logging.info(f"Updating {repo_name} from {repo_url}...")
    
    # Check if the repository already exists locally
    if not os.path.exists(repo_name):
        logging.info(f"Cloning repository {repo_name}...")
        subprocess.run(['git', 'clone', '--verbose', '--depth', '1', '--recurse-submodules', '--shallow-submodules', repo_url, repo_name], check=True)

    # Check current commit hash
    os.chdir(repo_name)

    result = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)
    current_commit = result.stdout.strip()
    logging.info(f"Current commit hash for {repo_name}: {current_commit}")

    # Check if the repository has changes
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    if result.stdout.strip():
        logging.warning(f"Warning: Repository {repo_name} has uncommitted changes. Please commit or stash them before deploying.")
        return

    # Get the latest commit hash from the remote repository
    result = subprocess.run(['git', 'ls-remote', repo_url, 'HEAD'], capture_output=True, text=True)
    latest_commit = result.stdout.split()[0]
    logging.info(f"Latest commit hash for {repo_name} on remote: {latest_commit}")

    if current_commit == latest_commit:
        logging.info(f"{repo_name} is already up to date.")
        return

    logging.info(f"Fetching latest changes for {repo_name}...")
    subprocess.run(['git', 'fetch', '--verbose', '--depth', '1', '--prune', '--prune-tags', '--no-tags', '--recurse-submodules=on-demand'], check=True)

    logging.info(f"Resetting {repo_name} to latest commit...")
    subprocess.run(['git', 'reset', '--hard', latest_commit], check=True)

def deploy_repository(repo_url):
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    if not os.path.exists(repo_name):
        logging.error(f"Error: Repository {repo_name} does not exist locally. Cannot deploy.")
        return

    os.chdir(repo_name)

    # Check for docker-compose.yml file
    if not os.path.exists('docker-compose.yml') and not os.path.exists('docker-compose.yaml'):
        logging.warning(f"Warning: No docker-compose.yml found in {repo_name}. Skipping Docker deployment.")
        return

    logging.info(f"Deploying {repo_name} using Docker Compose...")
    logging.info(f"Pulling latest Docker images for {repo_name}...")
    subprocess.run(['docker', 'compose', 'pull', '--ignore-buildable', '--include-deps'], check=True)

    logging.info(f"Building required containers for {repo_name}...")
    subprocess.run(['docker', 'compose', 'build', '--pull', '--with-dependencies'], check=True)

    logging.info(f"Starting containers for {repo_name}...")
    subprocess.run(['docker', 'compose', 'up', '--detach', '--force-recreate', '--remove-orphans', '--wait', '--yes'], check=True)


for repo in REPOSITORIES:
    pwd = os.getcwd()
    update_repository(repo)
    if os.getcwd() != pwd:
        os.chdir(pwd)
    deploy_repository(repo)
    if os.getcwd() != pwd:
        os.chdir(pwd)
