from __future__ import annotations

import queue
import threading
import time
from dataclasses import replace
from datetime import datetime

import customtkinter as ctk
from PIL import Image

from .automation import GameAutomation, StopRequested, SummonJob
from .config import AppSettings, load_settings, save_settings
from .cores import ASSET_DIR, CORES, Core


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG = "#070a12"
SURFACE = "#0d1422"
SURFACE_2 = "#121c2c"
BORDER = "#243348"
TEXT = "#f5f7fb"
MUTED = "#94a3b8"
TEAL = "#35d0ba"
BLUE = "#5ab8ff"
RED = "#ef5b5b"


class CoreCard(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass, core: Core, settings: AppSettings) -> None:
        super().__init__(master, corner_radius=8, fg_color=SURFACE_2, border_width=1, border_color=BORDER)
        self.core = core
        self.enabled = ctk.BooleanVar(value=settings.selected_enabled.get(core.slug, True))
        self.count = ctk.StringVar(value=str(settings.selected_counts.get(core.slug, core.default_count)))
        self.grid_columnconfigure(1, weight=1)

        icon = self._load_icon(core)
        box = ctk.CTkFrame(self, width=70, height=58, corner_radius=8, fg_color="#1c2a42")
        box.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12)
        box.grid_propagate(False)
        label = ctk.CTkLabel(box, image=icon, text="")
        label.image = icon
        label.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self, text=core.name, anchor="w", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).grid(
            row=0, column=1, sticky="ew", padx=(0, 8), pady=(13, 2)
        )
        ctk.CTkLabel(self, text="目标使用次数", anchor="w", font=ctk.CTkFont(size=12), text_color=MUTED).grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 12)
        )
        ctk.CTkEntry(
            self,
            textvariable=self.count,
            width=86,
            height=34,
            justify="center",
            corner_radius=8,
            fg_color="#0a1020",
            border_color="#2e4568",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=2, rowspan=2, padx=(0, 10), pady=12)
        ctk.CTkSwitch(self, text="", variable=self.enabled, width=42, progress_color=TEAL).grid(
            row=0, column=3, rowspan=2, padx=(0, 12), pady=12
        )

    def as_job(self) -> SummonJob | None:
        if not self.enabled.get():
            return None
        try:
            count = int(self.count.get())
        except ValueError:
            raise ValueError(f"{self.core.name} 的次数不是整数。")
        if count <= 0:
            raise ValueError(f"{self.core.name} 的次数必须大于 0。")
        return SummonJob(self.core.slug, count)

    def apply_to_settings(self, settings: AppSettings) -> None:
        settings.selected_enabled[self.core.slug] = self.enabled.get()
        try:
            settings.selected_counts[self.core.slug] = int(self.count.get())
        except ValueError:
            settings.selected_counts[self.core.slug] = self.core.default_count

    @staticmethod
    def _load_icon(core: Core) -> ctk.CTkImage:
        if core.icon_path.exists():
            image = Image.open(core.icon_path).convert("RGBA")
        else:
            image = Image.new("RGBA", (80, 58), "#223047")
        return ctk.CTkImage(light_image=image, dark_image=image, size=(64, 46))


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title("Auto Summon")
        self.geometry("1040x720")
        self.minsize(920, 640)
        self._set_window_icon()

        self.settings = load_settings()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.automation: GameAutomation | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_workspace()
        self._build_log()
        self.after(100, self._drain_logs)

    def _set_window_icon(self) -> None:
        icon = ASSET_DIR / "app_icon.ico"
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except Exception:
                pass

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="加密召唤自动化", font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        self.watermark_box = ctk.CTkTextbox(
            header,
            width=680,
            height=24,
            corner_radius=0,
            fg_color=BG,
            border_width=0,
            font=ctk.CTkFont(size=13),
            text_color=BG,
        )
        self.watermark_box.grid(row=1, column=0, sticky="ew")
        self.watermark_box.insert(
            "1.0",
            "蔚色艾达-水銀灯 爱来自星海旅人 ♥ Copyright © Auto Summon. All right reserved",
        )
        self.watermark_box.configure(state="disabled")
        self.status = ctk.CTkLabel(
            header,
            text="空闲",
            width=92,
            height=34,
            corner_radius=8,
            fg_color="#0e2430",
            text_color=TEAL,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.status.grid(row=0, column=1, padx=(18, 0), sticky="e")

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        workspace.grid(row=1, column=0, sticky="nsew", padx=22)
        workspace.grid_columnconfigure(0, weight=5)
        workspace.grid_columnconfigure(1, weight=3)
        workspace.grid_rowconfigure(0, weight=1)

        left_shell = ctk.CTkFrame(workspace, corner_radius=8, fg_color=SURFACE, border_width=1, border_color="#1e2b40")
        left_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_shell.grid_columnconfigure(0, weight=1)
        left_shell.grid_rowconfigure(0, weight=1)
        left = ctk.CTkScrollableFrame(
            left_shell,
            corner_radius=8,
            fg_color=SURFACE,
            scrollbar_button_color="#2b405f",
            scrollbar_button_hover_color="#3f5f8c",
        )
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="加密核心队列", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT).grid(
            row=0, column=0, padx=18, pady=(18, 4), sticky="w"
        )
        ctk.CTkLabel(left, text="按顺序使用勾选的核心，每种核心执行设定次数", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, padx=18, pady=(0, 12), sticky="w"
        )
        self.rows: list[CoreCard] = []
        for index, core in enumerate(CORES):
            row = CoreCard(left, core, self.settings)
            row.grid(row=index + 2, column=0, padx=14, pady=8, sticky="ew")
            self.rows.append(row)

        self._build_control_panel(workspace)

    def _button(self, master, text, command, color, hover, text_color=TEXT):
        return ctk.CTkButton(
            master,
            text=text,
            command=command,
            height=38,
            corner_radius=8,
            fg_color=color,
            hover_color=hover,
            text_color=text_color,
            font=ctk.CTkFont(size=14, weight="bold"),
        )

    def _build_control_panel(self, master: ctk.CTkFrame) -> None:
        shell = ctk.CTkFrame(master, corner_radius=8, fg_color=SURFACE, border_width=1, border_color="#1e2b40")
        shell.grid(row=0, column=1, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        side = ctk.CTkScrollableFrame(
            shell,
            corner_radius=8,
            fg_color=SURFACE,
            scrollbar_button_color="#2b405f",
            scrollbar_button_hover_color="#3f5f8c",
        )
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(side, text="运行控制", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT).grid(
            row=0, column=0, padx=18, pady=(18, 4), sticky="w"
        )
        ctk.CTkLabel(side, text="扫描会最小化本程序，避免遮挡游戏画面", font=ctk.CTkFont(size=12), text_color=MUTED).grid(
            row=1, column=0, padx=18, pady=(0, 12), sticky="w"
        )

        actions = ctk.CTkFrame(side, corner_radius=8, fg_color="#0a1020", border_width=1, border_color="#1f314b")
        actions.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)
        self._button(actions, "扫描界面", self.scan_screen, BLUE, "#449ee0").grid(row=0, column=0, padx=8, pady=10, sticky="ew")
        self._button(actions, "开始召唤", self.start_summon, TEAL, "#28b59f").grid(row=0, column=1, padx=8, pady=10, sticky="ew")
        self._button(actions, "停止", self.stop, RED, "#cf4848").grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 10), sticky="ew")

        self.title_keyword = ctk.StringVar(value=self.settings.window_title_keyword)
        self.threshold = ctk.StringVar(value=str(self.settings.match_threshold))
        self.interval = ctk.StringVar(value=str(self.settings.action_interval))
        self.timeout = ctk.StringVar(value=str(self.settings.summon_wait_timeout))
        self.dry_run = ctk.BooleanVar(value=self.settings.dry_run)

        self._field(side, "窗口标题关键字", self.title_keyword, 3)
        self._field(side, "识别阈值", self.threshold, 4)
        self._field(side, "操作间隔秒", self.interval, 5)
        self._field(side, "召唤等待超时", self.timeout, 6)

        dry_box = ctk.CTkFrame(side, corner_radius=8, fg_color=SURFACE_2, border_width=1, border_color=BORDER)
        dry_box.grid(row=7, column=0, padx=14, pady=8, sticky="ew")
        dry_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dry_box, text="安全模式", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT).grid(
            row=0, column=0, padx=12, pady=(10, 2), sticky="w"
        )
        ctk.CTkLabel(dry_box, text="开启后只写日志，不向游戏发送点击", font=ctk.CTkFont(size=12), text_color=MUTED).grid(
            row=1, column=0, padx=12, pady=(0, 10), sticky="w"
        )
        ctk.CTkSwitch(dry_box, text="", variable=self.dry_run, progress_color=TEAL).grid(row=0, column=1, rowspan=2, padx=12, pady=10)

        ctk.CTkButton(side, text="保存配置", command=self.save, height=38, corner_radius=8, fg_color="#27364e").grid(
            row=8, column=0, padx=14, pady=(8, 12), sticky="ew"
        )
        self.scan_result = ctk.CTkTextbox(side, height=150, wrap="word", corner_radius=8, fg_color="#090f1c", border_width=1, border_color="#1f314b")
        self.scan_result.grid(row=9, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.scan_result.insert("end", "扫描结果会显示在这里。\n")
        self.scan_result.configure(state="disabled")

    def _field(self, master: ctk.CTkFrame, label: str, variable: ctk.StringVar, row: int) -> None:
        box = ctk.CTkFrame(master, corner_radius=8, fg_color=SURFACE_2, border_width=1, border_color=BORDER)
        box.grid(row=row, column=0, padx=14, pady=7, sticky="ew")
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text=label, anchor="w", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=12, pady=(8, 2), sticky="ew")
        ctk.CTkEntry(box, textvariable=variable, height=34, corner_radius=8, fg_color="#090f1c", border_color="#2b405f").grid(
            row=1, column=0, padx=12, pady=(0, 10), sticky="ew"
        )

    def _build_log(self) -> None:
        bottom = ctk.CTkFrame(self, corner_radius=8, fg_color=SURFACE, border_width=1, border_color="#1e2b40")
        bottom.grid(row=2, column=0, sticky="nsew", padx=22, pady=(12, 18))
        bottom.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bottom, text="运行日志", font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).grid(row=0, column=0, padx=14, pady=(12, 4), sticky="w")
        self.log_box = ctk.CTkTextbox(bottom, height=132, wrap="word", corner_radius=8, fg_color="#070c16", border_width=1, border_color="#1f314b")
        self.log_box.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.log("准备就绪。建议先进入操作仪附近，点击“扫描界面”确认识别结果，再开始召唤。")

    def collect_settings(self) -> AppSettings:
        settings = replace(self.settings)
        settings.window_title_keyword = self.title_keyword.get().strip() or "幻塔"
        settings.match_threshold = float(self.threshold.get())
        settings.action_interval = float(self.interval.get())
        settings.summon_wait_timeout = float(self.timeout.get())
        settings.dry_run = self.dry_run.get()
        for row in self.rows:
            row.apply_to_settings(settings)
        self.settings = settings
        return settings

    def save(self) -> None:
        try:
            save_settings(self.collect_settings())
            self.log("设置已保存。")
        except Exception as exc:
            self.log(f"保存失败: {exc}")

    def start_summon(self) -> None:
        try:
            settings = self.collect_settings()
            jobs = [job for row in self.rows if (job := row.as_job()) is not None]
            if not jobs:
                self.log("没有选中任何加密核心。")
                return
            save_settings(settings)
            self._start_worker(lambda bot: bot.run_summon(jobs), settings)
        except Exception as exc:
            self.log(f"启动失败: {exc}")

    def scan_screen(self) -> None:
        try:
            settings = self.collect_settings()
            save_settings(settings)
            self.log("扫描准备：即将最小化本程序。")
            self.iconify()
            self._start_worker(self._scan_worker, settings)
        except Exception as exc:
            self.log(f"扫描失败: {exc}")

    def stop(self) -> None:
        if self.automation:
            self.automation.request_stop()
        self.log("已请求停止。")

    def _start_worker(self, task, settings: AppSettings) -> None:
        if self.worker and self.worker.is_alive():
            self.log("已有任务正在运行。")
            return
        self.status.configure(text="运行中", fg_color="#1b2b32", text_color=TEAL)
        self.automation = GameAutomation(settings, self._thread_log)
        self.worker = threading.Thread(target=self._run_task, args=(task, self.automation), daemon=True)
        self.worker.start()

    def _run_task(self, task, bot: GameAutomation) -> None:
        try:
            task(bot)
        except StopRequested as exc:
            self._thread_log(str(exc))
        except Exception as exc:
            self._thread_log(f"任务失败: {exc}")
        finally:
            self.log_queue.put("__STATUS_IDLE__")

    def _scan_worker(self, bot: GameAutomation) -> None:
        self._thread_log("等待窗口最小化完成。")
        time.sleep(0.65)
        lines = bot.scan()
        self.log_queue.put("__SCAN__" + "\n".join(lines))
        self.log_queue.put("__RESTORE__")

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{stamp}] {message}\n")
        self.log_box.see("end")

    def _thread_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_logs(self) -> None:
        while not self.log_queue.empty():
            message = self.log_queue.get()
            if message == "__STATUS_IDLE__":
                self.status.configure(text="空闲", fg_color="#0e2430", text_color=TEAL)
                continue
            if message == "__RESTORE__":
                self.deiconify()
                self.lift()
                self.focus_force()
                continue
            if message.startswith("__SCAN__"):
                self.scan_result.configure(state="normal")
                self.scan_result.delete("1.0", "end")
                self.scan_result.insert("end", message.removeprefix("__SCAN__"))
                self.scan_result.configure(state="disabled")
                self.log("扫描完成。")
                continue
            self.log(message)
        self.after(100, self._drain_logs)


def main() -> None:
    app = App()
    app.mainloop()
