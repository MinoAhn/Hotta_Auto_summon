from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = resource_root()
ASSET_DIR = PROJECT_ROOT / "assets"
TEMPLATE_DIR = ASSET_DIR / "templates"


@dataclass(frozen=True)
class Core:
    slug: str
    name: str
    default_count: int
    icon_file: str
    select_point: tuple[int, int]

    @property
    def icon_path(self) -> Path:
        return ASSET_DIR / self.icon_file


CORES: tuple[Core, ...] = (
    Core("blue", "蓝色加密核心", 1, "core_blue.png", (548, 398)),
    Core("purple", "紫色加密核心", 1, "core_purple.png", (548, 566)),
    Core("gold", "金色加密核心", 1, "core_gold.png", (548, 735)),
)


CORE_BY_SLUG = {item.slug: item for item in CORES}
