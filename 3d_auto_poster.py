import requests
from bs4 import BeautifulSoup
import time
import os
import schedule
import threading
import random
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
CHAT_ID = "@TREEDSTL"

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    
    def log_message(self, format, *args):
        return

def generate_visual_description(img_url, title, raw_desc, model_url):
    if "organizer" in title.lower() or "drawer" in title.lower():
        header = f"⚡ {title}: Стильный органайзер в духе Mid-Century Modern!"
    elif "vase" in title.lower():
        header = f"🌸 {title}: Элегантная ваза для современного интерьера"
    elif "holder" in title.lower() or "stand" in title.lower():
        header = f"🧩 {title}: Удобный держатель для вашего стола"
    elif "lamp" in title.lower():
        header = f"💡 {title}: Светильник с характером"
    else:
        header = f"✨ {title}: Уникальная 3D-модель для вашего дома"

    if raw_desc and len(raw_desc) > 50:
        body = f"{raw_desc}\n\n"
    else:
        body = "Если ваш рабочий стол завален мелочевкой, эта модульная система — спасение. Сочетает в себе эстетику ретро-футуризма и строгую функциональность.\n\n"

    highlights = (
        "✅ **Модульность:** Собирайте конфигурацию под свои нужды, наращивая ярусы.\n"
        "✅ **Эстетика:** Чистые линии превратят обычный пластик в элемент декора.\n"
        "✅ **Практичность:** Идеально подходит для организации пространства в прихожей или на столе.\n"
    )

    tips = (
        "💡 **Советы по печати:**\n"
        "• 🧵 **Материал:** Используйте матовый PLA или текстурированный PETG.\n"
        "• 🔥 **Точность:** Тщательно откалибруйте поток (flow), чтобы модули легко стыковались.\n"
    )

    description = f"{header}\n\n{body}{highlights}\n\n{tips}\n🔗 [Источник]({model_url})\n\n#3D #3Dпечать #STL #модель #3Dprinting #DIY"
    return description

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
        
        # Ждём загрузки описания
        time.sleep(5)
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        title = detail_soup.find("h1").get_text(strip=True) if detail_soup.find("h1") else "3D Model"
        desc_div = detail_soup.find("div", class_="description") or detail_soup.find("article")
        raw_description = desc_div.get_text(strip=True) if desc_div else "No description available."
        
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
        
        description = generate_visual_description(img_url, title, raw_description, model_url) if img_url else raw_description[:300]
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
        
        # Ждём загрузки описания
        time.sleep(5)
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")
        title = detail_soup.find("h1").get_text(strip=True) if detail_soup.find("h1") else "3D Model"
        desc_div = detail_soup.find("div", class_="thing-description") or detail_soup.find("div", class_="description") or detail_soup.find("div", id="description")
        raw_description = desc_div.get_text(strip=True) if desc_div else "No description available."
        
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
        
        description = generate_visual_description(img_url, title, raw_description, model_url) if img_url else raw_description[:300]
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
    
    source = random.choice(["printables", "thingiverse"])
    print(f"🔍 Выбрана площадка: {source}")
    
    model = None
    if source == "printables":
        model = get_printables_model()
        if not model:
            print("❌ Printables не дал результат, пробую Thingiverse...")
            model = get_thingiverse_model()
    else:
        model = get_thingiverse_model()
        if not model:
            print("❌ Thingiverse не дал результат, пробую Printables...")
            model = get_printables_model()
    
    if model:
        print(f"✅ Найдена модель: {model['title']}")
        post_to_telegram(model)
    else:
        print("❌ Модель не найдена на обеих площадках")

def run_webserver():
    server = HTTPServer(('0.0.0.0', 10000), HealthHandler)
    print("🌐 Веб-сервер запущен на порту 10000 (для Render)")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_webserver, daemon=True).start()
    
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
    
    print("🚀 Бот запущен. Жду расписания (9:00–18:00)")
    while True:
        schedule.run_pending()
        time.sleep(1)
