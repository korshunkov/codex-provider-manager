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

    def test_remote_compaction_v2_is_detected_from_metadata(self):
        headers = {"x-codex-turn-metadata": '{"request_kind":"compaction"}'}
        self.assertTrue(codex_provider_proxy.is_compaction_request(headers, {}))
        self.assertTrue(
            codex_provider_proxy.is_compaction_request({}, {"request_kind": "compaction"})
        )
        self.assertFalse(codex_provider_proxy.is_compaction_request({}, {"model": "a6/kimi-k3"}))

    def test_compaction_stream_has_one_completed_compaction_item(self):
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        sent = []
        handler.send_response = lambda status: sent.append(("status", status))
        handler.send_header = lambda name, value: sent.append(("header", name, value))
        handler.end_headers = lambda: sent.append(("end",))

        response = {
            "id": "resp_compact_test",
            "object": "response",
            "model": "am/kimi-k3",
            "status": "completed",
            "output": [],
        }
        item = {
            "id": "item_resp_compact_test",
            "type": "compaction",
            "encrypted_content": "ready",
        }
        response["output"] = [item]
        handler.send_compaction_stream(response, item)

        raw = handler.wfile.getvalue().decode("utf-8")
        self.assertTrue(handler.close_connection)
        self.assertIn(("status", 200), sent)
        self.assertIn("event: response.output_item.done", raw)
        self.assertEqual(raw.count('"type": "compaction"'), 2)
        completed = json.loads(raw.split("event: response.completed\ndata: ", 1)[1].split("\n\n", 1)[0])
        self.assertEqual(completed["response"]["status"], "completed")
        self.assertEqual(len(completed["response"]["output"]), 1)
        self.assertEqual(completed["response"]["output"][0]["type"], "compaction")

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

    def test_forward_closes_clean_stream_without_terminal_event(self):
        class StreamWithoutCompletion:
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
                return b""

            def close(self):
                self.closed = True

        response = StreamWithoutCompletion()
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        handler.send_response = lambda _status: None
        handler.send_header = lambda *_args: None
        handler.end_headers = lambda: None
        handler.upstream_response = lambda _url, _payload, _provider: response

        handler.forward("https://example.test/responses", {}, "anymodel")

        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("event: response.created", body)
        self.assertIn("event: response.failed", body)
        self.assertTrue(handler.close_connection)
        self.assertTrue(response.closed)

    def test_forward_closes_body_without_explicit_length(self):
        class ChunkedJSONResponse:
            status = 200
            headers = Message()

            def __init__(self):
                self.headers["Content-Type"] = "application/json"
                self.closed = False
                self.read_count = 0

            def read(self, _size):
                self.read_count += 1
                if self.read_count == 1:
                    return b'{"type":"response.completed"}'
                return b""

            def close(self):
                self.closed = True

        response = ChunkedJSONResponse()
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        sent = []
        handler.send_response = lambda status: sent.append(("status", status))
        handler.send_header = lambda name, value: sent.append((name, value))
        handler.end_headers = lambda: sent.append(("end",))
        handler.upstream_response = lambda _url, _payload, _provider: response

        handler.forward("https://example.test/responses", {}, "anymodel")

        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('{"type":"response.completed"}', body)
        self.assertNotIn("event: response.failed", body)
        self.assertIn(("Connection", "close"), sent)
        self.assertTrue(handler.close_connection)
        self.assertTrue(response.closed)

    def test_forward_reports_non_stream_200_as_stream_failure(self):
        class NonStreamResponse:
            status = 200
            headers = Message()

            def __init__(self):
                self.headers["Content-Type"] = "application/json"
                self.closed = False
                self.read_count = 0

            def read(self, _size):
                self.read_count += 1
                if self.read_count == 1:
                    return b'{"type":"response.completed"}'
                return b""

            def close(self):
                self.closed = True

        response = NonStreamResponse()
        handler = object.__new__(codex_provider_proxy.ProxyHandler)
        handler.wfile = io.BytesIO()
        handler.close_connection = False
        handler.send_response = lambda _status: None
        handler.send_header = lambda *_args: None
        handler.end_headers = lambda: None
        handler.upstream_response = lambda _url, _payload, _provider: response

        handler.forward(
            "https://example.test/responses",
            {"stream": True},
            "anymodel",
        )

        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("event: response.failed", body)
        self.assertIn("upstream_stream_error", body)
        self.assertTrue(handler.close_connection)
        self.assertTrue(response.closed)

    def test_stream_terminal_event_may_span_chunks(self):
        pending = bytearray()
        self.assertFalse(
            codex_provider_proxy.observe_sse_terminal(b"event: response.comp", pending)
        )
        self.assertTrue(
            codex_provider_proxy.observe_sse_terminal(b"leted\ndata: {}\n\n", pending)
        )
        self.assertEqual(pending, bytearray())

    def test_chat_request_is_converted_for_responses_provider(self):
        request = {
            "messages": [
                {"role": "system", "content": "Be brief"},
                {"role": "user", "content": "ok?"},
            ],
            "max_tokens": 17,
            "stream": True,
            "tools": [{
                "type": "function",
                "function": {"name": "read", "parameters": {"type": "object"}},
            }],
        }
        payload = codex_provider_proxy.upstream_payload(request, "model", "responses", "chat")
        self.assertEqual(payload["model"], "model")
        self.assertEqual(payload["instructions"], "Be brief")
        self.assertEqual(payload["input"][-1]["content"][0]["text"], "ok?")
        self.assertEqual(payload["max_output_tokens"], 17)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["tools"][0]["name"], "read")

    def test_responses_request_is_converted_for_chat_provider(self):
        request = {
            "instructions": "Be brief",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "ok?"}]}],
            "max_output_tokens": 17,
            "stream": True,
            "tools": [{"type": "function", "name": "read", "parameters": {"type": "object"}}],
        }
        payload = codex_provider_proxy.upstream_payload(request, "model", "chat", "responses")
        self.assertEqual(payload["model"], "model")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][-1]["content"], "ok?")
        self.assertEqual(payload["max_tokens"], 17)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["tools"][0]["function"]["name"], "read")

    def test_responses_result_becomes_chat_completion(self):
        result = codex_provider_proxy.chat_completion_from_responses(
            {
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "ready"}]},
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "read",
                        "arguments": "{}",
                    },
                ],
                "usage": {"input_tokens": 3, "output_tokens": 4},
            },
            "proxy/model",
        )
        message = result["choices"][0]["message"]
        self.assertEqual(message["content"], "ready")
        self.assertEqual(message["tool_calls"][0]["id"], "call_1")
        self.assertEqual(result["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(result["usage"]["prompt_tokens"], 3)

    def test_chat_result_becomes_responses_payload(self):
        result = codex_provider_proxy.responses_from_chat_completion(
            {
                "choices": [{
                    "message": {"role": "assistant", "content": "ready"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
            "proxy/model",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model"], "proxy/model")
        self.assertEqual(result["output"][0]["content"][0]["text"], "ready")
        self.assertEqual(result["usage"]["input_tokens"], 3)

    def test_chat_stream_terminal_is_detected(self):
        pending = bytearray()
        self.assertFalse(
            codex_provider_proxy.observe_sse_terminal(
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n', pending
            )
        )
        self.assertTrue(
            codex_provider_proxy.observe_sse_terminal(b"data: [DONE]\n\n", pending)
        )


if __name__ == "__main__":
    unittest.main()
