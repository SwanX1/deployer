import webhooks
import json
from threading import Thread
import deploy
import logging
import config
from quart import Quart, request, Response

app = Quart(__name__)
logger = logging.getLogger(__name__)

@app.route('/recheck/<service>', methods=['POST'])
async def recheck(service: str):
    config_data = config.get_config()
    repo = next((repo for repo in config_data.repositories if repo.name == service), None)
    if repo is None:
        return f"Service '{service}' not found in configuration.", 404
    Thread(target=deploy.recheck, args=(repo,)).start() # TODO: replace with task queue
    return Response(f"Recheck triggered for {service}", 202, mimetype='text/plain')

@app.route('/reload', methods=['POST'])
async def reload():
    logger.info("Reload triggered")
    try:
        config.load_config()
    except Exception as e:
        logger.error(f"Failed to reload configuration: {str(e)}")
        return Response(f"Failed to reload configuration: {str(e)}", 500, mimetype='text/plain')
    logger.info("Configuration reloaded successfully")
    return Response("Configuration reloaded successfully", 200, mimetype='text/plain')

@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.content_type != 'application/json' and request.content_type != 'application/x-www-form-urlencoded':
        return Response("Unsupported Media Type", 415, mimetype='text/plain')

    determined_type = webhooks.determine_webhook_type(request.headers)
    if determined_type is None:
        return Response("Unrecognized webhook type", 400, mimetype='text/plain')

    # TODO: idempotency with delivery header

    body = webhooks.get_payload(await request.get_data(as_text=True), request.content_type)
    if body is None:
        return Response("Bad Request: Unable to extract payload", 400, mimetype='text/plain')

    if not body:
        return Response("Bad Request: Empty request body", 400, mimetype='text/plain')

    # Validate webhook secret
    secret = config.get_config().webhook_secret
    if secret is not None:
        signature = webhooks.get_signature(determined_type, request.headers)
        if signature is None:
            return Response("Bad Request: Missing signature", 400, mimetype='text/plain')
        if not webhooks.validate_webhook(body, secret, signature):
            return Response("Unauthorized: Invalid signature", 401, mimetype='text/plain')

    

    try:
        body = json.loads(body)
    except json.JSONDecodeError:
        return Response("Bad Request: Invalid JSON in request body", 400, mimetype='text/plain')

    print(f"Received webhook ({determined_type}): {json.dumps(body, indent=2)}")
    print(f"Headers: {json.dumps(dict(request.headers), indent=2)}")

    # TODO: Actually handle webhook

    return Response("Accepted", 202, mimetype='text/plain')
