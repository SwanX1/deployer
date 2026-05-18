import os
import logging
from typing import overload, Literal
import subprocess

logger = logging.getLogger(__name__)
logging.addLevelName(11, "DOCKER")
logging.addLevelName(12, "GIT")

class CommandResult:
    def __init__(self, exit_code: int, output: str):
        self.exit_code = exit_code
        self.output = output

    @property
    def success(self) -> bool:
        return self.exit_code == 0

def _print_subprocess_output(level: int, text: str):
    if text:
        for line in text.strip().splitlines():
            logger.log(level, line)

def run_git(args, pwd=None, capture_output=True) -> CommandResult:
    command = ['git'] + args

    # Pipe stdout and stderr to the logger
    process = subprocess.Popen(command, cwd=pwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()
    exit_code = process.returncode
    if not capture_output:
        _print_subprocess_output(12, stdout)
        _print_subprocess_output(logging.ERROR if exit_code != 0 else 12, stderr)
    if exit_code != 0:
        logger.error(f"Command failed: {' '.join(command)}")
        return CommandResult(exit_code, stdout.strip() + "\n" + stderr.strip())
    return CommandResult(exit_code, stdout.strip())


def run_docker_compose(args, pwd=None) -> CommandResult:
    command = ['docker', 'compose'] + args

    # Pipe stdout and stderr to the logger
    process = subprocess.Popen(command, cwd=pwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = process.communicate(timeout=3600) # If it takes more than an hour, something is very wrong.
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        logger.error(f"Command timed out: {' '.join(command)}")
        _print_subprocess_output(11, stdout)
        _print_subprocess_output(logging.ERROR, stderr)
        return CommandResult(-1, stdout.strip() + "\n" + stderr.strip())

    exit_code = process.returncode
    _print_subprocess_output(11, stdout)
    _print_subprocess_output(logging.ERROR if exit_code != 0 else 11, stderr)
    if exit_code != 0:
        logger.error(f"Command failed: {' '.join(command)}")
    return CommandResult(exit_code, stdout.strip())

def clone_repository(repo_url, target_dir) -> CommandResult:
    logger.info(f"Cloning repository from {repo_url} to {target_dir}...")
    # Ensure parent directory exists
    parent_dir = os.path.dirname(target_dir)
    os.makedirs(parent_dir, exist_ok=True)
    # git clone
    return run_git(['clone', '--verbose', '--depth', '1', '--recurse-submodules', '--shallow-submodules', repo_url, target_dir], capture_output=False)

def check_repository_exists(repo_dir) -> bool:
    if not os.path.exists(repo_dir):
        return False
    if not os.path.isdir(repo_dir):
        return False
    if not os.path.exists(os.path.join(repo_dir, '.git')):
        return False

    # If 'git status' returns non-zero, it means the repository does not exist or is not a valid git repository
    return run_git(['status', '--porcelain'], pwd=repo_dir, capture_output=True).success

def get_current_commit(repo_dir) -> str:
    # git rev-parse HEAD
    return run_git(['rev-parse', 'HEAD'], pwd=repo_dir, capture_output=True).output.strip()

def has_uncommitted_changes(repo_dir) -> bool:
    # git status --porcelain
    return run_git(['status', '--porcelain'], pwd=repo_dir, capture_output=True).output.strip() != ''

def get_latest_remote_commit(repo_url) -> CommandResult:
    # git ls-remote <url> HEAD
    result = run_git(['ls-remote', repo_url, 'HEAD'], capture_output=True)
    if not result.success:
        return result

    # Parse :)
    result.output = result.output.strip().split()[0].strip()
    return result

def fetch_latest(repo_dir) -> CommandResult:
    # git fetch
    return run_git(['fetch', '--verbose', '--depth', '1', '--prune', '--prune-tags', '--no-tags', '--recurse-submodules=on-demand'], pwd=repo_dir, capture_output=False)

def reset_to_commit(repo_dir, commit_hash) -> CommandResult:
    # git reset --hard <commit_hash>
    return run_git(['reset', '--hard', commit_hash], pwd=repo_dir, capture_output=False)

def docker_pull_images(dir) -> CommandResult:
    # docker compose pull
    return run_docker_compose(['pull', '--ignore-buildable', '--include-deps'], pwd=dir)

def docker_build_images(dir) -> CommandResult:
    # docker compose build
    return run_docker_compose(['build', '--pull', '--with-dependencies'], pwd=dir)

def docker_start_containers(dir) -> CommandResult:
    # docker compose up -d
    return run_docker_compose(['up', '--detach', '--force-recreate', '--remove-orphans', '--wait', '--yes'], pwd=dir)
