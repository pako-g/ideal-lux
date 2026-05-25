"""
Generatore JSON — Prodotti SEMPLICI Magento
Categoria: Lampada da parete
Output: simple_products_lampada_da_parete.json

STEP 1: solo famiglie singole (29 famiglie, 29 SKU)
Man mano aggiungeremo le regole per le altre famiglie.
"""

import json
import re
import pandas as pd
from pathlib import Path
from utility.magento_api import (
    get_oauth_session, get_attribute_set_id, get_attribute_options
)


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH           = "./file/giacenzeECommerce.csv"
CATEGORIA          = "Lampada da parete"
OUTPUT_PATH        = "./file/simple_products_lampada_da_parete.json"
MARCA              = "Ideal Lux"
ATTRIBUTE_SET_NAME = "Ideal-Lux"
WEBSITE_IDS        = [1]


# ─────────────────────────────────────────────
# FAMIGLIE DA SALTARE COMPLETAMENTE
# ─────────────────────────────────────────────

FAMIGLIE_DA_SALTARE = {
    "CANAPA", "BERGEN", "TRIADE",
}

FINITURE_DA_SALTARE = set()


# ─────────────────────────────────────────────
# LOOKUP LABEL
# ─────────────────────────────────────────────

FINITURA_LABEL = {
    "Coffee":           "Caffè",
    "Nickel":           "Nichel",
    "Ambra sfumato":    "Ambra",
    "Fume' sfumato":    "Fumé",
    "Fume'":            "Fumé",
    "Ottone satinato":  "Ottone Satinato",
    "Cromo sfumato":    "Cromo",
}

DIMMER_LABEL = {
    "ON-OFF":    "On/Off",
    "DALI/PUSH": "Dimmer Dali / Push",
    "DALI": "Dimmer Dali"
}

def finitura_label(finitura: str) -> str:
    label = str(finitura).capitalize()
    return FINITURA_LABEL.get(label, label)

def dimmer_label(token: str) -> str:
    return DIMMER_LABEL.get(token, token)

def luci_label(n) -> str:
    try:
        n = int(float(str(n)))
    except (ValueError, TypeError):
        return ""
    return "1 Sorgente Luminosa" if n == 1 else f"{n} Sorgenti Luminose"

def mm_to_cm(val_mm: int) -> str:
    cm = val_mm / 10
    return str(int(cm)) if cm == int(cm) else str(cm)

def dim_from_col(dim_str: str, prefix: str) -> str:
    m = re.search(rf'{prefix}\s+(\d+)', str(dim_str))
    if not m:
        return ""
    label = {"D": "Diametro", "H": "Altezza", "L": "Lunghezza"}[prefix]
    return f"{label} {mm_to_cm(int(m.group(1)))}cm"

def dim_from_desc(descrizione: str) -> str:
    m = re.search(r'_D(\d+)_', str(descrizione))
    if not m:
        return ""
    return f"Diametro {int(m.group(1))}cm"

def altezza_from_col(dim_str: str) -> str:
    m = re.search(r'H\s+(\d+)', str(dim_str))
    if not m:
        return ""
    return f"Altezza {mm_to_cm(int(m.group(1)))}cm"

def token_from_desc(descrizione: str, pattern: str) -> str:
    m = re.search(pattern, descrizione)
    return m.group(1) if m else ""


# ─────────────────────────────────────────────
# REGOLE PER FAMIGLIA
#
# Ogni entry è un dict con:
#   "gruppo"   : callable(row) → chiave di raggruppamento (default: famiglia)
#   "assi"     : lista di codici attributo configurabili per questa famiglia
#   "valori"   : dict { codice_attributo: callable(row) → valore stringa }
#   "saltare"  : callable(row) → True se il prodotto va escluso (opzionale)
# ─────────────────────────────────────────────

REGOLE: dict[str, dict] = {}

def _solo_colore(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["color"],
            "valori": {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
        }

def _solo_tipo_luci(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_tipo"],
            "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
        }

def _solo_diametro(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_dimensioni"],
            "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
        }

def _solo_lunghezza(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_dimensioni"],
            "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "L")},
        }


# ════════════════════════════════════════════
# STEP 2 — FAMIGLIE SOLO COLORE
# (1 asse: color — 41 famiglie, 112 SKU)
# ════════════════════════════════════════════

_solo_colore(
    "ATLAS", "BASE", "CANTINA", "CARLTON", "CIMA", "CLIO", "CORTE",
    "DESK", "DOWN", "DUBAI", "DYNAMO", "ELIO", "FIRENZE", "FLORIAN",
    "FRIDA", "GAS", "GEA", "GIM", "GIOCONDA", "GIOVE", "GOOSE",
    "IKO", "IO", "LITE", "LITIO", "LOLLY", "MIRROR-10", "NEWTON",
    "PASHA'", "PEGASO", "PIANO", "PIPE", "RADIO", "SIRIO", "TAB",
    "TICK", "TOFFEE", "TRONCO", "TWIN", "WINERY", "XENO",
)


# ════════════════════════════════════════════
# STEP 3 — COLORE + TEMPERATURA COLORE
# (5 famiglie, 44 SKU)
# ════════════════════════════════════════════

# ── ETERE: color + config_temperatura_colore ──
REGOLE["ETERE"] = {
    "assi": ["color", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── RUBIK: color + config_temperatura_colore ──
REGOLE["RUBIK"] = {
    "assi": ["color", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── SNOW: solo config_temperatura_colore (1 solo colore) ──
REGOLE["SNOW"] = {
    "assi": ["config_temperatura_colore"],
    "valori": {
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── STYLE: 2 gruppi (AP normale / AP SENSOR), color + config_temperatura_colore ──
REGOLE["STYLE"] = {
    "gruppo": lambda r: "SENSOR" if "SENSOR" in r["Descrizione"] else "AP",
    "assi": ["color", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── OZ: color + config_temperatura_colore + config_dimmer ──
REGOLE["OZ"] = {
    "assi": ["color", "config_temperatura_colore", "config_dimmer"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
        "config_dimmer":            lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI)")),
    },
}


# ════════════════════════════════════════════
# STEP 4A — FAMIGLIE VARIE / STANDALONE
# ════════════════════════════════════════════

# ── DORICA: color (AP1 unico, tutti colori diversi) ──
_solo_colore("DORICA")

# ── ELF: color (con label speciali per bicolore) ──
FINITURA_LABEL["Bianco oro"] = "Bianco / Oro"

def _elf_color(r):
    desc = r["Descrizione"]
    if "ORO+BIANCO" in desc:
        return "Bianco / Oro"
    elif "ORO+NERO" in desc:
        return "Nero / Oro"
    return finitura_label(r["Finitura"].capitalize())

REGOLE["ELF"] = {
    "assi":   ["color"],
    "valori": {"color": _elf_color},
}

# ── EQUINOXE: color ──
_solo_colore("EQUINOXE")

# ── DYNAMITE: gruppo per shape (SQUARE/ROUND), saltare PL ──
#    SQUARE: AP1(1 luce) + AP2(2 luci) → color + config_tipo
#    ROUND:  solo AP2(2 luci)          → color
REGOLE["DYNAMITE"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"(?:AP\d+|PL\d+)_(ROUND|SQUARE)"),
    "saltare": lambda r: "PL" in r["Descrizione"],
    "assi":    ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── KEOPE: color + config_tipo (1,2 sorgenti luminose) ──
REGOLE["KEOPE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── RUDY: gruppo per shape (ROUND/SQUARE), color + config_tipo ──
REGOLE["RUDY"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"AP\d+_(ROUND|SQUARE)"),
    "assi":   ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── FEBE: config_tipo (Orizzontale / Verticale) ──
REGOLE["FEBE"] = {
    "assi":   ["config_tipo"],
    "valori": {
        "config_tipo": lambda r: "Orizzontale" if "FEBE-1" in r["Descrizione"] else "Verticale",
    },
}

# ── OBY: config_tipo (1,2 sorgenti luminose) ──
REGOLE["OBY"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
}

# ── SODA: config_dimensioni (lunghezza) ──
REGOLE["SODA"] = {
    "assi":   ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "L")},
}

# ── TRIPLO: config_dimensioni (altezza) ──
REGOLE["TRIPLO"] = {
    "assi":   ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: altezza_from_col(r["Dimensione Articolo"])},
}

# ── TRIUMPH: config_tipo (1,2 sorgenti luminose) ──
REGOLE["TRIUMPH"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
}

# ── DA SALTARE ──
FAMIGLIE_DA_SALTARE.update({"POSTA", "BOOK", "PENTA"})


# ════════════════════════════════════════════
# STEP 4E — FAMIGLIE CON CONFIG_TIPO / TEMPERATURA
# (5 famiglie)
# ════════════════════════════════════════════

# ── PRIVE': color + config_tipo (6,8 sorgenti luminose) ──
REGOLE["PRIVE'"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── REX: gruppo(REX-1, REX-2, REX-3), color ──
REGOLE["REX"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"(REX-\d)"),
    "assi":   ["color"],
    "valori": {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
}

# ── TETRIS: gruppo(TETRIS-1, TETRIS-2), color ──
REGOLE["TETRIS"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"(TETRIS-\d)"),
    "assi":   ["color"],
    "valori": {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
}

# ── ARGO: gruppo(AP1, AP2), color + config_temperatura_colore ──
REGOLE["ARGO"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"ARGO_(AP\d)"),
    "assi": ["color", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── OMEGA: color + config_tipo (Round, Square) + config_temperatura_colore ──
REGOLE["OMEGA"] = {
    "assi": ["color", "config_tipo", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo":              lambda r: token_from_desc(r["Descrizione"], r"AP_(ROUND|SQUARE)").capitalize(),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}


# ════════════════════════════════════════════
# STEP 4F — SOLO DIMENSIONI / CONFIG_TIPO (senza colore)
# (12 famiglie)
# ════════════════════════════════════════════

# ── MAPA: config_dimensioni (diametro) ──
_solo_diametro("MAPA")

# ── COTTON: config_dimensioni (diametro) ──
_solo_diametro("COTTON")

# ── MAKE-UP: config_dimensioni (lunghezza) ──
_solo_lunghezza("MAKE-UP")

# ── PRETTY: config_dimensioni (lunghezza) ──
_solo_lunghezza("PRETTY")

# ── CLICK: config_dimensioni (lunghezza) ──
_solo_lunghezza("CLICK")

# ── BLOCK: config_dimensioni (lunghezza) ──
_solo_lunghezza("BLOCK")

# ── CAMERINO: config_dimensioni (lunghezza) ──
_solo_lunghezza("CAMERINO")

# ── KOALA: config_potenza (3W / 7W) ──
def _koala_potenza(r):
    m = re.search(r'_(\d+)W', r["Descrizione"])
    return f"{m.group(1)} Watt" if m else ""

REGOLE["KOALA"] = {
    "assi":   ["config_potenza"],
    "valori": {"config_potenza": _koala_potenza},
}

# ── PEGGY: config_dimensioni (lunghezza) ──
_solo_lunghezza("PEGGY")

# ── FLASH: config_tipo (High, Round, Small) ──
REGOLE["FLASH"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: token_from_desc(r["Descrizione"], r"AP1_(HIGH|ROUND|SMALL)").capitalize()},
}

# ── POUCHE: config_tipo (Round, Square) ──
REGOLE["POUCHE"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: token_from_desc(r["Descrizione"], r"AP_(ROUND|SQUARE)").capitalize()},
}

# ── TERRA: config_dimensioni (lunghezza) ──
_solo_lunghezza("TERRA")


# ════════════════════════════════════════════
# STEP 1 — PRODOTTI SINGOLI standalone
# (1 solo prodotto per famiglia, nessuna config)
# ════════════════════════════════════════════

for _f in [
    "ALI", "APOLLO", "BARBER", "BIRDS", "CARTA", "CHALET", "COMETA",
    "CRAFT", "CUBE", "ECLISSI", "EDISON", "FIX", "HAREM", "KEPLER",
    "MIRROR-20", "MORIS", "NEGRESCO", "NORDIK", "O-ZONE", "OPERA",
    "OVALINO", "PAN", "PAUL", "PETER", "RETRO'", "ROMA", "SHOWER",
    "SMARTIES", "STRAUSS",
]:
    REGOLE[_f] = {"assi": [], "valori": {}}


# ─────────────────────────────────────────────
# CARICAMENTO CSV
# ─────────────────────────────────────────────

def _normalizza_df(df: pd.DataFrame) -> pd.DataFrame:
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


def load_categoria(csv_path: str, categoria: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = df[df["Categoria Articolo"] == categoria].copy()
    return _normalizza_df(df)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def build_url_key(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def build_nome(row: pd.Series, regola: dict, assi: list) -> str:
    famiglia = row["Famiglia Articolo"]
    desc     = row["Descrizione"].replace("_", " ").lower()

    fin_str = str(row["Finitura"]).lower() if pd.notna(row["Finitura"]) else ""
    modello = desc.replace(fin_str, "")
    modello = re.sub(r'\b[hdlp]\d+\b', '', modello)
    modello = re.sub(r'\b\d{4}k(?:-\d{4}k)?\b', '', modello)
    modello = re.sub(r'\s{2,}', ' ', modello).strip().strip("-").strip()
    modello = modello[0].upper() + modello[1:] if modello else modello

    parti = [f"{MARCA} {modello} Lampada Da Parete"]

    valori = regola.get("valori", {})

    if "config_tipo" in assi:
        tipo = valori["config_tipo"](row)
        if tipo:
            parti.append(tipo)

    if "color" in assi and pd.notna(row["Finitura"]):
        parti.append(finitura_label(row["Finitura"].capitalize()))

    if "config_dimensioni" in assi:
        dim = valori["config_dimensioni"](row)
        if dim:
            parti.append(dim.replace(" ", "-"))

    if "config_temperatura_colore" in assi:
        temp = valori["config_temperatura_colore"](row)
        if temp:
            parti.append(temp)

    return "-".join(parti)


# ─────────────────────────────────────────────
# BUILD PRODOTTO SEMPLICE
# ─────────────────────────────────────────────

def build_simple(row: pd.Series, assi: list, regola: dict,
                 color_map: dict, attacco_map: dict, dimensioni_map: dict,
                 manufacturer_map: dict, tipo_map: dict, temp_map: dict,
                 dimmer_map: dict, potenza_map: dict, attribute_set_id: int) -> dict:

    nome   = build_nome(row, regola, assi)
    valori = regola.get("valori", {})

    print(f"  {row['sku']}  {nome}")

    attrs_config = []

    if "color" in assi and pd.notna(row["Finitura"]):
        label = finitura_label(row["Finitura"].capitalize())
        attrs_config.append({
            "attribute_code": "color",
            "value": color_map[label],
        })

    if "config_tipo" in assi:
        tipo = valori["config_tipo"](row)
        if tipo:
            attrs_config.append({
                "attribute_code": "config_tipo",
                "value": tipo_map[tipo],
            })

    if "config_dimensioni" in assi:
        dim = valori["config_dimensioni"](row)
        if dim:
            attrs_config.append({
                "attribute_code": "config_dimensioni",
                "value": dimensioni_map[dim],
            })

    if "config_temperatura_colore" in assi:
        temp = valori["config_temperatura_colore"](row)
        if temp:
            attrs_config.append({
                "attribute_code": "config_temperatura_colore",
                "value": temp_map[temp],
            })

    if "config_dimmer" in assi:
        dimmer = valori["config_dimmer"](row)
        if dimmer:
            attrs_config.append({
                "attribute_code": "config_dimmer",
                "value": dimmer_map[dimmer],
            })

    if "config_attacco_lamp" in assi:
        attacco = valori["config_attacco_lamp"](row)
        if attacco:
            attrs_config.append({
                "attribute_code": "config_attacco_lamp",
                "value": attacco_map[attacco],
            })

    if "config_potenza" in assi:
        potenza = valori["config_potenza"](row)
        if potenza:
            attrs_config.append({
                "attribute_code": "config_potenza",
                "value": potenza_map[potenza],
            })

    # Singoli standalone → visibility 4, con config → visibility 1
    visibility = 4 if not assi else 1

    return {
        "product": {
            "sku":              f"IL-{row['sku']}",
            "name":             nome,
            "attribute_set_id": attribute_set_id,
            "price":            float(row["prezzo"]),
            "status":           2,
            "visibility":       visibility,
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
    dimmer_map       = get_attribute_options(session, "config_dimmer")
    potenza_map      = get_attribute_options(session, "config_potenza")

    varianti = load_categoria(CSV_PATH, CATEGORIA)

    semplici      = []
    famiglie_skip = []
    famiglie_ok   = []

    for famiglia, g_fam in varianti.groupby("Famiglia Articolo"):

        if famiglia in FAMIGLIE_DA_SALTARE:
            continue

        if FINITURE_DA_SALTARE:
            g_fam = g_fam[~g_fam["Finitura"].isin(FINITURE_DA_SALTARE)].copy()
        if g_fam.empty:
            continue

        if famiglia not in REGOLE:
            famiglie_skip.append(famiglia)
            continue

        regola = REGOLE[famiglia]

        gruppo_fn = regola.get("gruppo", lambda r: famiglia)
        g_fam["_gruppo"] = g_fam.apply(gruppo_fn, axis=1)

        for gruppo_key, gruppo in g_fam.groupby("_gruppo"):

            if "_assi_dinamici" in regola:
                assi_def, valori_override = regola["_assi_dinamici"](gruppo_key)
                regola_gruppo = {**regola, "assi": assi_def, "valori": valori_override}
            else:
                assi_def = regola["assi"]
                regola_gruppo = regola

            saltare_fn = regola_gruppo.get("saltare")

            assi_attivi = []
            for asse in assi_def:
                fn = regola_gruppo["valori"].get(asse)
                if fn is None:
                    continue
                valori_gruppo = set(fn(r) for _, r in gruppo.iterrows())
                valori_gruppo.discard("")
                if len(valori_gruppo) > 1:
                    assi_attivi.append(asse)

            for _, row in gruppo.iterrows():
                if saltare_fn and saltare_fn(row):
                    continue
                semplici.append(
                    build_simple(row, assi_attivi, regola_gruppo,
                                 color_map, attacco_map, dimensioni_map,
                                 manufacturer_map, tipo_map, temp_map, dimmer_map,
                                 potenza_map, attribute_set_id)
                )

        famiglie_ok.append(famiglia)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(semplici, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {OUTPUT_PATH}")
    print(f"    Prodotti generati: {len(semplici)}")

    if famiglie_skip:
        print(f"\n⚠️  Famiglie senza regola ({len(famiglie_skip)}) — da aggiungere:")
        for f in sorted(set(famiglie_skip)):
            print(f"     - {f}")