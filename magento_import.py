"""
magento_import.py — Import completo prodotti in Magento 2

Flusso:
  1. Legge aline_simple_products.json e configurable_products.json
  2. Recupera via API gli attribute_id numerici per ogni attributo variante
  3. Crea i prodotti semplici  → POST /rest/V1/products
  4. Crea i prodotti configurabili con configurable_product_options → POST /rest/V1/products
  5. Associa i semplici al configurabile → POST /rest/V1/configurable-products/{sku}/child
"""

import json
import os
import time
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

SIMPLE_JSON      = "./file/aline_simple_products.json"
CONFIG_JSON      = "./file/configurable_products.json"

MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")
RETRY_DELAY      = 1.0   # secondi tra una chiamata e l'altra
MAX_RETRIES      = 3


# ─────────────────────────────────────────────
# OAUTH SESSION
# ─────────────────────────────────────────────

def get_oauth_session() -> OAuth1Session:
    return OAuth1Session(
        client_key            = os.getenv("MAGENTO_CONSUMER_KEY"),
        client_secret         = os.getenv("MAGENTO_CONSUMER_SECRET"),
        resource_owner_key    = os.getenv("MAGENTO_ACCESS_TOKEN"),
        resource_owner_secret = os.getenv("MAGENTO_TOKEN_SECRET"),
        signature_method      = "HMAC-SHA256",
    )


# ─────────────────────────────────────────────
# UTILITY API
# ─────────────────────────────────────────────

def api_post(session: OAuth1Session, endpoint: str, payload: dict) -> dict:
    """POST con retry su errori temporanei (5xx)."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/{endpoint}"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.post(url, json=payload, verify=False)
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            print(f"    ⚠️  {resp.status_code} — retry {attempt}/{MAX_RETRIES}...")
            time.sleep(RETRY_DELAY * attempt)
            continue
        # Errore non recuperabile
        raise RuntimeError(
            f"POST /rest/V1/{endpoint} → {resp.status_code}\n{resp.text}"
        )


def get_attribute_info(session: OAuth1Session, attribute_code: str) -> dict:
    """
    Restituisce:
      {
        "attribute_id": "93",           # ID numerico stringa
        "options": {"1840": "Bianco", "1844": "Nero", ...}
      }
    """
    url = f"{MAGENTO_BASE_URL}/rest/V1/products/attributes/{attribute_code}"
    resp = session.get(url, verify=False)
    resp.raise_for_status()
    data = resp.json()
    options = {
        opt["value"]: opt["label"]
        for opt in data.get("options", [])
        if opt.get("value")
    }
    return {
        "attribute_id": str(data["attribute_id"]),
        "options": options,
    }


# ─────────────────────────────────────────────
# STEP 1 — RISOLVI ATTRIBUTE_ID
# ─────────────────────────────────────────────

def build_attr_map(session: OAuth1Session, configurabili: list) -> dict:
    """
    Recupera attribute_id e opzioni per tutti i codici attributo
    presenti nei configurabili.

    Restituisce:
      {
        "color":                   {"attribute_id": "93",  "options": {...}},
        "config_attacco_lamp":     {"attribute_id": "150", "options": {...}},
        "config_temperatura_colore": {...},
        ...
      }
    """
    # Raccogli tutti i codici unici
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
    Crea ogni prodotto semplice via API.
    Restituisce un dict {sku: entity_id} per i semplici creati con successo.
    """
    creati = {}
    totale = len(semplici)

    for i, s in enumerate(semplici, start=1):
        sku  = s["product"]["sku"]
        nome = s["product"]["name"]
        print(f"  [{i}/{totale}]  Creo semplice  {sku}  —  {nome}")
        try:
            result = api_post(session, "products", s)
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
    semplici_map: dict,    # sku → prodotto semplice
    attr_map: dict,        # code → {attribute_id, options}
) -> list:
    """
    Costruisce la lista configurable_product_options da passare all'API.

    Per ogni attributo raccoglie i value_index distinti dai semplici associati.
    """
    options = []
    for pos, code in enumerate(attr_codes):
        info = attr_map.get(code)
        if not info:
            print(f"    ⚠️  attribute_id non trovato per '{code}', salto")
            continue

        # Raccoglie i valori distinti dai semplici di questo configurabile
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
            "label": code.replace("_", " ").title(),
            "position": pos,
            "values": [{"value_index": v} for v in sorted(valori)],
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
    Per ogni configurabile:
      1. Aggiunge configurable_product_options al payload
      2. POST /rest/V1/products
      3. Restituisce lista di {config_sku, child_skus} per il linking
    """
    da_linkare = []
    totale = len(configurabili)

    for i, c in enumerate(configurabili, start=1):
        sku        = c["product"]["sku"]
        nome       = c["product"]["name"]
        attr_codes = c.get("_attr_codes", [])
        child_skus = c.get("_child_skus", [])

        print(f"  [{i}/{totale}]  Creo configurabile  {sku}  —  {nome}")

        # Costruisci configurable_product_options
        config_options = build_config_options(
            attr_codes, child_skus, semplici_map, attr_map
        )

        # Clona il payload e aggiungi le options
        payload = json.loads(json.dumps(c["product"]))   # deep copy
        payload["extension_attributes"]["configurable_product_options"] = config_options

        try:
            result = api_post(session, "products", {"product": payload})
            print(f"             ✅  entity_id={result.get('id')}")
            da_linkare.append({"config_sku": sku, "child_skus": child_skus})
        except RuntimeError as e:
            print(f"             ❌  ERRORE: {e}")

        time.sleep(RETRY_DELAY)

    return da_linkare


# ─────────────────────────────────────────────
# STEP 5 — ASSOCIA SEMPLICI AL CONFIGURABILE
# ─────────────────────────────────────────────

def linka_semplici(session: OAuth1Session, da_linkare: list) -> None:
    """
    POST /rest/V1/configurable-products/{config_sku}/child
    per ogni semplice da associare.
    """
    for item in da_linkare:
        config_sku = item["config_sku"]
        child_skus = item["child_skus"]
        print(f"\n  🔗  Associo semplici a  {config_sku}  ({len(child_skus)} prodotti)")

        for sku in child_skus:
            endpoint = f"configurable-products/{config_sku}/child"
            try:
                api_post(session, endpoint, {"childSku": sku})
                print(f"       ✅  {sku}")
            except RuntimeError as e:
                print(f"       ❌  {sku}  —  {e}")
            time.sleep(RETRY_DELAY)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  MAGENTO IMPORT — Semplici + Configurabili")
    print("=" * 60)

    # Carica JSON
    with open(SIMPLE_JSON, encoding="utf-8") as f:
        semplici = json.load(f)
    with open(CONFIG_JSON, encoding="utf-8") as f:
        configurabili = json.load(f)

    print(f"\n📦  Semplici    : {len(semplici)}")
    print(f"🔗  Configurabili: {len(configurabili)}")

    # Mappa sku → semplice (per build_config_options)
    semplici_map = {s["product"]["sku"]: s for s in semplici}

    # Sessione OAuth
    session = get_oauth_session()

    # ── Step 1: risolvi attribute_id ──────────────────────────
    print("\n── Step 1: Recupero attribute_id da Magento ─────────────")
    attr_map = build_attr_map(session, configurabili)

    # ── Step 2: crea semplici ─────────────────────────────────
    print("\n── Step 2: Creazione prodotti semplici ──────────────────")
    crea_semplici(session, semplici)

    # ── Step 3+4: crea configurabili ─────────────────────────
    print("\n── Step 3: Creazione prodotti configurabili ─────────────")
    da_linkare = crea_configurabili(session, configurabili, semplici_map, attr_map)

    # ── Step 5: linka semplici ───────────────────────────────
    print("\n── Step 4: Associazione semplici ai configurabili ───────")
    linka_semplici(session, da_linkare)

    print("\n✅  Import completato!")


if __name__ == "__main__":
    main()
