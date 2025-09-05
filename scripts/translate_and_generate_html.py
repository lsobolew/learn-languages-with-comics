# scripts/translate_and_generate_html.py

import os
import io
import json
from pathlib import Path
from PIL import Image
from openai import OpenAI

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

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Jesteś pomocnym tłumaczem komiksów. Przetłumacz tekst z tego fragmentu komiksu na język polski."
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Przetłumacz na polski"},
                    {"type": "input_image", "image_data": buf.getvalue()},
                ]
            }
        ]
    )
    return response.choices[0].message.content.strip()

def process_page(image_file):
    base = image_file.stem
    json_file = INPUT_DIR / f"{base}.json"
    if not json_file.exists():
        print(f"Brak JSON dla {image_file.name}, pomijam...")
        return

    # wczytaj bounding boxy
    with open(json_file, "r") as f:
        boxes = json.load(f)

    img = Image.open(image_file).convert("RGB")

    translations = []
    for b in boxes:
        x1, y1 = int(b["x"]), int(b["y"])
        x2, y2 = int(b["x"] + b["width"]), int(b["y"] + b["height"])
        crop = img.crop((x1, y1, x2, y2))
        translation = translate_frame(crop)
        translations.append({"id": b["id"], "translation": translation})

    # zapisz tłumaczenia
    out_trans_file = INPUT_DIR / f"{base}_translations.json"
    with open(out_trans_file, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    # generowanie HTML z <map> i modalem
    html_file = INPUT_DIR / f"{base}.html"
    w, h = img.size

    areas_html = "\n    ".join(
        f'<area shape="rect" coords="{int(b["x"])},{int(b["y"])},{int(b["x"]+b["width"])},{int(b["y"]+b["height"])}" '
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
        const id = parseInt(area.dataset.id);
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
