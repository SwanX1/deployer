import json
from pydantic import BaseModel
import hmac
from typing import Literal
from urllib.parse import parse_qs

type WebhookType = Literal['github', 'forgejo', 'gitea']
WEBHOOK_TYPE_TO_HEADER: dict[WebhookType, str] = {
    'github': 'GitHub',
    'forgejo': 'Forgejo',
    'gitea': 'Gitea'
}

def determine_webhook_type(headers) -> WebhookType | None:
    for type, header in WEBHOOK_TYPE_TO_HEADER.items():
        if f'X-{header}-Event' in headers:
            return type
    return None

def get_webhook_event(headers) -> str | None:
    for header in WEBHOOK_TYPE_TO_HEADER.values():
        if f'X-{header}-Event' in headers:
            return headers[f'X-{header}-Event']
    return None

def get_webhook_delivery(headers) -> str | None:
    for header in WEBHOOK_TYPE_TO_HEADER.values():
        if f'X-{header}-Delivery' in headers:
            return headers[f'X-{header}-Delivery']
    return None

def get_payload(body: str | bytes, content_type: str) -> str | None:
    if isinstance(body, bytes):
        body = body.decode('utf-8')
    
    if content_type == 'application/json':
        return body
    elif content_type == 'application/x-www-form-urlencoded':
        # If the content type is form data, we need to extract the payload
        parsed = parse_qs(body)
        payload = parsed.get('payload')
        if payload and isinstance(payload, list) and len(payload) > 0:
            return payload[0]

    return None

def get_signature(type: WebhookType, headers) -> str | None:
    signature = None
    # Cannot use WEBHOOK_TYPE_TO_HEADER here because the header names are not consistent (WHY IS IT NOT "X-GitHub-Signature-256"??)
    if type == 'github':
        signature = headers.get('X-Hub-Signature-256')
    elif type == 'forgejo':
        signature = headers.get('X-Forgejo-Signature-256')
    elif type == 'gitea':
        signature = headers.get('X-Gitea-Signature-256')

    if signature is None:
        return None

    sha256literal, signature = signature.split('=')
    if sha256literal != 'sha256':
        return None

    return signature

def validate_webhook(payload: str, secret: str, signature: str) -> bool:
    hash = hmac.new(secret.encode(), msg=payload.encode(), digestmod='sha256')
    return hmac.compare_digest(hash.hexdigest(), signature)

class PushInfo(BaseModel):
    repository: str
    possible_urls: list[str]
    ref: str
    commit: str

def extract_push_info(type: WebhookType, payload: str) -> PushInfo | None:
    if type == 'github':
        try:
            data = json.loads(payload)
            repository = data['repository']['name']
            possible_urls = [data['repository']['clone_url'], data['repository']['ssh_url'], data['repository']['git_url'], data['repository']['svn_url']]
            ref = data['ref']
            commit = data['after']
        except Exception as _:
            return None
        return PushInfo(repository=repository, possible_urls=possible_urls, ref=ref, commit=commit)
    else:
        return None # TODO: implement for forgejo and gitea as well (are they different from github?)
