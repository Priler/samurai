from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_path = "ruspam_model/"
tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True)

def predict(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        predicted_class = torch.argmax(logits, dim=1).item()
    return True if predicted_class == 1 else False

print("Результат: " , predict("Привет, нужны 2 человека ,все с телефона, или  компьютера. От 220 $ в день. Удалённая занятость , пиши + в лс"))