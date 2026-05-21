"""
Generatore JSON — Prodotti SEMPLICI Magento
Output: simple_products_{categoria}.json
"""

import json
import re
import pandas as pd
from pathlib import Path
from utility.magento_api import *


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH           = "./file/giacenzeECommerce.csv"
CATEGORIA          = "Lampada a sospensione"
OUTPUT_PATH        = f"./file/simple_products_{CATEGORIA.lower().replace(' ', '_')}.json"
MARCA              = "Ideal Lux"
ATTRIBUTE_SET_NAME = "Ideal-Lux"
WEBSITE_IDS        = [1]


# ─────────────────────────────────────────────
# LOOKUP / COSTANTI
# ─────────────────────────────────────────────

FINITURA_LABEL = {
    "Coffee":         "Caffè",
    "Nickel":         "Nichel",
    "Ambra sfumato":  "Ambra",
    "Fume' sfumato":  "Fumé",
    "Fume'":          "Fumé",
    "Ottone satinato": 'Ottone Satinato',
    "Cromo sfumato": 'Cromo',
}

TIPO_LABEL = {
    "Round":  "Rotondo",
    "Square": "Quadrato",
    "Line":   "Linea",
    "Sphere": "Sfera",
}

# Mappa numero luci SP → label Magento config_tipo
SP_TIPO_LABEL = {
    "SP1":  "1 Sorgente Luminosa",
    "SP2":  "2 Sorgenti Luminose",
    "SP3":  "3 Sorgenti Luminose",
    "SP4":  "4 Sorgenti Luminose",
    "SP5":  "5 Sorgenti Luminose",
    "SP6":  "6 Sorgenti Luminose",
    "SP7":  "7 Sorgenti Luminose",
    "SP8":  "8 Sorgenti Luminose",
    "SP9":  "9 Sorgenti Luminose",
    "SP10": "10 Sorgenti Luminose",
    "SP11": "11 Sorgenti Luminose",
    "SP12": "12 Sorgenti Luminose",
    "SP14": "14 Sorgenti Luminose",
    "SP15": "15 Sorgenti Luminose",
    "SP16": "16 Sorgenti Luminose",
    "SP18": "18 Sorgenti Luminose",
    "SP20": "20 Sorgenti Luminose",
    "SP22": "22 Sorgenti Luminose",
    "SP24": "24 Sorgenti Luminose",
}

# Famiglie dove la dimensione nella descrizione è D ma va letta come Lunghezza
FAMIGLIE_LUNGHEZZA = {"SASSO"}

# Famiglie senza attributo dimensione
FAMIGLIE_SENZA_DIMENSIONE = {"DRIFTWOOD", "BINOMIO"}

# Famiglie con attributo config_tipo
FAMIGLIE_CONFIG_TIPO = {"EDO", "ESSENCE", "TWIGGY", "DRIFTWOOD",
                        "AMADEUS", "BRIGITTA", "CHALET", "GALAXY"}

# Pattern per estrarre il tipo dalla descrizione, per famiglia
FAMIGLIE_TIPO = {
    "EDO":     r'_(?:PT1_)(ROUND|SQUARE)_',
    "ESSENCE": r'_PT_(ROUND|SQUARE)_',
    "TWIGGY":  r'_(LINE|SPHERE)_',
}

# Famiglie dove config_tipo è il numero di luci (letto dalla colonna Luci del CSV)
FAMIGLIE_CONFIG_TIPO_LUCI = {"AMADEUS", "BRIGITTA", "CHALET", "GALAXY"}

# Famiglie dove il colore è l'unico attributo configurabile
FAMIGLIE_SOLO_COLORE = {"DRIFTWOOD"}


# ─────────────────────────────────────────────
# CARICAMENTO CSV
# ─────────────────────────────────────────────

def _normalizza_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizza colonne comuni a tutti i caricamenti."""
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


def load_famiglia(csv_path: str, famiglia: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = df[df["Famiglia Articolo"] == famiglia].copy()
    return _normalizza_df(df)


def load_categoria(csv_path: str, categoria: str, escludi: list = []) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = df[df["Categoria Articolo"] == categoria].copy()
    if escludi:
        df = df[~df["Famiglia Articolo"].isin(escludi)]
    return _normalizza_df(df)


# ─────────────────────────────────────────────
# PARSING DESCRIZIONE
# ─────────────────────────────────────────────

def estrai_modello(descrizione: str, finitura: str) -> str:
    raw = descrizione.replace("_" + str(finitura) if pd.notna(finitura) else "", "")
    # ── NUOVO: rimuovi il token rimasto in coda se diverso dalla finitura (es. ANTRACITE vs GRIGIO)
    raw = re.sub(r'_[A-Za-z]+$', '', raw)
    raw = raw.replace("_", " ").lower()
    raw = re.sub(r'\b[hdlp]\d+\b', '', raw)
    raw = re.sub(r'\b\d{4}k(?:-\d{4}k)?\b', '', raw)
    raw = re.sub(r'\s{2,}', ' ', raw).strip()
    return raw[0].upper() + raw[1:] if raw else raw


def estrai_tipo(descrizione: str, famiglia: str) -> str:
    if famiglia in FAMIGLIE_SOLO_COLORE:
        return ""
    pattern = FAMIGLIE_TIPO.get(famiglia, "")
    if not pattern:
        return ""
    match = re.search(pattern, descrizione)
    if not match:
        return ""
    tipo = match.group(1).upper()
    # Per pattern SP (numero luci) usa SP_TIPO_LABEL
    if tipo in SP_TIPO_LABEL:
        return SP_TIPO_LABEL[tipo]
    # Per altri pattern (ROUND, SQUARE ecc.) usa TIPO_LABEL
    tipo_cap = tipo.capitalize()
    return TIPO_LABEL.get(tipo_cap, tipo_cap)


def estrai_temperatura(descrizione: str) -> str:
    match = re.search(r'_(\d{4}K(?:-\d{4}K)?)(?:_|$)', descrizione)
    return match.group(1) if match else ""


def luci_to_tipo_label(n_luci) -> str:
    """Converte il numero di luci (colonna Luci del CSV) nella label Magento di config_tipo."""
    try:
        n = int(float(str(n_luci)))
    except (ValueError, TypeError):
        return ""
    if n == 1:
        return "1 Sorgente Luminosa"
    return f"{n} Sorgenti Luminose"


def estrai_dimensione(descrizione: str, finitura: str, famiglia: str,
                      famiglia_varianti: pd.DataFrame) -> str:

    if famiglia in FAMIGLIE_SENZA_DIMENSIONE:
        return ""

    def estrai_misura(dim_str, prefix):
        m = re.search(rf'{prefix}\s+(\d+)', str(dim_str))
        return int(m.group(1)) if m else None

    modello = descrizione.replace("_" + str(finitura) if pd.notna(finitura) else "", "")
    match   = re.search(r'_(D\d+|H\d+)$', modello)

    if match:
        prefix  = match.group(1)[0]
        dim_str = famiglia_varianti.loc[
            famiglia_varianti["Descrizione"] == descrizione,
            "Dimensione Articolo"
        ].iloc[0]

        if prefix == "D":
            val = estrai_misura(dim_str, "D")
            if val:
                label = "Diametro"
            else:
                val   = estrai_misura(dim_str, "L")
                label = "Lunghezza"
        else:
            val   = estrai_misura(dim_str, prefix)
            label = "Altezza" if prefix == "H" else prefix

        return f"{label} {_mm_to_cm(val)}cm" if val else ""

    # Nessun token in descrizione: cerca quale misura cambia tra le varianti
    for prefix in ["D", "H", "L"]:
        valori = famiglia_varianti["Dimensione Articolo"].apply(
            lambda x: estrai_misura(x, prefix)
        )
        if valori.nunique() > 1:
            val = estrai_misura(
                famiglia_varianti.loc[
                    famiglia_varianti["Descrizione"] == descrizione,
                    "Dimensione Articolo"
                ].iloc[0], prefix
            )
            label = {"D": "Diametro", "H": "Altezza", "L": "Lunghezza"}[prefix]
            return f"{label} {_mm_to_cm(val)}cm" if val else ""

    return ""


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def _mm_to_cm(val_mm: int) -> str:
    """600 → '60', 655 → '65.5'"""
    cm = val_mm / 10
    return str(int(cm)) if cm == int(cm) else str(cm)


def _finitura_label(finitura: str) -> str:
    label = str(finitura).capitalize()
    return FINITURA_LABEL.get(label, label)


def build_nome_semplice(modello: str, finitura: str, attacco: str, tipo: str = "",
                        categoria: str = "", dimensione: str = "", temperatura: str = "") -> str:
    cat_str        = f" {categoria.title()}" if categoria else ""
    finitura_str   = _finitura_label(finitura) if finitura and pd.notna(finitura) else ""
    attacco_str    = str(attacco) if attacco else ""
    modello_str    = modello[0].upper() + modello[1:] if modello else ""
    dimensione_str = dimensione.replace(" ", "-") if dimensione else ""
    tokens = [t for t in [f"{modello_str}{cat_str}", tipo, finitura_str,
                          dimensione_str, temperatura, attacco_str] if t]
    return f"{MARCA} " + "-".join(tokens)


def build_url_key(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


# ─────────────────────────────────────────────
# LOGICA VARIANTI
# ─────────────────────────────────────────────

def _attributi_varianti(gruppo: pd.DataFrame, famiglia: str,
                        color_map: dict, attacco_map: dict,
                        dimensioni_map: dict, tipo_map: dict,
                        temp_map: dict) -> set:
    """
    Restituisce il set dei codici attributo che variano nel gruppo,
    cioè quelli che devono diventare assi configurabili.
    """
    varianti = set()

    # color
    colori = set()
    for _, r in gruppo.iterrows():
        fin = r["Finitura"]
        if pd.notna(fin):
            colori.add(color_map.get(_finitura_label(fin.capitalize()), ""))
    if len(colori) > 1:
        varianti.add("color")

    # config_attacco_lamp
    if gruppo["Attacco Portalampada"].nunique() > 1:
        varianti.add("config_attacco_lamp")

    # config_dimensioni
    dimensioni = set(
        estrai_dimensione(r["Descrizione"], r["Finitura"], famiglia, gruppo)
        for _, r in gruppo.iterrows()
    )
    if len(dimensioni) > 1:
        varianti.add("config_dimensioni")

    # config_tipo
    if famiglia in FAMIGLIE_CONFIG_TIPO_LUCI:
        # Usa direttamente la colonna Luci del CSV
        tipi = set(luci_to_tipo_label(r["Luci"]) for _, r in gruppo.iterrows())
    else:
        tipi = set(estrai_tipo(r["Descrizione"], famiglia) for _, r in gruppo.iterrows())
    if len(tipi) > 1:
        varianti.add("config_tipo")

    # config_temperatura_colore
    temp = set(estrai_temperatura(r["Descrizione"]) for _, r in gruppo.iterrows())
    if len(temp) > 1:
        varianti.add("config_temperatura_colore")

    return varianti


# ─────────────────────────────────────────────
# BUILD PRODOTTO SEMPLICE
# ─────────────────────────────────────────────

def build_simple(row: pd.Series, gruppo: pd.DataFrame,
                 color_map: dict, attacco_map: dict, dimensioni_map: dict,
                 manufacturer_map: dict, tipo_map: dict, temp_map: dict,
                 attribute_set_id: int) -> dict:

    famiglia   = row["Famiglia Articolo"]
    dimensione = estrai_dimensione(row["Descrizione"], row["Finitura"], famiglia, gruppo)
    tipo       = luci_to_tipo_label(row["Luci"]) if famiglia in FAMIGLIE_CONFIG_TIPO_LUCI \
                 else estrai_tipo(row["Descrizione"], famiglia)
    temperatura = estrai_temperatura(row["Descrizione"])
    modello    = estrai_modello(row["Descrizione"], row["Finitura"])

    #print(modello + f"-{row['sku']}")

    # Quali attributi variano nel gruppo
    assi = _attributi_varianti(gruppo, famiglia, color_map, attacco_map,
                                dimensioni_map, tipo_map, temp_map)

    # Costruisce il nome includendo solo le parti che variano
    finitura_nome    = row["Finitura"] if pd.notna(row["Finitura"]) else ""
    attacco_nome     = str(row["Attacco Portalampada"]) if "config_attacco_lamp" in assi else ""
    dimensione_nome  = dimensione if "config_dimensioni" in assi else ""
    tipo_nome        = tipo if "config_tipo" in assi else ""
    temperatura_nome = temperatura if "config_temperatura_colore" in assi else ""

    nome = build_nome_semplice(modello, finitura_nome, attacco_nome, tipo_nome,
                               row["Categoria Articolo"], dimensione_nome, temperatura_nome)

    # Risolve gli ID attributo configurabili (solo quelli che variano)
    attrs_config = []

    if "color" in assi and pd.notna(row["Finitura"]):
        attrs_config.append({
            "attribute_code": "color",
            "value": color_map[_finitura_label(row["Finitura"].capitalize())],
        })

    attacco_val = row["Attacco Portalampada"]
    if "config_attacco_lamp" in assi and attacco_val and pd.notna(attacco_val):
        attrs_config.append({
            "attribute_code": "config_attacco_lamp",
            "value": attacco_map[attacco_val],
        })

    if "config_dimensioni" in assi and dimensione:
        attrs_config.append({
            "attribute_code": "config_dimensioni",
            "value": dimensioni_map[dimensione],
        })

    if "config_tipo" in assi and tipo:
        attrs_config.append({
            "attribute_code": "config_tipo",
            "value": tipo_map[tipo],
        })

    if "config_temperatura_colore" in assi and temperatura:
        attrs_config.append({
            "attribute_code": "config_temperatura_colore",
            "value": temp_map[temperatura],
        })

    return {
        "product": {
            "sku":              f"IL-{row['sku']}",
            "name":             nome,
            "attribute_set_id": attribute_set_id,
            "price":            float(row["prezzo"]),
            "status":           2,
            "visibility":       1,
            "type_id":          "simple",
            "weight":           float(row["Peso Netto"]) if pd.notna(row["Peso Netto"]) else 0,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "stock_item": {
                    "qty":          int(row["qty"]),
                    "is_in_stock":  int(row["is_in_stock"]),
                    "manage_stock": True,
                },
            },
            "custom_attributes": attrs_config + [
                {"attribute_code": "lamp_ean",     "value": str(row["Nr"])},
                {"attribute_code": "manufacturer", "value": manufacturer_map[MARCA]},
                {"attribute_code": "url_key",      "value": build_url_key(nome) + "-" + row["sku"]},
            ],
            "media_gallery_entries": [],
        }
    }


# ─────────────────────────────────────────────
# SOTTOFAMIGLIA
# ─────────────────────────────────────────────

def calcola_sottofamiglia(descrizione: str, famiglia: str, finitura: str) -> str:
    # Famiglie con config_tipo (incluse AMADEUS, CHALET, GALAXY) → raggruppate per famiglia
    if famiglia in FAMIGLIE_CONFIG_TIPO:
        return famiglia
    finitura_str = "" if str(finitura) == "nan" else "_" + str(finitura)
    core = str(descrizione).replace(famiglia + "_", "").replace(finitura_str, "")
    # ── NUOVO: rimuovi anche l'ultimo token se rimasto (es. ANTRACITE ≠ GRIGIO) ──
    core = re.sub(r'_[A-Z]+$', '', core)
    core = re.sub(r'_(D\d+|H\d+|L\d+|\d{4}K[^_]*).*$', '', core)
    core = re.sub(r'^(D\d+|H\d+|L\d+|\d{4}K[^_]*).*$', '', core)
    sottomodello = core.strip("_")
    return f"{famiglia}_{sottomodello}" if sottomodello else famiglia


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    Path("./file").mkdir(exist_ok=True)

    session = get_oauth_session()

    attribute_set_id = get_attribute_set_id(session, ATTRIBUTE_SET_NAME)
    color_map        = get_attribute_options(session, "color")
    attacco_map      = get_attribute_options(session, "config_attacco_lamp")
    dimensioni_map   = get_attribute_options(session, "config_dimensioni")
    tipo_map         = get_attribute_options(session, "config_tipo")
    temp_map         = get_attribute_options(session, "config_temperatura_colore")
    manufacturer_map = get_attribute_options(session, "manufacturer")

    # Carica varianti per categoria
    varianti = load_categoria(CSV_PATH, CATEGORIA)
    varianti["sottofamiglia"] = varianti.apply(
        lambda r: calcola_sottofamiglia(r["Descrizione"], r["Famiglia Articolo"], str(r["Finitura"])),
        axis=1,
    )

    # Genera prodotti semplici
    semplici = []
    for _, gruppo in varianti.groupby("sottofamiglia"):
        for _, row in gruppo.iterrows():
            semplici.append(
                build_simple(row, gruppo, color_map, attacco_map, dimensioni_map,
                             manufacturer_map, tipo_map, temp_map, attribute_set_id)
            )

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(semplici, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_PATH}")
    print(f"    Prodotti generati: {len(semplici)}")
    for s in semplici:
        p  = s["product"]
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