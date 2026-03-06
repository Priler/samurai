"""
NSFW image classification service using SigLIP model.

Features:
- Lazy loading (saves RAM at startup)
- Thumbnail processing (256x256 - model's native size, saves RAM)
- Auto-unload after TTL to save RAM
"""
from typing import Optional
import logging
import time
import gc

from PIL import Image
import torch
import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "prithivMLmods/siglip2-x256-explicit-content"

# lazy-loaded model and processor
_model = None
_processor = None
_last_used: float = 0.0  # timestamp of last usage

# model expects 256x256 images - resize to this for RAM savings
TARGET_SIZE = (256, 256)

# ID to label mapping
ID2LABEL = {
    "0": "Anime Picture",
    "1": "Hentai",
    "2": "Normal",
    "3": "Pornography",
    "4": "Enticing or Sensual"
}


def _get_processor():
    """Lazy load processor on first use."""
    global _processor
    if _processor is None:
        from transformers import AutoImageProcessor
        _processor = AutoImageProcessor.from_pretrained(MODEL_NAME, use_fast=False)
    return _processor


def _get_model():
    """Lazy load model on first use."""
    global _model
    if _model is None:
        from transformers import SiglipForImageClassification
        _model = SiglipForImageClassification.from_pretrained(
            MODEL_NAME, low_cpu_mem_usage=False, device_map=None
        )
        _model.eval()
    return _model


def _touch() -> None:
    """Update last used timestamp."""
    global _last_used
    _last_used = time.time()


def _force_reload() -> None:
    """Force full model reload, clearing corrupted torch state."""
    global _model, _processor

    logger.warning("Forcing full NSFW model reload (torch state recovery)")

    _model = None
    _processor = None

    # clear torch internal caches that accumulate over load/unload cycles
    torch.clear_autocast_cache()
    if hasattr(torch._C, '_jit_clear_class_registry'):
        torch._C._jit_clear_class_registry()
    if hasattr(torch, 'compiler') and hasattr(torch.compiler, 'reset'):
        torch.compiler.reset()
    elif hasattr(torch, '_dynamo'):
        try:
            torch._dynamo.reset()
        except Exception:
            pass

    gc.collect()

    # reload fresh
    _get_processor()
    _get_model()


def classify_explicit_content(image: np.ndarray) -> dict[str, float]:
    """
    Classify image for explicit content.

    Args:
        image: Image as numpy array

    Returns:
        Dictionary with prediction probabilities for each category:
        - 'Anime Picture'
        - 'Hentai'
        - 'Normal'
        - 'Pornography'
        - 'Enticing or Sensual'
    """
    # convert to PIL and resize (saves RAM)
    pil_image = Image.fromarray(image).convert("RGB")
    pil_image = pil_image.resize(TARGET_SIZE, Image.Resampling.LANCZOS)

    # free original array memory
    del image

    result = _run_inference(pil_image)
    if result is not None:
        return result

    # torch state is corrupted - force reload and retry once
    logger.warning("NSFW inference failed, attempting recovery...")
    try:
        _force_reload()
    except Exception as e:
        logger.error(f"NSFW model reload failed: {e}, returning safe fallback")
        return {v: 0.0 for v in ID2LABEL.values()}

    result = _run_inference(pil_image)
    if result is not None:
        return result

    logger.error("NSFW inference failed after recovery, returning safe fallback")
    return {v: 0.0 for v in ID2LABEL.values()}


def _run_inference(pil_image: Image.Image) -> Optional[dict[str, float]]:
    """Run model inference, returns None on torch device errors."""
    try:
        processor = _get_processor()
        model = _get_model()
        _touch()

        inputs = processor(images=pil_image, return_tensors="pt")

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

        del inputs, outputs, logits

        return {
            ID2LABEL[str(i)]: round(probs[i], 3) for i in range(len(probs))
        }
    except RuntimeError as e:
        if "meta" in str(e) or "expected device" in str(e).lower():
            return None
        raise


def unload_model() -> bool:
    """Free memory by unloading model."""
    global _model, _processor, _last_used

    if _model is None and _processor is None:
        return False

    _model = None
    _processor = None
    _last_used = 0.0

    # clear torch dispatch caches to prevent meta device corruption on next load
    torch.clear_autocast_cache()
    if hasattr(torch, 'compiler') and hasattr(torch.compiler, 'reset'):
        torch.compiler.reset()
    elif hasattr(torch, '_dynamo'):
        try:
            torch._dynamo.reset()
        except Exception:
            pass

    gc.collect()
    return True


def is_loaded() -> bool:
    """Check if model is currently loaded."""
    return _model is not None


def get_last_used() -> float:
    """Get timestamp of last model usage."""
    return _last_used
