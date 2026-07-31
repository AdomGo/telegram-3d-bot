import requests
from bs4 import BeautifulSoup
import time
import os

TOKEN = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
CHAT_ID = "@TREEDSTL"

def generate_visual_description(img_url, title, raw_desc):
    from openai import OpenAI
    import os
    client = OpenAI()
    
    try:
        # Using vision model to describe the image
        # Note: Using gemini-3-flash-preview as it's excellent for multimodal tasks
        response = client.chat.completions.create(
            model="gemini-3-flash-preview",
            messages=[
                {
                    "role": "system", 
                    "content": "Ты — эксперт по 3D-печати. Твоя задача — составить увлекательный и полезный пост для Telegram-канала на основе изображения 3D-модели. Опиши, что это, зачем оно нужно, и дай пару советов по печати. Пиши на русском языке, используй эмодзи. Не пиши лишних вступлений, сразу к сути. Общий объем до 800 символов."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Название модели: {title}\nОригинальное описание: {raw_desc}"},
                        {"type": "image_url", "image_url": {"url": img_url}}
                    ]
                }
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        import traceback
        print(f"Vision error details: {traceback.format_exc()}")
        return f"📦 *{title}*\n\n{raw_desc[:300]}..." # Fallback

def get_printables_model():
    url = "https://www.printables.com/model?period=day&sort=trending"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        model_links = [a for a in soup.find_all('a', href=True) if a['href'].startswith('/model/') and not a['href'].endswith('/comments')]
        if not model_links: return None
        
        # Find first not posted
        model_url = None
        for a in model_links:
            test_url = "https://www.printables.com" + a['href']
            if not is_already_posted(test_url):
                model_url = test_url
                break
        
        if not model_url: return None
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
        title = detail_soup.find('h1').get_text(strip=True) if detail_soup.find('h1') else "3D Model"
        desc_div = detail_soup.find('div', class_='description') or detail_soup.find('article')
        raw_description = desc_div.get_text(strip=True) if desc_div else "No description available."
        
        img_url = None
        # Try to find the main model image
        img_tags = detail_soup.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if 'media.printables.com' in src:
                # Replace thumb with original if possible
                if '/thumbs/' in src:
                    src = src.replace('/thumbs/render/', '/media/').replace('/thumbs/model/', '/media/')
                    # Remove the suffix like _thumb_card.jpg or similar if present
                    import re
                    src = re.sub(r'_thumb_.*?\.', '.', src)
                img_url = src
                break
        
        # Fallback to meta tags if no img found in body
        if not img_url:
            og_image = detail_soup.find('meta', property='og:image')
            if og_image: img_url = og_image['content']
        
        description = generate_visual_description(img_url, title, raw_description) if img_url else raw_description[:300]
        return {"title": title, "url": model_url, "description": description, "image": img_url}
    except Exception as e:
        print(f"Printables error: {e}")
        return None

def get_thingiverse_model():
    url = "https://www.thingiverse.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Find all thing links
        model_links = [a for a in soup.find_all('a', href=True) if '/thing:' in a['href']]
        if not model_links: return None
        
        # Get unique IDs
        unique_urls = []
        for a in model_links:
            href = a['href']
            if not href.startswith('http'): href = "https://www.thingiverse.com" + href
            if href not in unique_urls: unique_urls.append(href)
            
        # Find first not posted
        model_url = None
        for test_url in unique_urls:
            if not is_already_posted(test_url):
                model_url = test_url
                break
        
        if not model_url: return None
        
        print(f"Visiting Thingiverse model: {model_url}")
        
        detail_res = requests.get(model_url, headers=headers)
        detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
        
        # Find title
        title = detail_soup.find('h1').get_text(strip=True) if detail_soup.find('h1') else "3D Model"
        
        # Find description
        desc_div = detail_soup.find('div', class_='thing-description') or detail_soup.find('div', class_='description') or detail_soup.find('div', id='description')
        raw_description = desc_div.get_text(strip=True) if desc_div else "No description available."
        
        # Find image - look for large previews
        img_url = None
        # Try meta tags first as they are most reliable for the main photo
        og_image = detail_soup.find('meta', property='og:image')
        if og_image:
            img_url = og_image['content']
            # Thingiverse often uses large previews in og:image, but let's double check
            if '/renders/' in img_url:
                img_url = img_url.replace('/card/', '/large/').replace('/thumb/', '/large/')
        else:
            img_tags = detail_soup.find_all('img')
            for img in img_tags:
                src = img.get('src', '')
                if 'cdn.thingiverse.com' in src:
                    img_url = src.replace('/card/', '/large/').replace('/thumb/', '/large/')
                    break
                
        description = generate_visual_description(img_url, title, raw_description) if img_url else raw_description[:300]
        return {"title": title, "url": model_url, "description": description, "image": img_url}
    except Exception as e:
        print(f"Thingiverse error: {e}")
        return None

def get_trending_model():
    import random
    # Randomly pick between Printables and Thingiverse
    source = random.choice(["printables", "thingiverse"])
    print(f"Selected source: {source}")
    if source == "printables":
        model = get_printables_model()
        if not model: model = get_thingiverse_model()
    else:
        model = get_thingiverse_model()
        if not model: model = get_printables_model()
    return model

def is_already_posted(url):
    history_file = "/home/ubuntu/posted_models.txt"
    if not os.path.exists(history_file):
        return False
    with open(history_file, "r") as f:
        posted = f.read().splitlines()
    return url in posted

def mark_as_posted(url):
    history_file = "/home/ubuntu/posted_models.txt"
    with open(history_file, "a") as f:
        f.write(url + "\n")

def download_file(url, filename):
    headers = {"User-Agent": "Mozilla/5.0"}
    # Sanitize filename to remove slashes and other problematic characters
    filename = "".join([c for c in filename if c.isalnum() or c in ('.', '_', '-')]).strip()
    try:
        if not os.path.exists("/home/ubuntu/Downloads"):
            os.makedirs("/home/ubuntu/Downloads")
        r = requests.get(url, headers=headers, stream=True)
        path = os.path.join("/home/ubuntu/Downloads", filename)
        with open(path, 'wb') as f:
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
    
    if is_already_posted(model['url']):
        print(f"Model {model['url']} already posted. Skipping.")
        return None

    caption = f"📦 *{model['title']}*\n\n"
    caption += f"{model['description']}\n\n"
    caption += f"🔗 [Источник]({model['url']})\n\n"
    caption += "#3D #3Dпечать #STL #модель #3Dprinting #DIY"
    
    # Send Photo with Caption
    if model['image']:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        data = {"chat_id": CHAT_ID, "photo": model['image'], "caption": caption, "parse_mode": "Markdown"}
        res = requests.post(url, data=data).json()
    else:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "Markdown"}
        res = requests.post(url, data=data).json()
    
    # Attempt to download and send the file
    if res.get("ok"):
        file_url = None
        if "printables.com" in model['url']:
            # Printables direct download link pattern
            model_id = model['url'].split('/')[-1].split('-')[0]
            file_url = f"https://www.printables.com/model/{model_id}/download" # This might need auth or direct file link
        elif "thingiverse.com" in model['url']:
            # Thingiverse direct download link pattern
            thing_id = model['url'].split(':')[-1]
            file_url = f"https://www.thingiverse.com/thing:{thing_id}/zip"

        if file_url:
            print(f"Attempting to download file from {file_url}")
            file_path = download_file(file_url, f"{model['title'][:30]}.zip")
            if file_path and os.path.getsize(file_path) < 50 * 1024 * 1024: # TG limit 50MB
                url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
                with open(file_path, 'rb') as f:
                    files = {'document': f}
                    data = {'chat_id': CHAT_ID}
                    doc_res = requests.post(url, data=data, files=files).json()
                    print("Document send result:", doc_res)
                os.remove(file_path)
    
    return res

if __name__ == "__main__":
    # Try multiple times to find a unique model
    posted_success = False
    for i in range(5):
        model = get_trending_model()
        if model:
            print(f"Found model: {model['title']}")
            result = post_to_telegram(model)
            if result and result.get("ok"):
                mark_as_posted(model['url'])
                print("Post result: Success")
                posted_success = True
                break
            elif result is None: # Already posted
                print("Trying another model...")
                continue
            else:
                print("Post result error:", result)
                break
        else:
            print("Failed to get model info.")
            break
    
    if not posted_success:
        print("Could not post any unique model after multiple attempts.")
