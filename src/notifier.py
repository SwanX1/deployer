from enum import Enum, auto
from config import Config, RepositoryConfig

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


def log_and_notify(type: NotificationType, service: str, message: str):
    # TODO: discord webhook
    pass

