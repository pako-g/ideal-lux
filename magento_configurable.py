"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Legge: ./file/aline_simple_products.json
Scrive: ./file/configurable_products.json

Logica:
  - Raggruppa i semplici per sottofamiglia (stesso modello/dimensione)
  - Per ogni gruppo crea un configurabile con i dati base
  - configurable_product_options e linking semplici → gestiti a runtime da magento_import.py
  - SKU configurabile: IL-CONFIG-001, IL-CONFIG-002, ...
  - Titolo: "Ideal Lux <Modello> [Led] <Categoria>"
"""

import json
import re
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

INPUT_JSON       = "./file/aline_simple_products.json"
OUTPUT_JSON      = "./file/configurable_products.json"

ATTRIBUTE_SET_ID = 4
WEBSITE_IDS      = [1]

# Attributi che NON sono assi di variazione del configurabile
ESCLUDI_DA_CONFIG = {"lamp_ean", "manufacturer", "url_key"}


# ─────────────────────────────────────────────
# UTILITY: COSTRUZIONE TITOLO CONFIGURABILE
# ─────────────────────────────────────────────

def build_titolo(nome_semplice: str) -> str:
    """
    Ricava il titolo del configurabile dal nome di un prodotto semplice.

    Esempi:
      "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
      → "Ideal Lux Agos Pt H60 Led Lampada Da Terra"

      "Ideal Lux A-line sp1 d13-Bianco-GU10 Lampada da Parete"
      → "Ideal Lux A-Line Sp1 D13 Lampada Da Parete"
    """
    nome = nome_semplice.strip()

    # 1. Presenza LED
    is_led = bool(re.search(r'\bLED\b', nome, re.IGNORECASE))

    # 2. Categoria lampada in fondo (es. "Lampada Da Terra", "Lampada Da Parete" …)
    cat_match = re.search(r'(Lampada\s+[Dd]a\s+\w+)', nome, re.IGNORECASE)
    categoria = cat_match.group(0).title() if cat_match else ""

    # 3. Rimuovi la parte dopo il trattino (varianti: colore, attacco)
    nome_pulito = re.split(r'-[A-Z]', nome)[0].strip()

    # 4. Rimuovi la categoria dalla parte pulita
    if categoria:
        nome_pulito = re.sub(re.escape(categoria), '', nome_pulito, flags=re.IGNORECASE).strip()

    # 5. Rimuovi temperature (3000k, 4000k, 2700k-5700k) e "LED"
    nome_pulito = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', nome_pulito)
    nome_pulito = re.sub(r'\bLED\b', '', nome_pulito, flags=re.IGNORECASE)
    nome_pulito = re.sub(r'\s{2,}', ' ', nome_pulito).strip()

    # 6. Titolizza ogni token
    modello_str = " ".join(t[0].upper() + t[1:] for t in nome_pulito.split() if t)

    # 7. Componi titolo finale
    led_str = " Led" if is_led else ""
    return f"{modello_str}{led_str} {categoria}".strip()


# ─────────────────────────────────────────────
# UTILITY: ATTRIBUTI CONFIGURABILI
# ─────────────────────────────────────────────

def get_config_attribute_codes(semplici: list) -> list:
    """
    Raccoglie tutti gli attribute_code dei semplici del gruppo,
    escludendo quelli non configurabili.
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

def build_configurable(config_sku: str, semplici: list) -> dict:
    """
    Costruisce il dict del prodotto configurabile da salvare nel JSON.

    Contiene solo i dati base del prodotto + metadati per magento_import.py:
      _child_skus  → SKU dei semplici da associare
      _attr_codes  → codici attributo da risolvere a runtime (attribute_id numerico)
    """
    titolo     = build_titolo(semplici[0]["product"]["name"])
    url_key    = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")
    child_skus = [s["product"]["sku"] for s in semplici]
    attr_codes = get_config_attribute_codes(semplici)

    # Recupera manufacturer dal primo semplice
    manufacturer_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "manufacturer"),
        None
    )
    if manufacturer_val:
        prodotto["product"]["custom_attributes"].append(
            {"attribute_code": "manufacturer", "value": manufacturer_val}
        )

    return {
        "product": {
            "sku": config_sku,
            "name": titolo,
            "attribute_set_id": ATTRIBUTE_SET_ID,
            "status": 1,
            "visibility": 4,          # Catalog, Search
            "type_id": "configurable",
            "weight": 0,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
            },
            "custom_attributes": [
                {"attribute_code": "url_key", "value": url_key}
            ],
        },
        "_child_skus": child_skus,    # usato da magento_import.py per il linking
        "_attr_codes": attr_codes,    # risolti in attribute_id numerico a runtime
    }


# ─────────────────────────────────────────────
# RAGGRUPPAMENTO SEMPLICI → SOTTOFAMIGLIE
# ─────────────────────────────────────────────

def estrai_sottofamiglia(nome: str) -> str:
    """
    Chiave di raggruppamento dal nome del prodotto semplice.

    Es.: "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
         → "ideal lux agos pt h60 lampada da terra"
    """
    base = re.split(r'-[A-Z]', nome)[0].strip()
    base = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', base)
    base = re.sub(r'\bLED\b', '', base, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', base).strip().lower()


def raggruppa_per_sottofamiglia(semplici: list) -> dict:
    gruppi = {}
    for s in semplici:
        key = estrai_sottofamiglia(s["product"]["name"])
        gruppi.setdefault(key, []).append(s)
    return gruppi


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)

    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    gruppi = raggruppa_per_sottofamiglia(semplici_tutti)
    print(f"🔗  Gruppi (configurabili) trovati: {len(gruppi)}\n")

    configurabili = []
    for idx, (key, gruppo) in enumerate(sorted(gruppi.items()), start=1):
        config_sku = f"IL-CONFIG-{idx:03d}"
        config     = build_configurable(config_sku, gruppo)
        configurabili.append(config)

        print(
            f"  [{config_sku}]  {config['product']['name']}\n"
            f"           attributi varianti : {config['_attr_codes']}\n"
            f"           semplici ({len(config['_child_skus'])}): {config['_child_skus']}\n"
        )

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_JSON}  ({len(configurabili)} configurabili generati)")


if __name__ == "__main__":
    main()
