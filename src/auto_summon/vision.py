from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .config import Rect


@dataclass(frozen=True)
class TemplateMatch:
    name: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    scale: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def read_bgr(path: Path) -> np.ndarray:
    raw = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取模板图片: {path}")
    return image


def crop(image: np.ndarray, rect: Rect) -> np.ndarray:
    return image[rect.y : rect.y + rect.h, rect.x : rect.x + rect.w]


class TemplateVision:
    def __init__(self, templates: dict[str, Path], threshold: float) -> None:
        self.threshold = threshold
        self.scales = (0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25)
        self.templates = {name: read_bgr(path) for name, path in templates.items()}

    def missing_templates(self) -> list[str]:
        return [name for name, image in self.templates.items() if image.size == 0]

    def find_best(self, screenshot_bgr: np.ndarray, region: Rect, name: str) -> TemplateMatch | None:
        template = self.templates[name]
        roi = crop(screenshot_bgr, region)
        if roi.size == 0:
            return None
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        best: TemplateMatch | None = None
        for scale in self.scales:
            scaled = self._resize(template_gray, scale)
            height, width = scaled.shape[:2]
            if height > roi_gray.shape[0] or width > roi_gray.shape[1]:
                continue
            result = cv2.matchTemplate(roi_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, confidence, _, location = cv2.minMaxLoc(result)
            if confidence < self.threshold:
                continue
            candidate = TemplateMatch(
                name=name,
                confidence=float(confidence),
                x=int(region.x + location[0]),
                y=int(region.y + location[1]),
                width=width,
                height=height,
                scale=scale,
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate
        return best

    @staticmethod
    def _resize(template_gray: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1.0:
            return template_gray
        height, width = template_gray.shape[:2]
        size = max(1, round(width * scale)), max(1, round(height * scale))
        return cv2.resize(template_gray, size, interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)
