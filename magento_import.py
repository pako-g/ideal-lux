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

CATEGORIA    = "Lampada da soffitto"
SIMPLE_JSON  = f"./file/simple_products_{CATEGORIA.lower().replace(' ', '_')}.json"
CONFIG_JSON  = f"./file/configurable_products_{CATEGORIA.lower().replace(' ', '_')}.json"
IMAGES_DIR   = Path("./file/images")
SCRAPING_DIR = Path("./file/scraping")


# ─────────────────────────────────────────────
# UTILITY IMMAGINI
# ─────────────────────────────────────────────

def _trova_immagine(nome_prodotto: str, sku: str) -> Path | None:
    """Cerca l'immagine principale per nome+sku, con fallback glob."""
    sku_pulito = sku.replace("IL-", "")
    slug = re.sub(r"[^a-z0-9]+", "-", nome_prodotto.lower()).strip("-")
    path = IMAGES_DIR / f"{slug}-{sku_pulito}.jpg"
    if path.exists():
        return path
    matches = list(IMAGES_DIR.glob(f"*{sku_pulito}*.jpg"))
    print(f"    🔍  Fallback trovati: {[m.name for m in matches]}")
    return matches[0] if matches else None


def _to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _media_entry(path: Path, label: str, position: int, is_main: bool) -> dict:
    """Costruisce una singola entry media gallery."""
    return {
        "media_type": "image",
        "label":      label,
        "position":   position,
        "disabled":   False,
        "types":      ["image", "small_image", "thumbnail"] if is_main else [],
        "content": {
            "base64_encoded_data": _to_base64(path),
            "type": "image/jpeg",
            "name": path.name,
        },
    }


def build_media_entry_semplice(nome_prodotto: str, sku: str) -> list:
    """
    Restituisce una lista con la singola immagine principale del prodotto semplice.
    """
    print(f"    🏷️   Label immagine: {nome_prodotto}")
    path = _trova_immagine(nome_prodotto, sku)
    if not path:
        print(f"    ⚠️   Immagine non trovata per {sku}")
        return []
    print(f"    🖼️   Immagine semplice: {path.name}")
    return [_media_entry(path, nome_prodotto, position=1, is_main=True)]


def build_media_entries_configurabile(nome_prodotto: str, child_skus: list) -> list:
    """
    Restituisce tutte le immagini del configurabile:
      - immagine principale di ogni semplice figlio (da IMAGES_DIR)
      - immagini scraping (da SCRAPING_DIR)
    La prima immagine trovata è quella principale (types = image/small_image/thumbnail).
    """
    entries = []

    # Immagini principali dei semplici figli
    for sku in child_skus:
        path = _trova_immagine(nome_prodotto, sku)
        if path:
            print(f"    🖼️   Immagine semplice: {path.name}")
            entries.append(_media_entry(path, nome_prodotto, len(entries) + 1, is_main=not entries))

    # Immagini scraping
    scraping_imgs = []
    for sku in child_skus:
        sku_pulito = sku.replace("IL-", "")
        scraping_imgs.extend(sorted(SCRAPING_DIR.glob(f"*-{sku_pulito}-*.jpg")))

    for path in sorted(scraping_imgs):
        print(f"    🖼️   Immagine scraping: {path.name}")
        entries.append(_media_entry(path, nome_prodotto, len(entries) + 1, is_main=False))

    return entries


# ─────────────────────────────────────────────
# ATTRIBUTI CONFIGURABILI
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
# CREAZIONE PRODOTTI
# ─────────────────────────────────────────────

def crea_semplici(session: OAuth1Session, semplici: list) -> dict:
    """
    Crea ogni prodotto semplice via API con la sua immagine principale.
    Restituisce {sku: entity_id} per i prodotti creati con successo.
    """
    creati = {}
    totale = len(semplici)

    for i, s in enumerate(semplici, start=1):
        sku  = s["product"]["sku"]
        nome = s["product"]["name"]
        print(f"\n  [{i}/{totale}]  Creo semplice  {sku}  —  {nome}")

        payload = json.loads(json.dumps(s))
        payload["product"]["media_gallery_entries"] = build_media_entry_semplice(nome, sku)

        try:
            result = api_post(session, "products", payload)
            entity_id = result.get("id")
            creati[sku] = entity_id
            print(f"             ✅  entity_id={entity_id}")
        except RuntimeError as e:
            print(f"             ❌  ERRORE: {e}")

        time.sleep(RETRY_DELAY)

    return creati


def crea_configurabili(
    session: OAuth1Session,
    configurabili: list,
    semplici_map: dict,
    attr_map: dict,
) -> list:
    """
    Crea ogni configurabile via API con configurable_product_options e tutte le immagini.
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

        payload = json.loads(json.dumps(c["product"]))
        payload["extension_attributes"]["configurable_product_options"] = build_config_options(
            attr_codes, child_skus, semplici_map, attr_map
        )
        payload["media_gallery_entries"] = build_media_entries_configurabile(nome, child_skus)

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

    print(f"\n📦  Semplici       : {len(semplici)}")
    print(f"🔗  Configurabili  : {len(configurabili)}")
    print(f"🖼️   Cartella img   : {IMAGES_DIR.resolve()}")
    print(f"🖼️   Cartella scraping: {SCRAPING_DIR.resolve()}")

    semplici_map = {s["product"]["sku"]: s for s in semplici}
    session      = get_oauth_session()

    print("\n── Step 1: Recupero attribute_id da Magento ─────────────")
    attr_map = build_attr_map(session, configurabili)

    print("\n── Step 2: Creazione prodotti semplici ──────────────────")
    crea_semplici(session, semplici)

    print("\n── Step 3: Creazione prodotti configurabili ─────────────")
    da_linkare = crea_configurabili(session, configurabili, semplici_map, attr_map)

    print("\n── Step 4: Associazione semplici ai configurabili ───────")
    risultati = linka_semplici(session, da_linkare)

    falliti = [sku for sku, ok in risultati.items() if not ok]
    if falliti:
        print(f"\n⚠️   Link falliti ({len(falliti)}): {falliti}")
    else:
        print("\n✅  Import completato!")


if __name__ == "__main__":
    main()