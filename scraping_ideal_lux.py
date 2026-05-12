"""
scraping_ideal_lux.py — Scraping prodotti Ideal Lux

Flusso:
  1. Legge ./file/sitemap_index.xml
  2. Filtra solo gli URL con /it/prodotti/
  3. Per ogni URL scarica la pagina e recupera:
     - codice prodotto (span.product-code)
     - descrizione (div dopo hr che segue il codice)
  4. Salva i risultati in ./file/descrizioni_prodotti.json
"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import re
import shutil
from PIL import Image
import io

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

SITEMAP_PATH  = "./file/sitemap_index.xml"
OUTPUT_JSON   = "./file/descrizioni_prodotti.json"
DELAY         = 1.0       # secondi tra una richiesta e l'altra
MAX_RETRIES   = 3
HEADERS       = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

IMAGES_DIR = Path("./file/scraping")

# ─────────────────────────────────────────────
# SCARICA IMMAGINI
# ─────────────────────────────────────────────

def scarica_immagini(codice: str, img_urls: list) -> list:
    """
    Scarica le immagini del prodotto in ./file/scraping/{codice}/
    Restituisce la lista dei path salvati.
    """
    cartella = IMAGES_DIR / codice
    cartella.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, url in enumerate(img_urls, start=1):
        ext = Path(url.split("?")[0]).suffix or ".jpg"
        filename = f"{codice}_{i:02d}{ext}"
        path = cartella / filename

        if path.exists():
            paths.append(str(path))
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, stream=True)
            resp.raise_for_status()
            with open(path, "wb") as f:
                shutil.copyfileobj(resp.raw, f)
            paths.append(str(path))
        except Exception as e:
            print(f"    ⚠️  Errore download img {url}: {e}")

    return paths


# ─────────────────────────────────────────────
# LEGGI SITEMAP
# ─────────────────────────────────────────────

def leggi_url_prodotti(sitemap_path: str) -> list:
    """
    Legge il sitemap_index.xml e restituisce solo gli URL
    che contengono /it/prodotti/.
    Gestisce sia sitemap index (con <sitemap>) che sitemap diretta (con <url>).
    """
    tree = ET.parse(sitemap_path)
    root = tree.getroot()

    # Namespace Sitemap
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = []

    # Caso 1: sitemap index → contiene altri sitemap da scaricare
    sitemap_locs = root.findall("sm:sitemap/sm:loc", ns)
    if sitemap_locs:
        print(f"📄  Sitemap index trovato — {len(sitemap_locs)} sitemap figlie")
        for loc in sitemap_locs:
            child_url = loc.text.strip()
            print(f"    Scarico sitemap figlia: {child_url}")
            try:
                resp = requests.get(child_url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                child_tree = ET.fromstring(resp.content)
                for url_el in child_tree.findall("sm:url/sm:loc", ns):
                    u = url_el.text.strip()
                    if "/it/prodotti/" in u:
                        urls.append(u)
            except Exception as e:
                print(f"    ⚠️  Errore sitemap figlia: {e}")
            time.sleep(0.5)
    else:
        # Caso 2: sitemap diretta
        for url_el in root.findall("sm:url/sm:loc", ns):
            u = url_el.text.strip()
            if "/it/prodotti/" in u:
                urls.append(u)

    # Rimuovi duplicati mantenendo ordine
    urls = list(dict.fromkeys(urls))
    print(f"🔗  URL prodotti trovati: {len(urls)}")
    return urls


# ─────────────────────────────────────────────
# SCRAPING SINGOLA PAGINA
# ─────────────────────────────────────────────

def scrapa_pagina(url: str) -> dict | None:
    """
    Scarica la pagina e recupera:
      - codice: <span class="product-code">
      - descrizione: <div> subito dopo <hr> che segue il codice
    Restituisce None se la pagina è 404 o il codice non è trovato.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)

            if resp.status_code == 404:
                return None  # pagina non trovata, saltiamo silenziosamente

            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                print(f"    ⚠️  Errore dopo {MAX_RETRIES} tentativi: {e}")
                return None
            time.sleep(DELAY * attempt)

    soup = BeautifulSoup(resp.text, "html.parser")

    # Codice prodotto
    codice_tag = soup.find("span", class_="product-code")
    if not codice_tag:
        return None
    codice = codice_tag.text.strip()

    # Descrizione: div subito dopo il primo <hr> che segue il codice
    descrizione = ""
    hr_tag = codice_tag.find_parent("p")
    if hr_tag:
        hr = hr_tag.find_next("hr")
        if hr:
            desc_div = hr.find_next("div")
            if desc_div:
                descrizione = desc_div.get_text(strip=True)

    # Immagini dalla swiper gallery
    img_urls = []
    swiper = soup.find("div", class_="swiper-wrapper")
    if swiper:
        for img in swiper.find_all("img", class_="product-gallery-image"):
            src = img.get("src")
            if src:
                img_urls.append(src)

    immagini = scarica_immagini(codice, img_urls)

    return {
        "codice": codice,
        "url": url,
        "descrizione": descrizione,
        "immagini": immagini,
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  SCRAPING Ideal Lux — Codici e Descrizioni")
    print("=" * 60)

    # 1. Leggi URL dalla sitemap
    urls = leggi_url_prodotti(SITEMAP_PATH)

    # 2. Carica risultati già salvati (per riprendere in caso di interruzione)
    output_path = Path(OUTPUT_JSON)
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            risultati = json.load(f)
        codici_presenti = {r["codice"] for r in risultati}
        url_presenti    = {r["url"] for r in risultati}
        print(f"♻️   Risultati esistenti: {len(risultati)} — riprendo da dove mi ero fermato")
    else:
        risultati       = []
        codici_presenti = set()
        url_presenti    = set()

    totale   = len(urls)
    ok       = 0
    saltati  = 0
    errori   = 0
    non_trovati = 0

    for i, url in enumerate(urls, start=1):
        # Salta URL già processati
        if url in url_presenti:
            saltati += 1
            continue

        print(f"  [{i}/{totale}]  {url}")

        result = scrapa_pagina(url)

        if result is None:
            non_trovati += 1
            print(f"             ⚠️  404 o codice non trovato")
        elif result["codice"] in codici_presenti:
            # Stesso codice su URL diverso (variante colore ecc.) — aggiorna descrizione se mancante
            saltati += 1
            print(f"             ⏭️  Codice {result['codice']} già presente")
        else:
            risultati.append(result)
            codici_presenti.add(result["codice"])
            url_presenti.add(url)
            ok += 1
            desc_preview = result["descrizione"][:60] + "..." if len(result["descrizione"]) > 60 else result["descrizione"]
            print(f"             ✅  cod. {result['codice']}  —  {desc_preview}")

        # Salva ogni 50 prodotti per sicurezza
        if i % 50 == 0:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(risultati, f, ensure_ascii=False, indent=2)
            print(f"    💾  Checkpoint salvato ({len(risultati)} prodotti)")

        time.sleep(DELAY)

    # Salvataggio finale
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(risultati, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅  Completato")
    print(f"   Prodotti scrappati : {ok}")
    print(f"   Saltati            : {saltati}")
    print(f"   404 / non trovati  : {non_trovati}")
    print(f"   Errori             : {errori}")
    print(f"   Output             : {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
