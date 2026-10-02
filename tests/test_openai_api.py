import json
import unittest
from urllib.error import HTTPError

from screenquery.openai_api import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    OpenAIError,
    endpoint,
    error_message,
    explain,
    json_body,
    parse_assistant_text,
    should_retry_replacing_max_tokens,
)


class Response:
    def __init__(self, status, payload):
        self.status = status
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class OpenAIRequestTests(unittest.TestCase):
    def test_default_and_v1_base_urls(self):
        self.assertEqual(endpoint(""), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(endpoint("https://api.openai.com/v1"), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(endpoint("https://api.openai.com/v1/"), "https://api.openai.com/v1/chat/completions")
        self.assertEqual(endpoint("https://api.openai.com"), "https://api.openai.com/v1/chat/completions")

    def test_full_completions_url_drops_query(self):
        self.assertEqual(
            endpoint("https://example.com/v1/chat/completions?debug=1"),
            "https://example.com/v1/chat/completions",
        )

    def test_custom_base_appends_completions_path(self):
        self.assertEqual(
            endpoint("https://proxy.example/openai/v1"),
            "https://proxy.example/openai/v1/chat/completions",
        )

    def test_localhost_http_is_allowed(self):
        self.assertEqual(
            endpoint("http://127.0.0.1:8080/v1"),
            "http://127.0.0.1:8080/v1/chat/completions",
        )

    def test_insecure_remote_url_is_rejected(self):
        with self.assertRaises(OpenAIError):
            endpoint("http://example.com/v1")

    def test_invalid_url_is_rejected(self):
        with self.assertRaises(OpenAIError):
            endpoint("not a url")

    def test_userinfo_is_stripped(self):
        self.assertEqual(
            endpoint("https://user:secret@api.openai.com/v1"),
            "https://api.openai.com/v1/chat/completions",
        )

    def test_json_body_carries_image_and_omits_any_api_key(self):
        body = json.loads(json_body(" gpt-4o ", b"pixels", "image/jpeg"))
        self.assertEqual(body["model"], "gpt-4o")
        self.assertEqual(body["max_tokens"], MAX_OUTPUT_TOKENS)
        self.assertNotIn("max_completion_tokens", body)
        content = body["messages"][0]["content"]
        self.assertIn("ScreenQuery", content[0]["text"])
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(content[1]["image_url"]["detail"], "auto")
        raw = json.dumps(body)
        self.assertNotIn("sk-", raw)
        self.assertNotIn("Bearer", raw)
        self.assertNotIn("api_key", raw)

    def test_completion_token_field(self):
        body = json.loads(json_body("", b"\x00", "image/png", token_field="max_completion_tokens"))
        self.assertEqual(body["model"], DEFAULT_MODEL)
        self.assertEqual(body["max_completion_tokens"], MAX_OUTPUT_TOKENS)
        self.assertNotIn("max_tokens", body)

    def test_retry_hint(self):
        self.assertTrue(
            should_retry_replacing_max_tokens(
                "Unsupported parameter: max_tokens. Use max_completion_tokens instead."
            )
        )
        self.assertFalse(should_retry_replacing_max_tokens("Incorrect API key provided."))

    def test_parse_string_and_array_content(self):
        string_payload = json.dumps({"choices": [{"message": {"content": "  A blue window.  "}}]}).encode()
        self.assertEqual(parse_assistant_text(string_payload), "A blue window.")
        array_payload = json.dumps(
            {"choices": [{"message": {"content": [{"type": "text", "text": "Line one"}, {"type": "text", "text": "Line two"}]}}]}
        ).encode()
        self.assertEqual(parse_assistant_text(array_payload), "Line one\nLine two")

    def test_parse_api_error_empty_and_malformed(self):
        error = b'{"error":{"message":"Incorrect API key provided."}}'
        with self.assertRaises(OpenAIError):
            parse_assistant_text(error)
        self.assertEqual(error_message(error), "Incorrect API key provided.")
        empty = b'{"choices":[{"message":{"content":"  "}}]}'
        with self.assertRaises(OpenAIError):
            parse_assistant_text(empty)
        with self.assertRaises(OpenAIError):
            parse_assistant_text(b"[]")

    def test_explain_retries_with_completion_tokens_and_keeps_key_out_of_body(self):
        calls = []

        def urlopen(request, timeout=0):
            calls.append(request)
            if len(calls) == 1:
                return Response(
                    400,
                    {"error": {"message": "Unsupported parameter: max_tokens"}},
                )
            return Response(200, {"choices": [{"message": {"content": "Done"}}]})

        text = explain(b"pixels", "image/jpeg", "sk-test-key", "https://api.openai.com/v1", "gpt-4o", urlopen)
        self.assertEqual(text, "Done")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer sk-test-key")
        first = calls[0].data.decode()
        second = calls[1].data.decode()
        self.assertIn("max_tokens", first)
        self.assertNotIn("sk-test-key", first)
        self.assertIn("max_completion_tokens", second)
        self.assertNotIn("max_tokens", second)
        self.assertNotIn("sk-test-key", second)
        self.assertIsNotNone(HTTPError)


if __name__ == "__main__":
    unittest.main()
