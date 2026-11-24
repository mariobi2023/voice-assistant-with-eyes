"""Image enhancement: better pictures before OCR and YOLO (bonus feature).

Two fixes, both plain OpenCV (no AI model):
  1. Dark frame  (mean brightness < DARK_MAX):
       CLAHE  = local contrast boost on the lightness channel only (colours are kept), then
       gamma  = lifts the dark tones more than the bright ones, so the frame becomes brighter
                without turning the light parts white.
  2. Slightly blurry frame (SHARPNESS_MIN <= sharpness < SLIGHTLY_BLURRY_MAX):
       unsharp mask = frame + AMOUNT x (frame - blurred frame): edges get stronger, so
                      letters are easier for OCR to read.

Every function returns a NEW image; the input frame is never changed.
Test on one photo:   python -m app.enhance path/to/photo.jpg   (writes photo_enhanced.jpg)
"""
import math

import cv2
import numpy as np

from app import config


def is_dark(brightness):
    """True if the frame's mean brightness (0-255) is below DARK_MAX."""
    return brightness < config.DARK_MAX


def is_slightly_blurry(sharpness):
    """True if the frame passed the sharpness check, but only just (worth sharpening)."""
    return config.SHARPNESS_MIN <= sharpness < config.SLIGHTLY_BLURRY_MAX


def apply_clahe(frame):
    """CLAHE on the L (lightness) channel of the LAB colour space.
    CLAHE boosts contrast tile by tile, so a dark corner gets brighter even if the
    rest of the frame is lit. The clip limit stops it from boosting noise too much."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=config.CLAHE_CLIP_LIMIT,
                            tileGridSize=(config.CLAHE_TILE_GRID, config.CLAHE_TILE_GRID))
    lab = cv2.merge((clahe.apply(lightness), a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def choose_gamma(brightness):
    """Pick the gamma that moves the mean brightness to about GAMMA_TARGET_BRIGHTNESS.
    output = 255 * (input / 255) ** gamma; gamma < 1 brightens. Solving for the mean gives
    gamma = log(target/255) / log(mean/255). Clamped so a nearly black frame is not overdone."""
    mean = min(max(brightness, 1.0), 254.0) / 255  # avoid log(0) and log(1)
    gamma = math.log(config.GAMMA_TARGET_BRIGHTNESS / 255) / math.log(mean)
    return min(max(gamma, config.GAMMA_MIN), 1.0)  # never darken (gamma > 1)


def apply_gamma(frame, gamma):
    """Gamma correction with a lookup table (256 values computed once, then applied to every pixel)."""
    table = (((np.arange(256) / 255.0) ** gamma) * 255).round().astype(np.uint8)
    return cv2.LUT(frame, table)


def brighten(frame):
    """Dark frame fix: CLAHE first (local contrast), then gamma (overall brightness)."""
    contrasted = apply_clahe(frame)
    brightness = float(cv2.cvtColor(contrasted, cv2.COLOR_BGR2GRAY).mean())
    return apply_gamma(contrasted, choose_gamma(brightness))


def sharpen(frame):
    """Mild unsharp mask: subtract a blurred copy to strengthen the edges.
    result = (1 + amount) * frame - amount * blurred"""
    blurred = cv2.GaussianBlur(frame, (0, 0), config.UNSHARP_SIGMA)
    amount = config.UNSHARP_AMOUNT
    return cv2.addWeighted(frame, 1 + amount, blurred, -amount, 0)


def main():
    """Try the enhancement on one photo and save the result next to it."""
    import sys
    from pathlib import Path

    path = Path(sys.argv[1])
    frame = cv2.imread(str(path))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    print(f"brightness {brightness:.0f} (dark below {config.DARK_MAX:.0f})")
    if is_dark(brightness):
        frame = brighten(frame)
        print("dark → brightened (CLAHE + gamma)")
    sharpness = float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    print(f"sharpness {sharpness:.0f}")
    if is_slightly_blurry(sharpness):
        frame = sharpen(frame)
        print("slightly blurry → sharpened (unsharp mask)")
    out = path.with_name(path.stem + "_enhanced.jpg")
    cv2.imwrite(str(out), frame)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
