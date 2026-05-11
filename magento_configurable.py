"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Legge: ./file/aline_simple_products.json
Scrive: ./file/configurable_products.json

Logica:
  - Raggruppa i semplici per sottofamiglia (stesso modello/dimensione)
  - Per ogni gruppo crea un configurabile
  - Gli attributi configurabili sono tutti gli attribute_code dei semplici
    ESCLUSI: lamp_ean, manufacturer, url_key (non sono assi di variazione)
  - SKU configurabile: IL-CONFIG-001, IL-CONFIG-002, ...
  - Titolo: "Ideal Lux <Modello> [Led] <Categoria>"
  - Prezzo = prezzo minimo tra i semplici del gruppo
"""

import json
import re
import os
from pathlib import Path
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

INPUT_JSON   = "./file/aline_simple_products.json"
OUTPUT_JSON  = "./file/configurable_products.json"

ATTRIBUTE_SET_ID = 263
WEBSITE_IDS      = [1]
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")

# Attributi che NON diventano assi di variazione del configurabile
ESCLUDI_DA_CONFIG = {"lamp_ean", "manufacturer", "url_key"}


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
# UTILITY: RECUPERO LABEL DA MAGENTO
# ─────────────────────────────────────────────

def get_attribute_options(session: OAuth1Session, attribute_code: str) -> dict:
    """Restituisce {option_id: label} per un attributo select."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/products/attributes/{attribute_code}"
    resp = session.get(url, verify=False)
    resp.raise_for_status()
    data = resp.json()
    result = {}
    for opt in data.get("options", []):
        if opt.get("value"):
            result[opt["value"]] = opt["label"]
    return result


# ─────────────────────────────────────────────
# UTILITY: COSTRUZIONE TITOLO CONFIGURABILE
# ─────────────────────────────────────────────

def build_titolo(nome_semplice: str) -> str:
    """
    Ricava il titolo del configurabile dal nome di un prodotto semplice.

    Esempi input  → output:
      "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
      → "Ideal Lux Agos H60 Led Lampada Da Terra"

      "Ideal Lux A-line sp1 d13-Bianco-GU10 Lampada da Parete"
      → "Ideal Lux A-line Sp1 D13 Lampada da Parete"

    Strategia:
      1. Isola il prefisso "Ideal Lux <Famiglia>"
      2. Cerca la porzione di categoria (Lampada da ...) in fondo
      3. Estrae la parte centrale (modello/dimensione), rimuove colore e K
      4. Se "LED" o "Led" era presente → aggiunge "Led" prima della categoria
    """
    nome = nome_semplice.strip()

    # 1. Categoria lampada in fondo (es. "Lampada Da Terra", "Lampada Da Parete" …)
    cat_match = re.search(r'(Lampada\s+[Dd]a\s+\w+)', nome, re.IGNORECASE)
    categoria = cat_match.group(0).title() if cat_match else ""

    # 2. Presenza LED
    is_led = bool(re.search(r'\bLED\b', nome, re.IGNORECASE))

    # 3. Rimuovi la parte dopo il trattino (es. "-Antracite-LED", "-Bianco-GU10")
    nome_pulito = re.split(r'-[A-Z]', nome)[0].strip()

    # 4. Rimuovi la categoria dalla parte pulita
    if categoria:
        nome_pulito = re.sub(re.escape(categoria), '', nome_pulito, flags=re.IGNORECASE).strip()

    # 5. Rimuovi token inutili: temperature (3000k, 4000k ecc.), "LED"
    nome_pulito = re.sub(r'\b\d{4}[Kk]\b', '', nome_pulito)
    nome_pulito = re.sub(r'\bLED\b', '', nome_pulito, flags=re.IGNORECASE)
    nome_pulito = re.sub(r'\s{2,}', ' ', nome_pulito).strip()

    # 6. Titolizza ogni token (mantieni maiuscola su H60, D13, GU10…)
    token_titolizzati = []
    for t in nome_pulito.split():
        token_titolizzati.append(t[0].upper() + t[1:] if t else t)
    modello_str = " ".join(token_titolizzati)

    # 7. Componi titolo finale
    led_str = " Led" if is_led else ""
    titolo = f"{modello_str}{led_str} {categoria}".strip()
    return titolo


# ─────────────────────────────────────────────
# UTILITY: ESTRAZIONE ATTRIBUTI CONFIGURABILI
# ─────────────────────────────────────────────

def get_config_attribute_codes(semplici: list) -> list:
    """
    Raccoglie tutti gli attribute_code presenti nei semplici del gruppo,
    escludendo quelli non configurabili (ean, manufacturer, url_key).
    Restituisce la lista in ordine deterministico.
    """
    codes = set()
    for s in semplici:
        for attr in s["product"]["custom_attributes"]:
            code = attr["attribute_code"]
            if code not in ESCLUDI_DA_CONFIG:
                codes.add(code)
    return sorted(codes)


# ─────────────────────────────────────────────
# BUILD PRODOTTO CONFIGURABILE
# ─────────────────────────────────────────────

def build_configurable(
    config_sku: str,
    semplici: list,
    id_map: dict,          # attribute_code → {option_id → label}  (per info)
) -> dict:
    """
    Costruisce il dict del prodotto configurabile Magento 2.

    Struttura API:
      POST /rest/V1/products
      {
        "product": { ... },
        "extension_attributes": {
          "configurable_product_options": [...],
          "configurable_product_links": [...]
        }
      }

    Nota: configurable_product_links vuole gli ID numerici dei semplici.
    Se non li hai ancora (prodotti appena creati) puoi passare gli SKU
    e usare un secondo script per linkare via
    POST /rest/V1/configurable-products/{sku}/child
    """

    # --- Titolo: usa il nome del primo semplice come base ---
    primo_nome = semplici[0]["product"]["name"]
    titolo = build_titolo(primo_nome)

    # --- Attributi configurabili ---
    attr_codes = get_config_attribute_codes(semplici)

    # configurable_product_options: lista degli attributi variante
    # (position e attribute_id sono placeholder; Magento li risolve via attribute_code)
    config_options = []
    for pos, code in enumerate(attr_codes):
        # Raccoglie i valori distinti per questo attributo tra i semplici
        valori_distinti = list({
            attr["value"]
            for s in semplici
            for attr in s["product"]["custom_attributes"]
            if attr["attribute_code"] == code
        })
        config_options.append({
            "attribute_id": code,          # Magento accetta anche il code come stringa
            "attribute_code": code,
            "label": code.replace("_", " ").title(),
            "position": pos,
            "values": [{"value_index": v} for v in valori_distinti],
        })

    # configurable_product_links: SKU dei semplici associati
    child_skus = [s["product"]["sku"] for s in semplici]

    # url_key del configurabile: slug del titolo
    url_key = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")

    prodotto = {
        "product": {
            "sku": config_sku,
            "name": titolo,
            "attribute_set_id": ATTRIBUTE_SET_ID,
            "status": 0,
            "visibility": 4,           # Catalog, Search
            "type_id": "configurable",
            "weight": 0,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "configurable_product_options": config_options,
                "configurable_product_links": [],  # compilato dopo creazione semplici
            },
            "custom_attributes": [
                {
                    "attribute_code": "url_key",
                    "value": url_key,
                }
            ],
        },
        # Lista SKU separata per comodità (usata dallo script di linking)
        "_child_skus": child_skus,
    }

    return prodotto


# ─────────────────────────────────────────────
# RAGGRUPPAMENTO SEMPLICI → SOTTOFAMIGLIE
# ─────────────────────────────────────────────

def estrai_sottofamiglia(nome: str) -> str:
    """
    Ricava la chiave di raggruppamento dal nome del prodotto semplice.

    Es.: "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
         → "ideal lux agos pt h60 lampada da terra"

    Strategia:
      - Rimuovi la parte dopo il trattino (varianti: colore, attacco)
      - Rimuovi temperatura (3000k, 4000k, 2700k-5700k …)
      - Rimuovi "LED"
      - Lowercase e strip
    """
    # Rimuovi varianti dopo trattino
    base = re.split(r'-[A-Z]', nome)[0].strip()
    # Rimuovi temperature
    base = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', base)
    # Rimuovi LED
    base = re.sub(r'\bLED\b', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\s{2,}', ' ', base).strip().lower()
    return base


def raggruppa_per_sottofamiglia(semplici: list) -> dict:
    """
    Restituisce { sottofamiglia_key: [prodotto, ...] }
    """
    gruppi = {}
    for s in semplici:
        key = estrai_sottofamiglia(s["product"]["name"])
        gruppi.setdefault(key, []).append(s)
    return gruppi


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # 1. Leggi JSON semplici
    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)

    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    # 2. Connessione OAuth (opzionale — serve solo per risolvere label attributi)
    try:
        session = get_oauth_session()
        id_map = {}  # attribute_code → {id: label}
        # Recupera mappe per gli attributi configurabili comuni
        for code in ["color", "config_attacco_lamp", "config_dimensioni",
                     "config_temperatura_colore", "config_tipo"]:
            try:
                id_map[code] = get_attribute_options(session, code)
            except Exception:
                id_map[code] = {}
    except Exception:
        print("⚠️   OAuth non disponibile — id_map vuota (non bloccante)")
        id_map = {}

    # 3. Raggruppa semplici per sottofamiglia
    gruppi = raggruppa_per_sottofamiglia(semplici_tutti)
    print(f"🔗  Gruppi (configurabili) trovati: {len(gruppi)}")

    # 4. Genera configurabili
    configurabili = []
    for idx, (key, semplici_gruppo) in enumerate(sorted(gruppi.items()), start=1):
        config_sku = f"IL-CONFIG-{idx:03d}"
        config = build_configurable(config_sku, semplici_gruppo, id_map)
        configurabili.append(config)

        # Log
        child_skus = config["_child_skus"]
        attrs = [o["attribute_code"] for o in
                 config["product"]["extension_attributes"]["configurable_product_options"]]
        print(
            f"  [{config_sku}]  {config['product']['name']}\n"
            f"           attributi varianti: {attrs}\n"
            f"           semplici ({len(child_skus)}): {child_skus}\n"
        )

    # 5. Salva JSON
    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {OUTPUT_JSON}")
    print(f"    Configurabili generati: {len(configurabili)}")


if __name__ == "__main__":
    main()
