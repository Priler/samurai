"""
NSFW image classification service using ONNX model.

Features:
- Lazy loading (saves RAM at startup)
- Thumbnail processing (256x256 - model's native size, saves RAM)
- ONNX Runtime for lower memory usage
"""
from typing import Optional

import numpy as np
import onnxruntime as ort
from PIL import Image
from transformers import AutoImageProcessor

MODEL_PATH = "nsfw_model/"
ONNX_PATH = "nsfw_model/model.onnx"

# Lazy-loaded model and processor
_session: Optional[ort.InferenceSession] = None
_processor = None

# Model expects 256x256 images - resize to this for RAM savings
TARGET_SIZE = (256, 256)

# ID to Label mapping
ID2LABEL = {
    0: "Anime Picture",
    1: "Hentai",
    2: "Normal",
    3: "Pornography",
    4: "Enticing or Sensual"
}


def _get_processor():
    """Lazy load processor on first use."""
    global _processor
    if _processor is None:
        _processor = AutoImageProcessor.from_pretrained(MODEL_PATH, local_files_only=True)
    return _processor


def _get_session() -> ort.InferenceSession:
    """Lazy load ONNX session on first use."""
    global _session
    if _session is None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(ONNX_PATH, opts, providers=["CPUExecutionProvider"])
    return _session


def _softmax(x: np.ndarray) -> np.ndarray:
    """Compute softmax values."""
    exp_x = np.exp(x - np.max(x))  # Subtract max for numerical stability
    return exp_x / exp_x.sum()


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
    session = _get_session()
    
    inputs = processor(images=pil_image, return_tensors="np")
    
    # Free PIL image memory
    del pil_image

    outputs = session.run(["logits"], {"pixel_values": inputs["pixel_values"]})
    logits = outputs[0][0]
    
    # Apply softmax to get probabilities
    probs = _softmax(logits)
    
    # Free intermediate data
    del inputs, outputs, logits

    prediction = {
        ID2LABEL[i]: round(float(probs[i]), 3) for i in range(len(probs))
    }

    return prediction


def unload_model() -> bool:
    """Free memory by unloading model."""
    global _session, _processor
    import gc
    
    if _session is None and _processor is None:
        return False
    
    _session = None
    _processor = None
    gc.collect()
    return True
