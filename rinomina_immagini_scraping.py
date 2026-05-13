"""
rinomina_immagini_scraping.py

Legge configurable_products.json e rinomina le immagini in ./file/scraping/
cercando il codice prodotto (senza prefisso IL-) nel nome del file.

Esempio:
  135205_01.jpg  →  ideal-lux-acqua-pt1-lampada-da-terra-per-interni_1.jpg
  135205_02.jpg  →  ideal-lux-acqua-pt1-lampada-da-terra-per-interni_2.jpg
"""

import json
import re
from pathlib import Path
import hashlib
from collections import defaultdict

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CONFIG_JSON  = "./file/configurable_products.json"
SCRAPING_DIR = Path("./file/scraping")




def deduplicа_immagini(cartella: Path) -> None:
    """Cancella i duplicati mantenendo solo il primo file per ogni hash MD5."""
    hash_map = defaultdict(list)
    for img in sorted(cartella.glob("*.jpg")):
        h = hashlib.md5(img.read_bytes()).hexdigest()
        hash_map[h].append(img)

    cancellati = 0
    for h, files in hash_map.items():
        if len(files) > 1:
            # Tieni il primo, cancella gli altri
            for f in files[1:]:
                print(f"  🗑️   Duplicato cancellato: {f.name}")
                f.unlink()
                cancellati += 1

    print(f"🗑️   Duplicati cancellati: {cancellati}\n")


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def nome_to_slug(nome: str) -> str:
    """
    "Ideal Lux Acqua Pt1 Lampada Da Terra per Interni"
    → "ideal-lux-acqua-pt1-lampada-da-terra-per-interni"
    """
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    print("── Deduplicazione immagini ──────────────────────────────")
    deduplicа_immagini(SCRAPING_DIR)

    # 1. Carica configurabili
    with open(CONFIG_JSON, encoding="utf-8") as f:
        configurabili = json.load(f)

    # 2. Costruisci mappa codice_semplice → slug configurabile
    # Es: {"135205": "ideal-lux-acqua-pt1-...", "246918": "ideal-lux-acqua-pt1-..."}
    codice_slug = {}
    for c in configurabili:
        nome  = c["product"]["name"]
        slug  = nome_to_slug(nome)
        for sku in c.get("_child_skus", []):
            # Rimuovi prefisso IL-
            codice = sku.replace("IL-", "").strip()
            codice_slug[codice] = slug

    print(f"📦  Codici mappati: {len(codice_slug)}")

    # 3. Scansiona le immagini in ./file/scraping/
    immagini = sorted(SCRAPING_DIR.glob("*.jpg"))
    print(f"🖼️   Immagini trovate: {len(immagini)}\n")

    rinominate  = 0
    non_trovate = 0

    # Tiene traccia del contatore progressivo per slug
    # Es: {"ideal-lux-acqua-...": 1, ...}
    contatori = {}

    for img_path in immagini:
        nome_file = img_path.stem   # es. "135205_01"

        # Estrai il codice (parte prima del primo _)
        codice = nome_file.split("_")[0]

        if codice not in codice_slug:
            print(f"  ⚠️  Codice non trovato: {nome_file}.jpg")
            non_trovate += 1
            continue

        slug = codice_slug[codice]

        # Incrementa contatore per questo slug
        contatori[slug] = contatori.get(slug, 0) + 1
        progressivo = contatori[slug]

        nuovo_nome = f"{slug}-{codice}-{progressivo}.jpg"
        nuovo_path = SCRAPING_DIR / nuovo_nome

        # Evita sovrascritture
        if nuovo_path.exists() and nuovo_path != img_path:
            print(f"  ⚠️  File già esistente, salto: {nuovo_nome}")
            continue

        img_path.rename(nuovo_path)
        print(f"  ✅  {img_path.name}  →  {nuovo_nome}")
        rinominate += 1

    print(f"\n✅  Rinominate  : {rinominate}")
    print(f"⚠️   Non trovate : {non_trovate}")


if __name__ == "__main__":
    main()
