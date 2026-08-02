import requests
from bs4 import BeautifulSoup
import time
import os
import schedule
import threading
import random
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
CHAT_ID = "@TREEDSTL"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    
    def log_message(self, format, *args):
        return

def generate_description_with_gemini(img_url, title):
    """Генерирует описание по картинке через Google Gemini API"""
    try:
        # Сначала скачиваем картинку в base64
        img_data = requests.get(img_url, timeout=15).content
        img_b64 = base64.b64encode(img_data).decode('utf-8')
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        prompt = f"""Ты — эксперт по 3D-печати. Посмотри на эту картинку.
Напиши красивое описание для Telegram-канала на русском языке для этой модели.
Название модели: {title}

Опиши:
1. Что это за модель (кратко)
2. Для чего она нужна
3. Пару советов по печати (материал, слой, поддержки)

Используй эмодзи, не пиши лишнего. Максимум 500 символов."""
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=20)
        data = response.json()
        
        if 'candidates' in data and len(data['candidates']) > 0:
            text = data['candidates'][0]['content']['parts'][0]['text']
            return text.strip()
        else:
            return f"📦 *{title}*\n\nОтличная 3D-модель. Рекомендуется для печати."
    except Exception as e:
        print(f"Gemini error: {e}")
        return f"📦 *{title}*\n\nМодель для 3D-печати. Скачайте STL-файл."

def get_makerworld_model():
    url = "https://makerworld.com/en/models/trending"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем ссылки на модели
        model_links = [a for a in soup.find_all("a", href=True) if "/models/" in a["href"] and not a["href"].endswith("/comments")]
        if not model_links:
            return None
        
        model_url = None
        for a in model_links:
            href = a["href"]
            if href.startswith("/"): 
                href = "https://makerworld.com" + href
            if not is_already_posted(href):
                model_url = href
                break
        
        if not model_url:
            return None
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        
        # Название
        title_elem = detail_soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else "3D Model"
        
        # Картинка
        img_url = None
        og_image = detail_soup.find("meta", property="og:image")
        if og_image:
            img_url = og_image["content"]
        else:
            img_tags = detail_soup.find_all("img")
            for img in img_tags:
                src = img.get("src", "")
                if "makerworld.com" in src:
                    img_url = src
                    break
        
        # Описание через Gemini
        description = generate_description_with_gemini(img_url, title) if img_url else f"📦 *{title}*\n\nМодель для 3D-печати."
        return {"title": title, "url": model_url, "description": description, "image": img_url}
    except Exception as e:
        print(f"MakerWorld error: {e}")
        return None

def get_printables_model():
    url = "https://www.printables.com/model?period=day&sort=trending"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        model_links = [a for a in soup.find_all("a", href=True) if a["href"].startswith("/model/") and not a["href"].endswith("/comments")]
        if not model_links:
            return None
        
        model_url = None
        for a in model_links:
            test_url = "https://www.printables.com" + a["href"]
            if not is_already_posted(test_url):
                model_url = test_url
                break
        
        if not model_url:
            return None
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        title = detail_soup.find("h1").get_text(strip=True) if detail_soup.find("h1") else "3D Model"
        
        img_url = None
        img_tags = detail_soup.find_all("img")
        for img in img_tags:
            src = img.get("src", "")
            if "media.printables.com" in src:
                if "/thumbs/" in src:
                    src = src.replace("/thumbs/render/", "/media/").replace("/thumbs/model/", "/media/")
                    import re
                    src = re.sub(r"_thumb_.*?\.", ".", src)
                img_url = src
                break
        
        if not img_url:
            og_image = detail_soup.find("meta", property="og:image")
            if og_image:
                img_url = og_image["content"]
        
        description = generate_description_with_gemini(img_url, title) if img_url else f"📦 *{title}*\n\nМодель для 3D-печати."
        return {"title": title, "url": model_url, "description": description, "image": img_url}
    except Exception as e:
        print(f"Printables error: {e}")
        return None

def get_thingiverse_model():
    url = "https://www.thingiverse.com/explore/popular?page=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        model_links = [a for a in soup.find_all("a", href=True) if "/thing:" in a["href"]]
        if not model_links:
            return None
        
        unique_urls = []
        for a in model_links:
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.thingiverse.com" + href
            if href not in unique_urls:
                unique_urls.append(href)
        
        model_url = None
        for test_url in unique_urls:
            if not is_already_posted(test_url):
                model_url = test_url
                break
        
        if not model_url:
            return None
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        title = detail_soup.find("h1").get_text(strip=True) if detail_soup.find("h1") else "3D Model"
        
        img_url = None
        og_image = detail_soup.find("meta", property="og:image")
        if og_image:
            img_url = og_image["content"]
            if "/renders/" in img_url:
                img_url = img_url.replace("/card/", "/large/").replace("/thumb/", "/large/")
        else:
            img_tags = detail_soup.find_all("img")
            for img in img_tags:
                src = img.get("src", "")
                if "cdn.thingiverse.com" in src:
                    img_url = src.replace("/card/", "/large/").replace("/thumb/", "/large/")
                    break
        
        description = generate_description_with_gemini(img_url, title) if img_url else f"📦 *{title}*\n\nМодель для 3D-печати."
        return {"title": title, "url": model_url, "description": description, "image": img_url}
    except Exception as e:
        print(f"Thingiverse error: {e}")
        return None

def is_already_posted(url):
    history_file = "posted_models.txt"
    if not os.path.exists(history_file):
        return False
    with open(history_file, "r") as f:
        posted = f.read().splitlines()
    return url in posted

def mark_as_posted(url):
    history_file = "posted_models.txt"
    with open(history_file, "a") as f:
        f.write(url + "\n")

def download_file(url, filename):
    headers = {"User-Agent": "Mozilla/5.0"}
    filename = "".join([c for c in filename if c.isalnum() or c in (".", "_", "-")]).strip()
    try:
        if not os.path.exists("Downloads"):
            os.makedirs("Downloads")
        r = requests.get(url, headers=headers, stream=True)
        path = os.path.join("Downloads", filename)
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return path
    except Exception as e:
        print(f"Download error: {e}")
        return None

def post_to_telegram(model):
    if not model:
        print("No model found to post.")
        return
    if is_already_posted(model["url"]):
        print(f"Model {model['url']} already posted. Skipping.")
        return None

    caption = model["description"]
    
    # 1. Сначала скачиваем фото локально
    img_path = None
    if model["image"]:
        img_filename = f"img_{int(time.time())}.jpg"
        img_path = download_file(model["image"], img_filename)

    # 2. Отправляем фото (как файл, а не как ссылку)
    if img_path:
        with open(img_path, "rb") as f:
            url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
            res = requests.post(url, data=data, files=files).json()
            if res.get("ok"):
                print("✅ Фото отправлено")
            else:
                print(f"❌ Ошибка фото: {res.text}")
                return
        # Удаляем временный файл
        if os.path.exists(img_path):
            os.remove(img_path)
    else:
        # Если фото нет — отправляем только текст
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "Markdown"}
        res = requests.post(url, data=data).json()
        if not res.get("ok"):
            print(f"❌ Ошибка текста: {res.text}")
            return

    # 3. Скачиваем и отправляем STL/ZIP
    file_url = None
    if "printables.com" in model["url"]:
        model_id = model["url"].split("/")[-1].split("-")[0]
        file_url = f"https://www.printables.com/model/{model_id}/download"
    elif "thingiverse.com" in model["url"]:
        thing_id = model["url"].split(":")[-1]
        file_url = f"https://www.thingiverse.com/thing:{thing_id}/zip"
    elif "makerworld.com" in model["url"]:
        # Для MakerWorld попробуем найти ZIP или STL на странице
        detail_res = requests.get(model["url"], headers={"User-Agent": "Mozilla/5.0"})
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        download_links = [a for a in detail_soup.find_all("a", href=True) if ".stl" in a["href"] or "download" in a["href"].lower()]
        if download_links:
            file_url = download_links[0]["href"]
            if not file_url.startswith("http"):
                file_url = "https://makerworld.com" + file_url

    if file_url:
        file_path = download_file(file_url, f"{model['title'][:30]}.zip")
        if file_path and os.path.getsize(file_path) < 50 * 1024 * 1024:
            with open(file_path, "rb") as f:
                url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
                files = {"document": f}
                data = {"chat_id": CHAT_ID}
                doc_res = requests.post(url, data=data, files=files).json()
                if doc_res.get("ok"):
                    print("✅ ZIP отправлен")
                else:
                    print(f"❌ Ошибка ZIP: {doc_res.text}")
            os.remove(file_path)
    
    mark_as_posted(model["url"])
    print("✅ Пост полностью завершён!")

def job():
    print(f"⏰ {time.strftime('%H:%M')} - Запуск поиска модели...")
    
    # Случайный выбор площадки (MakerWorld теперь тоже в списке)
    source = random.choice(["printables", "thingiverse", "makerworld"])
    print(f"🔍 Выбрана площадка: {source}")
    
    model = None
    if source == "printables":
        model = get_printables_model()
    elif source == "thingiverse":
        model = get_thingiverse_model()
    else:
        model = get_makerworld_model()
    
    # Если выбранная площадка не дала результат, пробуем другие
    if not model:
        print(f"❌ {source} не дал результат, пробую другие площадки...")
        for try_source in ["printables", "thingiverse", "makerworld"]:
            if try_source == source: continue
            if try_source == "printables":
                model = get_printables_model()
            elif try_source == "thingiverse":
                model = get_thingiverse_model()
            else:
                model = get_makerworld_model()
            if model:
                break
    
    if model:
        print(f"✅ Найдена модель: {model['title']} с {source}")
        post_to_telegram(model)
    else:
        print("❌ Модель не найдена на всех площадках")

def run_webserver():
    server = HTTPServer(('0.0.0.0', 10000), HealthHandler)
    print("🌐 Веб-сервер запущен на порту 10000 (для Render)")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_webserver, daemon=True).start()
    
    # РАСПИСАНИЕ: с 9:00 до 21:00 каждый час
    schedule.every().day.at("09:00").do(job)
    schedule.every().day.at("10:00").do(job)
    schedule.every().day.at("11:00").do(job)
    schedule.every().day.at("12:00").do(job)
    schedule.every().day.at("13:00").do(job)
    schedule.every().day.at("14:00").do(job)
    schedule.every().day.at("15:00").do(job)
    schedule.every().day.at("16:00").do(job)
    schedule.every().day.at("17:00").do(job)
    schedule.every().day.at("18:00").do(job)
    schedule.every().day.at("19:00").do(job)
    schedule.every().day.at("20:00").do(job)
    schedule.every().day.at("21:00").do(job)
    
    print("🚀 Бот запущен. Жду расписания (9:00–21:00, 13 постов в день)")
    while True:
        schedule.run_pending()
        time.sleep(1)
