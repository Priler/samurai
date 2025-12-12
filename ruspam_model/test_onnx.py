"""Test ONNX model."""
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

MODEL_PATH = "./"
ONNX_PATH = "./model.onnx"

# Load tokenizer and ONNX session
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
session = ort.InferenceSession(ONNX_PATH, providers=["CPUExecutionProvider"])

# Test messages
test_messages = [
    "Привет, как дела?",
    "Заработок в интернете! Пиши в лс!",
    "Кто хочет в нашу команду? Пассивный доход!",
]

for text in test_messages:
    inputs = tokenizer(text, return_tensors="np", truncation=True, max_length=256)
    outputs = session.run(
        ["logits"],
        {
            "input_ids": inputs["input_ids"],
            "attention_mask": inputs["attention_mask"]
        }
    )
    logits = outputs[0]
    predicted = np.argmax(logits, axis=1)[0]
    label = "SPAM" if predicted == 1 else "OK"
    print(f"[{label}] {text}")