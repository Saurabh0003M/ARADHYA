"""Interactive startup helpers for Ollama model selection and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from src.aradhya.model_provider import ModelHealth, build_text_model_provider
from src.aradhya.runtime_profile import RuntimeProfile, persist_model_name
from src.aradhya.utils.hardware_profile import HardwareProfile

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

@dataclass(frozen=True)
class CatalogModel:
    """A local model with an approximate memory footprint (Q4 quantized)."""

    name: str
    description: str
    params_b: float
    min_ram_gb: float


# Ordered small → large. ``min_ram_gb`` is the rough working-set for a Q4
# quantization; real usage varies, so recommendations keep headroom.
FEASIBLE_MODEL_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("gemma3:1b", "Tiny model for very constrained machines.", 1.0, 2.0),
    CatalogModel("llama3.2:3b", "Small general-purpose model, fits most laptops.", 3.0, 4.0),
    CatalogModel("phi4-mini", "Compact reasoning-focused model.", 3.8, 4.5),
    CatalogModel("gemma3:4b", "Balanced general-purpose model.", 4.0, 5.0),
    CatalogModel("qwen2.5-coder:7b", "Coding-focused 7B model.", 7.0, 8.0),
    CatalogModel("llama3.1:8b", "Capable general 8B model.", 8.0, 9.0),
    CatalogModel("gemma3:12b", "Stronger reasoning, needs a roomy machine.", 12.0, 12.0),
    CatalogModel("qwen2.5:14b", "High-quality 14B model for workstations.", 14.0, 14.0),
    CatalogModel("qwen2.5:32b", "Large model; needs lots of RAM or VRAM.", 32.0, 22.0),
)

# Below this budget, local inference isn't worthwhile — suggest gated cloud.
_MIN_LOCAL_BUDGET_GB = 2.0
# Fraction of system RAM usable for CPU/iGPU inference (leave room for the OS).
_CPU_RAM_FRACTION = 0.6


@dataclass(frozen=True)
class HardwareRecommendation:
    """What this machine can realistically run locally."""

    budget_gb: float | None
    basis: str  # "vram" | "system_ram"
    feasible: tuple[CatalogModel, ...]
    suggest_cloud: bool
    note: str

    def format_for_user(self) -> str:
        lines = [self.note]
        if self.feasible:
            lines.append("")
            lines.append("Models you can run locally (largest first):")
            for model in self.feasible:
                lines.append(
                    f"  • {model.name} (~{model.params_b:g}B, needs ~{model.min_ram_gb:g} GB) "
                    f"— {model.description}"
                )
            lines.append(f"\nPull one with `ollama pull {self.feasible[0].name}`.")
        if self.suggest_cloud:
            lines.append("")
            lines.append(
                "For anything heavier, route to gated cloud (OpenRouter) through "
                "the privacy gate rather than running it locally."
            )
        return "\n".join(lines)


def recommend_for_profile(
    profile: HardwareProfile,
    *,
    max_results: int = 3,
) -> HardwareRecommendation:
    """Map a detected HardwareProfile to feasible local models.

    Uses discrete-GPU VRAM when present, otherwise a fraction of system RAM
    (CPU/iGPU inference shares system memory). Returns the largest models that
    fit, plus whether to suggest gated cloud for heavier work.
    """
    if profile.has_discrete_gpu and profile.total_vram_mb:
        budget_gb: float | None = round(profile.total_vram_mb / 1024.0, 1)
        basis = "vram"
    elif profile.ram_gb:
        budget_gb = round(profile.ram_gb * _CPU_RAM_FRACTION, 1)
        basis = "system_ram"
    else:
        budget_gb = None
        basis = "system_ram"

    if budget_gb is None or budget_gb < _MIN_LOCAL_BUDGET_GB:
        return HardwareRecommendation(
            budget_gb=budget_gb,
            basis=basis,
            feasible=(),
            suggest_cloud=True,
            note=(
                "Could not detect enough usable memory for comfortable local "
                "inference. Prefer gated cloud, or detect hardware again."
            ),
        )

    fitting = [m for m in FEASIBLE_MODEL_CATALOG if m.min_ram_gb <= budget_gb]
    # Largest-fitting first, capped.
    fitting.sort(key=lambda m: m.params_b, reverse=True)
    feasible = tuple(fitting[:max_results])

    basis_label = "discrete-GPU VRAM" if basis == "vram" else "system RAM (CPU/iGPU)"
    note = (
        f"Based on ~{budget_gb:g} GB usable ({basis_label}), here's what runs "
        "comfortably locally."
    )
    # Anything in the catalog bigger than the budget → cloud is the better path.
    suggest_cloud = any(m.min_ram_gb > budget_gb for m in FEASIBLE_MODEL_CATALOG)
    if not feasible:
        note = (
            f"With ~{budget_gb:g} GB usable, even the smallest catalog model is a "
            "tight fit. Try gemma3:1b, or use gated cloud."
        )
        suggest_cloud = True

    return HardwareRecommendation(
        budget_gb=budget_gb,
        basis=basis,
        feasible=feasible,
        suggest_cloud=suggest_cloud,
        note=note,
    )


_CatalogItem = TypeVar("_CatalogItem")


def render_model_health(health: ModelHealth, output_handler: Callable[[str], None] = print) -> None:
    """Print a human-readable health summary for the current model setup."""

    output_handler(f"Model > Provider: {health.provider}")
    output_handler(f"Model > Configured model: {health.configured_model}")
    output_handler(f"Model > Reachable: {'yes' if health.reachable else 'no'}")
    output_handler(f"Model > Ready: {'yes' if health.ready else 'no'}")

    model_list_label = (
        "Local models" if health.provider.lower() == "ollama" else "Available models"
    )
    if health.available_models:
        output_handler(f"Model > {model_list_label}:")
        for index, model_name in enumerate(health.available_models, start=1):
            output_handler(f"Model >   {index}. {model_name}")
    else:
        output_handler(f"Model > {model_list_label}: none")

    output_handler(f"Model > {health.message}")

    if not health.reachable and health.provider.lower() == "ollama":
        output_handler(
            f"Model > Install Ollama from {OLLAMA_DOWNLOAD_URL} or start the Ollama service."
        )
    elif not health.available_models and health.provider.lower() == "ollama":
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

    if runtime_profile.model.provider.lower() != "ollama":
        return runtime_profile

    health = build_text_model_provider(runtime_profile.model).health_check()
    if health.ready:
        return runtime_profile

    if not health.reachable:
        return _handle_unreachable_provider(health, runtime_profile, output_handler)

    if health.configured_model in health.available_models:
        return _handle_unusable_model(health, runtime_profile, output_handler)

    if len(health.available_models) == 1:
        return _handle_single_available_model(
            health, runtime_profile, project_root, output_handler
        )

    if health.available_models:
        return _handle_multiple_available_models(
            health, runtime_profile, project_root, input_func, output_handler
        )

    return _handle_no_local_models(
        runtime_profile, project_root, input_func, output_handler
    )


def _handle_unreachable_provider(
    health: ModelHealth,
    runtime_profile: RuntimeProfile,
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
    output_handler(f"Model > {health.message}")
    output_handler(
        f"Model > Install Ollama from {OLLAMA_DOWNLOAD_URL} or start it, then restart Aradhya."
    )
    output_handler("")
    return runtime_profile


def _handle_unusable_model(
    health: ModelHealth,
    runtime_profile: RuntimeProfile,
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
    output_handler(f"Model > {health.message}")
    output_handler("Model > The installed model is not usable on the current machine state.")
    output_handler("Model > Suggested smaller local models:")
    for index, model in enumerate(RECOMMENDED_OLLAMA_MODELS, start=1):
        output_handler(f"Model >   {index}. {model.name} - {model.description}")
    output_handler(
        "Model > Pull a smaller model, then update the profile with /setup or profile.local.json."
    )
    output_handler("")
    return runtime_profile


def _handle_single_available_model(
    health: ModelHealth,
    runtime_profile: RuntimeProfile,
    project_root: Path,
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
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


def _handle_multiple_available_models(
    health: ModelHealth,
    runtime_profile: RuntimeProfile,
    project_root: Path,
    input_func: Callable[[str], str],
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
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


def _handle_no_local_models(
    runtime_profile: RuntimeProfile,
    project_root: Path,
    input_func: Callable[[str], str],
    output_handler: Callable[[str], None],
) -> RuntimeProfile:
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
            "Model > I could not save "
            f"{model_name} to the local runtime override file. Details: {error}"
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
