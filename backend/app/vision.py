import asyncio
from collections.abc import Callable
from io import BytesIO
from typing import Any

ModelFn = Callable[[bytes], dict]


def decode_dicom_pixels(data: bytes) -> Any:
    import numpy as np
    import pydicom

    ds = pydicom.dcmread(BytesIO(data))
    arr = ds.pixel_array.astype(np.float32)
    return arr


def _biomedclip_model(data: bytes) -> dict:
    """Zero-shot BiomedCLIP scoring. Lazy: only loads when called."""
    import numpy as np
    import torch
    from transformers import AutoModel, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        "microsoft/BiomedCLIP-PubMedBERT_25k-vit_base_patch16_224"
    )
    model = AutoModel.from_pretrained(
        "microsoft/BiomedCLIP-PubMedBERT_25k-vit_base_patch16_224",
        trust_remote_code=True,
    ).eval()
    pixels = decode_dicom_pixels(data)
    lo, hi = float(pixels.min()), float(pixels.max())
    norm = (pixels - lo) / ((hi - lo) or 1.0)
    gray = (norm * 255).astype("uint8")
    rgb = np.stack([gray] * 3, axis=-1)
    from PIL import Image

    image = Image.fromarray(rgb)
    prompts = [
        "CT scan showing a malignant pulmonary nodule",
        "CT scan showing a normal lung",
    ]
    inputs = processor(text=prompts, images=image, return_tensors="pt")
    with torch.no_grad():
        out = model(**inputs)
        logits = out.logits_per_image.softmax(dim=-1)[0].tolist()
    return {
        "flagged": bool(logits[0] >= 0.5),
        "findings": [
            {"label": "pulmonary nodule", "score": round(float(logits[0]), 3)},
            {"label": "normal lung", "score": round(float(logits[1]), 3)},
        ],
        "model": "biomedclip",
    }


class VisionWorker:
    def __init__(self, model: ModelFn | None = None) -> None:
        self._model = model

    def analyze_sync(self, data: bytes) -> dict:
        if self._model is not None:
            return self._model(data)
        return _biomedclip_model(data)

    async def analyze(self, data: bytes) -> dict:
        return await asyncio.to_thread(self.analyze_sync, data)


_worker: VisionWorker | None = None


def get_vision_worker() -> VisionWorker:
    global _worker
    if _worker is None:
        _worker = VisionWorker()
    return _worker
