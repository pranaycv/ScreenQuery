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
    "You are ScreenQuery. Look at the screenshot. "
    "If it shows a question, a problem, a quiz, or anything that wants an answer, "
    "reply with only the answer. Be direct. Do not restate the question and do not add a label. "
    "If it is not a question, describe the topic in two or three sentences. "
    "Use very easy words, as if you are explaining it to a friend. "
    "When you write more than one sentence, put each sentence on its own line. "
    "Plain text."
)

REGION_PROMPT = (
    "You are ScreenQuery. The user dragged a rectangle around a small part of the screen. "
    "If that crop is one word, or only one line of text, explain what that word or that line means. "
    "Use two or three sentences and very easy words. "
    "If the crop is a question, a problem, or a quiz, reply with only the answer. "
    "Be direct. Do not restate the question and do not add a label. "
    "Otherwise describe what is in the crop in two or three sentences, in very easy words. "
    "When you write more than one sentence, put each sentence on its own line. "
    "Plain text."
)


def prompt_for(kind: str | None) -> str:
    if kind == "region":
        return REGION_PROMPT
    return PROMPT


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
    kind: str = "window",
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
                    {"type": "text", "text": prompt_for(kind)},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}",
                            "detail": "high" if kind == "region" else "auto",
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
    kind: str = "window",
) -> str:
    try:
        return _send(
            image_data, mime_type, api_key, base_url, model, "max_tokens", urlopen_fn, kind
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
                kind,
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
    kind: str = "window",
) -> str:
    url = endpoint(base_url)
    body = json_body(model, image_data, mime_type, token_field, kind)
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
