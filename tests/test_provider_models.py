from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from provider_models import (  # noqa: E402
    SHELF_LIMIT,
    _is_free_openrouter_model,
    build_shelf,
    a6_marketplace_estimates,
    find_model,
    merge_a6_marketplace_prices,
    merge_artificial_analysis_from_reference,
    merge_reasoning_from_reference,
    normalize_model,
    _with_model_fields,
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
        "reasoning_levels_source": "reference",
        "input_price_per_million": None,
        "output_price_per_million": None,
        "intelligence_index": None,
        "coding_index": None,
        "agentic_index": None,
        "supports_search_tool": None,
        "supports_function_tools": True,
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

    def test_any_model_pricing_uses_five_cent_base(self) -> None:
        normalized = normalize_model("anymodel", {
            "id": "glm/glm-5.3",
            "billing": {
                "unit": "token",
                "coefficient": {"input": 1.5, "output": 0.6},
            },
            "benchmarks": {
                "artificial_analysis": {
                    "intelligence_index": 57.0,
                    "coding_index": 71.0,
                    "agentic_index": 59.1,
                },
            },
        })
        self.assertAlmostEqual(normalized["input_price_per_million"], 0.075)
        self.assertAlmostEqual(normalized["output_price_per_million"], 0.03)
        self.assertEqual(normalized["intelligence_index"], 57.0)
        self.assertEqual(normalized["coding_index"], 71.0)
        self.assertEqual(normalized["agentic_index"], 59.1)

    def test_openrouter_prices_are_scaled_to_million_tokens(self) -> None:
        normalized = normalize_model("openrouter-all", {
            "id": "z-ai/glm-5.3",
            "pricing": {"prompt": "0.0000014", "completion": "0.0000044"},
            "benchmarks": {
                "artificial_analysis": {
                    "intelligence_index": 58.1,
                    "coding_index": 71.8,
                    "agentic_index": 59.1,
                },
            },
        })
        self.assertEqual(normalized["input_price_per_million"], 1.4)
        self.assertEqual(normalized["output_price_per_million"], 4.4)
        self.assertEqual(normalized["intelligence_index"], 58.1)
        self.assertEqual(normalized["coding_index"], 71.8)
        self.assertEqual(normalized["agentic_index"], 59.1)

    def test_a6_marketplace_prices_cut_expensive_half_and_mark_estimate(self) -> None:
        estimates = a6_marketplace_estimates([
            {"model_name": "qwen3.8-max", "input_price_micros": 10, "output_price_micros": 10,
             "charge_type": "per_token", "pricing_currency": "USD", "pricing_unit": "per_1m_tokens",
             "listing_availability": 1},
            {"model_name": "qwen3.8-max", "input_price_micros": 30, "output_price_micros": 30,
             "charge_type": "per_token", "pricing_currency": "USD", "pricing_unit": "per_1m_tokens",
             "listing_availability": 1},
            {"model_name": "qwen3.8-max", "input_price_micros": 100, "output_price_micros": 100,
             "charge_type": "per_token", "pricing_currency": "USD", "pricing_unit": "per_1m_tokens",
             "listing_availability": 1},
            {"model_name": "qwen3.8-max", "input_price_micros": 500, "output_price_micros": 500,
             "charge_type": "per_token", "pricing_currency": "USD", "pricing_unit": "per_1m_tokens",
             "listing_availability": 1},
        ])
        self.assertAlmostEqual(estimates["qwen3.8-max"]["input"], 0.00002)
        self.assertAlmostEqual(estimates["qwen3.8-max"]["output"], 0.00002)

        models = merge_a6_marketplace_prices([model("qwen3.8-max")], estimates)
        self.assertEqual(models[0]["price_is_estimate"], True)

    def test_analysis_indices_are_filled_from_unique_reference(self) -> None:
        anymodel = model("glm/glm-5.3")
        reference = model("z-ai/glm-5.3")
        reference["intelligence_index"] = 58.1
        reference["coding_index"] = 71.8
        reference["agentic_index"] = 59.1
        enriched = merge_artificial_analysis_from_reference([anymodel], [reference])
        self.assertEqual(enriched[0]["intelligence_index"], 58.1)
        self.assertEqual(enriched[0]["coding_index"], 71.8)
        self.assertEqual(enriched[0]["agentic_index"], 59.1)

    def test_anymodel_does_not_invent_reasoning_levels_or_search_support(self) -> None:
        normalized = normalize_model("anymodel", {
            "id": "am/kimi-k3",
            "capabilities": {"reasoning": True, "search": False, "tools": True},
        })
        self.assertEqual(normalized["reasoning_levels"], ["medium"])
        self.assertEqual(normalized["default_reasoning_level"], "medium")
        self.assertFalse(normalized["supports_search_tool"])
        self.assertTrue(normalized["supports_function_tools"])

    def test_explicit_provider_reasoning_levels_are_not_replaced(self) -> None:
        normalized = normalize_model("anymodel", {
            "id": "am/kimi-k3",
            "reasoning": {
                "supported_efforts": ["low", "medium"],
                "default_effort": "low",
            },
        })
        reference = model("moonshotai/kimi-k3")
        reference["reasoning_levels"] = ["max", "high", "low"]
        reference["default_reasoning_level"] = "max"
        enriched = merge_reasoning_from_reference([normalized], [reference])
        self.assertEqual(enriched[0]["reasoning_levels"], ["low", "medium"])
        self.assertEqual(enriched[0]["default_reasoning_level"], "low")

    def test_search_support_can_be_read_from_openrouter_parameters(self) -> None:
        normalized = normalize_model("openrouter-all", {
            "id": "vendor/search-model",
            "supported_parameters": ["tools", "web_search_options"],
        })
        self.assertTrue(normalized["supports_search_tool"])

    def test_models_without_tools_are_not_offered(self) -> None:
        self.assertIsNone(normalize_model("anymodel", {
            "id": "am/text-only",
            "capabilities": {"tools": False},
        }))

    def test_anymodel_reasoning_levels_are_inherited_from_openrouter(self) -> None:
        anymodel = normalize_model("anymodel", {
            "id": "am/kimi-k3",
            "capabilities": {"reasoning": True},
        })
        reference = model("moonshotai/kimi-k3")
        reference["reasoning_levels"] = ["max", "high", "low"]
        reference["default_reasoning_level"] = "max"
        batch_reference = model("moonshotai/kimi-k3:batch")
        batch_reference["reasoning_levels"] = ["max", "high", "low"]
        enriched = merge_reasoning_from_reference([anymodel], [reference, batch_reference])
        self.assertEqual(enriched[0]["reasoning_levels"], ["max", "high", "low"])
        self.assertEqual(enriched[0]["default_reasoning_level"], "max")

    def test_legacy_inferred_levels_are_migrated_for_reference_fallback(self) -> None:
        legacy = model("am/kimi-k3")
        legacy.pop("reasoning_levels_source")
        legacy["reasoning_levels"] = ["low", "medium", "high"]
        migrated = _with_model_fields(legacy, "anymodel")
        self.assertEqual(migrated["reasoning_levels"], ["medium"])
        self.assertEqual(migrated["reasoning_levels_source"], "reference")

        legacy["reasoning_levels"] = ["medium"]
        migrated = _with_model_fields(legacy, "anymodel")
        self.assertEqual(migrated["reasoning_levels_source"], "reference")

    @patch("provider_models._bundled_catalog")
    def test_catalog_uses_provider_capabilities(self, bundled_catalog) -> None:
        from provider_models import write_codex_catalog

        bundled_catalog.return_value = {"models": [{
            "slug": "gpt-5.4",
            "display_name": "GPT-5.4",
            "description": "template",
            "default_reasoning_level": "high",
            "supported_reasoning_levels": [{"effort": "high", "description": "high"}],
            "supports_search_tool": True,
            "web_search_tool_type": "text_and_image",
            "use_responses_lite": True,
            "supports_image_detail_original": True,
            "support_verbosity": True,
            "tool_mode": "code_mode_only",
            "additional_speed_tiers": ["fast"],
            "service_tiers": [{"id": "priority"}],
        }]}
        selected = model("am/kimi-k3")
        selected["reasoning_levels"] = ["max", "high", "low"]
        selected["default_reasoning_level"] = "max"
        selected["supports_search_tool"] = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            write_codex_catalog(path, [selected], Path("/fake/codex"), "anymodel")
            entry = json.loads(path.read_text(encoding="utf-8"))["models"][0]
        self.assertEqual(entry["supported_reasoning_levels"], [
            {"effort": "max", "description": "Максимальная глубина рассуждений"},
            {"effort": "high", "description": "Глубокие рассуждения для сложных задач"},
            {"effort": "low", "description": "Быстрый ответ с лёгкими рассуждениями"},
        ])
        self.assertFalse(entry["supports_search_tool"])
        self.assertNotIn("web_search_tool_type", entry)
        self.assertFalse(entry["use_responses_lite"])
        self.assertFalse(entry["supports_image_detail_original"])
        self.assertNotIn("tool_mode", entry)


if __name__ == "__main__":
    unittest.main()
