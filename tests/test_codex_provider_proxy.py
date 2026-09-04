import importlib.util
import io
import json
from importlib.machinery import SourceFileLoader
import unittest
from pathlib import Path
from email.message import Message
from http.client import IncompleteRead


PROXY_PATH = Path(__file__).resolve().parents[1] / "src" / "codex-provider-proxy"
spec = importlib.util.spec_from_file_location(
    "codex_provider_proxy",
    PROXY_PATH,
    loader=SourceFileLoader("codex_provider_proxy", str(PROXY_PATH)),
)
codex_provider_proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex_provider_proxy)


class CodexProviderProxyTests(unittest.TestCase):
    def test_proxy_names_use_short_provider_prefixes(self):
        self.assertEqual(codex_provider_proxy.proxy_model_id("a6api", "kimi-k3"), "a6/kimi-k3")
        self.assertEqual(codex_provider_proxy.proxy_model_id("openrouter-all", "z-ai/glm-5.3"), "or/z-ai/glm-5.3")
        self.assertEqual(codex_provider_proxy.proxy_model_id("anymodel", "am/kimi-k3"), "am/kimi-k3")

    def test_model_route_uses_exact_selected_model_and_separate_compaction(self):
        state = {
            "selected_models": [
                {"provider_id": "anymodel", "model_id": "am/kimi-k3"},
                {"provider_id": "a6api", "model_id": "kimi-k3"},
            ],
            "compaction_model": {"provider_id": "openrouter-all", "model_id": "z-ai/glm-5.3"},
        }
        self.assertEqual(
            codex_provider_proxy.model_route(state, "a6/kimi-k3"),
            {"provider_id": "a6api", "model_id": "kimi-k3"},
        )
        self.assertEqual(
            codex_provider_proxy.model_route(state, "or/z-ai/glm-5.3"),
            {"provider_id": "openrouter-all", "model_id": "z-ai/glm-5.3"},
        )
        self.assertIsNone(codex_provider_proxy.model_route(state, "unknown"))

    def test_compaction_text_supports_responses_and_chat_completions(self):
        responses_payload = {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "ready"}]}
            ]
        }
        chat_payload = {
            "choices": [{"message": {"content": "summarized"}}]
        }
        self.assertEqual(codex_provider_proxy.response_text(responses_payload), "ready")
        self.assertEqual(codex_provider_proxy.response_text(chat_payload), "summarized")

    def test_stream_failure_event_uses_failed_response_status(self):
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.send_stream_failure()

        raw = handler.wfile.getvalue().decode("utf-8")
        self.assertTrue(raw.startswith("event: response.failed\n"))
        event = json.loads(raw.split("data: ", 1)[1])
        self.assertEqual(event["type"], "response.failed")
        self.assertEqual(event["response"]["status"], "failed")
        self.assertEqual(event["response"]["error"]["code"], "upstream_stream_error")

    def test_forward_closes_truncated_stream_with_failure_event(self):
        class TruncatedResponse:
            status = 200
            headers = Message()

            def __init__(self):
                self.headers["Content-Type"] = "text/event-stream"
                self.closed = False
                self.read_count = 0

            def read(self, _size):
                self.read_count += 1
                if self.read_count == 1:
                    return b"event: response.created\ndata: {}\n\n"
                raise IncompleteRead(b"partial")

            def close(self):
                self.closed = True

        response = TruncatedResponse()
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        sent = []
        handler.send_response = lambda status: sent.append(("status", status))
        handler.send_header = lambda name, value: sent.append(("header", name, value))
        handler.end_headers = lambda: sent.append(("end",))
        handler.upstream_response = lambda _url, _payload, _provider: response

        handler.forward("https://example.test/responses", {}, "anymodel")

        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("event: response.created", body)
        self.assertIn("event: response.failed", body)
        self.assertIn("upstream_stream_error", body)
        self.assertTrue(handler.close_connection)
        self.assertTrue(response.closed)
        self.assertIn(("status", 200), sent)


if __name__ == "__main__":
    unittest.main()
