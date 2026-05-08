"""
Thin wrapper around InsightFace's FaceAnalysis.
Handles both face detection and 512D embedding in one call.
Models are auto-downloaded to ~/.insightface/models/ on first run.
"""
import numpy as np
from insightface.app import FaceAnalysis


class FaceEngine:
    def __init__(self, model_name: str = "buffalo_sc", det_size: tuple = (640, 480)):
        # ctx_id=-1 → CPU; providers kwarg forces CPU ONNX backend
        self.app = FaceAnalysis(
            name=model_name,
            providers=["CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=-1, det_size=det_size)

    def process(self, frame: np.ndarray) -> list:
        """
        Run detection + embedding on a BGR frame.
        Returns list of insightface Face objects, each with:
            .bbox            – [x1, y1, x2, y2] float
            .kps             – 5×2 keypoints
            .normed_embedding – 512D L2-normalized ndarray
            .det_score       – detection confidence
        """
        return self.app.get(frame)
