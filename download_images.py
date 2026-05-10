"""
Download e processing immagini prodotti Magento - Ideal Lux

- Legge il JSON dei prodotti semplici
- Scarica le immagini da ideal-lux.com
- Ridimensiona a 1000x1000px con sfondo bianco
- Converte in JPEG (quality 85)
- Salva in ./file/images/{nome_prodotto}-{sku}.jpg
- Salta le immagini già presenti
- Aggiorna il JSON con l'URL pubblico su lampadestore.it
"""

import json
import re
import time
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

JSON_INPUT  = "./file/aline_simple_products.json"
IMG_DIR     = Path("./file/images")
BASE_URL    = "https://lampadestore.it/pub/media/tmp"

IMG_SIZE    = (1000, 1000)
JPEG_QUALITY = 85


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def build_filename(product_name: str, sku: str) -> str:
    """
    'Ideal Lux A-line sp1 d13-Bianco-GU10', '232690'
    → 'ideal-lux-a-line-sp1-d13-bianco-gu10-232690.jpg'
    """
    slug = re.sub(r"[^a-z0-9]+", "-", product_name.lower()).strip("-")
    return f"{slug}-{sku}.jpg"


def download_and_process(url: str, dest_path: Path) -> bool:
    """
    Scarica l'immagine, la ridimensiona a 1000x1000 con sfondo bianco,
    la converte in JPEG e la salva. Restituisce True se ok, False se errore.
    """
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        img = Image.open(BytesIO(response.content)).convert("RGBA")

        # Crea sfondo bianco 1000x1000
        background = Image.new("RGB", IMG_SIZE, (255, 255, 255))

        # Ridimensiona mantenendo aspect ratio
        img.thumbnail(IMG_SIZE, Image.LANCZOS)

        # Centra sul background
        offset = (
            (IMG_SIZE[0] - img.width)  // 2,
            (IMG_SIZE[1] - img.height) // 2,
        )
        background.paste(img, offset, mask=img.split()[3])  # usa canale alpha

        background.save(dest_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True

    except Exception as e:
        print(f"     ⚠️  Errore: {e}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    with open(JSON_INPUT, encoding="utf-8") as f:
        products = json.load(f)

    totale     = len(products)
    scaricate  = 0
    saltate    = 0
    errori     = 0

    for i, item in enumerate(products, start=1):
        p       = item["product"]
        sku     = p["sku"]
        nome    = p["name"]
        gallery = p.get("media_gallery_entries", [])

        if not gallery:
            print(f"[{i}/{totale}] {sku} — nessuna immagine nel JSON, salto")
            continue

        entry    = gallery[0]
        src_url  = entry["content"]["url"]
        filename = build_filename(nome, sku)
        dest     = IMG_DIR / filename

        if dest.exists():
            print(f"[{i}/{totale}] {sku} — già presente, salto")
            saltate += 1
        else:
            print(f"[{i}/{totale}] {sku} — scarico {src_url.split('/')[-1]} ...")
            ok = download_and_process(src_url, dest)
            if ok:
                scaricate += 1
                print(f"     ✅  {filename} ({dest.stat().st_size // 1024} KB)")
            else:
                errori += 1


        # Pausa educata per non sovraccaricare il server
        if i < totale:
            time.sleep(0.3)


    print()
    print("─" * 50)
    print(f"✅  Completato")
    print(f"   Scaricate : {scaricate}")
    print(f"   Saltate   : {saltate}")
    print(f"   Errori    : {errori}")
