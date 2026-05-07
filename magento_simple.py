"""
Generatore JSON — Prodotti SEMPLICI Magento
Famiglia: A-LINE (4 varianti)

Attributi configurabili usati:
  color               → Finitura (Bianco / Nero)
  config_dimensioni   → Dimensione diffusore (D13 / D30)
  config_attacco_lamp → Attacco portalampada (GU10 / E27)

Output: aline_simple_products.json
"""

import json
import re
import pandas as pd
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH        = "./file/giacenzeECommerce.csv"
OUTPUT_PATH     = "./file/aline_simple_products.json"

MARCA           = "Ideal Lux"
ATTRIBUTE_SET_ID = 4       # adatta al tuo Attribute Set in Magento
WEBSITE_IDS     = [1]


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def load_famiglia(csv_path: str, famiglia: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = df[df["Famiglia Articolo"] == famiglia].copy()

    df["sku"] = df["Nr"].astype(str).str[-6:]

    df["prezzo"] = (
        df["Prezzo Al Pubblico"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

    for col in ["Peso Netto", "Peso Lordo"]:
        df[col] = (
            df[col].astype(str)
            .str.replace(",", ".", regex=False)
            .pipe(pd.to_numeric, errors="coerce")
        )

    df["qty"]         = df["Magazzino"].clip(lower=0).astype(int)
    df["is_in_stock"] = (df["qty"] > 0).astype(int)

    return df


def estrai_modello(descrizione: str, finitura: str) -> str:
    """'A-LINE_SP1_D13_BIANCO', 'BIANCO' → 'A-line sp1 d13'"""
    raw = descrizione.replace("_" + finitura, "").replace("_", " ").lower()
    return raw[0].upper() + raw[1:] if raw else raw


def estrai_dimensione(descrizione: str, finitura: str) -> str:
    """
    Estrae la dimensione (D13, D30, ecc.) dalla descrizione.
    'A-LINE_SP1_D13_BIANCO', 'BIANCO' → 'D13'
    Cerca il token che inizia con D seguito da cifre.
    """
    modello = descrizione.replace("_" + finitura, "")
    match = re.search(r'_(D\d+)$', modello)
    return match.group(1).upper() if match else ""


def build_nome_semplice(modello: str, finitura: str, attacco: str) -> str:
    """Ideal Lux A-line sp1 d13-Bianco-GU10"""
    return f"{MARCA} {modello}-{finitura.capitalize()}-{attacco}"


def build_url_key(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def build_url_immagine(ean: str, descrizione: str) -> str:
    sku6    = str(ean)[-6:]
    desc_up = descrizione.upper()
    return (
        f"https://www.ideal-lux.com/assets/products/web/"
        f"{sku6}_WEB001_{desc_up}.png"
    )


# ─────────────────────────────────────────────
# BUILD PRODOTTO SEMPLICE
# ─────────────────────────────────────────────

def build_simple(row: pd.Series) -> dict:
    modello   = estrai_modello(row["Descrizione"], row["Finitura"])
    dimensione = estrai_dimensione(row["Descrizione"], row["Finitura"])
    nome      = build_nome_semplice(modello, row["Finitura"], row["Attacco Portalampada"])
    img_url   = build_url_immagine(row["Nr"], row["Descrizione"])

    return {
        "product": {
            "sku":              row["sku"],
            "name":             nome,
            "attribute_set_id": ATTRIBUTE_SET_ID,
            "price":            float(row["prezzo"]),
            "status":           1,    # abilitato
            "visibility":       1,    # Not Visible Individually
            "type_id":          "simple",
            "weight":           float(row["Peso Netto"]) if pd.notna(row["Peso Netto"]) else 0,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "stock_item": {
                    "qty":          int(row["qty"]),
                    "is_in_stock":  int(row["is_in_stock"]),
                    "manage_stock": True,
                }
            },
            "custom_attributes": [
                # ── Attributi configurabili ──────────────────────────
                {"attribute_code": "color",               "value": row["Finitura"].capitalize()},
                {"attribute_code": "config_dimensioni",   "value": dimensione},
                {"attribute_code": "config_attacco_lamp", "value": row["Attacco Portalampada"]},
                # ── Attributi informativi ────────────────────────────
                {"attribute_code": "ean",                 "value": str(row["Nr"])},
                {"attribute_code": "manufacturer",        "value": MARCA},
                {"attribute_code": "peso_lordo",          "value": str(row["Peso Lordo"])},
                {"attribute_code": "dimensione_articolo", "value": row["Dimensione Articolo"]},
                {"attribute_code": "url_key",             "value": build_url_key(nome)},
            ],
            "media_gallery_entries": [
                {
                    "media_type": "image",
                    "label":      nome,
                    "position":   1,
                    "disabled":   False,
                    "types":      ["image", "small_image", "thumbnail"],
                    "content": {
                        "type": "image/png",
                        "name": f"{row['sku']}_WEB001.png",
                        "url":  img_url,
                    }
                }
            ]
        }
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    Path("./file").mkdir(exist_ok=True)

    FAMIGLIA = "A-LINE"
    varianti = load_famiglia(CSV_PATH, FAMIGLIA)
    semplici = [build_simple(row) for _, row in varianti.iterrows()]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(semplici, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_PATH}")
    print(f"    Prodotti generati: {len(semplici)}")
    print()
    for s in semplici:
        p  = s["product"]
        ca = {a["attribute_code"]: a["value"] for a in p["custom_attributes"]}
        print(
            f"  [{p['sku']}]  {p['name']}\n"
            f"           color={ca['color']}  "
            f"dimensioni={ca['config_dimensioni']}  "
            f"attacco={ca['config_attacco_lamp']}  "
            f"€{p['price']}  qty={p['extension_attributes']['stock_item']['qty']}\n"
        )
