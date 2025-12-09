"""
NSFW image classification service using SigLIP model.
"""
from transformers import AutoImageProcessor, SiglipForImageClassification
from PIL import Image
import torch
import numpy as np

# Load model and processor
MODEL_NAME = "prithivMLmods/siglip2-x256-explicit-content"
model = SiglipForImageClassification.from_pretrained(MODEL_NAME)
processor = AutoImageProcessor.from_pretrained(MODEL_NAME)

# ID to Label mapping
ID2LABEL = {
    "0": "Anime Picture",
    "1": "Hentai",
    "2": "Normal",
    "3": "Pornography",
    "4": "Enticing or Sensual"
}


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
    pil_image = Image.fromarray(image).convert("RGB")
    inputs = processor(images=pil_image, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

    prediction = {
        ID2LABEL[str(i)]: round(probs[i], 3) for i in range(len(probs))
    }

    return prediction
