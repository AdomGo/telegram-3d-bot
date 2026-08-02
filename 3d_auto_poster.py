import requests
import os
import base64
import time

TOKEN = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
CHAT_ID = "@TREEDSTL"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print(f"🔑 Проверка ключа: {'ЕСТЬ' if GEMINI_API_KEY else 'НЕТ'}")

def test_gemini():
    try:
        img_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/Dragon_3D_model.jpg/640px-Dragon_3D_model.jpg"
        img_data = requests.get(img_url, timeout=10).content
        img_b64 = base64.b64encode(img_data).decode('utf-8')
        
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        prompt = "Опиши эту картинку на русском языке, кратко, 100 символов."
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        
        if 'candidates' in data and len(data['candidates']) > 0:
            text = data['candidates'][0]['content']['parts'][0]['text']
            print(f"✅ Gemini ответил: {text}")
        else:
            print(f"❌ Gemini не вернул ответ: {data}")
    except Exception as e:
        print(f"❌ Ошибка Gemini: {e}")

if __name__ == "__main__":
    test_gemini()
