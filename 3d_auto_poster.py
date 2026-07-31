import requests
from bs4 import BeautifulSoup
import time
import os
import schedule
import threading
import socket

TOKEN = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
CHAT_ID = "@TREEDSTL"

def generate_visual_description(img_url, title, raw_desc, model_url):
    # Автоматический подбор заголовка по типу модели
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

    # Основной текст (берём из сырого описания, если есть)
    if raw_desc and len(raw_desc) > 50:
        body = f"{raw_desc}\n\n"
    else:
        body = "Если ваш рабочий стол завален мелочевкой, эта модульная система — спасение. Сочетает в себе эстетику ретро-футуризма и строгую функциональность.\n\n"

    # Блок "Почему это круто"
    highlights = (
        "✅ **Модульность:** Собирайте конфигурацию под свои нужды, наращивая ярусы.\n"
        "✅ **Эстетика:** Чистые линии превратят обычный пластик в элемент декора.\n"
        "✅ **Практичность:** Идеально подходит для организации пространства в прихожей или на столе.\n"
    )

    # Блок "Советы по печати"
    tips = (
        "💡 **Советы по печати:**\n"
        "• 🧵 **Материал:** Используйте матовый PLA или текстурированный PETG — они лучше всего поддерживают форму и скрывают слои.\n"
        "• 🔥 **Точность:** Тщательно откалибруйте поток (flow), чтобы модули легко стыковались.\n"
    )

    # Финальное объединение
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
    
    # Отправляем фото
    if model["image"]:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        data = {"chat_id": CHAT_ID, "photo": model["image"], "caption": caption, "parse_mode": "Markdown"}
        res = requests.post(url, data=data).json()
    else:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "Markdown"}
        res = requests.post(url, data=data).json()
    
    if res.get("ok"):
        # Скачиваем STL/ZIP
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
                url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
                with open(file_path, "rb") as f:
                    files = {"document": f}
                    data = {"chat_id": CHAT_ID}
                    doc_res = requests.post(url, data=data, files=files).json()
                    print("Document send result:", doc_res)
                os.remove(file_path)
    return res

def job():
    print(f"⏰ {time.strftime('%H:%M')} - Запуск поиска модели...")
    model = get_printables_model()
    if model:
        print(f"Found model: {model['title']}")
        result = post_to_telegram(model)
        if result and result.get("ok"):
            mark_as_posted(model["url"])
            print("✅ Пост опубликован!")
        else:
            print("❌ Ошибка публикации")
    else:
        print("❌ Модель не найдена")

def fake_server():
    """Фейковый сервер для Render, чтобы он не перезапускал бота"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', 8080))
        sock.listen(1)
        print("🟢 Фейковый порт 8080 открыт для Render (защита от перезапусков)")
        while True:
            sock.accept()
    except Exception as e:
        print(f"⚠️ Фейковый порт: {e}")

if __name__ == "__main__":
    # Запускаем фейковый сервер в отдельном потоке
    threading.Thread(target=fake_server, daemon=True).start()
    
    # Расписание: каждый час с 9:00 до 18:00
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
