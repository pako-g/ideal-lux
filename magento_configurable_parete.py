"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Categoria: Lampada da parete
Output: configurable_products_lampada_da_parete.json

Usa le stesse REGOLE di magento_simple_parete.py per raggruppare
i prodotti — nessuna logica duplicata.
"""

import json
import re
import sys
import pandas as pd
from pathlib import Path

# Importa REGOLE e helpers dal simple_parete
sys.path.insert(0, str(Path(__file__).parent))
from magento_simple_parete import (
    REGOLE, FAMIGLIE_DA_SALTARE, FINITURE_DA_SALTARE,
    CATEGORIA, MARCA,
    load_categoria, token_from_desc, finitura_label,
)

from utility.magento_api import (
    get_oauth_session, get_attribute_set_id, get_attribute_options,
    build_categorie_map,
)


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH           = "./file/giacenzeECommerce.csv"
INPUT_JSON         = "./file/simple_products_lampada_da_parete.json"
OUTPUT_JSON        = "./file/configurable_products_lampada_da_parete.json"
DESC_CSV           = "./file/descrizioni_configurabili_lampada_da_parete.csv"

WEBSITE_IDS        = [1]
ATTRIBUTE_SET_NAME = "Ideal-Lux"
CATEGORIE_FISSE    = ["Marchi", "Ideal Lux", "Illuminazione"]
ESCLUDI_DA_CONFIG  = {"lamp_ean", "manufacturer", "url_key"}

CONFIG_SKU_START   = 315


# ─────────────────────────────────────────────
# LOOKUP
# ─────────────────────────────────────────────

MATERIALI_MAP = {
    "AL":  "Alluminio", "ME":  "Metallo",  "CO": "Cemento",
    "CR":  "Cristallo", "GE":  "Gesso",    "LE": "Legno",
    "MA":  "Marmo",     "PVC": "PVC",      "RE": "Resina",
    "TE":  "Tessuto",   "VE":  "Vetro",    "PS": "Plexiglas",
    "CE":  "Ceramica",  "CON": "Concreto",
}

CATEGORIA_PLURALE = {
    "Lampada Da Terra":      "Lampade da Terra",
    "Lampada Da Tavolo":     "Lampade da Tavolo",
    "Lampada A Sospensione": "Lampade a Sospensione",
    "Lampada Da Parete":     "Lampade da Parete",
    "Lampada Da Soffitto":   "Lampade da Soffitto",
    "Lampada Portatile":     "Lampade Portatili",
}


# ─────────────────────────────────────────────
# HELPERS
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


def formatta_watt(w: str, luci: int) -> str:
    match = re.search(r'(\d+)\s*x\s*(\d+)\s*W', w, re.IGNORECASE)
    if match:
        return f"{luci} x {match.group(2)}W" if luci > 1 else f"{match.group(2)}W"
    match = re.search(r'(\d+)\s*W', w, re.IGNORECASE)
    if match:
        return f"{match.group(1)}W"
    return w


def build_url_key(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def _ambiente(righe: pd.DataFrame) -> str:
    ip_nums = righe["IP"].dropna().astype(int).unique().tolist()
    return "Esterni" if any(v >= 44 for v in ip_nums) else "Interni"


def _dati_gruppo(skus_puliti: list, df: pd.DataFrame) -> pd.DataFrame:
    return df[df["Nr"].astype(str).str[-6:].isin(skus_puliti)]


def _lamp_attributi(righe: pd.DataFrame, primo_sku: str,
                    df: pd.DataFrame, attacco_menu_map: dict) -> dict:
    riga_primo = df[df["Nr"].astype(str).str[-6:] == primo_sku]

    lamp_val = (
        "1" if not riga_primo.empty
        and str(riga_primo.iloc[0].get("LampadinaInclusa", "")).strip().lower() == "sì"
        else "0"
    )
    dimmer_val = (
        "1" if not righe.empty
        and (righe["Dimmer"].dropna().str.strip().str.lower() == "sì").any()
        else "0"
    )
    dimensioni = righe["Dimensione Articolo"].dropna().str.strip().unique().tolist()
    dimensioni_val = " - ".join(converti_dimensione(d) for d in dimensioni if d)

    materiali_set = set()
    for m in righe["Materiale"].dropna().str.strip():
        for sigla in m.split(","):
            materiali_set.add(MATERIALI_MAP.get(sigla.strip(), sigla.strip()))
    materiali_val = ", ".join(sorted(materiali_set))

    watt_formattati = set()
    for _, row in righe.iterrows():
        w    = str(row["Watt"]).strip()
        luci = int(row["Luci"]) if pd.notna(row["Luci"]) else 1
        watt_formattati.add(formatta_watt(w, luci))
    watt_val = " - ".join(sorted(watt_formattati))

    ip_strs = righe["IP"].dropna().astype(str).str.strip().unique().tolist()
    ip_val  = " - ".join(f"IP{int(float(v))}" for v in ip_strs if v and v != "nan")

    attacchi = righe["Attacco Portalampada"].dropna().str.strip().unique().tolist()
    attacchi_filtrati = [a for a in attacchi if a and a in attacco_menu_map]
    attacco_menu_val  = attacco_menu_map[attacchi_filtrati[0]] if len(attacchi_filtrati) == 1 else ""

    return {
        "lamp_lampadina":             lamp_val,
        "lamp_dimmer":                dimmer_val,
        "lamp_dimensioni":            dimensioni_val,
        "lamp_materiali_costruzione": materiali_val,
        "lamp_max_potenza":           watt_val,
        "lamp_grado_protezione":      ip_val,
        "lamp_attacco_lamp_menu":     attacco_menu_val,
    }


def _get_attr_codes(semplici: list) -> list:
    codes = set()
    for s in semplici:
        for attr in s["product"]["custom_attributes"]:
            if attr["attribute_code"] not in ESCLUDI_DA_CONFIG:
                codes.add(attr["attribute_code"])
    return sorted(codes)


# ─────────────────────────────────────────────
# BUILD CONFIGURABILE
# ─────────────────────────────────────────────

def build_configurable(
        config_sku: str,
        semplici: list,
        df: pd.DataFrame,
        df_desc: pd.DataFrame,
        attacco_menu_map: dict,
        categorie_map: dict,
        attribute_set_id: int,
) -> dict:

    is_single   = len(semplici) == 1
    skus_puliti = [s["product"]["sku"].replace("IL-", "") for s in semplici]
    righe       = _dati_gruppo(skus_puliti, df)
    ambiente    = _ambiente(righe)
    lamp        = _lamp_attributi(righe, skus_puliti[0], df, attacco_menu_map)

    # Nome: prende il nome del primo semplice, rimuove varianti (colore/dimensione in coda)
    nome_semplice = semplici[0]["product"]["name"]
    # Rimuove tutto dopo l'ultimo trattino che introduce una variante
    nome_base = re.sub(r'\s*-[\dA-Z].*$', '', nome_semplice).strip()
    # Aggiunge ambiente
    cat_plurale = CATEGORIA_PLURALE.get(CATEGORIA.title(), CATEGORIA)
    titolo = f"{nome_base} per {ambiente}"
    for singolare, plurale in CATEGORIA_PLURALE.items():
        titolo = titolo.replace(singolare, plurale)

    url_key = build_url_key(titolo)

    # Attributi varianti
    child_skus = [s["product"]["sku"] for s in semplici]
    attr_codes = [] if is_single else _get_attr_codes(semplici)

    # Manufacturer
    manufacturer_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "manufacturer"), None,
    )

    # Prezzo/stock/ean solo per singoli
    prezzo_val   = semplici[0]["product"].get("price", 0)   if is_single else None
    weight_val   = semplici[0]["product"].get("weight", 0)  if is_single else None
    lamp_ean_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "lamp_ean"), None
    ) if is_single else None
    qty_val  = semplici[0]["product"]["extension_attributes"]["stock_item"]["qty"]      if is_single else 0
    in_stock = semplici[0]["product"]["extension_attributes"]["stock_item"]["is_in_stock"] if is_single else 1

    # Categorie
    if ambiente == "Esterni":
        nomi_cat = CATEGORIE_FISSE + ["Esterni", f"{cat_plurale} per Esterni"]
    else:
        nomi_cat = CATEGORIE_FISSE + ["Interni", cat_plurale]
    category_ids = [categorie_map[n] for n in nomi_cat if n in categorie_map]

    # Descrizioni
    desc_row    = df_desc.loc[config_sku] if config_sku in df_desc.index else None
    short_desc  = desc_row["short_description"] if desc_row is not None else ""
    description = desc_row["description"]       if desc_row is not None else ""
    meta_desc   = desc_row["meta_description"]  if desc_row is not None else ""

    lamp_attrs = [
        {"attribute_code": "lamp_lampadina",             "value": lamp["lamp_lampadina"]},
        {"attribute_code": "lamp_dimmer",                "value": lamp["lamp_dimmer"]},
        {"attribute_code": "lamp_dimensioni",            "value": lamp["lamp_dimensioni"]},
        {"attribute_code": "lamp_materiali_costruzione", "value": lamp["lamp_materiali_costruzione"]},
        {"attribute_code": "lamp_max_potenza",           "value": lamp["lamp_max_potenza"]},
        {"attribute_code": "lamp_grado_protezione",      "value": lamp["lamp_grado_protezione"]},
        *([{"attribute_code": "lamp_attacco_lamp_menu",  "value": lamp["lamp_attacco_lamp_menu"]}]
          if lamp["lamp_attacco_lamp_menu"] else []),
    ]

    return {
        "product": {
            "sku":              config_sku,
            "name":             titolo,
            "attribute_set_id": attribute_set_id,
            "status":           2,
            "visibility":       4,
            "type_id":          "configurable",
            "price":            prezzo_val,
            "weight":           weight_val,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "stock_item": {
                    "qty":          qty_val,
                    "is_in_stock":  in_stock,
                    "manage_stock": is_single,
                },
                "category_links": [
                    {"position": i, "category_id": str(cat_id)}
                    for i, cat_id in enumerate(category_ids)
                ],
            },
            "custom_attributes": [
                {"attribute_code": "url_key",           "value": url_key},
                {"attribute_code": "manufacturer",      "value": manufacturer_val},
                {"attribute_code": "meta_title",        "value": titolo},
                {"attribute_code": "short_description", "value": short_desc},
                {"attribute_code": "description",       "value": description},
                {"attribute_code": "meta_description",  "value": meta_desc},
                *([{"attribute_code": "lamp_ean", "value": lamp_ean_val}] if lamp_ean_val else []),
                *lamp_attrs,
            ],
            "media_gallery_entries": [],
        },
        "_child_skus": [] if is_single else child_skus,
        "_attr_codes": attr_codes,
    }


# ─────────────────────────────────────────────
# RAGGRUPPAMENTO — usa le stesse REGOLE del simple
# ─────────────────────────────────────────────

def raggruppa(varianti: pd.DataFrame, semplici_map: dict) -> dict:
    """
    Raggruppa i prodotti usando le stesse REGOLE del simple_parete.
    Ritorna { gruppo_key: [lista semplici JSON] }
    """
    gruppi = {}

    for famiglia, g_fam in varianti.groupby("Famiglia Articolo"):
        if famiglia in FAMIGLIE_DA_SALTARE:
            continue

        if FINITURE_DA_SALTARE:
            g_fam = g_fam[~g_fam["Finitura"].isin(FINITURE_DA_SALTARE)].copy()
        if g_fam.empty:
            continue

        if famiglia not in REGOLE:
            continue

        regola    = REGOLE[famiglia]
        saltare_fn = regola.get("saltare")
        gruppo_fn  = regola.get("gruppo", lambda r: famiglia)

        g_fam["_gruppo"] = g_fam.apply(gruppo_fn, axis=1)

        for gruppo_key, g_sub in g_fam.groupby("_gruppo"):

            semplici_gruppo = []
            for _, row in g_sub.iterrows():
                if saltare_fn and saltare_fn(row):
                    continue
                sku = f"IL-{row['sku']}"
                if sku in semplici_map:
                    semplici_gruppo.append(semplici_map[sku])

            if not semplici_gruppo:
                continue

            # Chiave univoca: famiglia + gruppo_key
            key = f"{famiglia}::{gruppo_key}"
            gruppi[key] = semplici_gruppo

    return gruppi


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print(f"\n⚠️  CONFIG_SKU_START = {CONFIG_SKU_START}  (primo SKU: IL-CONFIG-{CONFIG_SKU_START:03d})")
    print(f"    Assicurati che non sovrascriva SKU già esistenti in Magento.")
    risposta = input("    Continuare? [s/N] ").strip().lower()
    if risposta != "s":
        print("    Operazione annullata.")
        sys.exit(0)

    # Carica semplici come mappa sku → prodotto
    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)
    semplici_map = {s["product"]["sku"]: s for s in semplici_tutti}
    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    # Carica CSV e descrizioni
    df      = pd.read_csv(CSV_PATH, sep=None, engine="python")
    df["sku"] = df["Nr"].astype(str).str[-6:]

    if Path(DESC_CSV).exists():
        df_desc = pd.read_csv(DESC_CSV, sep=",", encoding="utf-8")
        if not df_desc.empty and "sku" in df_desc.columns:
            df_desc = df_desc.set_index("sku")
        else:
            df_desc = pd.DataFrame()
    else:
        print(f"⚠️  File descrizioni non trovato: {DESC_CSV} — procedo senza descrizioni.")
        df_desc = pd.DataFrame()

    # Carica varianti categoria
    varianti = load_categoria(CSV_PATH, CATEGORIA)

    # Connessione Magento
    session          = get_oauth_session()
    attribute_set_id = get_attribute_set_id(session, ATTRIBUTE_SET_NAME)
    attacco_menu_map = get_attribute_options(session, "lamp_attacco_lamp_menu")
    categorie_map    = build_categorie_map(session)

    # Raggruppa
    gruppi = raggruppa(varianti, semplici_map)
    print(f"🔗  Gruppi trovati: {len(gruppi)}\n")

    # Genera configurabili
    configurabili = []
    for idx, (key, gruppo) in enumerate(sorted(gruppi.items()), start=CONFIG_SKU_START):
        config_sku = f"IL-CONFIG-{idx:03d}"
        config = build_configurable(
            config_sku, gruppo, df, df_desc,
            attacco_menu_map, categorie_map, attribute_set_id,
        )
        configurabili.append(config)

        n_child = len(config["_child_skus"])
        if n_child > 0:
            print(
                f"  [{config_sku}]  {config['product']['name']}\n"
                f"           assi    : {config['_attr_codes']}\n"
                f"           semplici: {config['_child_skus']}\n"
            )
        else:
            print(f"  [{config_sku}]  {config['product']['name']}  (singolo)\n")

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {OUTPUT_JSON}")
    print(f"    Configurabili generati : {len(configurabili)}")
    print(f"    di cui singoli         : {sum(1 for c in configurabili if not c['_child_skus'])}")
    print(f"    di cui con varianti    : {sum(1 for c in configurabili if c['_child_skus'])}")
