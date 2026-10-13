"""Page rectification: undo the perspective of photographed documents.

A page shot with a phone is a keystone, not a rotated rectangle: its ruling
lines converge, so no single rotation straightens it. When the page holds a
ruled table, the table's outer frame is a known rectangle seen in perspective;
mapping its four corners back onto a rectangle straightens the whole page.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.logging_config import get_logger
from app.services import cells

log = get_logger(__name__)

# Below this corner displacement (fraction of the page width) the page is
# treated as already straight: warping would only blur it.
_MIN_DISTORTION = 0.002
# A frame leaning more than this is not a keystone we can trust.
_MAX_DISTORTION = 0.12


def _frame_corners(gray: np.ndarray) -> np.ndarray | None:
    """Return the 4 corners (tl, tr, br, bl) of the largest table frame."""
    horizontal, vertical = cells.find_rules(gray)
    boxes = cells.table_boxes(horizontal, vertical)
    if not boxes:
        return None
    x, y, bw, bh = max(boxes, key=lambda b: b[2] * b[3])

    points = cv2.findNonZero(cv2.add(horizontal, vertical)[y : y + bh, x : x + bw])
    if points is None:
        return None
    pts = points.reshape(-1, 2).astype(np.float32) + (x, y)
    sums = pts[:, 0] + pts[:, 1]
    diffs = pts[:, 1] - pts[:, 0]
    return np.array(
        [pts[sums.argmin()], pts[diffs.argmin()], pts[sums.argmax()], pts[diffs.argmax()]],
        dtype=np.float32,
    )


def rectify(image: np.ndarray) -> np.ndarray:
    """Straighten a page using its largest table frame.

    Args:
        image: BGR or grayscale page image.

    Returns:
        The rectified page, or the input unchanged when no table frame is
        found or the page is already straight.
    """
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners = _frame_corners(gray)
    if corners is None:
        return image
    tl, tr, br, bl = corners

    left, right = (tl[0] + bl[0]) / 2, (tr[0] + br[0]) / 2
    top, bottom = (tl[1] + tr[1]) / 2, (bl[1] + br[1]) / 2
    target = np.array(
        [[left, top], [right, top], [right, bottom], [left, bottom]], dtype=np.float32
    )

    h, w = gray.shape[:2]
    distortion = float(np.abs(corners - target).max()) / w
    if distortion < _MIN_DISTORTION or distortion > _MAX_DISTORTION:
        return image

    matrix = cv2.getPerspectiveTransform(corners, target)
    log.info("dewarp.rectify", distortion=round(distortion, 4))
    white = 255 if image.ndim == 2 else (255, 255, 255)
    return cv2.warpPerspective(
        image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=white
    )
