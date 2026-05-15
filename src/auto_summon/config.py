from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .cores import CORES


APP_DIR = Path.home() / "Documents" / "Auto_summon"
CONFIG_PATH = APP_DIR / "settings.json"
BASE_WIDTH = 1920
BASE_HEIGHT = 1080


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass
class ClickMap:
    status_region: Rect = field(default_factory=lambda: Rect(760, 420, 780, 300))
    summon_dialog_region: Rect = field(default_factory=lambda: Rect(360, 230, 1220, 680))
    generate_image_button: Point = field(default_factory=lambda: Point(148, 46))
    verify_core_button: Point = field(default_factory=lambda: Point(1040, 759))
    close_dialog: Point = field(default_factory=lambda: Point(1500, 289))


@dataclass
class AppSettings:
    window_title_keyword: str = "幻塔"
    match_threshold: float = 0.72
    action_interval: float = 0.25
    summon_wait_timeout: float = 90.0
    dry_run: bool = False
    selected_counts: dict[str, int] = field(default_factory=lambda: {item.slug: item.default_count for item in CORES})
    selected_enabled: dict[str, bool] = field(default_factory=lambda: {item.slug: True for item in CORES})
    click_map: ClickMap = field(default_factory=ClickMap)


def _point(raw: dict, default: Point) -> Point:
    return Point(**raw) if raw else default


def _rect(raw: dict, default: Rect) -> Rect:
    return Rect(**raw) if raw else default


def load_settings() -> AppSettings:
    if not CONFIG_PATH.exists():
        return AppSettings()
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    defaults = AppSettings()
    click_raw = raw.get("click_map", {}) if raw.get("automation_schema_version") == 2 else {}
    default_map = ClickMap()
    defaults.window_title_keyword = raw.get("window_title_keyword", defaults.window_title_keyword)
    defaults.match_threshold = float(raw.get("match_threshold", defaults.match_threshold))
    defaults.action_interval = float(raw.get("action_interval", defaults.action_interval))
    defaults.summon_wait_timeout = float(raw.get("summon_wait_timeout", defaults.summon_wait_timeout))
    defaults.dry_run = bool(raw.get("dry_run", defaults.dry_run))
    defaults.selected_counts.update(raw.get("selected_counts", {}))
    defaults.selected_enabled.update(raw.get("selected_enabled", {}))
    defaults.click_map = ClickMap(
        status_region=_rect(click_raw.get("status_region", {}), default_map.status_region),
        summon_dialog_region=_rect(click_raw.get("summon_dialog_region", {}), default_map.summon_dialog_region),
        generate_image_button=_point(click_raw.get("generate_image_button", {}), default_map.generate_image_button),
        verify_core_button=_point(click_raw.get("verify_core_button", {}), default_map.verify_core_button),
        close_dialog=_point(click_raw.get("close_dialog", {}), default_map.close_dialog),
    )
    return defaults


def save_settings(settings: AppSettings) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({**asdict(settings), "automation_schema_version": 2}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
