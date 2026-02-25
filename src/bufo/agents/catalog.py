"""Agent descriptor loading from package data and user overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from bufo.agents.schema import AgentCatalog, AgentDescriptor
from bufo.paths import custom_agents_dir

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(slots=True)
class CatalogLoadResult:
    agents: list[AgentDescriptor]
    warnings: list[str]


class AgentRegistry:
    def __init__(self, package_data_dir: Path, custom_dir: Path | None = None) -> None:
        self.package_data_dir = package_data_dir
        self.custom_dir = custom_dir or custom_agents_dir()

    def load(self) -> CatalogLoadResult:
        warnings: list[str] = []
        by_identity: dict[str, AgentDescriptor] = {}

        for descriptor in self._iter_descriptors(self.package_data_dir, warnings):
            by_identity[descriptor.identity] = descriptor

        for descriptor in self._iter_descriptors(self.custom_dir, warnings):
            by_identity[descriptor.identity] = descriptor

        agents = sorted(by_identity.values(), key=lambda item: item.name.lower())
        return CatalogLoadResult(agents=agents, warnings=warnings)

    def _iter_descriptors(self, root: Path, warnings: list[str]) -> Iterable[AgentDescriptor]:
        if not root.exists():
            return []

        loaded: list[AgentDescriptor] = []
        for path in sorted(root.glob("*.toml")):
            try:
                payload = tomllib.loads(path.read_text(encoding="utf-8"))
                catalog = AgentCatalog.model_validate(payload)
                loaded.extend(catalog.agents)
            except Exception as exc:  # pragma: no cover - defensive parser path
                warnings.append(f"{path.name}: {exc}")
        return loaded
