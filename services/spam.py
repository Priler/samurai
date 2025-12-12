"""
Spam detection service using ONNX model.

Features:
- Lazy loading of ONNX model (faster startup)
- Quick substring check before expensive ML inference
- Lower RAM usage (hopefully) with ONNX
"""
from typing import Optional

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

MODEL_PATH = "ruspam_model/"
ONNX_PATH = "ruspam_model/model.onnx"

# Lazy-loaded model and tokenizer
_tokenizer: Optional[AutoTokenizer] = None
_session: Optional[ort.InferenceSession] = None

# Known spam substrings to check first (faster than ML)
SPAM_SUBSTRINGS = [
    "official_vpnbot",
    "rkt_vpn_bot",
    "vpnbot",
    "vpn_bot"
]

# Precompute lowercase versions for faster matching
_SPAM_SUBSTRINGS_LOWER = [s.lower() for s in SPAM_SUBSTRINGS]


def _get_tokenizer() -> AutoTokenizer:
    """Lazy load tokenizer on first use."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
    return _tokenizer


def _get_session() -> ort.InferenceSession:
    """Lazy load ONNX session on first use."""
    global _session
    if _session is None:
        # Use CPU provider, limit threads for lower memory
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(ONNX_PATH, opts, providers=["CPUExecutionProvider"])
    return _session


def predict(text: str) -> bool:
    """
    Predict if text is spam.

    Args:
        text: Text to check for spam

    Returns:
        True if spam, False otherwise
    """
    # Quick check for known spam patterns (O(n) string search)
    text_lower = text.lower()
    if any(sub in text_lower for sub in _SPAM_SUBSTRINGS_LOWER):
        return True

    # ONNX inference (lazy load on first call)
    tokenizer = _get_tokenizer()
    session = _get_session()
    
    inputs = tokenizer(text, return_tensors="np", truncation=True, max_length=256)
    
    outputs = session.run(
        ["logits"],
        {
            "input_ids": inputs["input_ids"],
            "attention_mask": inputs["attention_mask"]
        }
    )
    
    logits = outputs[0]
    predicted_class = np.argmax(logits, axis=1)[0]

    return predicted_class == 1


def preload_model() -> None:
    """
    Preload the ONNX model (call during startup if you want eager loading).
    Useful if you want to avoid latency on first spam check.
    """
    _get_tokenizer()
    _get_session()
