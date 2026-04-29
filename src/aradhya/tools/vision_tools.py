"""Screen capture and OCR tools for the agent loop.

These tools give Aradhya the ability to "see" what's on the screen —
capturing screenshots and extracting text via OCR.  The agent uses
these to monitor for notifications, check download progress, or read
any on-screen content.

Dependencies:
- ``mss`` or ``Pillow`` for screen capture (falls back to PowerShell)
- ``pytesseract`` for OCR (optional — falls back to Windows OCR API)
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import time
from pathlib import Path

from loguru import logger

from src.aradhya.tools.tool_registry import tool_definition


def _capture_with_mss(output_path: str, region: dict | None = None) -> bool:
    """Try to capture using mss (fast, cross-platform)."""
    try:
        import mss  # type: ignore[import-untyped]

        with mss.mss() as sct:
            if region:
                monitor = {
                    "left": region.get("x", 0),
                    "top": region.get("y", 0),
                    "width": region.get("width", 800),
                    "height": region.get("height", 600),
                }
            else:
                monitor = sct.monitors[0]  # Full virtual screen

            screenshot = sct.grab(monitor)
            # Save as PNG
            from mss.tools import to_png
            to_png(screenshot.rgb, screenshot.size, output=output_path)
            return True
    except ImportError:
        return False
    except Exception as error:
        logger.debug("mss capture failed: {}", error)
        return False


def _capture_with_pillow(output_path: str, region: tuple | None = None) -> bool:
    """Try to capture using Pillow's ImageGrab."""
    try:
        from PIL import ImageGrab  # type: ignore[import-untyped]

        if region:
            screenshot = ImageGrab.grab(bbox=region)
        else:
            screenshot = ImageGrab.grab(all_screens=True)
        screenshot.save(output_path, "PNG")
        return True
    except ImportError:
        return False
    except Exception as error:
        logger.debug("Pillow capture failed: {}", error)
        return False


def _capture_with_powershell(output_path: str) -> bool:
    """Fallback: use PowerShell to take a screenshot."""
    if os.name != "nt":
        return False
    try:
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$screen = [System.Windows.Forms.Screen]::PrimaryScreen; "
            "$bitmap = New-Object System.Drawing.Bitmap("
            "$screen.Bounds.Width, $screen.Bounds.Height); "
            "$graphics = [System.Drawing.Graphics]::FromImage($bitmap); "
            "$graphics.CopyFromScreen($screen.Bounds.Location, "
            "[System.Drawing.Point]::Empty, $screen.Bounds.Size); "
            f"$bitmap.Save('{output_path}'); "
            "$graphics.Dispose(); $bitmap.Dispose()"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0 and Path(output_path).is_file()
    except Exception as error:
        logger.debug("PowerShell capture failed: {}", error)
        return False


def _ocr_with_pytesseract(image_path: str) -> str | None:
    """Try OCR using pytesseract."""
    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except ImportError:
        return None
    except Exception as error:
        logger.debug("pytesseract OCR failed: {}", error)
        return None


def _ocr_with_windows_api(image_path: str) -> str | None:
    """Fallback: use Windows OCR via PowerShell."""
    if os.name != "nt":
        return None
    try:
        ps_script = (
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
            "$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]; "
            "$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]; "
            "$null = [Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime]; "
            f"$file = [Windows.Storage.StorageFile]::GetFileFromPathAsync('{image_path}').GetAwaiter().GetResult(); "
            "$stream = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read).GetAwaiter().GetResult(); "
            "$decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream).GetAwaiter().GetResult(); "
            "$bitmap = $decoder.GetSoftwareBitmapAsync().GetAwaiter().GetResult(); "
            "$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); "
            "$result = $engine.RecognizeAsync($bitmap).GetAwaiter().GetResult(); "
            "Write-Output $result.Text"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception as error:
        logger.debug("Windows OCR failed: {}", error)
        return None


@tool_definition(
    name="screen_capture",
    description=(
        "Take a screenshot of the current screen and save it. "
        "Returns the path to the saved image file. "
        "Use this to see what's on screen — download progress, "
        "notifications, application state, etc."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": (
                    "Optional filename for the screenshot. "
                    "Defaults to a timestamped name in the temp directory."
                ),
            },
            "region": {
                "type": "object",
                "description": (
                    "Optional region to capture: {x, y, width, height}. "
                    "Omit to capture the full screen."
                ),
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
            },
        },
    },
)
def screen_capture(filename: str = "", region: dict | None = None) -> str:
    """Capture the screen and return the path to the saved image."""
    if not filename:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        filename = str(Path(tempfile.gettempdir()) / f"aradhya_screen_{stamp}.png")

    # Ensure parent directory exists
    Path(filename).parent.mkdir(parents=True, exist_ok=True)

    # Try capture methods in order of preference
    if _capture_with_mss(filename, region):
        return f"Screenshot saved to {filename}"

    pillow_region = None
    if region:
        pillow_region = (
            region.get("x", 0),
            region.get("y", 0),
            region.get("x", 0) + region.get("width", 800),
            region.get("y", 0) + region.get("height", 600),
        )
    if _capture_with_pillow(filename, pillow_region):
        return f"Screenshot saved to {filename}"

    if _capture_with_powershell(filename):
        return f"Screenshot saved to {filename} (via PowerShell)"

    return (
        "Failed to capture screen. Install one of: "
        "pip install mss  OR  pip install Pillow"
    )


@tool_definition(
    name="screen_read_text",
    description=(
        "Capture the screen and extract all visible text using OCR. "
        "Returns the text content visible on screen. "
        "Use this to read notifications, check application state, "
        "or monitor for specific text appearing on screen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "region": {
                "type": "object",
                "description": (
                    "Optional region to OCR: {x, y, width, height}. "
                    "Omit to read the full screen."
                ),
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
            },
        },
    },
)
def screen_read_text(region: dict | None = None) -> str:
    """Capture screen and extract text via OCR."""
    # First, capture the screen
    stamp = time.strftime("%Y%m%d_%H%M%S")
    temp_path = str(Path(tempfile.gettempdir()) / f"aradhya_ocr_{stamp}.png")

    captured = False
    if _capture_with_mss(temp_path, region):
        captured = True
    elif _capture_with_pillow(
        temp_path,
        (
            region.get("x", 0),
            region.get("y", 0),
            region.get("x", 0) + region.get("width", 800),
            region.get("y", 0) + region.get("height", 600),
        ) if region else None,
    ):
        captured = True
    elif _capture_with_powershell(temp_path):
        captured = True

    if not captured:
        return "Failed to capture screen for OCR."

    # Try OCR methods
    text = _ocr_with_pytesseract(temp_path)
    if text:
        # Clean up temp file
        try:
            Path(temp_path).unlink()
        except OSError:
            pass
        return f"Screen text:\n{text[:4000]}"

    text = _ocr_with_windows_api(temp_path)
    if text:
        try:
            Path(temp_path).unlink()
        except OSError:
            pass
        return f"Screen text:\n{text[:4000]}"

    return (
        f"Screen captured to {temp_path} but OCR failed. "
        "Install pytesseract for OCR: pip install pytesseract  "
        "(also needs Tesseract-OCR installed on the system)"
    )


ALL_VISION_TOOLS = [screen_capture, screen_read_text]
