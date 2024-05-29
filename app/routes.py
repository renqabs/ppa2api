import logging
import os
from datetime import datetime, timedelta

from flask import request, Response, current_app as app, Blueprint

from app.utils import send_chat_message, fetch_channel_id, map_model_name, process_content, get_user_contents, \
    generate_hash, get_next_auth_token, handle_error
from app.config import IGNORED_MODEL_NAMES, IMAGE_MODEL_NAMES, AUTH_TOKEN
from app.config import configure_logging

configure_logging()
storage_map = {}

def requires_auth(f):
    """装饰器函数，用于保护需要认证的路由"""
    def decorated(*args, **kwargs):
        authorization = request.headers.get('Authorization')
        accesstoken = os.getenv('ACCESS_TOKEN')
        try:
            prefix, token = authorization.split()
            if prefix.lower() != "bearer" or token != accesstoken:
                return Response('Invalid Access Token', 401)
        except:
            return Response('Authorization Failed', 401)
        return f(*args, **kwargs)
    return decorated

@app.route("/yyds/v1/chat/completions", methods=["GET", "POST", "OPTIONS"])
@requires_auth
def onRequest():
    try:
        return fetch(request)
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return handle_error(e)


@app.route('/yyds/v1/models')
def list_models():
    return {
        "object": "list",
        "data": [{
            "id": m,
            "object": "model",
            "created": int(datetime.now().timestamp()),
            "owned_by": "popai"
        } for m in IGNORED_MODEL_NAMES]
    }


def get_channel_id(hash_value, token, model_name, content, template_id):
    if hash_value in storage_map:
        channel_id, expiry_time = storage_map[hash_value]
        if expiry_time > datetime.now() and channel_id:
            return channel_id
    channel_id = fetch_channel_id(token, model_name, content, template_id)
    expiry_time = datetime.now() + timedelta(days=1)
    storage_map[hash_value] = (channel_id, expiry_time)
    return channel_id


def fetch(req):
    if req.method == "OPTIONS":
        return Response(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'})
    token = get_next_auth_token(AUTH_TOKEN.split(','))
    body = req.get_json()
    messages = body.get("messages", [])
    model_name = body.get("model")
    prompt = body.get("prompt", False)
    stream = body.get("stream", False)

    model_to_use = map_model_name(model_name)
    template_id = 2000000 if model_name in IMAGE_MODEL_NAMES else ''

    if not messages and prompt:
        final_user_content = prompt
        channel_id = os.getenv("CHAT_CHANNEL_ID")
    elif messages:
        last_message = messages[-1]
        final_user_content, image_url = process_content(last_message.get('content'))
        user_contents = get_user_contents(messages)
        hash_value = generate_hash(user_contents, model_to_use, token)
        channel_id = get_channel_id(hash_value, token, model_to_use, final_user_content, template_id)

    if final_user_content is None:
        return Response("No user message found", status=400)

    return send_chat_message(req, token, channel_id, final_user_content, model_to_use, stream, image_url)
