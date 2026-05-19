"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Legge: ./file/simple_products_{categoria}.json
Scrive: ./file/configurable_products_{categoria}.json
"""

import json
import re
import pandas as pd
from pathlib import Path
from utility.magento_api import *


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CATEGORIA  = "Lampada da tavolo"
INPUT_JSON = f"./file/simple_products_{CATEGORIA.lower().replace(' ', '_')}.json"
OUTPUT_JSON = f"./file/configurable_products_{CATEGORIA.lower().replace(' ', '_')}.json"
CSV_PATH   = "./file/giacenzeECommerce.csv"
DESC_CSV   = f"./file/descrizioni_configurabili_{CATEGORIA.lower().replace(' ', '_')}.csv"

WEBSITE_IDS        = [1]
ATTRIBUTE_SET_NAME = "Ideal-Lux"
ESCLUDI_DA_CONFIG  = {"lamp_ean", "manufacturer", "url_key"}
CATEGORIE_FISSE    = ["Marchi", "Ideal Lux", "Illuminazione"]


CONFIG_SKU_START = 89  # IL-CONFIG-086: i primi 85 sono occupati dalle lampade da terra


# ─────────────────────────────────────────────
# LOOKUP / COSTANTI
# ─────────────────────────────────────────────

MATERIALI_MAP = {
    "AL":  "Alluminio",
    "ME":  "Metallo",
    "CO":  "Cemento",
    "CR":  "Cristallo",
    "GE":  "Gesso",
    "LE":  "Legno",
    "MA":  "Marmo",
    "PVC": "PVC",
    "RE":  "Resina",
    "TE":  "Tessuto",
    "VE":  "Vetro",
}

CATEGORIA_PLURALE = {
    "Lampada Da Terra":     "Lampade da Terra",
    "Lampada Da Tavolo":    "Lampade da Tavolo",
    "Lampada Da Parete":    "Lampade da Parete",
    "Lampada Da Soffitto":  "Lampade da Soffitto",
    "Lampada Portatile":    "Lampade Portatili",
}


# ─────────────────────────────────────────────
# UTILITY PARSING
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


def estrai_sottofamiglia(nome: str) -> str:
    base = re.split(r'-[A-Z]', nome)[0].strip()
    base = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', base)
    base = re.sub(r'\bLED\b', '', base, flags=re.IGNORECASE)
    return re.sub(r'\s{2,}', ' ', base).strip().lower()


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
        num_w = match.group(2)
        return f"{luci} x {num_w}W" if luci > 1 else f"{num_w}W"
    match = re.search(r'(\d+)\s*W', w, re.IGNORECASE)
    if match:
        return f"{match.group(1)}W"
    return w


def get_config_attribute_codes(semplici: list) -> list:
    codes = set()
    for s in semplici:
        for attr in s["product"]["custom_attributes"]:
            code = attr["attribute_code"]
            if code not in ESCLUDI_DA_CONFIG:
                codes.add(code)
    return sorted(codes)


def raggruppa_per_sottofamiglia(semplici: list) -> dict:
    gruppi = {}
    for s in semplici:
        key = estrai_sottofamiglia(s["product"]["name"])
        gruppi.setdefault(key, []).append(s)
    return gruppi


# ─────────────────────────────────────────────
# DATI DI GRUPPO DAL CSV
# ─────────────────────────────────────────────

def _dati_gruppo(semplici: list, df: pd.DataFrame) -> pd.DataFrame:
    """Restituisce le righe CSV corrispondenti al gruppo di semplici."""
    skus_puliti = [s["product"]["sku"].replace("IL-", "") for s in semplici]
    return df[df["Nr"].astype(str).str.endswith(tuple(skus_puliti))]


def _ambiente(righe_gruppo: pd.DataFrame) -> str:
    ip_nums = righe_gruppo["IP"].dropna().astype(int).unique().tolist()
    return "Esterni" if any(v >= 44 for v in ip_nums) else "Interni"


def _lamp_attributi(righe_gruppo: pd.DataFrame, primo_sku: str,
                    df: pd.DataFrame, attacco_menu_map: dict) -> dict:
    """Raccoglie tutti gli attributi lamp_* dal CSV per il gruppo."""

    # lamp_lampadina
    riga_primo = df[df["Nr"].astype(str).str.endswith(primo_sku)]
    lamp_val = (
        "1"
        if not riga_primo.empty
        and str(riga_primo.iloc[0]["LampadinaInclusa"]).strip().lower() == "sì"
        else "0"
    )

    # lamp_dimmer
    dimmer_val = (
        "1"
        if not righe_gruppo.empty
        and (righe_gruppo["Dimmer"].dropna().str.strip().str.lower() == "sì").any()
        else "0"
    )

    # lamp_dimensioni
    dimensioni = righe_gruppo["Dimensione Articolo"].dropna().str.strip().unique().tolist()
    dimensioni_val = " - ".join(converti_dimensione(d) for d in dimensioni if d)

    # lamp_materiali_costruzione
    materiali_set = set()
    for m in righe_gruppo["Materiale"].dropna().str.strip():
        for sigla in m.split(","):
            materiali_set.add(MATERIALI_MAP.get(sigla.strip(), sigla.strip()))
    materiali_val = ", ".join(sorted(materiali_set))

    # lamp_max_potenza
    watt_formattati = set()
    for _, row in righe_gruppo.iterrows():
        w    = str(row["Watt"]).strip()
        luci = int(row["Luci"]) if pd.notna(row["Luci"]) else 1
        watt_formattati.add(formatta_watt(w, luci))
    watt_val = " - ".join(sorted(watt_formattati))

    # lamp_grado_protezione
    ip_strs = righe_gruppo["IP"].dropna().astype(str).str.strip().unique().tolist()
    ip_val  = " - ".join(f"IP{int(float(v))}" for v in ip_strs if v and v != "nan")

    # lamp_attacco_lamp_menu
    attacchi          = righe_gruppo["Attacco Portalampada"].dropna().str.strip().unique().tolist()
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

    righe_gruppo = _dati_gruppo(semplici, df)
    ambiente     = _ambiente(righe_gruppo)
    is_single    = len(semplici) == 1

    # Titolo e url_key
    titolo = f"{build_titolo(semplici[0]['product']['name'])} per {ambiente}"
    for singolare, plurale in CATEGORIA_PLURALE.items():
        titolo = titolo.replace(singolare, plurale)
    url_key = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")

    # Attributi varianti
    child_skus = [s["product"]["sku"] for s in semplici]
    attr_codes = get_config_attribute_codes(semplici)

    # Manufacturer dal primo semplice
    manufacturer_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "manufacturer"),
        None,
    )

    # Prezzo e stock (solo per prodotti singoli)
    prezzo_val  = semplici[0]["product"].get("price", 0) if is_single else None
    weight_val = semplici[0]["product"].get("weight", 0) if is_single else None
    lamp_ean_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "lamp_ean"),
        None
    ) if is_single else None
    qty_val     = semplici[0]["product"]["extension_attributes"]["stock_item"]["qty"] if is_single else 0
    in_stock    = semplici[0]["product"]["extension_attributes"]["stock_item"]["is_in_stock"] if is_single else 1

    # Categorie
    primo_sku_pulito = semplici[0]["product"]["sku"].replace("IL-", "")
    lamp = _lamp_attributi(righe_gruppo, primo_sku_pulito, df, attacco_menu_map)

    cat_plurale = CATEGORIA_PLURALE.get(CATEGORIA.title(), CATEGORIA)

    if ambiente == "Esterni":
        nomi_cat = CATEGORIE_FISSE + ["Esterni", f"{cat_plurale} per Esterni"]
    else:
        nomi_cat = CATEGORIE_FISSE + ["Interni", cat_plurale]

    category_ids = [categorie_map[n] for n in nomi_cat if n in categorie_map]

    # Descrizioni dal CSV
    desc_row   = df_desc.loc[config_sku] if config_sku in df_desc.index else None
    short_desc = desc_row["short_description"] if desc_row is not None else ""
    description = desc_row["description"]      if desc_row is not None else ""
    meta_desc  = desc_row["meta_description"]  if desc_row is not None else ""

    # Attributi custom_attributes lamp_*
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
            "weight": weight_val,
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
                {"attribute_code": "url_key",          "value": url_key},
                {"attribute_code": "manufacturer",     "value": manufacturer_val},
                {"attribute_code": "meta_title",       "value": titolo},
                {"attribute_code": "short_description","value": short_desc},
                {"attribute_code": "description",      "value": description},
                {"attribute_code": "meta_description", "value": meta_desc},
                *([{"attribute_code": "lamp_ean", "value": lamp_ean_val}] if lamp_ean_val else []),
                *lamp_attrs,
            ],
            "media_gallery_entries": [],
        },
        **({} if is_single else {"_child_skus": child_skus, "_attr_codes": attr_codes}),
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():

    print(f"\n⚠️  CONFIG_SKU_START = {CONFIG_SKU_START}  (il primo SKU sarà IL-CONFIG-{CONFIG_SKU_START:03d})")
    print(f"    Assicurati che non sovrascriva SKU già esistenti.")
    risposta = input("    Continuare? [s/N] ").strip().lower()
    if risposta != "s":
        print("    Operazione annullata.")
        return


    df_desc = pd.read_csv(DESC_CSV, sep=",", encoding="utf-8").set_index("sku")

    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)

    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    df               = pd.read_csv(CSV_PATH, sep=";")
    session          = get_oauth_session()
    attribute_set_id = get_attribute_set_id(session, ATTRIBUTE_SET_NAME)
    attacco_menu_map = get_attribute_options(session, "lamp_attacco_lamp_menu")
    categorie_map    = build_categorie_map(session)

    gruppi = raggruppa_per_sottofamiglia(semplici_tutti)
    print(f"🔗  Gruppi (configurabili) trovati: {len(gruppi)}\n")

    configurabili = []
    for idx, (key, gruppo) in enumerate(sorted(gruppi.items()), start=CONFIG_SKU_START): #DA CAMBIARE
        config_sku = f"IL-CONFIG-{idx:03d}"
        config = build_configurable(
            config_sku, gruppo, df, df_desc,
            attacco_menu_map, categorie_map, attribute_set_id,
        )
        configurabili.append(config)

        if "_child_skus" in config:
            print(
                f"  [{config_sku}]  {config['product']['name']}\n"
                f"           attributi varianti : {config['_attr_codes']}\n"
                f"           semplici ({len(config['_child_skus'])}): {config['_child_skus']}\n"
            )
        else:
            print(f"  [{config_sku}]  {config['product']['name']}\n           prodotto singolo\n")

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_JSON}  ({len(configurabili)} configurabili generati)")


if __name__ == "__main__":
    main()