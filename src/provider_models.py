"""Model discovery and compact Codex catalog generation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import urllib.error
import urllib.request


SHELF_LIMIT = 30
PROXY_SHELF_LIMIT = 30
CACHE_MAX_AGE_SECONDS = 6 * 60 * 60
KNOWN_REASONING_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max", "ultra")
REASONING_DESCRIPTIONS = {
    "minimal": "Минимальные рассуждения",
    "low": "Быстрый ответ с лёгкими рассуждениями",
    "medium": "Баланс скорости и глубины рассуждений",
    "high": "Глубокие рассуждения для сложных задач",
    "xhigh": "Очень глубокие рассуждения",
    "max": "Максимальная глубина рассуждений",
    "ultra": "Максимальные рассуждения с автоматическим делегированием",
}
PROXY_PROVIDER_ALIASES = {
    "vibecode": "vc",
    "anymodel": "am",
    "a6api": "a6",
    "openrouter-all": "or",
}

DEFAULT_PROVIDERS = {
    "openrouter-all": {
        "id": "openrouter-all",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_url": None,
        "credential_id": "openrouter",
        "alias": "or",
        "api_mode": "responses",
        "built_in": True,
        "model": "z-ai/glm-5.3",
        "reasoning": "high",
        "supports_websockets": False
    },
    "vibecode": {
        "id": "vibecode",
        "label": "VibeCode",
        "base_url": "https://vibecode.moe/v1",
        "models_url": None,
        "credential_id": "vibecode",
        "alias": "vc",
        "api_mode": "responses",
        "built_in": False,
        "model": "gpt-5.6-terra",
        "reasoning": "high",
        "supports_websockets": False
    },
    "anymodel": {
        "id": "anymodel",
        "label": "AnyModel",
        "base_url": "https://anymodel.org/v1",
        "models_url": None,
        "credential_id": "anymodel",
        "alias": "am",
        "api_mode": "responses",
        "built_in": False,
        "model": "gpt-5.6-terra",
        "reasoning": "high",
        "supports_websockets": False
    },
    "a6api": {
        "id": "a6api",
        "label": "A6 API",
        "base_url": "https://api.a6api.com/v1",
        "models_url": None,
        "credential_id": "a6api",
        "alias": "a6",
        "api_mode": "responses",
        "built_in": False,
        "model": "gpt-5.6-terra",
        "reasoning": "high",
        "supports_websockets": False
    },
}
ANYMODEL_BASE_PRICE_PER_MILLION = 0.05
A6_MARKETPLACE_PRICES_URL = "https://a6api.com/api/marketplace/public/channels/search?offset=0&limit=10000"
OPENROUTER_ENDPOINT_STATS_THREADS = 8
SPEED_STATS_CACHE_ID = "openrouter-endpoint-stats"


def _atomic_json_write(path: Path, payload: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(default)


def load_state(path: Path) -> dict[str, Any]:
    state = load_json(path, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("version", 1)
    state.setdefault("favorites", {})
    state.setdefault("recent", {})
    state.setdefault("last_model", {})
    state.setdefault("selected_models", [])
    state.setdefault("compaction_model", None)
    state.setdefault("providers", [dict(item) for item in DEFAULT_PROVIDERS.values()])
    state.setdefault("auto_compact_mode", "percent")
    state.setdefault("auto_compact_percent", 75)
    state.setdefault("auto_compact_tokens", 200_000)
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    _atomic_json_write(path, state)


def remember_model(state: dict[str, Any], provider_id: str, model_id: str) -> None:
    if not model_id:
        return
    state["last_model"][provider_id] = model_id
    recent = state["recent"].setdefault(provider_id, [])
    state["recent"][provider_id] = [model_id, *[item for item in recent if item != model_id]][:20]


def set_favorite(state: dict[str, Any], provider_id: str, model_id: str, enabled: bool) -> None:
    favorites = state["favorites"].setdefault(provider_id, [])
    favorites = [item for item in favorites if item != model_id]
    if enabled:
        favorites.insert(0, model_id)
    state["favorites"][provider_id] = favorites


def selection_key(provider_id: str, model_id: str) -> str:
    return f"{provider_id}|{model_id}"


def proxy_model_id(
    provider_id: str,
    model_id: str,
    providers: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Return the stable model name Codex sees through the local proxy."""
    if providers:
        alias = str(providers.get(provider_id, {}).get("alias", ""))
        return f"{alias}/{model_id}" if alias else model_id
    if provider_id == "anymodel" and model_id.startswith("am/"):
        return model_id
    alias = PROXY_PROVIDER_ALIASES.get(provider_id)
    return f"{alias}/{model_id}" if alias else model_id


def provider_definitions(state: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return user gateways plus built-in OpenRouter metadata."""
    definitions: dict[str, dict[str, Any]] = {}
    items = state.get("providers") if state else DEFAULT_PROVIDERS.values()
    if not isinstance(items, list):
        items = DEFAULT_PROVIDERS.values()
    for item in items:
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("id", "")).strip()
        base_url = str(item.get("base_url", "")).strip()
        alias = str(item.get("alias", "")).strip()
        if provider_id and base_url.startswith(("http://", "https://")) and alias:
            models_url = str(item.get("models_url") or "").strip()
            api_mode = str(item.get("api_mode", "responses")).strip()
            if api_mode not in ("responses", "chat"):
                api_mode = "responses"
            definitions[provider_id] = {
                "id": provider_id,
                "label": str(item.get("label", provider_id)),
                "base_url": base_url.rstrip("/"),
                "models_url": models_url or None,
                "api_mode": api_mode,
                "credential_id": str(item.get("credential_id", provider_id)),
                "alias": alias,
                "built_in": bool(item.get("built_in", False)),
            }
    return definitions


def provider_definition(
    provider_id: str, state: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    return provider_definitions(state).get(provider_id)


def set_selected_model(
    state: dict[str, Any], provider_id: str, model_id: str, enabled: bool
) -> None:
    key = selection_key(provider_id, model_id)
    selected = [
        item
        for item in state.get("selected_models", [])
        if not isinstance(item, dict)
        or selection_key(str(item.get("provider_id", "")), str(item.get("model_id", ""))) != key
    ]
    if enabled:
        selected.insert(0, {"provider_id": provider_id, "model_id": model_id})
    state["selected_models"] = selected


def set_compaction_model(
    state: dict[str, Any], provider_id: str | None, model_id: str | None
) -> None:
    if provider_id is None or model_id is None:
        state["compaction_model"] = None
        return
    state["compaction_model"] = {"provider_id": provider_id, "model_id": model_id}


def set_auto_compact_settings(
    state: dict[str, Any], mode: str, value: int
) -> None:
    if mode not in ("percent", "tokens"):
        raise ValueError("Режим автокомпакта должен быть percent или tokens")
    if mode == "percent":
        if not 10 <= int(value) <= 100:
            raise ValueError("Процент автокомпакта должен быть от 10 до 100")
        state["auto_compact_mode"] = "percent"
        state["auto_compact_percent"] = int(value)
    else:
        if not 4096 <= int(value) <= 10_000_000:
            raise ValueError("Лимит автокомпакта должен быть от 4096 до 10 000 000 токенов")
        state["auto_compact_mode"] = "tokens"
        state["auto_compact_tokens"] = int(value)


def auto_compact_percent(context_window: int, state: dict[str, Any]) -> int:
    mode = str(state.get("auto_compact_mode", "percent"))
    if mode == "tokens":
        limit = int(state.get("auto_compact_tokens", 200_000))
        return max(1, min(100, round(limit * 100 / max(1, context_window))))
    return max(1, min(100, int(state.get("auto_compact_percent", 75))))


def proxy_selections(state: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in state.get("selected_models", []):
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("provider_id", ""))
        model_id = str(item.get("model_id", ""))
        key = selection_key(provider_id, model_id)
        if provider_id and model_id and key not in seen:
            seen.add(key)
            result.append({"provider_id": provider_id, "model_id": model_id})
    return result


def compaction_selection(state: dict[str, Any]) -> dict[str, str] | None:
    item = state.get("compaction_model")
    if not isinstance(item, dict):
        return None
    provider_id = str(item.get("provider_id", ""))
    model_id = str(item.get("model_id", ""))
    return (
        {"provider_id": provider_id, "model_id": model_id}
        if provider_id and model_id
        else None
    )


def _codex_index(model: dict[str, Any]) -> float | None:
    """The same weighted score as the local model-picker table."""
    agentic = _positive_float(model.get("agentic_index"))
    coding = _positive_float(model.get("coding_index"))
    intelligence = _positive_float(model.get("intelligence_index"))
    if agentic is None or coding is None or intelligence is None:
        return None
    return agentic * 0.5 + coding * 0.3 + intelligence * 0.2


REASONING_LEVEL_ORDER = {level: index for index, level in enumerate(KNOWN_REASONING_LEVELS)}


def _catalog_display_name(model: dict[str, Any]) -> str:
    """Show a human-readable provider and model name in Codex."""
    model_name = str(model.get("provider_model_id") or model["id"])
    provider_label = str(model.get("provider_label") or "").strip()
    return f"{provider_label} {model_name}".strip()


def build_proxy_shelf(
    state: dict[str, Any],
    models_by_provider: dict[str, list[dict[str, Any]]],
    active: dict[str, str] | None = None,
    compaction: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build a Codex catalog from explicit selections, smartest models first."""
    selected = proxy_selections(state)
    for item in (active, compaction):
        if not item:
            continue
        key = selection_key(item["provider_id"], item["model_id"])
        if not any(
            selection_key(existing["provider_id"], existing["model_id"]) == key
            for existing in selected
        ):
            selected.append(item)

    providers = provider_definitions(state)
    shelf: list[dict[str, Any]] = []
    for item in selected:
        provider_id = item["provider_id"]
        model_id = item["model_id"]
        model = next(
            (
                candidate
                for candidate in models_by_provider.get(provider_id, [])
                if candidate["id"] == model_id
            ),
            None,
        )
        if model is None:
            continue
        external_model = dict(model)
        external_model["id"] = proxy_model_id(provider_id, model_id)
        external_model["provider_model_id"] = model_id
        external_model["provider_label"] = providers.get(provider_id, {}).get("label", provider_id)
        if not any(existing["id"] == external_model["id"] for existing in shelf):
            shelf.append(external_model)
    shelf.sort(
        key=lambda model: _codex_index(model) or float("-inf"),
        reverse=True,
    )
    return shelf[:PROXY_SHELF_LIMIT]


def _is_free_openrouter_model(item: dict[str, Any]) -> bool:
    pricing = item.get("pricing")
    if not isinstance(pricing, dict):
        return False
    if str(pricing.get("prompt", "1")) != "0" or str(pricing.get("completion", "1")) != "0":
        return False
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        outputs = architecture.get("output_modalities")
        if isinstance(outputs, list) and "text" not in outputs:
            return False
    parameters = item.get("supported_parameters")
    return not isinstance(parameters, list) or "tools" in parameters


def _model_supports_tools(provider_id: str, item: dict[str, Any]) -> bool:
    if provider_id in ("openrouter", "openrouter-all"):
        parameters = item.get("supported_parameters")
        return not isinstance(parameters, list) or "tools" in parameters
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and "tools" in capabilities:
        return bool(capabilities["tools"])
    return True


def _model_supports_search(item: dict[str, Any]) -> bool | None:
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and "search" in capabilities:
        return bool(capabilities["search"])
    parameters = item.get("supported_parameters")
    if isinstance(parameters, list):
        search_parameters = {"search", "web_search", "web_search_options"}
        return any(parameter in search_parameters for parameter in parameters)
    return None


def _reasoning_details(provider_id: str, item: dict[str, Any]) -> tuple[list[str], str, str]:
    reasoning = item.get("reasoning")
    if isinstance(reasoning, dict):
        efforts = reasoning.get("supported_efforts")
        if isinstance(efforts, list):
            levels = [str(level) for level in efforts if str(level) in KNOWN_REASONING_LEVELS]
            if levels:
                default = str(reasoning.get("default_effort", levels[0]))
                return levels, default if default in levels else levels[0], "provider"

    capabilities = item.get("capabilities")
    if provider_id in ("a6api", "anymodel"):
        # A6 and AnyModel expose only a reasoning boolean. Their real effort
        # list is filled later from an unambiguous OpenRouter match.
        return ["medium"], "medium", "reference"

    if isinstance(capabilities, dict) and capabilities.get("reasoning"):
        return ["low", "medium", "high"], "medium", "inferred"

    parameters = item.get("supported_parameters")
    if isinstance(parameters, list) and ("reasoning" in parameters or "reasoning_effort" in parameters):
        return ["low", "medium", "high"], "medium", "inferred"

    return ["medium"], "medium", "fallback"


def _input_modalities(item: dict[str, Any]) -> list[str]:
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        modalities = architecture.get("input_modalities")
        if isinstance(modalities, list):
            selected = [value for value in ("text", "image") if value in modalities]
            if selected:
                return selected
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("vision"):
        return ["text", "image"]
    return ["text"]


def _context_details(provider_id: str, item: dict[str, Any]) -> tuple[int, str]:
    capabilities = item.get("capabilities") if isinstance(item.get("capabilities"), dict) else {}
    top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
    candidates = (
        item.get("context_length"),
        item.get("context_window"),
        capabilities.get("contextWindow"),
        capabilities.get("context_window"),
        top_provider.get("context_length"),
    )
    for candidate in candidates:
        try:
            context_window = int(candidate)
        except (TypeError, ValueError):
            continue
        if context_window > 0:
            return max(16000, context_window), "provider"
    if provider_id in ("a6api", "anymodel"):
        return 128000, "missing"
    return 128000, "fallback"


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _pricing_details(provider_id: str, item: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return USD prices per million tokens."""
    if provider_id in ("openrouter", "openrouter-all"):
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        prompt = _positive_float(pricing.get("prompt"))
        completion = _positive_float(pricing.get("completion"))
        if prompt is None and completion is None:
            return None, None
        return (prompt or 0.0) * 1_000_000, (completion or 0.0) * 1_000_000

    if provider_id == "anymodel":
        billing = item.get("billing") if isinstance(item.get("billing"), dict) else {}
        coefficient = billing.get("coefficient") if isinstance(billing.get("coefficient"), dict) else {}
        input_coefficient = _positive_float(coefficient.get("input"))
        output_coefficient = _positive_float(coefficient.get("output"))
        if input_coefficient is None and output_coefficient is None:
            return None, None
        return (
            input_coefficient * ANYMODEL_BASE_PRICE_PER_MILLION if input_coefficient is not None else None,
            output_coefficient * ANYMODEL_BASE_PRICE_PER_MILLION if output_coefficient is not None else None,
        )

    return None, None


def a6_marketplace_estimates(items: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Average prices from the cheaper half of A6 marketplace channels."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        model_name = item.get("model_name")
        if not isinstance(model_name, str) or not model_name:
            continue
        if (
            item.get("charge_type") != "per_token"
            or item.get("pricing_currency") != "USD"
            or item.get("pricing_unit") != "per_1m_tokens"
            or item.get("listing_availability") != 1
            or item.get("supplier_channel_disabled", False)
            or item.get("user_channel_disabled", False)
        ):
            continue
        try:
            input_price = float(item["input_price_micros"]) / 1_000_000
            output_price = float(item["output_price_micros"]) / 1_000_000
        except (KeyError, TypeError, ValueError):
            continue
        if input_price < 0 or output_price < 0:
            continue
        groups.setdefault(model_name, []).append({"input": input_price, "output": output_price})

    estimates: dict[str, dict[str, float]] = {}
    for model_name, channels in groups.items():
        channels.sort(key=lambda price: price["input"] * 0.8 + price["output"] * 0.2)
        kept = channels[: len(channels) - len(channels) // 2]
        if not kept:
            continue
        estimates[model_name] = {
            "input": sum(channel["input"] for channel in kept) / len(kept),
            "output": sum(channel["output"] for channel in kept) / len(kept),
        }
    return estimates


def load_a6_marketplace_estimates(cache_path: Path, *, force: bool = False) -> dict[str, dict[str, float]]:
    cache = load_json(cache_path, {})
    cached = cache.get("a6-marketplace-prices", {}) if isinstance(cache, dict) else {}
    prices = cached.get("prices", {}) if isinstance(cached, dict) else {}
    fetched_at = cached.get("fetched_at", 0) if isinstance(cached, dict) else 0
    now = dt.datetime.now(tz=dt.timezone.utc).timestamp()
    if not force and prices and now - float(fetched_at or 0) < CACHE_MAX_AGE_SECONDS:
        return prices

    request = urllib.request.Request(
        A6_MARKETPLACE_PRICES_URL,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        items = payload.get("data", {}).get("items", []) if isinstance(payload, dict) else {}
        prices = a6_marketplace_estimates(items if isinstance(items, list) else [])
        if not prices:
            raise RuntimeError("A6 marketplace did not return usable prices")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        if prices:
            return prices
        raise RuntimeError(f"Не удалось загрузить примерные цены A6: {error}") from error

    if not isinstance(cache, dict):
        cache = {}
    cache["a6-marketplace-prices"] = {"fetched_at": now, "prices": prices}
    _atomic_json_write(cache_path, cache)
    return prices


def merge_a6_marketplace_prices(
    models: list[dict[str, Any]], estimates: dict[str, dict[str, float]]
) -> list[dict[str, Any]]:
    by_name = {name.casefold(): price for name, price in estimates.items()}
    enriched = []
    for model in models:
        price = by_name.get(model["id"].casefold())
        if price is not None:
            model = dict(model)
            model["input_price_per_million"] = price["input"]
            model["output_price_per_million"] = price["output"]
            model["price_is_estimate"] = True
        else:
            model = dict(model)
            model["price_is_estimate"] = False
        enriched.append(model)
    return enriched


def _with_model_fields(model: dict[str, Any], provider_id: str = "") -> dict[str, Any]:
    """Keep model caches created before pricing metadata readable."""
    model = dict(model)
    had_reasoning_source = "reasoning_levels_source" in model
    model.setdefault("context_window", 128000)
    model.setdefault("context_window_source", "fallback")
    model.setdefault("reasoning_levels_source", "fallback")
    model.setdefault("input_price_per_million", None)
    model.setdefault("output_price_per_million", None)
    model.setdefault("intelligence_index", None)
    model.setdefault("coding_index", None)
    model.setdefault("agentic_index", None)
    model.setdefault("price_is_estimate", False)
    model.setdefault("supports_search_tool", None)
    model.setdefault("supports_function_tools", True)
    model.setdefault("reference_tps_p50", None)
    model.setdefault("reference_tps_p90", None)
    model.setdefault("reference_ttft_ms_p50", None)
    model.setdefault("reference_ttft_ms_p90", None)
    model.setdefault("reference_endpoints", [])
    if "context_window_source" not in model:
        # A6 previously stored the generic 128K fallback, so let OpenRouter
        # replace it. Other legacy caches already contained provider data.
        model["context_window_source"] = "missing" if provider_id == "a6api" else "provider"
    if provider_id in ("a6api", "anymodel") and not had_reasoning_source:
        # Migrate caches created before the source marker was introduced.
        if model.get("reasoning_levels") == ["low", "medium", "high"]:
            model["reasoning_levels"] = ["medium"]
            model["default_reasoning_level"] = "medium"
            model["reasoning_levels_source"] = "reference"
        elif model.get("reasoning_levels") == ["medium"]:
            model["reasoning_levels_source"] = "reference"
        else:
            model["reasoning_levels_source"] = "provider"
    model.setdefault("reasoning_levels_source", "fallback")
    context_source = model.get("context_window_source")
    reasoning_source = model.get("reasoning_levels_source")
    model["metadata_status"] = (
        "provider" if context_source == "provider" and reasoning_source == "provider"
        else "reference" if context_source in ("openrouter", "reference") or reasoning_source in ("openrouter", "reference")
        else "unconfirmed"
    )
    return model


def _artificial_analysis(item: dict[str, Any]) -> dict[str, Any]:
    benchmarks = item.get("benchmarks") if isinstance(item.get("benchmarks"), dict) else {}
    artificial = benchmarks.get("artificial_analysis") if isinstance(benchmarks.get("artificial_analysis"), dict) else {}
    return artificial


def _analysis_indices(item: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    artificial = _artificial_analysis(item)
    return (
        _positive_float(artificial.get("intelligence_index")),
        _positive_float(artificial.get("coding_index")),
        _positive_float(artificial.get("agentic_index")),
    )


def normalize_model(provider_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    if not _model_supports_tools(provider_id, item):
        return None
    levels, default_level, levels_source = _reasoning_details(provider_id, item)
    context_window, context_source = _context_details(provider_id, item)
    display_name = item.get("display_name") or item.get("name") or model_id
    description = item.get("description") or f"Модель {display_name} через выбранного провайдера"
    input_price, output_price = _pricing_details(provider_id, item)
    intelligence_index, coding_index, agentic_index = _analysis_indices(item)
    return {
        "id": model_id,
        "display_name": str(display_name),
        "description": str(description),
        "context_window": context_window,
        "context_window_source": context_source,
        "input_modalities": _input_modalities(item),
        "reasoning_levels": levels,
        "default_reasoning_level": default_level,
        "reasoning_levels_source": levels_source,
        "metadata_status": "provider" if context_source == "provider" and levels_source == "provider" else (
            "reference" if context_source == "openrouter" or levels_source == "openrouter" else "unconfirmed"
        ),
        "input_price_per_million": input_price,
        "output_price_per_million": output_price,
        "intelligence_index": intelligence_index,
        "coding_index": coding_index,
        "agentic_index": agentic_index,
        "price_is_estimate": provider_id == "a6api",
        "supports_search_tool": _model_supports_search(item),
        "supports_function_tools": _model_supports_tools(provider_id, item),
        "reference_tps_p50": None,
        "reference_tps_p90": None,
        "reference_ttft_ms_p50": None,
        "reference_ttft_ms_p90": None,
        "reference_endpoints": [],
    }


def merge_context_window_from_reference(
    models: list[dict[str, Any]], reference_models: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fill missing context metadata using an unambiguous OpenRouter match."""
    by_short_name: dict[str, list[dict[str, Any]]] = {}
    for reference in reference_models:
        if reference.get("context_window_source") == "fallback":
            continue
        short_name = reference["id"].rsplit("/", 1)[-1].casefold()
        by_short_name.setdefault(short_name, []).append(reference)

    enriched = []
    for model in models:
        source = model.get("context_window_source")
        eligible = source in ("missing", "reference") or source is None
        if eligible:
            short_name = model["id"].rsplit("/", 1)[-1].casefold()
            matches = by_short_name.get(short_name, [])
            if len(matches) != 1:
                canonical = [
                    reference
                    for reference in matches
                    if ":" not in reference["id"].rsplit("/", 1)[-1]
                ]
                if len(canonical) == 1:
                    matches = canonical
            if len(matches) == 1:
                model = dict(model)
                model["context_window"] = matches[0]["context_window"]
                model["context_window_source"] = "openrouter"
        enriched.append(model)
    return enriched


def merge_reasoning_from_reference(
    models: list[dict[str, Any]], reference_models: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fill missing reasoning metadata using an unambiguous model-name match."""
    by_short_name: dict[str, list[dict[str, Any]]] = {}
    for reference in reference_models:
        short_name = reference["id"].rsplit("/", 1)[-1].casefold()
        by_short_name.setdefault(short_name, []).append(reference)

    enriched = []
    for model in models:
        source = model.get("reasoning_levels_source")
        eligible = source == "reference" or (source is None and len(model["reasoning_levels"]) == 1 and model["reasoning_levels"] == ["medium"])
        if eligible:
            short_name = model["id"].rsplit("/", 1)[-1].casefold()
            matches = by_short_name.get(short_name, [])
            if len(matches) != 1:
                # OpenRouter exposes billing variants such as :batch and
                # :free; the plain model is the canonical metadata source.
                canonical = [
                    reference
                    for reference in matches
                    if ":" not in reference["id"].rsplit("/", 1)[-1]
                ]
                if len(canonical) == 1:
                    matches = canonical
            if len(matches) == 1 and len(matches[0]["reasoning_levels"]) > 1:
                model = dict(model)
                model["reasoning_levels"] = list(matches[0]["reasoning_levels"])
                model["default_reasoning_level"] = matches[0]["default_reasoning_level"]
                model["reasoning_levels_source"] = "openrouter"
        enriched.append(model)
    return enriched


def merge_artificial_analysis_from_reference(
    models: list[dict[str, Any]], reference_models: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fill missing Artificial Analysis metrics from a unique OpenRouter match."""
    field_names = ("intelligence_index", "coding_index", "agentic_index")
    by_short_name: dict[str, list[dict[str, Any]]] = {}
    for reference in reference_models:
        if all(reference[field] is None for field in field_names):
            continue
        short_name = reference["id"].rsplit("/", 1)[-1].casefold()
        by_short_name.setdefault(short_name, []).append(reference)

    enriched = []
    for model in models:
        if all(model[field] is not None for field in field_names):
            enriched.append(model)
            continue

        short_name = model["id"].rsplit("/", 1)[-1].casefold()
        matches = by_short_name.get(short_name, [])
        if len(matches) != 1:
            canonical = [
                reference
                for reference in matches
                if ":" not in reference["id"].rsplit("/", 1)[-1]
            ]
            if len(canonical) == 1:
                matches = canonical
        if len(matches) == 1:
            model = dict(model)
            for field in field_names:
                if model[field] is None:
                    model[field] = matches[0][field]
        enriched.append(model)
    return enriched


def _percentile_stats(value: Any) -> dict[str, float]:
    """Normalize one OR PercentileStats object into p50/p90 floats."""
    if not isinstance(value, dict):
        return {}
    stats = {}
    for key, target in (("p50", "p50"), ("p90", "p90")):
        number = _positive_float(value.get(key))
        if number is not None:
            stats[target] = number
    return stats


def openrouter_speed_stats(endpoints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate throughput/latency percentiles across OR provider endpoints.

    Latency arrives in milliseconds despite what the API docs claim. Models
    with zero throughput (idle or broken endpoints) are skipped so a dead
    endpoint cannot drag the average down.
    """
    throughputs: list[tuple[float, float]] = []
    latencies: list[tuple[float, float]] = []
    names: list[str] = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        name = endpoint.get("provider_name")
        if not isinstance(name, str) or not name:
            continue
        throughput = _percentile_stats(endpoint.get("throughput_last_30m"))
        latency = _percentile_stats(endpoint.get("latency_last_30m"))
        if "p50" not in throughput or throughput["p50"] <= 0:
            continue
        throughputs.append((throughput["p50"], throughput.get("p90", throughput["p50"])))
        if "p50" in latency:
            latencies.append((latency["p50"], latency.get("p90", latency["p50"])))
        names.append(name)
    if not throughputs:
        return None
    result: dict[str, Any] = {
        "tps_p50": sum(item[0] for item in throughputs) / len(throughputs),
        "tps_p90": sum(item[1] for item in throughputs) / len(throughputs),
        "endpoints": names,
    }
    if latencies:
        result["ttft_ms_p50"] = sum(item[0] for item in latencies) / len(latencies)
        result["ttft_ms_p90"] = sum(item[1] for item in latencies) / len(latencies)
    return result


def load_openrouter_speed_stats(
    model_ids: list[str],
    api_key: str | None,
    cache_path: Path,
    *,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """Fetch per-model endpoint speed stats, keyed by OR model id.

    OpenRouter has no batch endpoint, so stats come one model at a time;
    the on-disk cache keeps each entry for CACHE_MAX_AGE_SECONDS and grows
    incrementally, so only new or stale models are re-requested.
    """
    cache = load_json(cache_path, {})
    if not isinstance(cache, dict):
        cache = {}
    cached = cache.get(SPEED_STATS_CACHE_ID, {})
    entries = cached.get("models", {}) if isinstance(cached, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    now = dt.datetime.now(tz=dt.timezone.utc).timestamp()
    wanted = list(dict.fromkeys(model_ids))
    stale = []
    for model_id in wanted:
        entry = entries.get(model_id)
        fetched_at = entry.get("fetched_at", 0) if isinstance(entry, dict) else 0
        if force or not isinstance(entry, dict) or not entry.get("stats") or now - float(fetched_at or 0) >= CACHE_MAX_AGE_SECONDS:
            stale.append(model_id)

    if stale and api_key:
        # Keep cache writes conservative: bump fetched_at even for models
        # whose request failed, so a flaky network does not hammer the API.
        def fetch(model_id: str) -> tuple[str, dict[str, Any] | None]:
            url = f"https://openrouter.ai/api/v1/models/{model_id}/endpoints"
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "CodexProviderManager/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.load(response)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                return model_id, None
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            endpoints = data.get("endpoints", []) if isinstance(data, dict) else []
            return model_id, {"endpoints": endpoints if isinstance(endpoints, list) else []}

        results = {}
        with ThreadPoolExecutor(max_workers=OPENROUTER_ENDPOINT_STATS_THREADS) as pool:
            for model_id, entry in pool.map(fetch, stale):
                results[model_id] = {"fetched_at": now, "stats": entry}
        for model_id, entry in results.items():
            entries[model_id] = entry
        cache[SPEED_STATS_CACHE_ID] = {"fetched_at": now, "models": entries}
        _atomic_json_write(cache_path, cache)

    aggregated: dict[str, dict[str, Any]] = {}
    for model_id in wanted:
        entry = entries.get(model_id)
        stats = entry.get("stats") if isinstance(entry, dict) else None
        if not isinstance(stats, dict):
            continue
        aggregated[model_id] = openrouter_speed_stats(stats.get("endpoints") or []) or {}
    return aggregated


def merge_speed_from_reference(
    models: list[dict[str, Any]],
    speed_stats: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach OR reference speed to models by unambiguous short-name match."""
    by_short_name: dict[str, list[dict[str, Any]]] = {}
    for reference_id, stats in speed_stats.items():
        if not stats:
            continue
        short_name = reference_id.rsplit("/", 1)[-1].casefold()
        by_short_name.setdefault(short_name, []).append(stats)

    enriched = []
    for model in models:
        short_name = model["id"].rsplit("/", 1)[-1].casefold()
        matches = by_short_name.get(short_name, [])
        if len(matches) != 1:
            # OR exposes billing variants such as :batch/:free; prefer the
            # canonical one when several variants share stats.
            canonical = [
                reference_id
                for reference_id, candidate_stats in speed_stats.items()
                if candidate_stats
                and reference_id.rsplit("/", 1)[-1].casefold() == short_name
                and ":" not in reference_id.rsplit("/", 1)[-1]
            ]
            if len(canonical) == 1:
                matches = [speed_stats[canonical[0]]]
        if len(matches) == 1:
            stats = matches[0]
            model = dict(model)
            model["reference_tps_p50"] = round(stats["tps_p50"], 1)
            model["reference_tps_p90"] = round(stats["tps_p90"], 1)
            model["reference_ttft_ms_p50"] = round(stats["ttft_ms_p50"]) if "ttft_ms_p50" in stats else None
            model["reference_ttft_ms_p90"] = round(stats["ttft_ms_p90"]) if "ttft_ms_p90" in stats else None
            model["reference_endpoints"] = list(stats.get("endpoints", []))
        enriched.append(model)
    return enriched



def fetch_models(
    provider_id: str,
    provider: dict[str, Any],
    api_key: str | None,
    cache_path: Path,
    *,
    force: bool = False,
    cache_id: str | None = None,
) -> list[dict[str, Any]]:
    cache_id = cache_id or provider_id
    cache = load_json(cache_path, {})
    cached = cache.get(cache_id, {}) if isinstance(cache, dict) else {}
    cached_models = cached.get("models", []) if isinstance(cached, dict) else []
    fetched_at = cached.get("fetched_at", 0) if isinstance(cached, dict) else 0
    now = dt.datetime.now(tz=dt.timezone.utc).timestamp()
    if not force and cached_models and now - float(fetched_at or 0) < CACHE_MAX_AGE_SECONDS:
        return [_with_model_fields(item, provider_id) for item in cached_models if isinstance(item, dict)]

    models_url = provider.get("models_url") or f"{str(provider['base_url']).rstrip('/')}/models"
    headers = {"Accept": "application/json", "User-Agent": "CodexProviderManager/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(models_url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        if cached_models:
            return [_with_model_fields(item, provider_id) for item in cached_models if isinstance(item, dict)]
        raise RuntimeError(f"Не удалось загрузить список моделей {provider_id}: {error}") from error

    raw_models = payload.get("data", []) if isinstance(payload, dict) else []
    normalized = [normalize_model(provider_id, item) for item in raw_models if isinstance(item, dict)]
    models = [item for item in normalized if item is not None]
    models.sort(key=lambda item: (item["display_name"].casefold(), item["id"].casefold()))
    if not models:
        if cached_models:
            return [_with_model_fields(item, provider_id) for item in cached_models if isinstance(item, dict)]
        raise RuntimeError(f"Провайдер {provider_id} не вернул совместимых моделей.")

    if not isinstance(cache, dict):
        cache = {}
    cache[cache_id] = {"fetched_at": now, "models": models}
    _atomic_json_write(cache_path, cache)
    return models


def find_model(models: list[dict[str, Any]], model_id: str | None) -> dict[str, Any] | None:
    if not model_id:
        return None
    exact = next((model for model in models if model["id"] == model_id), None)
    if exact is not None:
        return exact
    short_name = model_id.rsplit("/", 1)[-1].casefold()
    matches = [model for model in models if model["id"].rsplit("/", 1)[-1].casefold() == short_name]
    return matches[0] if len(matches) == 1 else None


def search_models(models: list[dict[str, Any]], query: str, limit: int = 50) -> list[dict[str, Any]]:
    words = [word.casefold() for word in query.split() if word.strip()]
    if not words:
        return models[:limit]
    matches = []
    for model in models:
        haystack = f"{model['display_name']} {model['id']} {model['description']}".casefold()
        if all(word in haystack for word in words):
            matches.append(model)
    return matches[:limit]


def build_shelf(
    provider_id: str,
    provider: dict[str, Any],
    models: list[dict[str, Any]],
    state: dict[str, Any],
    selected_model: str,
) -> list[dict[str, Any]]:
    by_id = {model["id"]: model for model in models}
    ordered_ids: list[str] = []

    def add(model_id: str | None) -> None:
        model = find_model(models, model_id)
        if model and model["id"] not in ordered_ids:
            ordered_ids.append(model["id"])

    add(selected_model)
    add(state["last_model"].get(provider_id))
    for model_id in state["favorites"].get(provider_id, []):
        add(model_id)
    for model_id in state["recent"].get(provider_id, []):
        add(model_id)
    add(provider.get("model"))

    recommended_terms = ("gpt-5.6", "gpt-5.5", "glm-5", "glm-4.7", "codex", "code")
    for term in recommended_terms:
        for model in models:
            if term in f"{model['id']} {model['display_name']}".casefold():
                add(model["id"])
    for model in models:
        add(model["id"])
        if len(ordered_ids) >= SHELF_LIMIT:
            break
    return [by_id[model_id] for model_id in ordered_ids[:SHELF_LIMIT]]


def _bundled_catalog(codex_binary: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(codex_binary), "debug", "models", "--bundled"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or not payload.get("models"):
        raise RuntimeError("Установленный Codex не вернул шаблон каталога моделей.")
    return payload


def write_codex_catalog(
    path: Path,
    shelf: list[dict[str, Any]],
    codex_binary: Path,
    provider_id: str = "",
    settings: dict[str, Any] | None = None,
) -> None:
    bundled = _bundled_catalog(codex_binary)
    bundled_by_slug = {model.get("slug"): model for model in bundled["models"] if isinstance(model, dict)}
    fallback = bundled["models"][0]
    catalog_models = []
    ordered_shelf = sorted(
        shelf,
        key=lambda model: (
            _catalog_display_name(model).casefold(),
            model["id"].casefold(),
        ),
    )
    for priority, model in enumerate(ordered_shelf, start=1):
        source = bundled_by_slug.get(model["id"])
        if source is None:
            short_name = model["id"].rsplit("/", 1)[-1]
            matches = [item for slug, item in bundled_by_slug.items() if slug and slug.rsplit("/", 1)[-1] == short_name]
            source = matches[0] if len(matches) == 1 else None
        entry = deepcopy(source or fallback)
        entry["slug"] = model["id"]
        entry["display_name"] = _catalog_display_name(model)
        entry["description"] = model["description"]
        entry["default_reasoning_level"] = model["default_reasoning_level"]
        entry["supported_reasoning_levels"] = [
            {"effort": level, "description": REASONING_DESCRIPTIONS[level]}
            for level in sorted(
                model["reasoning_levels"],
                key=lambda level: REASONING_LEVEL_ORDER.get(level, len(REASONING_LEVEL_ORDER)),
            )
        ]
        # The installed Codex version owns the request/tool contract. Keep its
        # required schema fields instead of carrying stale model metadata.
        entry["input_modalities"] = model["input_modalities"]
        entry["context_window"] = model["context_window"]
        entry["max_context_window"] = model["context_window"]
        entry["effective_context_window_percent"] = auto_compact_percent(
            model["context_window"], settings or {}
        )
        # These flags come from the selected provider's model metadata, not
        # from the OpenAI template used to fill unrelated catalog fields.
        supports_search = model.get("supports_search_tool")
        if supports_search is None:
            # The first-party gateway has Codex's native search contract;
            # third-party gateways must opt in through their metadata.
            supports_search = provider_id == "codex-sale"
        entry["supports_search_tool"] = supports_search
        if supports_search:
            entry["web_search_tool_type"] = "text"
        else:
            entry.pop("web_search_tool_type", None)
        if provider_id and provider_id != "codex-sale":
            # Generic OpenAI-compatible gateways do not promise Codex's
            # optimized event stream, image-detail flag, or paid speed tiers.
            entry["use_responses_lite"] = False
            entry["supports_image_detail_original"] = False
            entry["support_verbosity"] = False
            entry["additional_speed_tiers"] = []
            entry["service_tiers"] = []
            entry.pop("tool_mode", None)
        entry["priority"] = priority
        entry["visibility"] = "list"
        entry["supported_in_api"] = True
        # Agent tasks must use an effort supported by third-party models.
        if provider_id and provider_id != "codex-sale":
            entry["multi_agent_version"] = entry.get("multi_agent_version") or "v1"
            entry["multi_agent_reasoning_effort"] = entry.get("multi_agent_reasoning_effort") or "low"
        entry["availability_nux"] = None
        entry["upgrade"] = None
        catalog_models.append(entry)
    _atomic_json_write(path, {"models": catalog_models})
