from deploy import enqueue_recheck
import subprocess
import shutil
import argparse
import os
import config
import logging

logger: logging.Logger = None  # ty:ignore[invalid-assignment]

UVICORN_LOG_CONFIG  = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s"},
    },
    "handlers": {
        "default": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "loggers": {
        "uvicorn":        {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}

def setup_logging():
    global logger
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger = logging.getLogger(__name__)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi_logger = logging.getLogger(name)
        uvi_logger.handlers = [handler]   # replace uvicorn's default handler
        uvi_logger.propagate = False          # stop double-logging

REQUIRED_TOOLS = ['git', 'docker']

def main():
    parser = argparse.ArgumentParser(description='Deployer Service')
    repo_directory = os.path.dirname(os.path.abspath(__file__))
    repo_directory = os.path.dirname(repo_directory)  # Move up one level to the parent directory
    parser.add_argument('--config', type=str, default=f"{repo_directory}/config.json", help='Path to configuration file')
    parser.add_argument('--reload', help='Tell the running service to reload its configuration and exit', action='store_true')

    args = parser.parse_args()
    config_path = args.config

    if not args.reload:
        setup_logging()
        # TODO: these checks should be actually done every time we run a deployment, not just at startup.
        # TODO: what if we uninstall docker or git while the service is running?
        failed_checks = False
        if shutil.which('git') is None:
            logging.error("Error: Git is not installed or not in PATH.")
            failed_checks = True
        if shutil.which('docker') is None:
            logging.error("Error: Docker is not installed or not in PATH.")
            failed_checks = True
        else:
            # Check for "docker compose" as well
            result = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True)
            if result.returncode != 0:
                logging.error("Error: Docker Compose is not available. Please ensure you have Docker Compose installed and accessible via 'docker compose'.")
                failed_checks = True

        if failed_checks:
            exit(1)
    else:
        global logger
        logging.basicConfig(level=logging.INFO, format='%(message)s') # Plain logs when --reload is used
        logger = logging.getLogger(__name__)
        
    if not os.path.exists(config_path):
        logger.fatal(f"Error: Configuration file '{config_path}' not found.")
        exit(1)
    elif not os.path.isfile(config_path):
        logger.fatal(f"Error: '{config_path}' is not a valid file.")
        exit(1)

    config.set_config_path(config_path)
    logger.info(f"Loading configuration from '{config_path}'...")
    config.load_config()

    if args.reload:
        import requests
        host = config.get_config().host
        if host == '0.0.0.0':
            host = 'localhost'

        url = f"http://{host}:{config.get_config().port}/reload"

        try:
            response = requests.post(url)
            if response.status_code == 200:
                logger.info(response.text)
            else:
                logger.error(f"{response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send reload request: {str(e)}")
        return

    # Enqueue recheck for all services at startup to ensure they are up to date
    for service in config.get_config().repositories:
        logger.info(f"Enqueuing initial deployment for service '{service.name}'...")
        enqueue_recheck(service)

    # Start service
    from server import app
    import uvicorn
    uvicorn.run(app, host=config.get_config().host, port=config.get_config().port, log_config=UVICORN_LOG_CONFIG)


if __name__ == "__main__":
    main()
