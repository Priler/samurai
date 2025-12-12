"""
NSFW image classification service using SigLIP model.

Features:
- Lazy loading (saves RAM at startup)
- Thumbnail processing (256x256 - model's native size, saves RAM)
"""
from typing import Optional

from PIL import Image
import torch
import numpy as np

MODEL_NAME = "prithivMLmods/siglip2-x256-explicit-content"

# Lazy-loaded model and processor
_model = None
_processor = None

# Model expects 256x256 images - resize to this for RAM savings
TARGET_SIZE = (256, 256)

# ID to Label mapping
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
        _processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    return _processor


def _get_model():
    """Lazy load model on first use."""
    global _model
    if _model is None:
        from transformers import SiglipForImageClassification
        _model = SiglipForImageClassification.from_pretrained(MODEL_NAME)
        _model.eval()
    return _model


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
    # Convert to PIL and resize to model's expected size (saves RAM)
    pil_image = Image.fromarray(image).convert("RGB")
    pil_image = pil_image.resize(TARGET_SIZE, Image.Resampling.LANCZOS)
    
    # Free original array memory
    del image
    
    processor = _get_processor()
    model = _get_model()
    
    inputs = processor(images=pil_image, return_tensors="pt")
    
    # Free PIL image memory
    del pil_image

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()
    
    # Free tensors
    del inputs, outputs, logits

    prediction = {
        ID2LABEL[str(i)]: round(probs[i], 3) for i in range(len(probs))
    }

    return prediction


def unload_model() -> bool:
    """Free memory by unloading model."""
    global _model, _processor
    import gc
    
    if _model is None and _processor is None:
        return False
    
    _model = None
    _processor = None
    gc.collect()
    return True
