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
import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import urllib3

# Disabilita il warning SSL per certificati self-signed (solo sviluppo locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH        = "./file/giacenzeECommerce.csv"
OUTPUT_PATH     = "./file/aline_simple_products.json"

MARCA           = "Ideal Lux"
ATTRIBUTE_SET_ID = 4       # adatta al tuo Attribute Set in Magento
WEBSITE_IDS     = [1]

MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")


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
# RECUPERO OPZIONI ATTRIBUTO DA MAGENTO
# ─────────────────────────────────────────────

def get_attribute_options(session: OAuth1Session, attribute_code: str) -> dict:
    """
    Recupera le opzioni di un attributo select da Magento e restituisce
    un dizionario label → ID numerico (stringa).

    Esempio:
      get_attribute_options(session, "color")
      → {"Bianco": "49", "Nero": "50"}

    Se un valore non viene trovato nella mappa, build_simple() solleverà
    un KeyError esplicito — meglio fallire subito che scrivere un valore sbagliato.
    """
    url      = f"{MAGENTO_BASE_URL}/rest/V1/products/attributes/{attribute_code}"
    response = session.get(url, verify=False)
    response.raise_for_status()

    data    = response.json()
    options = data.get("options", [])

    # Salta la voce vuota che Magento aggiunge sempre come prima opzione
    return {
        opt["label"]: opt["value"]
        for opt in options
        if opt["label"] and opt["value"]
    }


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


def load_categoria(csv_path: str, categoria: str, escludi: list = []) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = df[df["Categoria Articolo"] == categoria].copy()
    if escludi:
        df = df[~df["Famiglia Articolo"].isin(escludi)]

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



# Famiglie dove la dimensione nella descrizione è D ma va letta come Lunghezza
FAMIGLIE_LUNGHEZZA = {"SASSO"}

def estrai_dimensione(descrizione: str, finitura: str, famiglia: str,
                      famiglia_varianti: pd.DataFrame) -> str:
    modello = descrizione.replace("_" + finitura, "")

    # Caso SASSO: D nella descrizione ma è Lunghezza
    if famiglia in FAMIGLIE_LUNGHEZZA:
        match = re.search(r'_(D\d+)$', modello)
        if match:
            return f"Lunghezza {match.group(1)[1:]}cm"

    # Caso normale: D o H nella descrizione
    match = re.search(r'_(D\d+|H\d+)$', modello)
    if match:
        token = match.group(1)
        numero = token[1:]
        return f"Diametro {numero}cm" if token.startswith("D") else f"Altezza {numero}cm"

    # Nessun token in descrizione: cerca quale misura cambia in Dimensione Articolo
    def estrai_misura(dim_str, prefix):
        m = re.search(rf'{prefix}\s+(\d+)', str(dim_str))
        return int(m.group(1)) if m else None

    for prefix in ["D", "H", "L"]:
        valori = famiglia_varianti["Dimensione Articolo"].apply(
            lambda x: estrai_misura(x, prefix)
        )
        if valori.nunique() > 1:
            val = estrai_misura(
                famiglia_varianti.loc[
                    famiglia_varianti["Descrizione"] == descrizione,
                    "Dimensione Articolo"
                ].iloc[0],
                prefix
            )
            label = {"D": "Diametro", "H": "Altezza", "L": "Lunghezza"}[prefix]
            return f"{label} {val}cm"

    return ""

FAMIGLIE_TIPO = {
    "EDO":       r'_(?:PT1_)(ROUND|SQUARE)_',
    "ESSENCE":   r'_PT_(ROUND|SQUARE)_',
    "TWIGGY":    r'_(LINE|SPHERE)_',
    "BINOMIO":   r'_(LED_PT4|PT3)_',
    "DRIFTWOOD": r'_(PT1|PT3)$',
}

def estrai_tipo(descrizione: str, famiglia: str) -> str:
    pattern = FAMIGLIE_TIPO.get(famiglia, "")
    if not pattern:
        return ""
    match = re.search(pattern, descrizione)
    return match.group(1).capitalize() if match else ""


def estrai_temperatura(descrizione: str) -> str:
    match = re.search(r'_(\d{4}K(?:-\d{4}K)?)(?:_|$)', descrizione)
    return match.group(1) if match else ""


def build_nome_semplice(modello: str, finitura: str, attacco: str, tipo: str = "") -> str:
    tipo_str = f"-{tipo.capitalize()}" if tipo else ""
    return f"{MARCA} {modello}-{tipo_str}-{finitura.capitalize()}-{attacco}"


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

def build_simple(row: pd.Series, color_map: dict, attacco_map: dict,
                 dimensioni_map: dict, manufacturer_map: dict,
                 tipo_map: dict, temp_map: dict,
                 famiglia_varianti: pd.DataFrame) -> dict:

    famiglia   = row["Famiglia Articolo"]
    dimensione = estrai_dimensione(row["Descrizione"], row["Finitura"],
                                   famiglia, famiglia_varianti)
    tipo       = estrai_tipo(row["Descrizione"], famiglia)
    temperatura = estrai_temperatura(row["Descrizione"])
    modello    = estrai_modello(row["Descrizione"], row["Finitura"])
    nome       = build_nome_semplice(modello, row["Finitura"],
                                     row["Attacco Portalampada"], tipo)
    img_url    = build_url_immagine(row["Nr"], row["Descrizione"])

    color_id        = color_map[row["Finitura"].capitalize()]
    attacco_val     = row["Attacco Portalampada"]
    manufacturer_id = manufacturer_map[MARCA]

    # Attributi configurabili — solo se presenti
    attrs_config = [
        {"attribute_code": "color", "value": color_id},
    ]
    if attacco_val and pd.notna(attacco_val):
        attrs_config.append(
            {"attribute_code": "config_attacco_lamp", "value": attacco_map[attacco_val]}
        )
    if dimensione:
        attrs_config.append(
            {"attribute_code": "config_dimensioni", "value": dimensioni_map[dimensione]}
        )
    if tipo:
        attrs_config.append(
            {"attribute_code": "config_tipo", "value": tipo_map[tipo.capitalize()]}
        )
    if temperatura:
        attrs_config.append(
            {"attribute_code": "config_temperatura_colore", "value": temp_map[temperatura]}
        )

    return {
        "product": {
            "sku":              row["sku"],
            "name":             nome,
            "attribute_set_id": ATTRIBUTE_SET_ID,
            "price":            float(row["prezzo"]),
            "status":           0,
            "visibility":       1,
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
            "custom_attributes": attrs_config + [
                {"attribute_code": "lamp_ean",      "value": str(row["Nr"])},
                {"attribute_code": "manufacturer",  "value": manufacturer_id},
                {"attribute_code": "url_key",       "value": build_url_key(nome) + "-" + row["sku"]},
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

    # 1. Connessione OAuth e recupero mappa colori
    session   = get_oauth_session()

    color_map = get_attribute_options(session, "color")
    attacco_map = get_attribute_options(session, "config_attacco_lamp")
    dimensioni_map = get_attribute_options(session, "config_dimensioni")
    tipo_map = get_attribute_options(session, "config_tipo")
    temp_map = get_attribute_options(session, "config_temperatura_colore")
    manufacturer_map = get_attribute_options(session, "manufacturer")

    print("🎨  Opzioni color recuperate da Magento:")
    for label, opt_id in color_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni config_attacco_lamp recuperate da Magento:")
    for label, opt_id in attacco_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni config_dimensioi_map recuperate da Magento:")
    for label, opt_id in dimensioni_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni manufacturer_map recuperate da Magento:")
    for label, opt_id in manufacturer_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔧  Opzioni config_tipo recuperate da Magento:")
    for label, opt_id in tipo_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🌡️   Opzioni config_temperatura_colore recuperate da Magento:")
    for label, opt_id in temp_map.items():
        print(f"     {label} → {opt_id}")
    print()

    # 2. Carica lampade da terra (escludi WAY e TOFFEE)
    varianti = load_categoria(CSV_PATH, "Lampada da terra", escludi=["WAY", "TOFFEE"])

    semplici = []
    for famiglia, gruppo in varianti.groupby("Famiglia Articolo"):
        for _, row in gruppo.iterrows():
            semplici.append(
                build_simple(row, color_map, attacco_map, dimensioni_map,
                             manufacturer_map, tipo_map, temp_map, gruppo)
            )

        # 3. Salva JSON
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(semplici, f, ensure_ascii=False, indent=2)

        print(f"✅  {OUTPUT_PATH}")
        print(f"    Prodotti generati: {len(semplici)}")
        print()
        for s in semplici:
            p = s["product"]
            ca = {a["attribute_code"]: a["value"] for a in p["custom_attributes"]}
            print(
                f"  [{p['sku']}]  {p['name']}\n"
                f"           color={ca.get('color', '-')}  "
                f"dimensioni={ca.get('config_dimensioni', '-')}  "
                f"attacco={ca.get('config_attacco_lamp', '-')}  "
                f"tipo={ca.get('config_tipo', '-')}  "
                f"temp={ca.get('config_temperatura_colore', '-')}  "
                f"€{p['price']}  qty={p['extension_attributes']['stock_item']['qty']}\n"
            )
