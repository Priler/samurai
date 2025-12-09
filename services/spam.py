"""
Spam detection service using ML model.

Features:
- Lazy loading of ML models (faster startup)
- Quick substring check before expensive ML inference
"""
from typing import Optional

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_PATH = "ruspam_model/"

# Lazy-loaded model and tokenizer
_tokenizer: Optional[AutoTokenizer] = None
_model: Optional[AutoModelForSequenceClassification] = None

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


def _get_model() -> AutoModelForSequenceClassification:
    """Lazy load model on first use."""
    global _model
    if _model is None:
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH, local_files_only=True)
        _model.eval()  # Set to evaluation mode
    return _model


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

    # ML-based prediction (lazy load models)
    tokenizer = _get_tokenizer()
    model = _get_model()
    
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        predicted_class = torch.argmax(logits, dim=1).item()

    return predicted_class == 1


def preload_model() -> None:
    """
    Preload the ML model (call during startup if you want eager loading).
    Useful if you want to avoid latency on first spam check.
    """
    _get_tokenizer()
    _get_model()
