from notifier import log_and_notify, NotificationType
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
        result = t.clone_repository(service.url, dir)
        if not result.success:
            log_and_notify(NotificationType.CHECK_CANNOT_CLONE, name, result.output)
            return
        latest_commit = t.get_current_commit(dir)
        force = True # Force deployment for new clones
    else:
        # Check if the repository has changes (in else block to avoid unnecessary checks for new clones)
        if t.has_uncommitted_changes(dir):
            log_and_notify(NotificationType.CHECK_UNCOMMITTED_CHANGES, name, None)
            return
        

        # Check current commit hash
        current_commit = t.get_current_commit(dir)
        logging.info(f"Current commit hash for {name}: {current_commit}")


        # Get the latest commit hash from the remote repository
        result = t.get_latest_remote_commit(service.url)
        if not result.success:
            log_and_notify(NotificationType.CHECK_LS_REMOTE_FAILED, name, result.output)
            return

        latest_commit = result.output
        
        logging.info(f"Latest commit hash for {name} on remote: {latest_commit}")

        if current_commit == latest_commit:
            logging.info(f"{name} is already up to date.")
            return

        # Fetch latest changes
        logging.info(f"Fetching latest changes for {name}...")
        result = t.fetch_latest(dir)
        if not result.success:
            log_and_notify(NotificationType.CHECK_FETCH_FAILED, name, result.output)
            return

        force = False

    redeploy(service, latest_commit, force)

def redeploy(service: RepositoryConfig, commit_hash: str, force: bool = False):
    # Assume the repository is already cloned, checked for changes,
    # fetched, and actually needs (re)deployment

    dir = service.directory
    name = service.name

    log_and_notify(NotificationType.DEPLOY_STARTED, name, None)

    previous_commit = t.get_current_commit(dir)
    if previous_commit == commit_hash and not force: # Redundant in this code
        logging.info(f"{name} is already at the latest commit {commit_hash}. No need to redeploy.")
        return

    # Reset to latest commit
    logging.info(f"Resetting {name} to latest commit...")
    result = t.reset_to_commit(dir, commit_hash)

    if not result.success:
        log_and_notify(NotificationType.DEPLOY_CANNOT_RESET, name, result.output)
        return

    base_dir = service.directory

    # Check for docker-compose.yml file
    if not path.exists(path.join(base_dir, 'docker-compose.yml')) and not path.exists(path.join(base_dir, 'docker-compose.yaml')):
        log_and_notify(NotificationType.DEPLOY_NO_DOCKER_COMPOSE, name, "No docker-compose.yml or docker-compose.yaml file found in commit")
        _revert(service, previous_commit)
        return

    # Pull latest images
    result = t.docker_pull_images(base_dir)
    if not result.success:
        log_and_notify(NotificationType.DEPLOY_CANNOT_PULL, name, result.output )
        _revert(service, previous_commit)
        return

    result = { "stage": "build", "success": False }

    # This can run indefinitely for all we care. (there is a hard limit of 1 hour in tools.py)
    def subprocess():
        # Build required containers
        cresult = t.docker_build_images(base_dir)
        result["stage"] = "start"
        if not cresult.success:
            output = cresult.output
            # Use only last 20 lines of output to avoid excessively long messages
            output_lines = output.splitlines()
            if len(output_lines) > 20:
                output = "\n".join(output_lines[-20:])
            log_and_notify(NotificationType.DEPLOY_CANNOT_BUILD, name, output)
            _revert(service, previous_commit)
            return

        # Start containers
        cresult = t.docker_start_containers(base_dir)
        result["stage"] = "complete"
        if not cresult.success:
            output = cresult.output
            # Use only last 20 lines of output to avoid excessively long messages
            output_lines = output.splitlines()
            if len(output_lines) > 20:
                output = "\n".join(output_lines[-20:])
            log_and_notify(NotificationType.DEPLOY_CANNOT_START, name, output)
            # No point in reverting. No idea how to even begin to revert a
            # failed container start. Just log the error and return.
            # We could end up in a loop of:
            #  - try to start containers, fail
            #  - revert to previous commit
            #  - try to start containers again, fail again
            return

        result["success"] = True
    
    subprocess_thread = Thread(target=subprocess)
    subprocess_thread.start()
    subprocess_thread.join(timeout=180) # Wait for up to 3 minutes for the deployment to complete

    if subprocess_thread.is_alive():
        if result["stage"] == "build":
            log_and_notify(NotificationType.DEPLOY_CANNOT_BUILD, name, "Timeout reached, too long to build")
        elif result["stage"] == "start":
            log_and_notify(NotificationType.DEPLOY_CANNOT_START, name, "Timeout reached, too long to start")
        return

    if result["success"]:
        log_and_notify(NotificationType.DEPLOY_SUCCESS, name, f"Deployment is now using commit {commit_hash}\nPrevious commit was {previous_commit}")
    
    

def _revert(service: RepositoryConfig, commit_hash: str):
    dir = service.directory
    name = service.name

    # Reset to previous commit
    logging.info(f"Reverting {name} to previous commit...")
    result = t.reset_to_commit(dir, commit_hash)

    if not result.success:
        logging.error(f"Failed to revert {name} to commit {commit_hash}.")
        return
