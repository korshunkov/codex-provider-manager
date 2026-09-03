import importlib.util
from importlib.machinery import SourceFileLoader
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
