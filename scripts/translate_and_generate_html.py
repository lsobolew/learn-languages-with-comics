# scripts/translate_and_generate_html.py

import os
import io
import json
from pathlib import Path
from PIL import Image
from openai import OpenAI
import hashlib
import base64

INPUT_DIR = Path("output")  # artefakt z poprzedniego joba
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def translate_frame(image_crop):
    """
    image_crop: PIL Image
    returns: dict with 'response' (str) and 'image_b64' (str)
    """
    buf = io.BytesIO()
    image_crop.save(buf, format="PNG")
    buf.seek(0)
    image_bytes = buf.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{image_b64}"

    # zapis scropowanego obrazu z bufora do katalogu frames
    frames_dir = INPUT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    data = buf.getvalue()
    frame_hash = hashlib.sha1(data).hexdigest()[:12]
    frame_path = frames_dir / f"frame_{frame_hash}.png"
    with open(frame_path, "wb") as f:
        f.write(data)

    system_prompt = (
        "Jesteś nauczycielem języka. "
        "Pomagaj w nauce. " 
        "Dostaniesz panele komiksowe. " 
        "Nie zadawaj żadnych pytań. "
    )
    
    response = client.chat.completions.create(
        model="gpt-5-chat-latest",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "Przetłumacz dymki i przygotuj odpowiedź w formacie Markdown. "
                        "Tłumacz tekst, gramatykę, dodawaj romaji i furiganę. " 
                        "Komiks to 'Crayon Shin-Chan'. Uzyj wiedzy o tej serii, zeby np. pozsnać postaci."
                        "Jeśli są jakieś ukryte znaczenia lub dwuznaczności wymagające znajomości np. kultury Japonii to też dodawaj. "
                        "Nie sugeruj żadnych dodatkowych ćwiczeń ani zadań. Nie pytaj mnie o nic. "
                        "Nie dodawaj głownego nagłówka."
                        "Jeśli nie ma tekstu, odpowiedz 'ERROR'."
                    )},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ]
    )

    response_text = response.choices[0].message.content.strip()
    print("OpenAI response:", response_text)
    
    return {
        "response": response_text,
        "image_b64": image_b64
    }

def process_page(image_file):
    print("Process", image_file)
    base = image_file.stem
    json_file = INPUT_DIR / f"{base}.json"
    if not json_file.exists():
        print(f"Brak JSON dla {image_file.name}, pomijam...")
        return

    # wczytaj bounding boxy
    with open(json_file, "r") as f:
        boxes = json.load(f)

    print("JSON", boxes)
    img = Image.open(image_file).convert("RGB")

    translations = []
    valid_boxes = []
    for idx, b in enumerate(boxes):
        x1, y1 = int(b["x1"]), int(b["y1"])
        x2, y2 = int(b["x2"]), int(b["y2"])
        crop = img.crop((x1, y1, x2, y2))

        result = translate_frame(crop)
        trans_id = b.get("id", idx)
        
        # Skip panels with ERROR response
        if result["response"].strip().upper() == "ERROR":
            print(f"Skipping panel {trans_id} - ERROR response from OpenAI")
            continue
            
        translations.append({
            "id": trans_id, 
            "translation": result["response"],
            "image_b64": result["image_b64"]
        })
        valid_boxes.append(b)

    # zapisz tłumaczenia
    out_trans_file = INPUT_DIR / f"{base}_translations.json"
    with open(out_trans_file, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    # generowanie HTML z <map> i modalem
    html_file = INPUT_DIR / f"{base}.html"
    w, h = img.size

    areas_html = "\n    ".join(
        f'<area shape="rect" coords="{int(b["x1"])},{int(b["y1"])},{int(b["x2"])},{int(b["y2"])}" '
        f'data-id="{b["id"]}" href="#"></area>'
        for b in valid_boxes
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{image_file.name} – panels</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>
<style>
  .container {{ position: relative; display: inline-block; }}
  img {{ max-width: 100%; height: auto; display: block; }}
  area {{ cursor: pointer; }}
  #hover-overlay {{
    position: absolute; pointer-events: none; border: 3px solid #007bff;
    background: rgba(0, 123, 255, 0.1); z-index: 10; display: none;
  }}
  #modal {{
    background: white; border: 2px solid #333; padding: 20px;
    max-width: 640px; max-height: 80vh; overflow: auto;
  }}
  #modal::backdrop {{
    background: rgba(0, 0, 0, 0.5);
  }}
  #modalImage {{
    margin: 0 15px 15px 0; max-width: 200px; max-height: 200px; outline: 2px solid gray; outline-offset: 4px;
  }}
  #modalText {{
    line-height: 1.6;
  }}
  #modalText h1, #modalText h2, #modalText h3 {{ margin-top: 0; }}
  #modalText p {{ margin: 0.5em 0; }}
  #modalText ul, #modalText ol {{ margin: 0.5em 0; padding-left: 1.5em; list-style-position: inside; }}
  #modalText strong {{ font-weight: bold; }}
  #modalText em {{ font-style: italic; }}
  #modalText code {{ background: #f5f5f5; padding: 0.2em 0.4em; border-radius: 3px; }}
</style>
</head>
<body>
<div class="container">
  <img src="{image_file.name}" usemap="#comicmap" />
  <div id="hover-overlay"></div>
  <map name="comicmap" id="comicmap">
    {areas_html}
  </map>
</div>
<dialog id="modal">
  <img id="modalImage" style="display: none;" />
  <div id="modalText"></div>
  <form method="dialog">
    <button type="submit" style="position: absolute; top: 10px; right: 10px; background: none; border: none; font-size: 20px; cursor: pointer;">×</button>
  </form>
</dialog>

<script>
const translations = {json.dumps(translations, ensure_ascii=False)};
const img = document.querySelector('img');
const overlay = document.getElementById('hover-overlay');

// Function to scale coordinates based on image display size
function scaleCoords(coords, imgWidth, imgHeight) {{
    const scaleX = img.clientWidth / imgWidth;
    const scaleY = img.clientHeight / imgHeight;
    return coords.map((coord, index) => {{
        return index % 2 === 0 ? coord * scaleX : coord * scaleY;
    }});
}}

document.querySelectorAll('area').forEach(area => {{
    const coords = area.coords.split(',').map(Number);
    
    area.addEventListener('mouseenter', () => {{
        const scaledCoords = scaleCoords(coords, img.naturalWidth, img.naturalHeight);
        const [x1, y1, x2, y2] = scaledCoords;
        
        overlay.style.left = x1 + 'px';
        overlay.style.top = y1 + 'px';
        overlay.style.width = (x2 - x1) + 'px';
        overlay.style.height = (y2 - y1) + 'px';
        overlay.style.display = 'block';
    }});
    
    area.addEventListener('mouseleave', () => {{
        overlay.style.display = 'none';
    }});
    
    area.addEventListener('click', e => {{
        e.preventDefault();
        const id = area.dataset.id;
        const t = translations.find(tr => tr.id === id);
        const modalText = document.getElementById('modalText');
        const modalImage = document.getElementById('modalImage');
        
        if (t && t.translation) {{
            modalText.innerHTML = marked.parse(t.translation);
            if (t.image_b64) {{
                modalImage.src = 'data:image/png;base64,' + t.image_b64;
                modalImage.style.display = 'block';
            }} else {{
                modalImage.style.display = 'none';
            }}
        }} else {{
            modalText.innerHTML = '<p>Brak tłumaczenia</p>';
            modalImage.style.display = 'none';
        }}
        document.getElementById('modal').showModal();
    }});
}});

// Dialog automatically closes when clicking outside or pressing Escape
// The close button uses form method="dialog" for native behavior
</script>
</body>
</html>
"""
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

# główna pętla po wszystkich stronach w output/
for img_path in INPUT_DIR.glob("*.jpg"):
    process_page(img_path)

print("Gotowe: przetłumaczone JSON-y i HTML w katalogu output/")
