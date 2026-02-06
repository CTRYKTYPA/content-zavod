"""Обработчик видео."""
import os
from pathlib import Path
from typing import Optional, Dict, Any
import cv2
import numpy as np

# Опциональный импорт moviepy (2.x: from moviepy; 1.x: from moviepy.editor)
try:
    try:
        from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
    except ImportError:
        from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    VideoFileClip = None
    CompositeVideoClip = None
    ImageClip = None

from PIL import Image, ImageEnhance, ImageDraw, ImageFont, ImageFilter
from loguru import logger
from config import settings
from database.models import Topic


class VideoProcessor:
    """Обработчик видео для уникализации и брендирования."""
    
    def __init__(self, topic: Topic):
        """
        Инициализация процессора.
        
        Args:
            topic: Тематика с настройками обработки
        """
        self.topic = topic
    
    def process_video(
        self, 
        input_path: str, 
        output_path: str,
        remove_watermarks: bool = False
    ) -> tuple[bool, Optional[str]]:
        """
        Обработать видео: уникализация + брендирование.
        
        Args:
            input_path: Путь к исходному видео
            output_path: Путь для сохранения обработанного видео
            remove_watermarks: Попытаться удалить водяные знаки
            
        Returns:
            (success, error_message)
        """
        try:
            video = VideoFileClip(str(input_path))
            # Не конвертируем в 9:16 и не ресайзим — обрезка/апскейл давали «заужено» и размытие.
            # Shorts уже вертикальные, только плашка.

            # Уникализация
            if self.topic.video_speed_change != 0:
                video = self._change_speed(video, self.topic.video_speed_change)
            
            if self.topic.brightness_adjustment != 0 or self.topic.contrast_adjustment != 0:
                video = self._adjust_brightness_contrast(video)
            
            if self.topic.crop_settings:
                video = self._crop_video(video, self.topic.crop_settings)
            
            # Удаление водяных знаков (по умолчанию выкл — размывало весь кадр)
            if remove_watermarks:
                video = self._remove_watermarks(video)
            
            # Брендирование: логотип или текстовая плашка (уникализация)
            if self.topic.branding_enabled:
                if self.topic.branding_logo_path:
                    video = self._add_branding(video)
                else:
                    video = self._inpaint_watermarks_auto(video)
                    video = self._add_text_plashka(video)
            
            # Сохраняем результат
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            quick = os.environ.get("STAGE1_QUICK") == "1"
            video.write_videofile(
                str(output_file),
                codec='libx264',
                audio_codec='aac',
                fps=video.fps,
                preset='veryfast' if quick else 'slow',
                bitrate='4000k' if quick else '8000k',
                ffmpeg_params=['-movflags', '+faststart'],
            )
            
            video.close()
            
            logger.info(f"Видео обработано: {output_path}")
            return True, None
        
        except Exception as e:
            logger.error(f"Ошибка обработки видео: {e}")
            return False, str(e)
    
    def _is_vertical_format(self, video: VideoFileClip) -> bool:
        """Проверить, является ли видео вертикальным форматом 9:16."""
        w, h = video.size
        aspect_ratio = h / w if w > 0 else 0
        # Проверяем, что соотношение близко к 16/9 ≈ 1.78
        return 1.5 < aspect_ratio < 2.0
    
    def _convert_to_vertical(self, video: VideoFileClip) -> VideoFileClip:
        """Конвертировать видео в вертикальный формат 9:16."""
        target_w, target_h = settings.VIDEO_TARGET_RESOLUTION
        w, h = video.size
        
        if h / w > target_h / target_w:
            new_w = int(h * target_w / target_h)
            new_h = h
            x_center = w / 2
            video = video.cropped(x_center=x_center, y_center=h / 2, width=new_w, height=new_h)
        else:
            new_h = int(w * target_h / target_w)
            new_w = w
            y_center = h / 2
            video = video.cropped(x_center=w / 2, y_center=y_center, width=new_w, height=new_h)
        
        video = video.resized(new_size=(target_w, target_h))
        return video
    
    def _change_speed(self, video: VideoFileClip, speed_change_percent: float) -> VideoFileClip:
        """Изменить скорость видео."""
        from moviepy.video.fx.MultiplySpeed import MultiplySpeed
        speed_multiplier = 1 + (speed_change_percent / 100)
        return video.with_effects([MultiplySpeed(speed_multiplier)])
    
    def _adjust_brightness_contrast(self, video: VideoFileClip) -> VideoFileClip:
        """Корректировать яркость и контраст."""
        brightness = self.topic.brightness_adjustment
        contrast = self.topic.contrast_adjustment
        
        def adjust_frame(frame):
            # Конвертируем в PIL Image
            img = Image.fromarray(frame)
            
            # Яркость
            if brightness != 0:
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1 + brightness / 100)
            
            # Контраст
            if contrast != 0:
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1 + contrast / 100)
            
            return np.array(img)
        
        return video.image_transform(adjust_frame)
    
    def _crop_video(self, video: VideoFileClip, crop_settings: Dict[str, int]) -> VideoFileClip:
        """Обрезать видео."""
        x = crop_settings.get("x", 0)
        y = crop_settings.get("y", 0)
        w, h = video.size
        width = crop_settings.get("width", w)
        height = crop_settings.get("height", h)
        return video.cropped(x1=x, y1=y, x2=x + width, y2=y + height)
    
    def _remove_watermarks(self, video: VideoFileClip) -> VideoFileClip:
        """
        Попытка удалить водяные знаки.
        
        Внимание: Это базовая реализация. Для реального удаления нужны более сложные алгоритмы.
        """
        # Здесь можно использовать различные техники:
        # 1. Inpainting для известных областей водяных знаков
        # 2. ML-модели для детекции и удаления
        # 3. Размытие углов (где обычно размещаются водяные знаки)
        
        # Размываем только углы (маска = 0 в центре, >0 в углах).
        def blur_corners(frame):
            h, w = frame.shape[:2]
            corner_size = min(w, h) // 10
            frame_blurred = cv2.GaussianBlur(frame, (15, 15), 0)
            mask = np.zeros((h, w), dtype=np.float32)
            mask[:corner_size, :corner_size] = 0.5
            mask[:corner_size, -corner_size:] = 0.5
            mask[-corner_size:, :corner_size] = 0.5
            mask[-corner_size:, -corner_size:] = 0.5
            if len(frame.shape) == 3:
                mask = np.stack([mask] * frame.shape[2], axis=2)
            out = frame.astype(np.float32) * (1 - mask) + frame_blurred.astype(np.float32) * mask
            return np.clip(out, 0, 255).astype(frame.dtype)
        
        return video.image_transform(blur_corners)

    def _detect_watermark_in_roi(self, roi: np.ndarray) -> np.ndarray:
        """
        Автопоиск водяного знака в ROI по цвету/яркости.
        ROI в RGB. Возвращает бинарную маску (0/255) того же размера.
        """
        rh, rw = roi.shape[:2]
        if len(roi.shape) != 3:
            return np.zeros((rh, rw), dtype=np.uint8)
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        # Эвристики под типичные вод. знаки (YouTube, TikTok, репосты и т.д.)
        purple = ((h >= 120) & (h <= 165) & (s >= 30)).astype(np.uint8)
        bright = ((v >= 180) & (s <= 80)).astype(np.uint8)
        dark = (v <= 55).astype(np.uint8)
        light_blue = ((h >= 85) & (h <= 110) & (s >= 40) & (s <= 200) & (v >= 140)).astype(np.uint8)
        light_gray = ((v >= 140) & (v <= 200) & (s <= 60)).astype(np.uint8)
        combined = np.clip(purple + bright + dark + light_blue + light_gray, 0, 1).astype(np.uint8)
        k = max(2, min(rw, rh) // 20)
        kernel = np.ones((k, k), np.uint8)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
        return (combined > 0).astype(np.uint8) * 255

    def _inpaint_watermarks_auto(self, video: VideoFileClip) -> VideoFileClip:
        """
        Автопоиск и затирка водяных знаков: сканируем углы (по настройкам),
        детекция по цвету/яркости, инпейнтинг только по маске.
        """
        roi_pct = getattr(settings, "WATERMARK_ROI_PERCENT", 0.08)
        corners_cfg = getattr(settings, "WATERMARK_CORNERS", "all")
        fallback_br = getattr(settings, "WATERMARK_FALLBACK_BOTTOM_RIGHT", True)

        corners = ["tl", "tr", "bl", "br"] if corners_cfg == "all" else ["br"]

        def inpaint_frame(frame: np.ndarray) -> np.ndarray:
            fh, fw = frame.shape[:2]
            if len(frame.shape) != 3:
                return frame
            rw = max(40, int(fw * roi_pct))
            rh = max(40, int(fh * roi_pct))
            full_mask = np.zeros((fh, fw), dtype=np.uint8)

            if "tl" in corners:
                roi = frame[0:rh, 0:rw].copy()
                m = self._detect_watermark_in_roi(roi)
                full_mask[0:rh, 0:rw] = np.maximum(full_mask[0:rh, 0:rw], m)
            if "tr" in corners:
                roi = frame[0:rh, -rw:].copy()
                m = self._detect_watermark_in_roi(roi)
                full_mask[0:rh, -rw:] = np.maximum(full_mask[0:rh, -rw:], m)
            if "bl" in corners:
                roi = frame[-rh:, 0:rw].copy()
                m = self._detect_watermark_in_roi(roi)
                full_mask[-rh:, 0:rw] = np.maximum(full_mask[-rh:, 0:rw], m)
            if "br" in corners:
                roi = frame[-rh:, -rw:].copy()
                m = self._detect_watermark_in_roi(roi)
                if fallback_br and m.sum() == 0:
                    cx, cy = rw // 2, rh // 2
                    ax, ay = max(4, rw // 4), max(4, rh // 4)
                    m = np.zeros((rh, rw), dtype=np.uint8)
                    cv2.ellipse(m, (cx, cy), (ax, ay), 0, 0, 360, 255, -1)
                full_mask[-rh:, -rw:] = np.maximum(full_mask[-rh:, -rw:], m)

            if full_mask.sum() == 0:
                return frame
            radius = max(2, min(rw, rh) // 8)
            return cv2.inpaint(frame, full_mask, radius, cv2.INPAINT_TELEA)

        return video.image_transform(inpaint_frame)

    def _draw_instagram_icon(self, size: int) -> Image.Image:
        """Рисует иконку Instagram (скруглённый квадрат + объектив + точка). Не прозрачная."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = size // 2
        pad = max(1, size // 8)
        box = [pad, pad, size - 1 - pad, size - 1 - pad]
        # Контур скруглённого квадрата (как у IG)
        d.rounded_rectangle(box, radius=max(2, size // 5), outline=(255, 255, 255), width=max(1, size // 12))
        cx, cy = size // 2, size // 2
        # Круг-объектив
        rad = size // 5
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255), width=max(1, size // 16))
        # Точка-блик справа сверху
        dot = max(2, size // 12)
        d.ellipse([cx + rad - dot, cy - rad, cx + rad + dot, cy - rad + 2 * dot], fill=(255, 255, 255))
        return img

    def _add_text_plashka(self, video: VideoFileClip) -> VideoFileClip:
        """Только значок Instagram + ник, без рамок. Чуть выше, тень чтобы не сливалось."""
        w, h = video.size
        margin = max(16, min(w, h) // 40)
        lift = 56  # поднять выше от низа
        font_size = max(18, min(24, h // 40))
        icon_size = max(20, font_size + 4)
        gap = 8
        pad_v = 4
        pad_h = 4
        text_pad_right = 12  # запас, чтобы ник не залезал за край

        font = None
        for path in (
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "arial.ttf",
        ):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        text = (getattr(settings, "BRANDING_DEFAULT_TEXT", None) or "Rise_motivation.7").strip() or "Rise_motivation.7"
        tmp = Image.new("RGB", (1, 1))
        dd = ImageDraw.Draw(tmp)
        try:
            bbox = dd.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw = len(text) * font_size // 2
            th = font_size

        bw = pad_h + icon_size + gap + tw + text_pad_right
        bh = pad_v * 2 + max(icon_size, th)
        canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        # Иконка слева
        icon = self._draw_instagram_icon(icon_size)
        iy = (bh - icon_size) // 2
        canvas.paste(icon, (pad_h, iy), icon)
        tx = pad_h + icon_size + gap
        ty = (bh - th) // 2
        # Лёгкая тень (чтобы не сливалось с фоном)
        draw.text((tx + 1, ty + 1), text, fill=(0, 0, 0), font=font)
        draw.text((tx, ty), text, fill=(255, 255, 255), font=font)

        arr = np.array(canvas)
        clip = ImageClip(arr, duration=video.duration)
        clip = clip.with_position((w - bw - margin, h - bh - margin - lift))
        return CompositeVideoClip([video, clip])

    def _add_branding(self, video: VideoFileClip) -> VideoFileClip:
        """Добавить брендированную плашку (логотип)."""
        logo_path = Path(self.topic.branding_logo_path)
        if not logo_path.exists():
            logger.warning(f"Логотип не найден: {logo_path}")
            return self._add_text_plashka(video)
        
        logo = ImageClip(str(logo_path), duration=video.duration)
        logo_size = self.topic.branding_size or 100
        logo = logo.resized(new_size=(logo_size, logo_size))
        w, h = video.size
        margin = self.topic.branding_margin or 20
        position_map = {
            "top_left": (margin, margin),
            "top_right": (w - logo_size - margin, margin),
            "bottom_left": (margin, h - logo_size - margin),
            "bottom_right": (w - logo_size - margin, h - logo_size - margin),
        }
        pos = position_map.get(
            getattr(self.topic, "branding_position", None) or "bottom_right",
            position_map["bottom_right"],
        )
        logo = logo.with_position(pos)
        return CompositeVideoClip([video, logo])
    
    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Получить информацию о видео."""
        if not MOVIEPY_AVAILABLE:
            return {"error": "moviepy не установлен"}
        
        try:
            video = VideoFileClip(video_path)
            info = {
                "duration": video.duration,
                "fps": video.fps,
                "size": video.size,
                "resolution": f"{video.size[0]}x{video.size[1]}",
                "has_audio": video.audio is not None,
            }
            video.close()
            return info
        except Exception as e:
            logger.error(f"Ошибка получения информации о видео: {e}")
            return {}
