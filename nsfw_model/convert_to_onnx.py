"""Convert NSFW model from HuggingFace to ONNX format."""
import torch
from transformers import AutoImageProcessor, SiglipForImageClassification
from PIL import Image
import numpy as np

MODEL_NAME = "prithivMLmods/siglip2-x256-explicit-content"
ONNX_PATH = "nsfw_model/model.onnx"

# Create output directory
import os
os.makedirs("nsfw_model", exist_ok=True)

print("Loading model from HuggingFace...")
processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
model = SiglipForImageClassification.from_pretrained(MODEL_NAME)
model.eval()

# Save processor locally (needed for inference)
processor.save_pretrained("nsfw_model")

# Create dummy input (256x256 RGB image)
dummy_image = Image.fromarray(np.zeros((256, 256, 3), dtype=np.uint8))
inputs = processor(images=dummy_image, return_tensors="pt")

print("Exporting to ONNX...")
torch.onnx.export(
    model,
    (inputs["pixel_values"],),
    ONNX_PATH,
    input_names=["pixel_values"],
    output_names=["logits"],
    dynamic_axes={
        "pixel_values": {0: "batch"},
        "logits": {0: "batch"}
    },
    opset_version=14
)

print(f"✅ Model exported to {ONNX_PATH}")
print(f"✅ Processor saved to nsfw_model/")