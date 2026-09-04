from pathlib import Path
import importlib.util
from importlib.machinery import SourceFileLoader
import sys
import tomllib
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "codex-provider"
SPEC = importlib.util.spec_from_loader(
    "codex_provider", SourceFileLoader("codex_provider", str(MODULE_PATH))
)
codex_provider = importlib.util.module_from_spec(SPEC)
sys.modules["codex_provider"] = codex_provider
SPEC.loader.exec_module(codex_provider)


class CodexProviderTests(unittest.TestCase):
    def test_managed_table_with_comment_is_replaced(self) -> None:
        text = "\n".join(
            [
                'model = "gpt-5.6-terra"',
                "",
                "[model_providers.custom]",
                'name = "Custom"',
                "",
                "[model_providers.codex-sale] # installed by codex-provider",
                'name = "Old"',
                'base_url = "https://old.example/v1"',
                "",
            ]
        )

        updated = codex_provider.configured_text(text, "anymodel")
        config = tomllib.loads(updated)

        self.assertEqual(config["model_provider"], "codex-sale")
        self.assertEqual(config["model_providers"]["codex-sale"]["base_url"], "https://anymodel.org/v1")
        self.assertEqual(config["model_providers"]["custom"]["name"], "Custom")
        self.assertEqual(updated.count("[model_providers.codex-sale]"), 1)

    def test_zcode_provider_is_created_and_model_list_is_replaced(self) -> None:
        config = {"provider": {"other": {"name": "Other", "models": {"old": {}}}}}
        selections = [
            {"provider_id": "a6api", "model_id": "gpt-5.6-terra", "proxy_id": "a6/gpt-5.6-terra"},
            {"provider_id": "openrouter-all", "model_id": "z-ai/glm-5.3", "proxy_id": "or/z-ai/glm-5.3"},
        ]
        models = {
            "a6api": {"gpt-5.6-terra": {"context_window": 200_000, "input_modalities": ["text", "image"]}},
            "openrouter-all": {"z-ai/glm-5.3": {"context_window": 100_000, "input_modalities": ["text"]}},
        }
        names = {}
        config, provider_key = codex_provider.upsert_zcode_provider(
            config, selections, models, names
        )

        provider = config["provider"][provider_key]
        self.assertEqual(provider_key, "codex-provider-manager")
        self.assertEqual(provider["options"]["baseURL"], codex_provider.PROXY_BASE_URL)
        self.assertEqual(list(provider["models"]), [item["proxy_id"] for item in selections])
        self.assertEqual(provider["models"]["a6/gpt-5.6-terra"]["limit"]["context"], 200_000)
        self.assertEqual(
            provider["models"]["a6/gpt-5.6-terra"]["modalities"]["input"],
            ["text", "image"],
        )
        self.assertEqual(config["provider"]["other"]["models"], {"old": {}})

        selections = [selections[0]]
        config, provider_key = codex_provider.upsert_zcode_provider(
            config, selections, models, names
        )
        provider = config["provider"][provider_key]
        self.assertEqual(list(provider["models"]), ["a6/gpt-5.6-terra"])
        self.assertEqual(config["provider"]["other"]["models"], {"old": {}})


if __name__ == "__main__":
    unittest.main()
