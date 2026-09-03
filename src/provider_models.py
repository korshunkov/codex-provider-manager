"""Model discovery and compact Codex catalog generation."""

from __future__ import annotations

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
ANYMODEL_BASE_PRICE_PER_MILLION = 0.05
A6_MARKETPLACE_PRICES_URL = "https://a6api.com/api/marketplace/public/channels/search?offset=0&limit=10000"


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
    model.setdefault("context_window", 128000)
    model.setdefault("input_price_per_million", None)
    model.setdefault("output_price_per_million", None)
    model.setdefault("intelligence_index", None)
    model.setdefault("coding_index", None)
    model.setdefault("agentic_index", None)
    model.setdefault("price_is_estimate", False)
    model.setdefault("supports_search_tool", None)
    model.setdefault("supports_function_tools", True)
    if "context_window_source" not in model:
        # A6 previously stored the generic 128K fallback, so let OpenRouter
        # replace it. Other legacy caches already contained provider data.
        model["context_window_source"] = "missing" if provider_id == "a6api" else "provider"
    if provider_id in ("a6api", "anymodel") and "reasoning_levels_source" not in model:
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
        "input_price_per_million": input_price,
        "output_price_per_million": output_price,
        "intelligence_index": intelligence_index,
        "coding_index": coding_index,
        "agentic_index": agentic_index,
        "price_is_estimate": provider_id == "a6api",
        "supports_search_tool": _model_supports_search(item),
        "supports_function_tools": _model_supports_tools(provider_id, item),
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
    if provider_id == "openrouter":
        raw_models = [item for item in raw_models if isinstance(item, dict) and _is_free_openrouter_model(item)]
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
    if provider_id == "openrouter":
        for model in models:
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
) -> None:
    bundled = _bundled_catalog(codex_binary)
    bundled_by_slug = {model.get("slug"): model for model in bundled["models"] if isinstance(model, dict)}
    # Older Codex model metadata exposes regular function tools. This is more
    # compatible with third-party models than the code-mode-only tool wrapper
    # used by the newest OpenAI models.
    fallback = bundled_by_slug.get("gpt-5.4") or bundled["models"][0]
    catalog_models = []
    for priority, model in enumerate(shelf, start=1):
        source = bundled_by_slug.get(model["id"])
        if source is None:
            short_name = model["id"].rsplit("/", 1)[-1]
            matches = [item for slug, item in bundled_by_slug.items() if slug and slug.rsplit("/", 1)[-1] == short_name]
            source = matches[0] if len(matches) == 1 else None
        entry = deepcopy(source or fallback)
        entry["slug"] = model["id"]
        entry["display_name"] = source.get("display_name") if source else model["display_name"]
        entry["description"] = model["description"]
        entry["default_reasoning_level"] = model["default_reasoning_level"]
        entry["supported_reasoning_levels"] = [
            {"effort": level, "description": REASONING_DESCRIPTIONS[level]}
            for level in model["reasoning_levels"]
        ]
        entry["input_modalities"] = model["input_modalities"]
        entry["context_window"] = model["context_window"]
        entry["max_context_window"] = model["context_window"]
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
        entry["availability_nux"] = None
        entry["upgrade"] = None
        catalog_models.append(entry)
    _atomic_json_write(path, {"models": catalog_models})
