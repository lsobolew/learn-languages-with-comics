# scripts/detect.py
import os
import json
import shutil
import hashlib
from glob import glob
from pathlib import Path
from PIL import Image
from ultralytics import YOLO

INPUT_DIR = Path("comic")
OUTPUT_DIR = Path("output")
MODEL_PATH = Path("models/comic.pt")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model = YOLO(str(MODEL_PATH))

def to_ints(*nums):
    return [int(round(float(n))) for n in nums]

def make_box_id(x1, y1, x2, y2):
    """Zwraca stabilny skrót na podstawie współrzędnych ramki.
    Używamy zaokrąglenia do 2 miejsc, by uniknąć szumu FP.
    """
    key = f"{float(x1):.2f}-{float(y1):.2f}-{float(x2):.2f}-{float(y2):.2f}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

def build_image_map_html(img_name, w, h, boxes):
    """
    img_name: nazwa pliku (np. shinchan.jpg) umieszczonego w katalogu output/
    w, h: naturalne wymiary obrazu
    boxes: lista dictów {x1,y1,x2,y2}
    """
    # obszary <area>
    areas = []
    print(boxes)
    for i, b in enumerate(boxes, 1):
        x1, y1, x2, y2 = to_ints(b["x1"], b["y1"], b["x2"], b["y2"])
        areas.append(
            f'<area shape="rect" coords="{x1},{y1},{x2},{y2}" '
            f'href="#" alt="panel {i}" title="panel {i}" data-panel-id="{i}">'
        )
    areas_html = "\n    ".join(areas)

    # Skrypt do automatycznego skalowania współrzędnych, gdy obraz nie jest w 100% naturalnej wielkości
    # (prosty, bez zewnętrznych bibliotek)
    js = f"""
<script>
(function() {{
  function rescaleMap(img, map) {{
    var natW = img.naturalWidth || {w};
    var natH = img.naturalHeight || {h};
    var curW = img.clientWidth;
    var curH = img.clientHeight;
    if (!natW || !natH || !curW || !curH) return;
    var scaleX = curW / natW, scaleY = curH / natH;
    Array.from(map.querySelectorAll('area')).forEach(function(a) {{
      var orig = a.getAttribute('data-orig');
      if (!orig) {{
        a.setAttribute('data-orig', a.coords);
        orig = a.coords;
      }}
      var pts = orig.split(',').map(Number);
      for (var i=0; i<pts.length; i+=2) {{
        pts[i]   = Math.round(pts[i]   * scaleX);
        pts[i+1] = Math.round(pts[i+1] * scaleY);
      }}
      a.coords = pts.join(',');
    }});
  }}

  var img = document.getElementById('comic-img');
  var map = document.getElementById('comic-map');
  function apply() {{ rescaleMap(img, map); }}
  if (img.complete) apply();
  img.addEventListener('load', apply);
  window.addEventListener('resize', apply);
}})();
</script>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{img_name} – panels</title>
<style>
  body {{ margin: 16px; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; }}
  img {{ width: 100%; height: auto; display:block; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{img_name}</h1>
  <img id="comic-img" src="{img_name}" alt="comic page" usemap="#comic" />
  <map name="comic" id="comic-map">
    {areas_html}
  </map>
  <p>Najedź/kliknij obszary — każdy panel to osobne <code>&lt;area&gt;</code>. Tu możesz podpiąć swoją logikę tłumaczeń.</p>
</div>
{js}
</body>
</html>"""
    return html

# przetwarzanie wszystkich obrazów (posortowane alfabetycznie)
image_paths = []
for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
    image_paths += glob(str(INPUT_DIR / ext))
image_paths.sort()

if not image_paths:
    print("Brak plików w katalogu 'comic/'.")
    raise SystemExit(0)

index_links = []

for in_path in image_paths:
    in_path = Path(in_path)
    base = in_path.stem
    out_img = OUTPUT_DIR / in_path.name
    out_json = OUTPUT_DIR / f"{base}.json"
    out_html = OUTPUT_DIR / f"{base}.html"

    # YOLO predykcja
    results = model.predict(source=str(in_path), save=False)
    r0 = results[0]

    # zbierz ramki (x1,y1,x2,y2), ewentualnie posortuj czytelnie (rząd po rzędzie)
    boxes = []
    for b in r0.boxes:
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        box_id = make_box_id(x1, y1, x2, y2)
        boxes.append({
            "id": box_id,
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2),
        })

    # sortowanie dla mangi: od góry (y rosnąco) i od prawej (x malejąco)
    boxes.sort(key=lambda b: (b["y1"], -b["x1"]))

    # zapisz JSON
    with open(out_json, "w") as f:
        json.dump(boxes, f, indent=2)

    # skopiuj oryginalny obraz do output/
    shutil.copy2(in_path, out_img)

    # pobierz wymiary naturalne
    with Image.open(in_path) as im:
        w, h = im.size

    # wygeneruj HTML z mapą
    html = build_image_map_html(in_path.name, w, h, boxes)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

    index_links.append(f'<li><a href="{out_html.name}">{in_path.name}</a></li>')

# indeks dla wielu stron
with open(OUTPUT_DIR / "index.html", "w", encoding="utf-8") as f:
    f.write(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><title>Comic pages</title>
<style>body{{font-family:system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin:24px}}</style>
</head>
<body>
<h1>Pages</h1>
<ol>
{''.join(index_links)}
</ol>
</body>
</html>""")

print("Gotowe: pliki w katalogu output/")
