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


if __name__ == "__main__":
    unittest.main()
