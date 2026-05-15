from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time
from dataclasses import dataclass
from typing import Callable

import keyboard
import pyautogui
import pygetwindow as gw

from .config import BASE_HEIGHT, BASE_WIDTH, AppSettings, Point, Rect
from .cores import CORE_BY_SLUG, TEMPLATE_DIR
from .vision import TemplateMatch, TemplateVision, pil_to_bgr


LogFn = Callable[[str], None]


@dataclass(frozen=True)
class SummonJob:
    slug: str
    count: int


class StopRequested(RuntimeError):
    pass


@dataclass(frozen=True)
class WindowContext:
    left: int
    top: int
    width: int
    height: int

    @property
    def scale(self) -> float:
        return min(self.width / BASE_WIDTH, self.height / BASE_HEIGHT)

    @property
    def content_width(self) -> int:
        return round(BASE_WIDTH * self.scale)

    @property
    def content_height(self) -> int:
        return round(BASE_HEIGHT * self.scale)

    @property
    def content_left(self) -> int:
        return self.left + (self.width - self.content_width) // 2

    @property
    def content_top(self) -> int:
        return self.top + (self.height - self.content_height) // 2

    @property
    def content_offset_x(self) -> int:
        return self.content_left - self.left

    @property
    def content_offset_y(self) -> int:
        return self.content_top - self.top

    def point(self, point: Point | tuple[int, int]) -> tuple[int, int]:
        x, y = (point.x, point.y) if isinstance(point, Point) else point
        return self.content_left + round(x * self.scale), self.content_top + round(y * self.scale)

    def rect(self, rect: Rect) -> Rect:
        return Rect(
            x=self.content_offset_x + round(rect.x * self.scale),
            y=self.content_offset_y + round(rect.y * self.scale),
            w=max(1, round(rect.w * self.scale)),
            h=max(1, round(rect.h * self.scale)),
        )


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class GameAutomation:
    def __init__(self, settings: AppSettings, log: LogFn) -> None:
        _enable_dpi_awareness()
        self.settings = settings
        self.log = log
        self.stop_event = threading.Event()
        self.window = None
        self.window_context: WindowContext | None = None
        self.vision = TemplateVision(
            {
                "generate": TEMPLATE_DIR / "generate_encrypted_image.png",
                "generate_text": TEMPLATE_DIR / "generate_text.png",
                "busy": TEMPLATE_DIR / "busy_text.png",
                "verify": TEMPLATE_DIR / "verify_encrypted_core.png",
                "summon_title": TEMPLATE_DIR / "summon_title.png",
            },
            threshold=settings.match_threshold,
        )

    def request_stop(self) -> None:
        self.stop_event.set()

    def run_summon(self, jobs: list[SummonJob]) -> None:
        self.stop_event.clear()
        self._install_hotkey()
        self._activate_game()
        self.log("开始自动加密召唤。按 Ctrl+Alt+S 可随时停止。")
        for job in jobs:
            core = CORE_BY_SLUG[job.slug]
            done = 0
            while done < job.count:
                self._guard()
                self.log(f"准备召唤: {core.name} {done + 1}/{job.count}")
                self._ensure_summon_page()
                self._click(self._context().point(core.select_point), f"选择 {core.name}")
                self._sleep(0.18)
                self._click_point(self.settings.click_map.verify_core_button, "验证加密核心")
                done += 1
                self.log(f"已点击验证: {core.name}，等待操作仪状态恢复。")
                self._wait_until_instrument_ready()
            self.log(f"{core.name} 已完成 {done} 次。")
        self.log("自动加密召唤任务结束。")

    def scan(self) -> list[str]:
        self._activate_game()
        screenshot = self._screenshot_game(self._context())
        lines = []
        for label, matcher in (
            ("召唤页", self._is_summon_page_match),
            ("生成加密影像", self._find_generate_status),
            ("操作仪使用中", self._find_busy_status),
            ("验证按钮", self._find_verify_button),
        ):
            match = matcher(screenshot)
            if match:
                lines.append(f"{label}: {match.confidence:.2f} scale {match.scale:.2f} @ {match.center}")
            else:
                lines.append(f"{label}: 未识别")
        return lines

    def _ensure_summon_page(self) -> None:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            self._guard()
            screenshot = self._screenshot_game(self._context())
            if self._is_summon_page_match(screenshot):
                self.log("已处于加密召唤页面。")
                return
            generate = self._find_generate_status(screenshot)
            if generate:
                self.log(f"识别到生成加密影像状态，置信度 {generate.confidence:.2f}，按 F 进入召唤页。")
                self._press("f", "生成加密影像")
                self._sleep(1.0)
                continue
            busy = self._find_busy_status(screenshot)
            if busy:
                self.log("操作仪正在使用中，等待状态恢复。")
                self._sleep(1.0)
                continue
            self.log("未识别到召唤页或操作仪可用状态，继续等待。")
            self._sleep(0.8)
        raise RuntimeError("等待加密召唤页面超时。请确认角色靠近加密操作仪，且页面未被遮挡。")

    def _wait_until_instrument_ready(self) -> None:
        deadline = time.monotonic() + self.settings.summon_wait_timeout
        saw_busy = False
        while time.monotonic() < deadline:
            self._guard()
            screenshot = self._screenshot_game(self._context())
            if self._find_generate_status(screenshot):
                self.log("操作仪已恢复到生成加密影像状态，可以进入下一轮。")
                return
            if self._find_busy_status(screenshot):
                saw_busy = True
                self.log("检测到操作仪正在使用中。")
            elif not saw_busy and self._is_summon_page_match(screenshot):
                self.log("召唤页仍存在，等待页面关闭或状态变化。")
            self._sleep(1.0)
        raise RuntimeError("等待操作仪恢复超时。可适当调大“召唤等待超时”。")

    def _find_generate_status(self, screenshot_bgr) -> TemplateMatch | None:
        return self.vision.find_best(screenshot_bgr, self._context().rect(self.settings.click_map.status_region), "generate_text")

    def _find_busy_status(self, screenshot_bgr) -> TemplateMatch | None:
        return self.vision.find_best(screenshot_bgr, self._context().rect(self.settings.click_map.status_region), "busy")

    def _find_verify_button(self, screenshot_bgr) -> TemplateMatch | None:
        return self.vision.find_best(screenshot_bgr, self._context().rect(self.settings.click_map.summon_dialog_region), "verify")

    def _is_summon_page_match(self, screenshot_bgr) -> TemplateMatch | None:
        return self._find_verify_button(screenshot_bgr) or self.vision.find_best(
            screenshot_bgr,
            self._context().rect(self.settings.click_map.summon_dialog_region),
            "summon_title",
        )

    def _activate_game(self) -> None:
        keyword = self.settings.window_title_keyword.strip()
        windows = [win for win in gw.getAllWindows() if keyword and keyword in win.title]
        if not windows:
            raise RuntimeError(f"找不到标题包含「{keyword}」的游戏窗口。")
        window = windows[0]
        self.log(f"切换到游戏窗口: {window.title}")
        if not self.settings.dry_run:
            window.activate()
        self._sleep(0.6)
        self.window = window
        self.window_context = self._read_window_context(window)
        ctx = self.window_context
        self.log(
            f"游戏客户区: {ctx.left},{ctx.top} {ctx.width}x{ctx.height}；"
            f"16:9内容区 {ctx.content_left},{ctx.content_top} {ctx.content_width}x{ctx.content_height}；"
            f"坐标缩放 x{ctx.scale:.3f}"
        )

    def _install_hotkey(self) -> None:
        try:
            keyboard.add_hotkey("ctrl+alt+s", self.request_stop, suppress=False)
        except Exception as exc:
            self.log(f"全局停止热键注册失败，仍可用 GUI 停止: {exc}")

    def _guard(self) -> None:
        if self.stop_event.is_set():
            raise StopRequested("用户停止任务。")

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + max(seconds, self.settings.action_interval)
        while time.monotonic() < end:
            self._guard()
            time.sleep(0.05)

    def _click_point(self, point: Point, label: str) -> None:
        self._click(self._context().point(point), label)

    def _click(self, xy: tuple[int, int], label: str) -> None:
        self._guard()
        if self.settings.dry_run:
            self.log(f"[Dry-run] {label}: click {xy[0]}, {xy[1]}")
            return
        pyautogui.click(*xy)

    def _press(self, key: str, label: str) -> None:
        self._guard()
        if self.settings.dry_run:
            self.log(f"[Dry-run] {label}: press {key}")
            return
        pyautogui.press(key)

    def _context(self) -> WindowContext:
        if self.window_context is None:
            self._activate_game()
        if self.window is not None:
            self.window_context = self._read_window_context(self.window)
        if self.window_context is None:
            raise RuntimeError("无法获取游戏窗口坐标。")
        return self.window_context

    @staticmethod
    def _screenshot_game(ctx: WindowContext):
        return pil_to_bgr(pyautogui.screenshot(region=(ctx.left, ctx.top, ctx.width, ctx.height)))

    @staticmethod
    def _read_window_context(window) -> WindowContext:
        hwnd = getattr(window, "_hWnd", None)
        if hwnd:
            rect = ctypes.wintypes.RECT()
            point = ctypes.wintypes.POINT(0, 0)
            if ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)) and ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
                return WindowContext(point.x, point.y, max(1, rect.right - rect.left), max(1, rect.bottom - rect.top))
        return WindowContext(window.left, window.top, max(1, window.width), max(1, window.height))
