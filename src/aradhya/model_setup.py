"""Interactive startup helpers for Ollama model selection and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from src.aradhya.model_provider import ModelHealth, build_text_model_provider
from src.aradhya.runtime_profile import RuntimeProfile, persist_model_name

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


@dataclass(frozen=True)
class RecommendedModel:
    """A starter model suggestion shown when Ollama has no local models."""

    name: str
    description: str


RECOMMENDED_OLLAMA_MODELS = (
    RecommendedModel(
        name="gemma3:4b",
        description="Balanced general-purpose model with a modest local footprint.",
    ),
    RecommendedModel(
        name="phi4-mini",
        description="Smaller reasoning-focused model that fits more laptops.",
    ),
    RecommendedModel(
        name="qwen2.5-coder:7b",
        description="Coding-focused model for local development workflows.",
    ),
)

_CatalogItem = TypeVar("_CatalogItem")


def render_model_health(health: ModelHealth, output_handler: Callable[[str], None] = print) -> None:
    """Print a human-readable health summary for the current model setup."""

    output_handler(f"Model > Provider: {health.provider}")
    output_handler(f"Model > Configured model: {health.configured_model}")
    output_handler(f"Model > Reachable: {'yes' if health.reachable else 'no'}")
    output_handler(f"Model > Ready: {'yes' if health.ready else 'no'}")

    if health.available_models:
        output_handler("Model > Local models:")
        for index, model_name in enumerate(health.available_models, start=1):
            output_handler(f"Model >   {index}. {model_name}")
    else:
        output_handler("Model > Local models: none")

    output_handler(f"Model > {health.message}")

    if not health.reachable:
        output_handler(
            f"Model > Install Ollama from {OLLAMA_DOWNLOAD_URL} or start the Ollama service."
        )
    elif not health.available_models:
        output_handler("Model > Suggested download catalog:")
        for index, model in enumerate(RECOMMENDED_OLLAMA_MODELS, start=1):
            output_handler(f"Model >   {index}. {model.name} - {model.description}")
        output_handler("Model > After installing one, run `ollama pull <model-name>`.")

    output_handler("")


def bootstrap_runtime_profile(
    runtime_profile: RuntimeProfile,
    project_root: Path,
    *,
    input_func: Callable[[str], str] = input,
    output_handler: Callable[[str], None] = print,
) -> RuntimeProfile:
    """Ensure Aradhya starts with a usable model selection when Ollama is available."""

    health = build_text_model_provider(runtime_profile.model).health_check()
    if health.ready:
        return runtime_profile

    if not health.reachable:
        output_handler(f"Model > {health.message}")
        output_handler(
            f"Model > Install Ollama from {OLLAMA_DOWNLOAD_URL} or start it, then restart Aradhya."
        )
        output_handler("")
        return runtime_profile

    if len(health.available_models) == 1:
        selected_model = health.available_models[0]
        output_handler(
            f"Model > Found one local Ollama model on this machine: {selected_model}. "
            "Using it by default."
        )
        updated_profile = _apply_selected_model(
            runtime_profile,
            project_root,
            selected_model,
            output_handler,
        )
        output_handler("")
        return updated_profile

    if health.available_models:
        output_handler(
            f"Model > The configured model {health.configured_model} is not installed locally."
        )
        output_handler("Model > Choose one of the installed models below:")
        selected_model = _choose_from_catalog(
            health.available_models,
            input_func=input_func,
            output_handler=output_handler,
            prompt="Select a model number or press Enter to keep the current profile: ",
            formatter=lambda model_name: model_name,
        )
        if selected_model is None:
            output_handler(
                "Model > No model selected. Aradhya will continue with limited "
                "model-backed features."
            )
            output_handler("")
            return runtime_profile

        updated_profile = _apply_selected_model(
            runtime_profile,
            project_root,
            selected_model,
            output_handler,
        )
        output_handler("")
        return updated_profile

    output_handler("Model > Ollama is reachable, but no local models are installed yet.")
    output_handler(
        f"Model > Install Ollama from {OLLAMA_DOWNLOAD_URL} if this machine does not have it yet."
    )
    output_handler("Model > Recommended download catalog:")
    selected_model = _choose_from_catalog(
        RECOMMENDED_OLLAMA_MODELS,
        input_func=input_func,
        output_handler=output_handler,
        prompt="Select a model number to save for later, or press Enter to skip: ",
        formatter=lambda model: f"{model.name} - {model.description}",
    )
    if selected_model is None:
        output_handler(
            "Model > No recommended model selected. Aradhya will continue with limited "
            "model-backed features."
        )
        output_handler("")
        return runtime_profile

    updated_profile = _apply_selected_model(
        runtime_profile,
        project_root,
        selected_model.name,
        output_handler,
    )
    output_handler(
        f"Model > Next step: run `ollama pull {selected_model.name}` and restart Aradhya."
    )
    output_handler("")
    return updated_profile


def _apply_selected_model(
    runtime_profile: RuntimeProfile,
    project_root: Path,
    model_name: str,
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
    updated_profile = replace(
        runtime_profile,
        model=replace(runtime_profile.model, model_name=model_name),
    )

    try:
        profile_path = persist_model_name(project_root, model_name)
    except OSError as error:
        output_handler(
            f"Model > I could not save {model_name} to profile.json. Details: {error}"
        )
    else:
        output_handler(f"Model > Saved {model_name} to {profile_path}.")

    return updated_profile


def _choose_from_catalog(
    options: Sequence[_CatalogItem],
    *,
    input_func: Callable[[str], str],
    output_handler: Callable[[str], None],
    prompt: str,
    formatter: Callable[[_CatalogItem], str],
) -> _CatalogItem | None:
    for index, option in enumerate(options, start=1):
        output_handler(f"Model >   {index}. {formatter(option)}")

    while True:
        raw_choice = input_func(prompt).strip()
        if not raw_choice:
            return None

        try:
            selected_index = int(raw_choice)
        except ValueError:
            output_handler("Model > Enter a catalog number or press Enter to skip.")
            continue

        if 1 <= selected_index <= len(options):
            return options[selected_index - 1]

        output_handler(
            f"Model > Choose a number between 1 and {len(options)}, or press Enter to skip."
        )
