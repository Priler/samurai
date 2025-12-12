"""Test NSFW ONNX model."""
import numpy as np
import onnxruntime as ort
from transformers import AutoImageProcessor
from PIL import Image

ONNX_PATH = "nsfw_model/model.onnx"
PROCESSOR_PATH = "nsfw_model/"

processor = AutoImageProcessor.from_pretrained(PROCESSOR_PATH)
session = ort.InferenceSession(ONNX_PATH, providers=["CPUExecutionProvider"])

ID2LABEL = {
    0: "Anime Picture",
    1: "Hentai", 
    2: "Normal",
    3: "Pornography",
    4: "Enticing or Sensual"
}

# Test with a blank image
test_image = Image.fromarray(np.zeros((256, 256, 3), dtype=np.uint8))
inputs = processor(images=test_image, return_tensors="np")

outputs = session.run(["logits"], {"pixel_values": inputs["pixel_values"]})
logits = outputs[0][0]

# Softmax
probs = np.exp(logits) / np.sum(np.exp(logits))

print("Predictions:")
for i, prob in enumerate(probs):
    print(f"  {ID2LABEL[i]}: {prob:.3f}")