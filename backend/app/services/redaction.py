"""Face and number-plate blurring before any photo can be shown (blueprint §6, §13).

Technology (OpenCV 4.14, opencv-python-headless):
- faces: YuNet (cv2.FaceDetectorYN, model backend/models/face_detection_yunet_2023mar.onnx, SHA-256 checked) as the
  main detector, run on the image and on a brightened copy, plus Haar frontal + profile cascades (both directions) as backup
- plates: haarcascade_russian_plate_number + haarcascade_license_plate_rus_16stages
Limitations (documented in docs/PHOTO_PRIVACY.md): YuNet is a modern small CNN but still misses tiny, dark or hidden
faces; the plate cascades are trained on Russian-format plates. At night, at an angle, small or blurred, they MISS faces and plates. That is why a redacted photo
is shown publicly only if the separate AI check also finds no recognisable face or readable plate (see analysis worker).

Fail closed: any error (OpenCV missing, unreadable image, detector not loaded, write failure) raises RedactionError and
no redacted image is produced.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app import config

PAD = 0.25  # enlarge every detected box by 25 % on each side before blurring
MAX_WIDTH = 640  # public photos are at most 640 px wide (blueprint §5)


class RedactionError(Exception):
    pass


@dataclass
class Redaction:
    faces: int
    plates: int
    width: int
    height: int


_detectors = None


def _load():
    global _detectors
    if _detectors is None:
        try:
            import cv2
        except ImportError as err:
            raise RedactionError(f"OpenCV is not installed: {err}")
        names = {
            "face": "haarcascade_frontalface_default.xml",
            "profile": "haarcascade_profileface.xml",
            "plate": "haarcascade_russian_plate_number.xml",
            "plate16": "haarcascade_license_plate_rus_16stages.xml",
        }
        loaded = {}
        for key, name in names.items():
            try:
                c = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / name))
            except Exception as err:  # e.g. OpenCV 5 has no CascadeClassifier: fail closed, never crash
                raise RedactionError(f"detector {name} unavailable in this OpenCV ({type(err).__name__})")
            if c.empty():
                raise RedactionError(f"detector {name} could not be loaded")
            loaded[key] = c
        model = Path(config.YUNET_MODEL)
        try:
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
        except OSError:
            raise RedactionError(f"YuNet face model missing at {model}")
        if digest != config.YUNET_SHA256:
            raise RedactionError("YuNet face model does not match its official checksum")
        try:
            loaded["yunet"] = cv2.FaceDetectorYN.create(str(model), "", (320, 320), config.YUNET_SCORE, 0.3, 5000)
        except Exception as err:
            raise RedactionError(f"YuNet face model could not be loaded ({type(err).__name__})")
        _detectors = (cv2, loaded)
    return _detectors


def detect(image) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    """Face boxes and plate boxes (x, y, w, h). Night photos are contrast-equalised first to help the detectors."""
    cv2, d = _load()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    h, w = gray.shape
    min_face = max(12, w // 60)

    def run(c, img, **kw):
        found = c.detectMultiScale(img, scaleFactor=1.08, minNeighbors=4, **kw)
        return [tuple(int(v) for v in b) for b in (found if len(found) else [])]

    faces = []
    yunet = d["yunet"]
    yunet.setInputSize((w, h))
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)  # brightened copy for dark night photos
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    for img in (image, cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)):
        _, found = yunet.detect(img)
        if found is not None:
            faces += [tuple(int(max(0, v)) for v in f[:4]) for f in found]
    faces += run(d["face"], gray, minSize=(min_face, min_face)) + run(d["profile"], gray, minSize=(min_face, min_face))
    flipped = cv2.flip(gray, 1)  # the profile detector only finds faces turned one way
    faces += [(w - x - bw, y, bw, bh) for x, y, bw, bh in run(d["profile"], flipped, minSize=(min_face, min_face))]
    plates = run(d["plate"], gray, minSize=(24, 8)) + run(d["plate16"], gray, minSize=(24, 8))
    return faces, plates


def blur_regions(image, boxes) -> None:
    """Blur the boxes in place, heavily (pixelate, then Gaussian), with padding around each box."""
    cv2, _ = _load()
    h, w = image.shape[:2]
    for x, y, bw, bh in boxes:
        px, py = int(bw * PAD), int(bh * PAD)
        x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(w, x + bw + px), min(h, y + bh + py)
        if x1 <= x0 or y1 <= y0:
            continue
        roi = image[y0:y1, x0:x1]
        small = cv2.resize(roi, (max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)), interpolation=cv2.INTER_LINEAR)
        roi = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        image[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (0, 0), sigmaX=max(3, (x1 - x0) / 8))


def redact_file(src: Path, dest: Path, detector=None) -> Redaction:
    """Read src, blur faces and plates, write dest (JPEG, ≤640 px, no EXIF/GPS metadata). Raises RedactionError
    for every failure, so callers can always fail closed."""
    try:
        return _redact(src, dest, detector)
    except RedactionError:
        raise
    except Exception as err:
        raise RedactionError(f"redaction failed: {type(err).__name__}")


def _redact(src: Path, dest: Path, detector=None) -> Redaction:
    cv2, _ = _load()
    data = None
    try:
        import numpy as np
        data = np.fromfile(str(src), dtype=np.uint8)
    except (OSError, ValueError) as err:
        raise RedactionError(f"original photo cannot be read: {err}")
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data is not None and data.size else None
    if image is None:
        raise RedactionError("original photo is not a readable image")
    h, w = image.shape[:2]
    if w > MAX_WIDTH:
        image = cv2.resize(image, (MAX_WIDTH, round(h * MAX_WIDTH / w)), interpolation=cv2.INTER_AREA)
    try:
        faces, plates = (detector or detect)(image)
    except RedactionError:
        raise
    except Exception as err:  # any detector failure: fail closed
        raise RedactionError(f"detection failed: {type(err).__name__}")
    blur_regions(image, faces + plates)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])  # re-encoding drops EXIF (incl. phone GPS)
    if not ok:
        raise RedactionError("redacted photo could not be encoded")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(buf.tobytes())
    tmp.replace(dest)  # appears only when complete
    return Redaction(faces=len(faces), plates=len(plates), width=image.shape[1], height=image.shape[0])
