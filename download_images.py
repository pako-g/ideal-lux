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
import pandas as pd

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

JSON_INPUT  = "./file/simple_products.json"
IMG_DIR     = Path("./file/images")
BASE_URL    = "https://lampadestore.it/pub/media/tmp"

IMG_SIZE    = (1000, 1000)
JPEG_QUALITY = 85

CSV_PATH = "./file/giacenzeECommerce.csv"

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

    # Legge il JSON solo per nome e sku
    with open(JSON_INPUT, encoding="utf-8") as f:
        products = json.load(f)

    # Legge il CSV per gli URL originali
    df = pd.read_csv(CSV_PATH, sep=None, engine="python")
    df["sku"] = df["Nr"].astype(str).str[-6:]
    url_map = df.set_index("sku")["Indirizzo Immagine"].to_dict()

    totale    = len(products)
    scaricate = 0
    saltate   = 0
    errori    = 0
    lista_errori = []

    for i, item in enumerate(products, start=1):
        p    = item["product"]
        sku  = p["sku"]
        nome = p["name"]

        sku_pulito = sku.replace("IL-", "")
        src_url = url_map.get(sku_pulito)
        if not src_url or pd.isna(src_url):
            print(f"[{i}/{totale}] {sku} — URL non trovato nel CSV, salto")
            errori += 1
            continue

        filename = build_filename(nome, sku_pulito)
        dest     = IMG_DIR / filename

        if dest.exists():
            print(f"[{i}/{totale}] {sku} — già presente, salto")
            saltate += 1
        else:
            print(f"[{i}/{totale}] {sku} — scarico ...")
            ok = download_and_process(src_url, dest)
            if ok:
                scaricate += 1
                print(f"     ✅  {filename} ({dest.stat().st_size // 1024} KB)")
            else:
                errori += 1
                # nel loop, quando c'è errore:
                lista_errori.append(f"{sku} | {src_url}")
                print(f"     ❌  {sku} — {src_url}")



        if i < totale:
            time.sleep(0.3)

    print()
    print("─" * 50)
    print(f"✅  Completato")
    print(f"   Scaricate : {scaricate}")
    print(f"   Saltate   : {saltate}")
    print(f"   Errori    : {errori}")


    if lista_errori:
        print()
        print("─" * 50)
        print("❌  URL con errore:")
        for e in lista_errori:
            print(f"   {e}")
