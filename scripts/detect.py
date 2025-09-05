import os, json
from PIL import Image, ImageDraw
from ultralytics import YOLO

INPUT_PATH = "comic/shinchan.jpg"
OUTPUT_DIR = "output"
MODEL_PATH = "models/comic.pt"

os.makedirs(OUTPUT_DIR, exist_ok=True)

model = YOLO(MODEL_PATH)
results = model.predict(source=INPUT_PATH, save=False)

# Save bounding boxes to JSON
boxes = []
for box in results[0].boxes:
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    boxes.append({
        "x": float(x1),
        "y": float(y1),
        "width": float(x2-x1),
        "height": float(y2-y1)
    })

with open(os.path.join(OUTPUT_DIR, "shinchan.json"), "w") as f:
    json.dump(boxes, f, indent=2)

# Draw overlay for preview
img = Image.open(INPUT_PATH).convert("RGB")
draw = ImageDraw.Draw(img)
for b in boxes:
    draw.rectangle(
        [b["x"], b["y"], b["x"]+b["width"], b["y"]+b["height"]],
        outline="red", width=3
    )
img.save(os.path.join(OUTPUT_DIR, "shinchan.jpg"))

# Generate HTML overlay
w, h = img.size
divs = "\n".join(
    f'<div class="panel" style="left:{b["x"]/w*100}%; top:{b["y"]/h*100}%; width:{b["width"]/w*100}%; height:{b["height"]/h*100}%;"></div>'
    for b in boxes
)

html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  .container {{
    position: relative;
    display: inline-block;
  }}
  .container img {{
    display: block;
    max-width: 100%;
    height: auto;
  }}
  .panel {{
    position: absolute;
    border: 2px solid rgba(255,0,0,0.5);
    box-sizing: border-box;
  }}
</style>
</head>
<body>
<div class="container">
  <img src="shinchan.jpg" alt="comic"/>
  {divs}
</div>
</body>
</html>"""
with open(os.path.join(OUTPUT_DIR, "shinchan.html"), "w") as f:
    f.write(html)
