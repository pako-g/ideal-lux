"""
magento_import.py — Import completo prodotti in Magento 2

Flusso:
  1. Legge simple_products.json e configurable_products.json
  2. Recupera via API gli attribute_id numerici per ogni attributo variante
  3. Crea i prodotti semplici → POST /rest/V1/products
  4. Crea i prodotti configurabili con configurable_product_options → POST /rest/V1/products
  5. Associa i semplici al configurabile → POST /rest/V1/configurable-products/{sku}/child
"""

import json
import re
import base64
from pathlib import Path
from utility.magento_api import *


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CATEGORIA   = "Lampada da tavolo"
SIMPLE_JSON = f"./file/simple_products_{CATEGORIA.lower().replace(' ', '_')}.json"
CONFIG_JSON = f"./file/configurable_products_{CATEGORIA.lower().replace(' ', '_')}.json"
IMAGES_DIR       = Path("./file/images")
SCRAPING_DIR     = Path("./file/scraping")


# ─────────────────────────────────────────────
# UTILITY IMMAGINI
# ─────────────────────────────────────────────

def trova_immagine(nome_prodotto: str, sku: str) -> Path | None:
    sku_pulito = sku.replace("IL-", "")
    slug = re.sub(r"[^a-z0-9]+", "-", nome_prodotto.lower()).strip("-")
    # Cerca prima per nome esatto
    path = IMAGES_DIR / f"{slug}-{sku_pulito}.jpg"
    if path.exists():
        return path
    # Fallback: cerca qualsiasi file che contenga lo SKU
    matches = list(IMAGES_DIR.glob(f"*{sku_pulito}*.jpg"))
    print(f"    🔍  Fallback trovati: {[m.name for m in matches]}")
    return matches[0] if matches else None


def immagine_to_base64(path: Path) -> str:
    """Legge un file immagine e restituisce la stringa base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_media_entry(nome_prodotto: str, sku: str) -> list:
    """
    Costruisce media_gallery_entries per un prodotto semplice.
    Cerca l'immagine in ./file/images/ per nome e SKU.
    """
    entries = []
    path = trova_immagine(nome_prodotto, sku)
    print(f"    🏷️   Label immagine: {nome_prodotto}")
    if path:
        print(f"    🖼️   Immagine semplice: {path.name}")
        entries.append({
            "media_type": "image",
            "label":      nome_prodotto,
            "position":   1,
            "disabled":   False,
            "types":      ["image", "small_image", "thumbnail"],
            "content": {
                "base64_encoded_data": immagine_to_base64(path),
                "type": "image/jpeg",
                "name": path.name,
            },
        })
    else:
        print(f"    ⚠️   Immagine non trovata per {sku}")
    return entries


def build_scraping_entries(nome_prodotto: str, child_skus: list, scraping_dir: Path) -> list:
    """
    Costruisce media_gallery_entries per le immagini scraping del configurabile.
    Cerca per ogni SKU figlio le immagini in ./file/scraping/.
    """
    imgs = []
    for s in child_skus:
        sku_pulito = s.replace("IL-", "")
        imgs.extend(sorted(scraping_dir.glob(f"*-{sku_pulito}-*.jpg")))
    imgs = sorted(imgs)

    entries = []
    for i, img_path in enumerate(imgs, start=1):
        print(f"    🖼️   Immagine scraping: {img_path.name}")
        print(f"    🏷️   Label immagine: {nome_prodotto}")
        entries.append({
            "media_type": "image",
            "label":      nome_prodotto,
            "position":   i,
            "disabled":   False,
            "types":      [],
            "content": {
                "base64_encoded_data": immagine_to_base64(img_path),
                "type": "image/jpeg",
                "name": img_path.name,
            },
        })
    return entries


# ─────────────────────────────────────────────
# STEP 1 — RISOLVI ATTRIBUTE_ID
# ─────────────────────────────────────────────

def build_attr_map(session: OAuth1Session, configurabili: list) -> dict:
    """
    Recupera attribute_id e opzioni per tutti i codici attributo
    presenti nei configurabili.
    """
    codes = set()
    for c in configurabili:
        codes.update(c.get("_attr_codes", []))

    attr_map = {}
    for code in sorted(codes):
        print(f"  🔍  Recupero attribute_id per '{code}'...")
        attr_map[code] = get_attribute_info(session, code)
        print(f"       → id={attr_map[code]['attribute_id']}  "
              f"opzioni={len(attr_map[code]['options'])}")
    return attr_map


# ─────────────────────────────────────────────
# STEP 2 — CREA PRODOTTI SEMPLICI
# ─────────────────────────────────────────────

def crea_semplici(session: OAuth1Session, semplici: list) -> dict:
    """
    Crea ogni prodotto semplice via API con immagine in base64.
    Restituisce {sku: entity_id} per i prodotti creati con successo.
    """
    creati = {}
    totale = len(semplici)

    for i, s in enumerate(semplici, start=1):
        sku  = s["product"]["sku"]
        nome = s["product"]["name"]
        print(f"\n  [{i}/{totale}]  Creo semplice  {sku}  —  {nome}")

        payload = json.loads(json.dumps(s))
        payload["product"]["media_gallery_entries"] = build_media_entry(nome, sku)

        try:
            result = api_post(session, "products", payload)
            entity_id = result.get("id")
            creati[sku] = entity_id
            print(f"             ✅  entity_id={entity_id}")
        except RuntimeError as e:
            print(f"             ❌  ERRORE: {e}")

        time.sleep(RETRY_DELAY)

    return creati


# ─────────────────────────────────────────────
# STEP 3 — COSTRUISCI configurable_product_options
# ─────────────────────────────────────────────

def build_config_options(
    attr_codes: list,
    child_skus: list,
    semplici_map: dict,
    attr_map: dict,
) -> list:
    """
    Costruisce configurable_product_options con attribute_id numerici reali
    e i value_index distinti raccolti dai semplici associati.
    """
    options = []
    for pos, code in enumerate(attr_codes):
        info = attr_map.get(code)
        if not info:
            print(f"    ⚠️  attribute_id non trovato per '{code}', salto")
            continue

        valori = set()
        for sku in child_skus:
            semplice = semplici_map.get(sku)
            if not semplice:
                continue
            for attr in semplice["product"]["custom_attributes"]:
                if attr["attribute_code"] == code:
                    valori.add(str(attr["value"]))

        options.append({
            "attribute_id": info["attribute_id"],
            "label":        code.replace("_", " ").title(),
            "position":     pos,
            "values":       [{"value_index": v} for v in sorted(valori)],
        })

    return options


# ─────────────────────────────────────────────
# STEP 4 — CREA PRODOTTI CONFIGURABILI
# ─────────────────────────────────────────────

def crea_configurabili(
    session: OAuth1Session,
    configurabili: list,
    semplici_map: dict,
    attr_map: dict,
) -> list:
    """
    Crea ogni configurabile via API con configurable_product_options.
    Le immagini del configurabile sono:
      - media_gallery_entries già nel JSON (immagini dei semplici in base64)
      - immagini scraping cercate per SKU figlio in ./file/scraping/
    Restituisce lista {config_sku, child_skus} per il linking.
    """
    da_linkare = []
    totale = len(configurabili)

    for i, c in enumerate(configurabili, start=1):
        sku        = c["product"]["sku"]
        nome       = c["product"]["name"]
        attr_codes = c.get("_attr_codes", [])
        child_skus = c.get("_child_skus", [])

        print(f"\n  [{i}/{totale}]  Creo configurabile  {sku}  —  {nome}")

        # Costruisci configurable_product_options
        config_options = build_config_options(
            attr_codes, child_skus, semplici_map, attr_map
        )

        # Deep copy del payload — include già media_gallery_entries dal JSON
        payload = json.loads(json.dumps(c["product"]))
        payload["extension_attributes"]["configurable_product_options"] = config_options

        # Aggiunge immagini scraping (cercate per SKU figlio)
        scraping_entries = build_scraping_entries(nome, child_skus, SCRAPING_DIR)
        existing = payload.get("media_gallery_entries", [])

        # Aggiorna position per le scraping (continuano dopo quelle esistenti)
        offset = len(existing)
        for j, entry in enumerate(scraping_entries):
            entry["position"] = offset + j + 1

        payload["media_gallery_entries"] = existing + scraping_entries

        print(f"    🖼️   Totale immagini: {len(payload['media_gallery_entries'])}")

        try:
            result = api_post(session, "products", {"product": payload})
            print(f"             ✅  entity_id={result.get('id')}")
            da_linkare.append({"config_sku": sku, "child_skus": child_skus})
        except RuntimeError as e:
            print(f"             ❌  ERRORE: {e}")

        time.sleep(RETRY_DELAY)

    return da_linkare


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  MAGENTO IMPORT — Semplici + Configurabili")
    print("=" * 60)

    with open(SIMPLE_JSON, encoding="utf-8") as f:
        semplici = json.load(f)
    with open(CONFIG_JSON, encoding="utf-8") as f:
        configurabili = json.load(f)

    print(f"\n📦  Semplici      : {len(semplici)}")
    print(f"🔗  Configurabili  : {len(configurabili)}")
    print(f"🖼️   Cartella img   : {IMAGES_DIR.resolve()}")
    print(f"🖼️   Cartella scraping: {SCRAPING_DIR.resolve()}")

    semplici_map = {s["product"]["sku"]: s for s in semplici}

    session = get_oauth_session()

    print("\n── Step 1: Recupero attribute_id da Magento ─────────────")
    attr_map = build_attr_map(session, configurabili)

    print("\n── Step 2: Creazione prodotti semplici ──────────────────")
    crea_semplici(session, semplici)

    print("\n── Step 3: Creazione prodotti configurabili ─────────────")
    da_linkare = crea_configurabili(session, configurabili, semplici_map, attr_map)

    print("\n── Step 4: Associazione semplici ai configurabili ───────")
    linka_semplici(session, da_linkare)

    print("\n✅  Import completato!")


if __name__ == "__main__":
    main()
