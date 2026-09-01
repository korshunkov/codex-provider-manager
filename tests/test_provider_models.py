from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from provider_models import (  # noqa: E402
    SHELF_LIMIT,
    _is_free_openrouter_model,
    build_shelf,
    find_model,
    merge_reasoning_from_reference,
)


def model(model_id: str) -> dict:
    return {
        "id": model_id,
        "display_name": model_id,
        "description": model_id,
        "context_window": 128000,
        "input_modalities": ["text"],
        "reasoning_levels": ["medium"],
        "default_reasoning_level": "medium",
    }


class ProviderModelsTests(unittest.TestCase):
    def test_openrouter_keeps_only_free_text_tool_models(self) -> None:
        compatible = {
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["text"]},
            "supported_parameters": ["tools"],
        }
        self.assertTrue(_is_free_openrouter_model(compatible))
        self.assertFalse(_is_free_openrouter_model({**compatible, "pricing": {"prompt": "0.1", "completion": "0"}}))
        self.assertFalse(_is_free_openrouter_model({**compatible, "supported_parameters": ["temperature"]}))

    def test_short_openai_name_matches_provider_prefixed_name(self) -> None:
        models = [model("cx/gpt-5.6-sol"), model("glm/glm-5.3")]
        self.assertEqual(find_model(models, "gpt-5.6-sol")["id"], "cx/gpt-5.6-sol")

    def test_shelf_is_limited_and_keeps_selected_model_first(self) -> None:
        models = [model(f"vendor/model-{index}") for index in range(50)]
        state = {"last_model": {}, "favorites": {}, "recent": {}}
        shelf = build_shelf("anymodel", {"model": "vendor/model-2"}, models, state, "vendor/model-40")
        self.assertEqual(len(shelf), SHELF_LIMIT)
        self.assertEqual(shelf[0]["id"], "vendor/model-40")

    def test_reasoning_can_be_filled_from_unique_reference_model(self) -> None:
        a6_model = model("glm-5.3-flash")
        reference = model("z-ai/glm-5.3-flash")
        batch_reference = model("z-ai/glm-5.3-flash:batch")
        reference["reasoning_levels"] = ["low", "medium", "high"]
        reference["default_reasoning_level"] = "medium"
        enriched = merge_reasoning_from_reference([a6_model], [reference, batch_reference])
        self.assertEqual(enriched[0]["reasoning_levels"], ["low", "medium", "high"])

    def test_reasoning_reference_requires_unique_match(self) -> None:
        a6_model = model("glm-5.3-flash")
        refs = [model("one/glm-5.3-flash"), model("two/glm-5.3-flash")]
        for ref in refs:
            ref["reasoning_levels"] = ["low", "medium", "high"]
        enriched = merge_reasoning_from_reference([a6_model], refs)
        self.assertEqual(enriched[0]["reasoning_levels"], ["medium"])


if __name__ == "__main__":
    unittest.main()
