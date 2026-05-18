"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Legge: ./file/simple_products.json
Scrive: ./file/configurable_products.json
"""

import json
import re
import os
import base64
import warnings
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

warnings.filterwarnings("ignore")
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CATEGORIA   = "Lampada da tavolo"
INPUT_JSON  = f"./file/simple_products_{CATEGORIA.lower().replace(' ', '_')}.json"
OUTPUT_JSON = f"./file/configurable_products_{CATEGORIA.lower().replace(' ', '_')}.json"
CSV_PATH         = "./file/giacenzeECommerce.csv"
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")

ATTRIBUTE_SET_ID = 264
WEBSITE_IDS      = [1]

ESCLUDI_DA_CONFIG = {"lamp_ean", "manufacturer", "url_key"}
CATEGORIE_FISSE   = ["Marchi", "Ideal Lux", "Illuminazione"]

MATERIALI_MAP = {
    "AL": "Alluminio",
    "ME": "Metallo",
    "CO": "Cemento",
    "CR": "Cristallo",
    "GE": "Gesso",
    "LE": "Legno",
    "MA": "Marmo",
    "PVC": "PVC",
    "RE": "Resina",
    "TE": "Tessuto",
    "VE": "Vetro",
}

CATEGORIA_PLURALE = {
    "Lampada Da Terra": "Lampade da Terra",
    "Lampada Da Tavolo": "Lampade da Tavolo",
    "Lampada Da Parete": "Lampade da Parete",
    "Lampada Da Soffitto": "Lampade da Soffitto",
    "Lampada Portatile": "Lampade Portatili",
}
DESC_CSV = "./file/descrizioni_configurabili_lampade_da_terra.csv"

# ─────────────────────────────────────────────
# OAUTH
# ─────────────────────────────────────────────

def get_oauth_session() -> OAuth1Session:
    # 1. Crea l'istanza della sessione
    session = OAuth1Session(
        client_key            = os.getenv("MAGENTO_CONSUMER_KEY"),
        client_secret         = os.getenv("MAGENTO_CONSUMER_SECRET"),
        resource_owner_key    = os.getenv("MAGENTO_ACCESS_TOKEN"),
        resource_owner_secret = os.getenv("MAGENTO_TOKEN_SECRET"),
        signature_method      = "HMAC-SHA256",
    )

    # 2. Aggiungi gli header globali
    # Questi verranno usati per OGNI chiamata fatta con questa sessione
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    })

    return session


# ─────────────────────────────────────────────
# API MAGENTO
# ─────────────────────────────────────────────

def get_attribute_options(session: OAuth1Session, attribute_code: str) -> dict:
    """Restituisce {label: id} per un attributo select."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/products/attributes/{attribute_code}"
    resp = session.get(url, verify=False)
    resp.raise_for_status()
    return {
        opt["label"]: opt["value"]
        for opt in resp.json().get("options", [])
        if opt["label"] and opt["value"]
    }


def build_categorie_map(session: OAuth1Session) -> dict:
    """Restituisce {nome_categoria: id} percorrendo l'albero Magento."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/categories"
    resp = session.get(url, verify=False)
    resp.raise_for_status()

    categorie_map = {}

    def scorri(nodo):
        categorie_map[nodo["name"]] = nodo["id"]
        for figlio in nodo.get("children_data", []):
            scorri(figlio)

    scorri(resp.json())
    return categorie_map


# ─────────────────────────────────────────────
# UTILITY TITOLO
# ─────────────────────────────────────────────

def build_titolo(nome_semplice: str) -> str:
    nome = nome_semplice.strip()

    is_led    = bool(re.search(r'\bLED\b', nome, re.IGNORECASE))
    cat_match = re.search(r'(Lampada\s+[Dd]a\s+\w+)', nome, re.IGNORECASE)
    categoria = cat_match.group(0).title() if cat_match else ""

    nome_pulito = re.split(r'-[A-Z]', nome)[0].strip()
    if categoria:
        nome_pulito = re.sub(re.escape(categoria), '', nome_pulito, flags=re.IGNORECASE).strip()
    nome_pulito = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', nome_pulito)
    nome_pulito = re.sub(r'\bLED\b', '', nome_pulito, flags=re.IGNORECASE)
    nome_pulito = re.sub(r'\s{2,}', ' ', nome_pulito).strip()

    modello_str = " ".join(t[0].upper() + t[1:] for t in nome_pulito.split() if t)
    led_str     = " Led" if is_led else ""
    return f"{modello_str}{led_str} {categoria}".strip()


# ─────────────────────────────────────────────
# UTILITY ATTRIBUTI
# ─────────────────────────────────────────────

def get_config_attribute_codes(semplici: list) -> list:
    codes = set()
    for s in semplici:
        for attr in s["product"]["custom_attributes"]:
            code = attr["attribute_code"]
            if code not in ESCLUDI_DA_CONFIG:
                codes.add(code)
    return sorted(codes)


# ─────────────────────────────────────────────
# UTILITY DIMENSIONI
# ─────────────────────────────────────────────

def converti_dimensione(dim_str: str) -> str:
    def converti_token(match):
        lettera = match.group(1)
        valore  = float(match.group(2).replace(",", "."))
        cm      = valore / 10
        cm_str  = f"{cm:.0f}" if cm == int(cm) else f"{cm:.1f}"
        prefisso = "Ø" if lettera == "D" else lettera
        return f"{prefisso}{cm_str}cm"

    risultato = re.sub(r'([DHLP])\s+([\d,]+)', converti_token, dim_str)
    risultato = re.sub(r'\s*mm\s*', '', risultato)
    return risultato.strip()


# ─────────────────────────────────────────────
# UTILITY WATT
# ─────────────────────────────────────────────

def formatta_watt(w: str, luci: int) -> str:
    # Prima cerca pattern "N x NW"
    match = re.search(r'(\d+)\s*x\s*(\d+)\s*W', w, re.IGNORECASE)
    if match:
        num_w = match.group(2)
        return f"{luci} x {num_w}W" if luci > 1 else f"{num_w}W"
    # Fallback: cerca solo il numero di watt
    match = re.search(r'(\d+)\s*W', w, re.IGNORECASE)
    if match:
        return f"{match.group(1)}W"
    return w


# ─────────────────────────────────────────────
# RAGGRUPPAMENTO
# ─────────────────────────────────────────────

def estrai_sottofamiglia(nome: str) -> str:
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
# BUILD CONFIGURABILE
# ─────────────────────────────────────────────

def build_configurable(
        config_sku: str,
        semplici: list,
        df: pd.DataFrame,
        df_desc: pd.DataFrame,
        attacco_menu_map: dict,
        categorie_map: dict
    ) -> dict:

    # ── Righe CSV del gruppo (usa SKU senza prefisso IL-) ──
    skus_puliti  = [s["product"]["sku"].replace("IL-", "") for s in semplici]
    righe_gruppo = df[df["Nr"].astype(str).str.endswith(tuple(skus_puliti))]

    # ── Ambiente ──
    ip_nums    = righe_gruppo["IP"].dropna().astype(int).unique().tolist()
    is_esterno = any(v >= 44 for v in ip_nums)
    ambiente   = "Esterni" if is_esterno else "Interni"

    # ── Titolo e url_key ──
    titolo  = f"{build_titolo(semplici[0]['product']['name'])} per {ambiente}"
    for singolare, plurale in CATEGORIA_PLURALE.items():
        titolo = titolo.replace(singolare, plurale)

    url_key = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")

    # ── SKU e attr_codes ──
    child_skus = [s["product"]["sku"] for s in semplici]

    prezzo_val = 0
    qty_val = 0
    is_in_stock = 0
    is_single = len(child_skus) == 1

    # Se prodotto singolo recupera prezzo e qty dal semplice
    if is_single:
        solo = semplici[0]["product"]
        prezzo_val = solo.get("price", 0)
        qty_val = solo["extension_attributes"]["stock_item"]["qty"]
        is_in_stock = solo["extension_attributes"]["stock_item"]["is_in_stock"]

    attr_codes = get_config_attribute_codes(semplici)

    # ── Manufacturer dal primo semplice ──
    manufacturer_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "manufacturer"),
        None,
    )

    # ── Immagini dai semplici ──
    media_entries = []
    for s in semplici:
        nome_s = s["product"]["name"]
        sku_s  = s["product"]["sku"].replace("IL-", "")
        slug   = re.sub(r"[^a-z0-9]+", "-", nome_s.lower()).strip("-")
        path   = Path(f"./file/images/{slug}-{sku_s}.jpg")
        if path.exists():
            media_entries.append({
                "media_type": "image",
                "label":      nome_s.replace("-", " "),
                "position":   len(media_entries) + 1,
                "disabled":   False,
                "types":      ["image", "small_image", "thumbnail"] if not media_entries else [],
                "content": {
                    "base64_encoded_data": base64.b64encode(path.read_bytes()).decode("utf-8"),
                    "type": "image/jpeg",
                    "name": path.name,
                },
            })

    # ── lamp_lampadina ──
    primo_sku_pulito = semplici[0]["product"]["sku"].replace("IL-", "")
    riga_primo       = df[df["Nr"].astype(str).str.endswith(primo_sku_pulito)]
    lamp_val = (
        "1"
        if not riga_primo.empty
        and str(riga_primo.iloc[0]["LampadinaInclusa"]).strip().lower() == "sì"
        else "0"
    )

    # ── lamp_dimmer ──
    dimmer_val = (
        "1"
        if not righe_gruppo.empty
        and (righe_gruppo["Dimmer"].dropna().str.strip().str.lower() == "sì").any()
        else "0"
    )

    # ── lamp_dimensioni ──
    dimensioni     = righe_gruppo["Dimensione Articolo"].dropna().str.strip().unique().tolist()
    dimensioni_val = " - ".join(converti_dimensione(d) for d in dimensioni if d)

    # ── lamp_materiali_costruzione ──
    materiali_set = set()
    for m in righe_gruppo["Materiale"].dropna().str.strip():
        for sigla in m.split(","):
            materiali_set.add(MATERIALI_MAP.get(sigla.strip(), sigla.strip()))
    materiali_val = ", ".join(sorted(materiali_set))

    # ── lamp_max_potenza ──
    watt_formattati = set()
    for _, row in righe_gruppo.iterrows():
        w    = str(row["Watt"]).strip()
        luci = int(row["Luci"]) if pd.notna(row["Luci"]) else 1
        watt_formattati.add(formatta_watt(w, luci))
    watt_val = " - ".join(sorted(watt_formattati))

    # ── lamp_grado_protezione ──
    ip_strs = righe_gruppo["IP"].dropna().astype(str).str.strip().unique().tolist()
    ip_val  = " - ".join(f"IP{int(float(v))}" for v in ip_strs if v and v != "nan")

    # ── lamp_attacco_lamp_menu ──
    attacchi         = righe_gruppo["Attacco Portalampada"].dropna().str.strip().unique().tolist()
    attacchi_filtrati = [a for a in attacchi if a and a in attacco_menu_map]
    attacco_menu_val  = attacco_menu_map[attacchi_filtrati[0]] if len(attacchi_filtrati) == 1 else ""

    # ── Categorie ──
    cat_nome    = "Lampade da Terra per Esterni" if is_esterno else "Lampade da Terra"
    nomi_cat    = CATEGORIE_FISSE + [cat_nome]
    category_ids = [categorie_map[n] for n in nomi_cat if n in categorie_map]

    desc_row = df_desc.loc[config_sku] if config_sku in df_desc.index else None
    short_desc = desc_row["short_description"] if desc_row is not None else ""
    description = desc_row["description"] if desc_row is not None else ""
    meta_desc = desc_row["meta_description"] if desc_row is not None else ""

    return {
        "product": {
            "sku":               config_sku,
            "name":              titolo,
            "attribute_set_id":  ATTRIBUTE_SET_ID,
            "status":            2, #disable
            "visibility":        4,
            "type_id":           "configurable",
            "price": prezzo_val if is_single else None,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "stock_item": {
                    "qty":          qty_val if is_single else 0,
                    "is_in_stock":  is_in_stock if is_single else 1,
                    "manage_stock": True if is_single else False,
                },
                "category_links": [
                    {"position": i, "category_id": str(cat_id)}
                    for i, cat_id in enumerate(category_ids)
                ],
            },
            "custom_attributes": [
                {"attribute_code": "url_key",                    "value": url_key},
                {"attribute_code": "manufacturer",               "value": manufacturer_val},
                {"attribute_code": "lamp_lampadina",             "value": lamp_val},
                {"attribute_code": "lamp_dimmer",                "value": dimmer_val},
                {"attribute_code": "lamp_dimensioni",            "value": dimensioni_val},
                {"attribute_code": "lamp_materiali_costruzione", "value": materiali_val},
                {"attribute_code": "lamp_max_potenza",           "value": watt_val},
                {"attribute_code": "lamp_grado_protezione",      "value": ip_val},
                *([{"attribute_code": "lamp_attacco_lamp_menu", "value": attacco_menu_val}] if attacco_menu_val else []),
                {"attribute_code": "meta_title",                 "value": titolo},
                {"attribute_code": "short_description",          "value": short_desc},
                {"attribute_code": "description",                "value": description},
                {"attribute_code": "meta_description",           "value": meta_desc},
            ],
            "media_gallery_entries": media_entries,
        },
        **({} if is_single else {"_child_skus": child_skus, "_attr_codes": attr_codes}),
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    df_desc = pd.read_csv(DESC_CSV, sep=",", encoding="utf-8").set_index("sku")

    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)

    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    df               = pd.read_csv(CSV_PATH, sep=";")
    session          = get_oauth_session()
    attacco_menu_map = get_attribute_options(session, "lamp_attacco_lamp_menu")
    categorie_map    = build_categorie_map(session)

    gruppi = raggruppa_per_sottofamiglia(semplici_tutti)
    print(f"🔗  Gruppi (configurabili) trovati: {len(gruppi)}\n")

    configurabili = []
    for idx, (key, gruppo) in enumerate(sorted(gruppi.items()), start=1):
        config_sku = f"IL-CONFIG-{idx:03d}"
        config = build_configurable(config_sku, gruppo, df, df_desc, attacco_menu_map, categorie_map)
        configurabili.append(config)


        if "_child_skus" in config:
            print(
                f"  [{config_sku}]  {config['product']['name']}\n"
                f"           attributi varianti : {config['_attr_codes']}\n"
                f"           semplici ({len(config['_child_skus'])}): {config['_child_skus']}\n"
            )
        else:
            print(
                f"  [{config_sku}]  {config['product']['name']}\n"
                f"           prodotto singolo\n"
            )

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_JSON}  ({len(configurabili)} configurabili generati)")


if __name__ == "__main__":
    main()
