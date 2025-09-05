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
    returns: str, przetłumaczony tekst
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

    # przygotuj obraz jako data URL (base64) do wysłania w wiadomości
    # b64 = base64.b64encode(data).decode("utf-8")
    # data_url = f"data:image/png;base64,{b64}"
    # response = "Tłumaczenie testowe"  # zamień na faktyczne wywołanie OpenAI
    # print(data_url)
    system_prompt = (
        "Jesteś profesjonalnym tłumaczem komiksów. "
        "Zachowuj styl, emocje i charakter postaci. "
        "Przetłumacz tekst z tej ramki komiksu na język polski tak, "
        "aby brzmiał naturalnie i oddawał humor lub dramatyzm oryginału. "
        "Nie dodawaj komentarzy, odpowiedź ma być tylko tekstem tłumaczenia."
    )
    
    response = client.chat.completions.create(
        model="chatgpt-4o-latest",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Przetłumacz tekst na polski"},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        temperature=0.4,   # niższa wartość = bardziej spójne tłumaczenie
        max_tokens=300 
    )

    print("OpenAI response:", response.choices[0].message.content.strip())
    # return response
    return response.choices[0].message.content.strip()

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
    for idx, b in enumerate(boxes):
        x1, y1 = int(b["x1"]), int(b["y1"])
        x2, y2 = int(b["x2"]), int(b["y2"])
        crop = img.crop((x1, y1, x2, y2))

        translation = translate_frame(crop)
        trans_id = b.get("id", idx)
        translations.append({"id": trans_id, "translation": translation})

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
        for b in boxes
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{image_file.name} – panels</title>
<style>
  .container {{ position: relative; display: inline-block; }}
  img {{ max-width: 100%; height: auto; display: block; }}
  #modal {{
    display: none; position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    background: white; border: 2px solid #333; padding: 20px; z-index: 100;
  }}
</style>
</head>
<body>
<div class="container">
  <img src="{image_file.name}" usemap="#comicmap" />
  <map name="comicmap" id="comicmap">
    {areas_html}
  </map>
</div>
<div id="modal"><span id="modalText"></span></div>

<script>
const translations = {json.dumps(translations, ensure_ascii=False)};

document.querySelectorAll('area').forEach(area => {{
    area.addEventListener('click', e => {{
        e.preventDefault();
        const id = area.dataset.id;
        const t = translations.find(tr => tr.id === id);
        document.getElementById('modalText').textContent = t ? t.translation : "Brak tłumaczenia";
        document.getElementById('modal').style.display = 'block';
    }});
}});

document.getElementById('modal').addEventListener('click', () => {{
    document.getElementById('modal').style.display = 'none';
}});
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
