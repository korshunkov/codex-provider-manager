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
    if provider_id == "openrouter":
        parameters = item.get("supported_parameters")
        return not isinstance(parameters, list) or "tools" in parameters
    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and "tools" in capabilities:
        return bool(capabilities["tools"])
    return True


def _reasoning_details(item: dict[str, Any]) -> tuple[list[str], str]:
    reasoning = item.get("reasoning")
    if isinstance(reasoning, dict):
        efforts = reasoning.get("supported_efforts")
        if isinstance(efforts, list):
            levels = [str(level) for level in efforts if str(level) in KNOWN_REASONING_LEVELS]
            if levels:
                default = str(reasoning.get("default_effort", levels[0]))
                return levels, default if default in levels else levels[0]

    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("reasoning"):
        return ["low", "medium", "high"], "medium"

    parameters = item.get("supported_parameters")
    if isinstance(parameters, list) and ("reasoning" in parameters or "reasoning_effort" in parameters):
        return ["low", "medium", "high"], "medium"

    return ["medium"], "medium"


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


def normalize_model(provider_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    if not _model_supports_tools(provider_id, item):
        return None
    levels, default_level = _reasoning_details(item)
    capabilities = item.get("capabilities") if isinstance(item.get("capabilities"), dict) else {}
    top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
    context_window = (
        item.get("context_length")
        or capabilities.get("contextWindow")
        or top_provider.get("context_length")
        or 128000
    )
    try:
        context_window = max(16000, int(context_window))
    except (TypeError, ValueError):
        context_window = 128000
    display_name = item.get("display_name") or item.get("name") or model_id
    description = item.get("description") or f"Модель {display_name} через выбранного провайдера"
    return {
        "id": model_id,
        "display_name": str(display_name),
        "description": str(description),
        "context_window": context_window,
        "input_modalities": _input_modalities(item),
        "reasoning_levels": levels,
        "default_reasoning_level": default_level,
    }


def fetch_models(
    provider_id: str,
    provider: dict[str, Any],
    api_key: str | None,
    cache_path: Path,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    cache = load_json(cache_path, {})
    cached = cache.get(provider_id, {}) if isinstance(cache, dict) else {}
    cached_models = cached.get("models", []) if isinstance(cached, dict) else []
    fetched_at = cached.get("fetched_at", 0) if isinstance(cached, dict) else 0
    now = dt.datetime.now(tz=dt.timezone.utc).timestamp()
    if not force and cached_models and now - float(fetched_at or 0) < CACHE_MAX_AGE_SECONDS:
        return cached_models

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
            return cached_models
        raise RuntimeError(f"Не удалось загрузить список моделей {provider_id}: {error}") from error

    raw_models = payload.get("data", []) if isinstance(payload, dict) else []
    if provider_id == "openrouter":
        raw_models = [item for item in raw_models if isinstance(item, dict) and _is_free_openrouter_model(item)]
    normalized = [normalize_model(provider_id, item) for item in raw_models if isinstance(item, dict)]
    models = [item for item in normalized if item is not None]
    models.sort(key=lambda item: (item["display_name"].casefold(), item["id"].casefold()))
    if not models:
        if cached_models:
            return cached_models
        raise RuntimeError(f"Провайдер {provider_id} не вернул совместимых моделей.")

    if not isinstance(cache, dict):
        cache = {}
    cache[provider_id] = {"fetched_at": now, "models": models}
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
        if source is None:
            entry["default_reasoning_level"] = model["default_reasoning_level"]
            entry["supported_reasoning_levels"] = [
                {"effort": level, "description": REASONING_DESCRIPTIONS[level]}
                for level in model["reasoning_levels"]
            ]
        entry["input_modalities"] = model["input_modalities"]
        entry["context_window"] = model["context_window"]
        entry["max_context_window"] = model["context_window"]
        entry["priority"] = priority
        entry["visibility"] = "list"
        entry["supported_in_api"] = True
        entry["availability_nux"] = None
        entry["upgrade"] = None
        catalog_models.append(entry)
    _atomic_json_write(path, {"models": catalog_models})
