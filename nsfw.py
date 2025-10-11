from transformers import AutoImageProcessor, SiglipForImageClassification
from PIL import Image
import torch
# import numpy as np

# Load model and processor
model_name = "prithivMLmods/siglip2-x256-explicit-content"  # Replace with your model path if needed
model = SiglipForImageClassification.from_pretrained(model_name)
processor = AutoImageProcessor.from_pretrained(model_name)

# ID to Label mapping
id2label = {
    "0": "Anime Picture",
    "1": "Hentai",
    "2": "Normal",
    "3": "Pornography",
    "4": "Enticing or Sensual"
}

# nsfw_test_images = [
#     ["711e91a37130db5dc6c23722b88696d5.jpg", False],
#     ["photo_2025-10-10_22-33-27.jpg", True],
#     ["photo_2025-10-11_00-03-44.jpg", True],
#     ["photo_2025-10-10_22-33-26.jpg", True],
#     ["256x256.png", False],
#     ["cf111925-a8e2-43db-8db0-f295a901161a.jpg", False],
#     ["Layer 538.png", False],
#     ["photo_2025-10-11_03-04-17.jpg", True],
# ]

# result format: {'Anime Picture': 0.835, 'Hentai': 0.015, 'Normal': 0.149, 'Pornography': 0.0, 'Enticing or Sensual': 0.0}
def classify_explicit_content(image):
    image = Image.fromarray(image).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

    prediction = {
        id2label[str(i)]: round(probs[i], 3) for i in range(len(probs))
    }

    return prediction

# Gradio Interface
import gradio as gr
iface = gr.Interface(
    fn=classify_explicit_content,
    inputs=gr.Image(type="numpy"),
    outputs=gr.Label(num_top_classes=5, label="Predicted Content Type"),
    title="siglip2-x256-explicit-content",
    description="Classifies images into explicit, suggestive, or safe categories (e.g., Hentai, Pornography, Normal)."
)

if __name__ == "__main__":
    iface.launch()
