"""OpenAI Chat Completions vision requests.

The API key is never placed in the JSON body. Callers send it only as a
Bearer token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o"
MAX_OUTPUT_TOKENS = 1200

PROMPT = (
    "You are ScreenQuery. The user just captured their screen with a hotkey. "
    "Read the screenshot and respond to whatever question, problem, error message, "
    "code, or other content is visible. If there is a clear question, answer it. "
    "If there is an error or code, explain what it means and how to fix it. "
    "If nothing asks a question, give a short explanation of what is on screen. "
    "Be direct and useful. Use plain text."
)


class OpenAIError(Exception):
    """User-visible failure from the vision request."""


@dataclass(frozen=True)
class PreparedRequest:
    url: str
    body: bytes
    headers: dict[str, str]


def endpoint(base_url: str) -> str:
    raw = (base_url or "").strip()
    trimmed = raw or DEFAULT_BASE_URL
    if "://" not in trimmed:
        raise OpenAIError(
            f"The OpenAI base URL is not valid ({trimmed}). "
            "Use an https URL such as https://api.openai.com/v1."
        )
    scheme, rest = trimmed.split("://", 1)
    scheme = scheme.lower()
    rest = rest.split("#", 1)[0]
    rest = rest.split("?", 1)[0]
    host_port, _, path = rest.partition("/")
    host_port = host_port.split("@")[-1]
    host = host_port.split(":")[0].lower()
    if not host:
        raise OpenAIError(f"The OpenAI base URL is not valid ({trimmed}).")
    _require_secure(scheme, host)
    path = "/" + path if path else ""
    while path.endswith("/"):
        path = path[:-1]
    if path.endswith("/chat/completions"):
        final_path = path
    elif host == "api.openai.com" and path in {"", "/"}:
        final_path = "/v1/chat/completions"
    else:
        final_path = path + "/chat/completions"
    return f"{scheme}://{host_port}{final_path}"


def normalized_model(model: str | None) -> str:
    trimmed = (model or "").strip()
    return trimmed or DEFAULT_MODEL


def json_body(
    model: str | None,
    image_data: bytes,
    mime_type: str,
    token_field: str = "max_tokens",
) -> bytes:
    import base64

    if token_field not in {"max_tokens", "max_completion_tokens"}:
        raise OpenAIError(f"Unknown token field {token_field}.")
    payload = {
        "model": normalized_model(model),
        token_field: MAX_OUTPUT_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}",
                            "detail": "auto",
                        },
                    },
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def should_retry_replacing_max_tokens(error_message: str) -> bool:
    lower = error_message.lower()
    if "max_tokens" not in lower:
        return False
    hints = (
        "unsupported",
        "not supported",
        "unknown",
        "unrecognized",
        "unexpected",
        "max_completion_tokens",
        "invalid",
    )
    return any(hint in lower for hint in hints)


def error_message(data: bytes) -> str | None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        return message or "OpenAI rejected the request."
    return None


def parse_assistant_text(data: bytes) -> str:
    message = error_message(data)
    if message and _payload_has_error(data):
        raise OpenAIError(message)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenAIError("OpenAI returned a response ScreenQuery could not read.") from exc
    if not isinstance(payload, dict):
        raise OpenAIError("OpenAI returned a response ScreenQuery could not read.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAIError("OpenAI returned a response ScreenQuery could not read.")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message_obj = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message_obj, dict):
        raise OpenAIError("OpenAI returned a response ScreenQuery could not read.")
    content = message_obj.get("content")
    if isinstance(content, str):
        return _non_empty(content)
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return _non_empty("\n".join(parts))
    raise OpenAIError("OpenAI returned a response ScreenQuery could not read.")


def explain(
    image_data: bytes,
    mime_type: str,
    api_key: str,
    base_url: str,
    model: str | None,
    urlopen_fn=urlopen,
) -> str:
    try:
        return _send(
            image_data, mime_type, api_key, base_url, model, "max_tokens", urlopen_fn
        )
    except OpenAIError as exc:
        if should_retry_replacing_max_tokens(str(exc)):
            return _send(
                image_data,
                mime_type,
                api_key,
                base_url,
                model,
                "max_completion_tokens",
                urlopen_fn,
            )
        raise


def _send(
    image_data: bytes,
    mime_type: str,
    api_key: str,
    base_url: str,
    model: str | None,
    token_field: str,
    urlopen_fn,
) -> str:
    url = endpoint(base_url)
    body = json_body(model, image_data, mime_type, token_field)
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ScreenQuery/1.0",
        },
    )
    try:
        with urlopen_fn(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            data = response.read()
    except HTTPError as exc:
        data = exc.read()
        status = exc.code
        message = error_message(data)
        if message:
            raise OpenAIError(f"{message} (HTTP {status})") from None
        raise OpenAIError(f"OpenAI returned HTTP {status}.") from None
    except URLError as exc:
        raise OpenAIError(f"Could not reach OpenAI. {exc.reason}") from None
    except TimeoutError as exc:
        raise OpenAIError("Could not reach OpenAI. The request timed out.") from exc
    if status and not 200 <= int(status) <= 299:
        message = error_message(data)
        if message:
            raise OpenAIError(f"{message} (HTTP {status})")
        raise OpenAIError(f"OpenAI returned HTTP {status}.")
    return parse_assistant_text(data)


def _payload_has_error(data: bytes) -> bool:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and "error" in payload


def _non_empty(text: str) -> str:
    trimmed = text.strip()
    if not trimmed:
        raise OpenAIError("OpenAI returned an empty answer.")
    return trimmed


def _require_secure(scheme: str, host: str) -> None:
    if scheme == "https":
        return
    if scheme == "http" and host in {"localhost", "127.0.0.1"}:
        return
    raise OpenAIError(
        "The OpenAI base URL must use https. http is only allowed for localhost."
    )
