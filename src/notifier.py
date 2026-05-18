from datetime import datetime, timezone
from threading import Thread
import logging
from enum import Enum, auto
import config
import requests

logger = logging.getLogger(__name__)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING) # Suppress noisy logs from requests library

class NotificationType(Enum):
    CHECK_CANNOT_CLONE = auto()
    CHECK_UNCOMMITTED_CHANGES = auto()
    CHECK_LS_REMOTE_FAILED = auto()
    CHECK_FETCH_FAILED = auto()
    DEPLOY_STARTED = auto()
    DEPLOY_CANNOT_RESET = auto()
    DEPLOY_NO_DOCKER_COMPOSE = auto()
    DEPLOY_CANNOT_PULL = auto()
    DEPLOY_CANNOT_BUILD = auto()
    DEPLOY_CANNOT_START = auto()
    DEPLOY_SUCCESS = auto()

    def __str__(self):
        match self:
            case NotificationType.CHECK_CANNOT_CLONE:
                return "cannot clone repository"
            case NotificationType.CHECK_UNCOMMITTED_CHANGES:
                return "uncommitted changes found"
            case NotificationType.CHECK_LS_REMOTE_FAILED:
                return "failed to list remote refs"
            case NotificationType.CHECK_FETCH_FAILED:
                return "failed to fetch updates"
            case NotificationType.DEPLOY_STARTED:
                return "deployment started"
            case NotificationType.DEPLOY_CANNOT_RESET:
                return "failed to reset to latest commit"
            case NotificationType.DEPLOY_NO_DOCKER_COMPOSE:
                return "no docker-compose file found"
            case NotificationType.DEPLOY_CANNOT_PULL:
                return "failed to pull latest Docker images"
            case NotificationType.DEPLOY_CANNOT_BUILD:
                return "failed to build Docker images"
            case NotificationType.DEPLOY_CANNOT_START:
                return "failed to start Docker containers (timeout)"
            case NotificationType.DEPLOY_SUCCESS:
                return "deployment completed successfully"

def log_and_notify(type: NotificationType, service: str, message: str | None):
    level = 0
    match type:
        case NotificationType.CHECK_CANNOT_CLONE:
            level = logging.ERROR
            logger.log(level, f"Failed to clone repository for {service}.")
        case NotificationType.CHECK_UNCOMMITTED_CHANGES:
            level = logging.WARNING
            logger.log(level, f"Uncommitted changes found in {service}. Skipping deployment.")
        case NotificationType.CHECK_LS_REMOTE_FAILED:
            level = logging.ERROR
            logger.log(level, f"Failed to list remote refs for {service}.")
        case NotificationType.CHECK_FETCH_FAILED:
            level = logging.ERROR
            logger.log(level, f"Failed to fetch updates for {service}.")
        case NotificationType.DEPLOY_STARTED:
            level = logging.INFO
            logger.log(level, f"Deployment started for {service}.")
        case NotificationType.DEPLOY_CANNOT_RESET:
            level = logging.ERROR
            logger.log(level, f"Failed to reset {service} to latest commit.")
        case NotificationType.DEPLOY_NO_DOCKER_COMPOSE:
            level = logging.WARNING
            logger.log(level, f"No docker-compose file found in {service}. Skipping Docker deployment.")
        case NotificationType.DEPLOY_CANNOT_PULL:
            level = logging.ERROR
            logger.log(level, f"Failed to pull latest Docker images for {service}.")
        case NotificationType.DEPLOY_CANNOT_BUILD:
            level = logging.ERROR
            logger.log(level, f"Failed to build required Docker images for {service}.")
        case NotificationType.DEPLOY_CANNOT_START:
            level = logging.ERROR
            logger.log(level, f"Failed to start Docker containers for {service}.")
        case NotificationType.DEPLOY_SUCCESS:
            level = logging.INFO
            logger.log(level, f"Deployment of {service} complete.")

    for notification in config.get_config().notifications:
        if notification.type == 'discord':
            # Send off
            Thread(target=discord_send, args=(notification.url, type, service, message, level, notification.username)).start()

def discord_send(webhook_url: str, type: NotificationType, service: str, message: str | None, level: int, username: str):
    color = 0x57F287 # Green for success/info

    match level:
        case logging.WARNING:
            color = 0xFEE75C # Yellow for warnings
        case logging.ERROR:
            color = 0xED4245 # Red for errors

    description = None
    
    match type:
        case NotificationType.CHECK_CANNOT_CLONE:
            title = f"`{service}` - Deployment failed"
            description = "Failed to clone repository"
        case NotificationType.CHECK_UNCOMMITTED_CHANGES:
            title = f"`{service}` - Deployment skipped"
            description = f"Uncommitted changes found in {service}. Skipping deployment."
        case NotificationType.CHECK_LS_REMOTE_FAILED:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to list remote refs for {service}."
        case NotificationType.CHECK_FETCH_FAILED:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to fetch updates for {service}."
        case NotificationType.DEPLOY_STARTED:
            title = f"`{service}` - Deployment started"
        case NotificationType.DEPLOY_CANNOT_RESET:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to reset {service} to latest commit."
        case NotificationType.DEPLOY_NO_DOCKER_COMPOSE:
            title = f"`{service}` - Deployment failed"
            description = f"No docker-compose file found in {service}. Skipping Docker deployment."
        case NotificationType.DEPLOY_CANNOT_PULL:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to pull latest Docker images for {service}."
        case NotificationType.DEPLOY_CANNOT_BUILD:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to build required Docker images for {service}."
        case NotificationType.DEPLOY_CANNOT_START:
            title = f"`{service}` - Deployment failed"
            description = f"Failed to start Docker containers for {service}."
        case NotificationType.DEPLOY_SUCCESS:
            title = f"`{service}` - Deployment successful"
            description = f"Deployment of {service} complete."

    if message is not None:
        description = f"{description}\n\nAdditional info: ```\n{message}\n```" if message is not None else description

    embed = {
        "title": title,
        "color": color,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if description is not None:
        embed["description"] = description

    response = requests.post(webhook_url, json={
        "username": username,
        "embeds": [embed]
    })

    if not response.ok:
        logger.error(f"Failed to send notification to Discord webhook (status code {response.status_code}): {response.text}")

