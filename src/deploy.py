from time import sleep
from os import path
from config import RepositoryConfig
from threading import Thread, Lock
import tools as t
import logging

logger = logging.getLogger(__name__)

SERVICE_THREADS: dict[str, Thread] = {} # Map from service name to thread object
SERVICE_THREADS_LOCK = Lock() # Lock to protect access to SERVICE_THREADS

def is_service_deploying(service_name: str) -> bool:
    with SERVICE_THREADS_LOCK:
        thread = SERVICE_THREADS.get(service_name)
        if thread is not None and thread.is_alive():
            return True
    return False

def enqueue_recheck(service: RepositoryConfig):
    name = service.name

    if is_service_deploying(name):
        # Start a new thread that waits for the current deployment to finish, then starts a new deployment
        def wait_and_recheck(deployment_thread: Thread):
            logger.info(f"Waiting for current deployment of {name} to finish before starting new deployment...")
            
            while deployment_thread.is_alive():
                sleep(1) # Check every second if the deployment is still running
            recheck(service)

        with SERVICE_THREADS_LOCK:
            thread = Thread(target=wait_and_recheck, args=(SERVICE_THREADS[name],))
            thread.start()
            SERVICE_THREADS[name] = thread
    else:
        # Start a new deployment immediately
        thread = Thread(target=recheck, args=(service,))
        thread.start()
        with SERVICE_THREADS_LOCK:
            SERVICE_THREADS[name] = thread

def recheck(service: RepositoryConfig):
    dir = service.directory
    name = service.name
    logging.info(f"Updating {name} from {service.url}...")

    # Check if the repository already exists locally
    if not t.check_repository_exists(dir):
        logging.info(f"Cloning repository {name}...")
        success = t.clone_repository(service.url, dir)
        if not success:
            logging.error(f"Failed to clone repository {name}.")
            return
        latest_commit = t.get_current_commit(dir)
        force = True # Force deployment for new clones
    else:
        # Check if the repository has changes (in else block to avoid unnecessary checks for new clones)
        if t.has_uncommitted_changes(dir):
            logging.warning(f"Warning: Repository {name} has uncommitted changes. Please commit or stash them before deploying.")
            return
        

        # Check current commit hash
        current_commit = t.get_current_commit(dir)
        logging.info(f"Current commit hash for {name}: {current_commit}")


        # Get the latest commit hash from the remote repository
        latest_commit = t.get_latest_remote_commit(service.url)
        if latest_commit is None:
            logging.error(f"Failed to get latest commit hash for {name} from remote.")
            return
        
        logging.info(f"Latest commit hash for {name} on remote: {latest_commit}")

        if current_commit == latest_commit:
            logging.info(f"{name} is already up to date.")
            return

        # Fetch latest changes
        logging.info(f"Fetching latest changes for {name}...")
        success = t.fetch_latest(dir)
        if not success:
            logging.error(f"Failed to fetch latest changes for {name}.")
            return

        force = False

    redeploy(service, latest_commit, force)

def redeploy(service: RepositoryConfig, commit_hash: str, force: bool = False):
    # Assume the repository is already cloned, checked for changes,
    # fetched, and actually needs (re)deployment

    dir = service.directory
    name = service.name

    previous_commit = t.get_current_commit(dir)
    if previous_commit == commit_hash and not force: # Redundant in this code
        logging.info(f"{name} is already at the latest commit {commit_hash}. No need to redeploy.")
        return

    # Reset to latest commit
    logging.info(f"Resetting {name} to latest commit...")
    success = t.reset_to_commit(dir, commit_hash)

    if not success:
        logging.error(f"Failed to reset {name} to commit {commit_hash}.")
        return

    base_dir = service.directory

    # Check for docker-compose.yml file
    if not path.exists(path.join(base_dir, 'docker-compose.yml')) and not path.exists(path.join(base_dir, 'docker-compose.yaml')):
        logging.warning(f"Warning: No docker-compose.yml found in {name}. Skipping Docker deployment.")
        _revert(service, previous_commit)
        return

    # Pull latest images
    success = t.docker_pull_images(base_dir)
    if not success:
        logging.error(f"Failed to pull latest Docker images for {name}.")
        _revert(service, previous_commit)
        return

    result = { "stage": "build" }

    # This can run indefinitely for all we care. (there is a hard limit of 1 hour in tools.py)
    def subprocess():
        # Build required containers
        success = t.docker_build_images(base_dir)
        result["stage"] = "start"
        if not success:
            logging.error(f"Failed to build required Docker images for {name}.")
            _revert(service, previous_commit)
            return

        # Start containers
        success = t.docker_start_containers(base_dir)
        result["stage"] = "complete"
        if not success:
            logging.error(f"Failed to start Docker containers for {name}.")
            # No point in reverting. No idea how to even begin to revert a
            # failed container start. Just log the error and return.
            # We could end up in a loop of:
            #  - try to start containers, fail
            #  - revert to previous commit
            #  - try to start containers again, fail again
            return
    
    subprocess_thread = Thread(target=subprocess)
    subprocess_thread.start()
    subprocess_thread.join(timeout=180) # Wait for up to 3 minutes for the deployment to complete

    if subprocess_thread.is_alive():
        if result["stage"] == "build":
            logging.error(f"Build for {name} is taking too long...")
        elif result["stage"] == "start":
            logging.error(f"Starting containers for {name} is taking too long...")
        return

    logging.info(f"Deployment of {name} complete.")
    
    

def _revert(service: RepositoryConfig, commit_hash: str):
    dir = service.directory
    name = service.name

    # Reset to previous commit
    logging.info(f"Reverting {name} to previous commit...")
    success = t.reset_to_commit(dir, commit_hash)

    if not success:
        logging.error(f"Failed to revert {name} to commit {commit_hash}.")
        return
