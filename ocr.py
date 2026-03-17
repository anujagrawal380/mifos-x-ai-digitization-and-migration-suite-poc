"""
ocr.py — Image preprocessing and Tesseract OCR extraction.

Handles skewed scans, low contrast, and mixed handwriting/print.
"""

import cv2
import numpy as np
import pytesseract
from PIL import Image
import io


def preprocess_image(image: Image.Image) -> np.ndarray:
    """
    Enhance scan quality before OCR:
    - Convert to grayscale
    - Deskew (straighten tilted scans)
    - Denoise
    - Adaptive threshold (handles uneven lighting)
    """
    img = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Denoise
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Deskew
    deskewed = _deskew(denoised)

    # Adaptive threshold — works better than global for handwriting
    thresh = cv2.adaptiveThreshold(
        deskewed, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    return thresh


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate image to correct skew using Hough line detection."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

    if lines is None:
        return gray

    angles = []
    for rho, theta in lines[:, 0]:
        angle = (theta - np.pi / 2) * (180 / np.pi)
        if abs(angle) < 45:  # ignore near-vertical lines
            angles.append(angle)

    if not angles:
        return gray

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:  # skip tiny corrections
        return gray

    h, w = gray.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def extract_text(image: Image.Image) -> dict:
    """
    Run Tesseract OCR on the image.
    Returns raw text + per-word confidence scores.
    """
    preprocessed = preprocess_image(image)
    pil_preprocessed = Image.fromarray(preprocessed)

    # Page segmentation mode 6 = uniform block of text
    # OEM 3 = default (LSTM + legacy)
    config = "--psm 6 --oem 3"

    raw_text = pytesseract.image_to_string(pil_preprocessed, config=config)

    # Get per-word confidence
    data = pytesseract.image_to_data(
        pil_preprocessed, config=config,
        output_type=pytesseract.Output.DICT
    )

    words = []
    for i, word in enumerate(data["text"]):
        if word.strip():
            conf = int(data["conf"][i])
            if conf > 0:
                words.append({"word": word, "confidence": conf})

    avg_confidence = (
        sum(w["confidence"] for w in words) / len(words) if words else 0
    )

    return {
        "raw_text": raw_text.strip(),
        "word_count": len(words),
        "avg_ocr_confidence": round(avg_confidence / 100, 2),  # normalize to 0-1
        "low_confidence_words": [w for w in words if w["confidence"] < 60],
    }


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes for passing to vision LLMs."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    return buf.getvalue()
