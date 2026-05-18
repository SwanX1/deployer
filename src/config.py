import json
from os import path
import logging
from pydantic import BaseModel, ValidationInfo, field_validator

logger = logging.getLogger(__name__)

class RepositoryConfig(BaseModel):
    name: str
    url: str
    directory: str
    branch: str | None = None

    @field_validator('directory', mode='after')
    def resolve_directory(cls, v: str, info: ValidationInfo) -> str:
        resolved_directory = path.abspath(v)
        if resolved_directory != v:
            logger.debug(f"Resolved directory for {info.data['name']} is '{resolved_directory}' (original: '{v}')")
        return resolved_directory
    
    @field_validator('branch', mode='after')
    def validate_branch(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            logger.debug(f"No branch specified for {info.data['name']}, defaulting to remote HEAD")
        return v


class NotificationConfig(BaseModel):
    type: str
    url: str

    @field_validator('type', mode='before')
    def validate_type(cls, v: str) -> str:
        if v not in ['discord']:
            raise ValueError(f"Unsupported notification type: {v}")
        return v


class Config(BaseModel):
    repositories: list[RepositoryConfig] = []
    notifications: list[NotificationConfig] = []
    host: str
    port: int
    webhook_secret: str | None = None

    @field_validator('webhook_secret', mode='before')
    def validate_webhook_secret(cls, v: str | None) -> str | None:
        if v is None:
            logger.warning("No secret_key specified in configuration. Webhook security will be disabled.")
        return v

    @field_validator('repositories', mode='after')
    def validate_repositories(cls, v: list[RepositoryConfig]) -> list[RepositoryConfig]:
        # Check for duplicate repository names
        names = set()
        for repo in v:
            if repo.name in names:
                raise ValueError(f"Duplicate repository name: {repo.name}")
            names.add(repo.name)
        return v


CONFIG: Config | None = None
CONFIG_PATH: str | None = None

def set_config_path(path: str):
    global CONFIG_PATH
    CONFIG_PATH = path

def get_config() -> Config:
    global CONFIG
    if CONFIG is None:
        raise ValueError("Configuration has not been loaded yet.")
    return CONFIG


def load_config():
    global CONFIG
    global CONFIG_PATH
    if CONFIG_PATH is None:
        raise ValueError("Configuration path has not been set.")
    with open(CONFIG_PATH, 'r') as f:
        data = json.load(f)

    CONFIG = Config(**data)
