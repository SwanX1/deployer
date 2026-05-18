import os
import logging
from typing import overload, Literal
import subprocess

logger = logging.getLogger(__name__)

@overload
def run_git(args, pwd=None, capture_output: Literal[True] = True) -> tuple[int, str]: ...
@overload
def run_git(args, pwd=None, capture_output: Literal[False] = False) -> int: ...

def run_git(args, pwd=None, capture_output=False) -> int | tuple[int, str]:
    command = ['git'] + args
    if capture_output:
        result = subprocess.run(command, cwd=pwd, capture_output=True, text=True)
        return result.returncode, result.stdout.strip()

    # Pipe stdout and stderr to the logger
    process = subprocess.Popen(command, cwd=pwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    if stdout:
        logger.info(stdout.strip())
    if stderr:
        logger.error(stderr.strip())
    return process.returncode


def run_docker_compose(args, pwd=None) -> int:
    command = ['docker', 'compose'] + args

    # Pipe stdout and stderr to the logger
    process = subprocess.Popen(command, cwd=pwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=3600) # If it takes more than an hour, something is very wrong.
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        logger.error(f"Command timed out: {' '.join(command)}")
        if stdout:
            logger.info(stdout.strip())
        if stderr:
            logger.error(stderr.strip())
        return -1

    if stdout:
        logger.info(stdout.strip())
    if stderr:
        logger.error(stderr.strip())
    return process.returncode

def clone_repository(repo_url, target_dir) -> bool:
    logger.info(f"Cloning repository from {repo_url} to {target_dir}...")
    # git clone
    return run_git(['clone', '--verbose', '--depth', '1', '--recurse-submodules', '--shallow-submodules', repo_url, target_dir], capture_output=False) == 0

def check_repository_exists(repo_dir) -> bool:
    if not os.path.exists(repo_dir):
        return False
    if not os.path.isdir(repo_dir):
        return False
    if not os.path.exists(os.path.join(repo_dir, '.git')):
        return False

    # If 'git status' returns non-zero, it means the repository does not exist or is not a valid git repository
    return run_git(['status', '--porcelain'], pwd=repo_dir, capture_output=True)[0] == 0

def get_current_commit(repo_dir) -> str:
    # git rev-parse HEAD
    return run_git(['rev-parse', 'HEAD'], pwd=repo_dir, capture_output=True)[1]

def has_uncommitted_changes(repo_dir) -> bool:
    # git status --porcelain
    return run_git(['status', '--porcelain'], pwd=repo_dir, capture_output=True)[1].strip() != ''

def get_latest_remote_commit(repo_url) -> str | None:
    # git ls-remote <url> HEAD
    result = run_git(['ls-remote', repo_url, 'HEAD'], capture_output=True)
    if result[0] != 0:
        return None
    return result[1].split()[0]

def fetch_latest(repo_dir) -> bool:
    # git fetch
    return run_git(['fetch', '--verbose', '--depth', '1', '--prune', '--prune-tags', '--no-tags', '--recurse-submodules=on-demand'], pwd=repo_dir, capture_output=False) == 0

def reset_to_commit(repo_dir, commit_hash) -> bool:
    # git reset --hard <commit_hash>
    return run_git(['reset', '--hard', commit_hash], pwd=repo_dir, capture_output=False) == 0

def docker_pull_images(dir) -> bool:
    # docker compose pull
    return run_docker_compose(['pull', '--ignore-buildable', '--include-deps'], pwd=dir) == 0

def docker_build_images(dir) -> bool:
    # docker compose build
    return run_docker_compose(['build', '--pull', '--with-dependencies'], pwd=dir) == 0

def docker_start_containers(dir) -> bool:
    # docker compose up -d
    return run_docker_compose(['up', '--detach', '--force-recreate', '--remove-orphans', '--wait', '--yes'], pwd=dir) == 0
