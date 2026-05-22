"""
Generatore JSON — Prodotti SEMPLICI Magento
Categoria: Lampada a sospensione
Output: simple_products_lampada_a_sospensione.json

Struttura: ogni famiglia ha una regola esplicita che definisce
- gli assi configurabili (color, config_tipo, config_dimensioni, config_temperatura_colore)
- come estrarre il valore di ciascun asse dalla riga CSV
- come raggruppare le varianti (chiave di raggruppamento)
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
CATEGORIA          = "Lampada a sospensione"
OUTPUT_PATH        = "./file/simple_products_lampada_a_sospensione.json"
MARCA              = "Ideal Lux"
ATTRIBUTE_SET_NAME = "Ideal-Lux"
WEBSITE_IDS        = [1]


# ─────────────────────────────────────────────
# FAMIGLIE DA SALTARE COMPLETAMENTE
# ─────────────────────────────────────────────

FAMIGLIE_DA_SALTARE = {
    "CANAPA", "BERGEN", "TRIADE",   # escluse dal catalogo
    "BOA", "KING", "MANHATTAN",     # da saltare per ora
    "ULTRATHIN", "MAPA PLUS",       # da saltare per ora
    "STEEL",                        # sistema lineare, gestione separata
}

# Finiture da saltare (indipendentemente dalla famiglia)
FINITURE_DA_SALTARE = {"CORTEN"}


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
    """Estrae una misura dalla colonna Dimensione Articolo e la converte in label cm."""
    m = re.search(rf'{prefix}\s+(\d+)', str(dim_str))
    if not m:
        return ""
    label = {"D": "Diametro", "H": "Altezza", "L": "Lunghezza"}[prefix]
    return f"{label} {mm_to_cm(int(m.group(1)))}cm"

def altezza_from_col(dim_str: str) -> str:
    """Estrae H dalla colonna Dimensione Articolo e converte in label cm."""
    m = re.search(r'H\s+(\d+)', str(dim_str))
    if not m:
        return ""
    return f"Altezza {mm_to_cm(int(m.group(1)))}cm"

def token_from_desc(descrizione: str, pattern: str) -> str:
    """Estrae un token dalla descrizione tramite regex, gruppo 1."""
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

# ── HELPER per registrare famiglie solo-colore ──
def _solo_colore(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["color"],
            "valori": {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
        }

# ── HELPER per famiglie solo config_tipo (numero luci) ──
def _solo_tipo_luci(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_tipo"],
            "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
        }

# ── HELPER per famiglie solo config_dimensioni (diametro) ──
def _solo_diametro(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_dimensioni"],
            "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
        }

# ── HELPER per famiglie solo config_dimensioni (lunghezza) ──
def _solo_lunghezza(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_dimensioni"],
            "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "L")},
        }


# ════════════════════════════════════════════
# FAMIGLIE SOLO COLORE
# ════════════════════════════════════════════

_solo_colore(
    "ARCHIMEDE",   # ← NB: ha anche config_tipo (Cilindro/Cono/Sfera) → override sotto
    "AUDI-10",
    "CANTINA",
    "CLIO",
    "COLOSSAL",
    "CONO",
    "DESK",
    "DIESIS",
    "ECLIPSE",
    "EDISON",
    "FADE",
    "FRIDA",
    "HOLLY",
    "LUCCIOLA",
    "MADAME",
    "MARTINEZ",
    "MIX-UP",
    "MOBY",
    "NORMA",
    "SET UP",
    "V-LINE",
    "YOKO",
)

# Override ARCHIMEDE: color + config_tipo (Cilindro, Cono, Sfera)
REGOLE["ARCHIMEDE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: token_from_desc(r["Descrizione"],
                                                  r"_SP_([A-Z]+)_").capitalize(),
    },
}

# ULTRATHIN: solo colore (3 colori ma standalone per ora)
_solo_colore("ULTRATHIN")


# ════════════════════════════════════════════
# FAMIGLIE SOLO CONFIG_TIPO (numero luci)
# ════════════════════════════════════════════

_solo_tipo_luci(
    "AMADEUS",      # 6, 8
    "BON BON",      # 6, 8
    "CHALET",       # 6, 8, 12
    "COPERNICO",    # 12, 20
    "DANIELI",      # 6, 8
    "FIESTA",       # 5, 10
    "GALAXY",       # 3, 6
    "GLORY",        # ← override sotto (config_dimensioni)
    "KONSE",        # 1, 6, 7
    "MAPA PLUS",    # saltato sopra, ignorato
    "MONET",        # 5, 6
    "NABUCCO",      # 12, 16
    "NEGRESCO",     # 8, 10
    "OPERA",        # 4, 6, 10
    "OVALINO",      # ← override sotto (config_dimensioni)
    "SMARTIES",     # ← override sotto (config_dimensioni)
    "STRAUSS",      # 6, 12, 18
    "UMILE",        # ← override sotto (sottofamiglie)
    "MINOR",        # ← override sotto (sottofamiglie)
)


# ════════════════════════════════════════════
# FAMIGLIE SOLO CONFIG_DIMENSIONI (diametro)
# ════════════════════════════════════════════

_solo_diametro(
    "BREEZE",
    "CANDY",
    "CARTA",
    "COTTON",
    "DREAM BIG",
    "EMPIRE",       # ← override sotto (config_tipo)
    "HULAHOOP",
    "LENA",
    "MIRACLE",
    "NORDIK",       # ← override sotto (config_dimensioni diametro)
    "ONION",
    "SOLE",
    "ULISSE",
)

# Override GLORY: config_dimensioni (diametro), non luci
REGOLE["GLORY"] = {
    "assi": ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
}

# Override OVALINO: config_dimensioni (diametro)
REGOLE["OVALINO"] = {
    "assi": ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
}

# Override SMARTIES: config_dimensioni (diametro)
REGOLE["SMARTIES"] = {
    "assi": ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
}

# Override NORDIK: config_dimensioni (diametro)
REGOLE["NORDIK"] = {
    "assi": ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
}

# Override EMPIRE: config_tipo (Cilindro, Cono, Sfera)
REGOLE["EMPIRE"] = {
    "assi": ["config_tipo"],
    "valori": {
        "config_tipo": lambda r: token_from_desc(r["Descrizione"],
                                                  r"_SP1_([A-Z]+)$").capitalize(),
    },
}


# ════════════════════════════════════════════
# FAMIGLIE SOLO CONFIG_DIMENSIONI (lunghezza)
# ════════════════════════════════════════════

_solo_lunghezza("CIRCUS")

# FRAME: color + config_tipo (Cerchio, Quadrato, Rettangolo)
REGOLE["FRAME"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: token_from_desc(r["Descrizione"],
                                                  r"_SP_([A-Z]+)_").capitalize(),
    },
}


# ════════════════════════════════════════════
# FAMIGLIE CON SOTTOGRUPPI (gruppo != famiglia)
# ════════════════════════════════════════════

# ARIZONA: config_dimensioni (diametro) — gruppo unico
REGOLE["ARIZONA"] = {
    "assi": ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
}

# FOLK: SP1 → config_dimensioni (diametro), SP3 → singola
REGOLE["FOLK"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"_(SP\d+)"),
    "assi":   ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
    "saltare": lambda r: "SP3" in r["Descrizione"],   # SP3 → singola
}

# HAREM: SP1 → singola, SP9 → singola (tutti standalone)
REGOLE["HAREM"] = {
    "gruppo":  lambda r: r["Descrizione"],  # chiave = prodotto singolo
    "assi":    [],
    "valori":  {},
}

# MILK: SP1 → singola, SP3 → singola
REGOLE["MILK"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# MINOR: LINEAR → config_tipo luci, ROUND → config_tipo luci (gruppi separati)
REGOLE["MINOR"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"MINOR_(LINEAR|ROUND)"),
    "assi":    ["config_tipo"],
    "valori":  {"config_tipo": lambda r: luci_label(r["Luci"])},
}

# UMILE: SP3 → singola, UMILE-1/2/3 SP1 → config_dimensioni (diametro)
REGOLE["UMILE"] = {
    "gruppo":  lambda r: "SP3" if "SP3" in r["Descrizione"] else "SP1",
    "assi":    ["config_dimensioni"],
    "valori":  {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
    "saltare": lambda r: "SP3" in r["Descrizione"],   # SP3 → singola
}

# ODEON: SP1 → config_dimensioni (diametro), SP3/SP6 → singole
REGOLE["ODEON"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"_(SP\d+)"),
    "assi":    ["config_dimensioni"],
    "valori":  {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
    "saltare": lambda r: any(x in r["Descrizione"] for x in ["SP3", "SP6"]),
}

# AMPOLLA: tutti singoli (forme diverse)
REGOLE["AMPOLLA"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# CITRUS: tutti singoli (forme diverse)
REGOLE["CITRUS"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# COCO: tutti singoli (forme diverse)
REGOLE["COCO"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# LUMIERE: tutti singoli (forme diverse)
REGOLE["LUMIERE"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# OIL: tutti singoli (forme diverse)
REGOLE["OIL"] = {
    "gruppo":  lambda r: r["Descrizione"],
    "assi":    [],
    "valori":  {},
}

# ESSENCE: ROUND e SQUARE separati, color + config_temperatura
REGOLE["ESSENCE"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"ESSENCE_SP_(ROUND|SQUARE)"),
    "assi":    ["color", "config_temperatura_colore"],
    "valori":  {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"],
                                                                r"_(\d{4}K(?:-\d{4}K)?)(?:_|$)"),
    },
}

# WAVES: color + config_dimensioni (lunghezza)
REGOLE["WAVES"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "L"),
    },
}

# PRODOTTI SINGOLI standalone (1 solo prodotto per famiglia)
for _f in ["ABC", "ARIA", "BIRDS", "CASANOVA", "CLOWN", "CRAFT", "CYLINDER",
           "DRIFTWOOD", "KARMA", "KAROUSEL", "LANA", "LORD", "LUXOR",
           "MAPA MAX", "OAK", "ORIGAMI", "PAN", "POP", "RHAPSODY",
           "TALL", "TOPICO", "TRIUMPH", "VANITY"]:
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
    """Costruisce il nome del prodotto includendo solo le parti che variano."""
    famiglia = row["Famiglia Articolo"]
    desc     = row["Descrizione"].replace("_", " ").lower()

    # Modello base: rimuove finitura e token tecnici dalla descrizione
    fin_str = str(row["Finitura"]).lower() if pd.notna(row["Finitura"]) else ""
    modello = desc.replace(fin_str, "")
    modello = re.sub(r'\b[hdlp]\d+\b', '', modello)
    modello = re.sub(r'\b\d{4}k(?:-\d{4}k)?\b', '', modello)
    modello = re.sub(r'\s{2,}', ' ', modello).strip().strip("-").strip()
    modello = modello[0].upper() + modello[1:] if modello else modello

    parti = [f"{MARCA} {modello} Lampada A Sospensione"]

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
                 dimmer_map: dict, attribute_set_id: int) -> dict:

    nome    = build_nome(row, regola, assi)
    valori  = regola.get("valori", {})

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
# MAIN
# ─────────────────────────────────────────────


# REGOLE AGGIUNTIVE — 49 famiglie mancanti
# ════════════════════════════════════════════

# ── A-LINE: color + config_dimensioni (diametro, token in descrizione) ──
REGOLE["A-LINE"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── ATLAS: color + config_tipo (luci) ──
REGOLE["ATLAS"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── AUDI-80: color + config_tipo (luci) ──
REGOLE["AUDI-80"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── BISTRO': color + config_tipo (Plate, Round, Square) ──
REGOLE["BISTRO'"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: token_from_desc(r["Descrizione"],
                                                  r"BISTRO'_SP1_(PLATE|ROUND|SQUARE)").capitalize(),
    },
}

# ── BLANCHE: color + config_tipo (luci) ──
REGOLE["BLANCHE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── BLOOM: color + config_dimensioni (diametro, token in descrizione) ──
REGOLE["BLOOM"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── BRIGITTA: color + config_tipo (luci) ──
REGOLE["BRIGITTA"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── CAESAR: color + config_tipo (luci) ──
REGOLE["CAESAR"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── CARLTON: color + config_tipo (luci) ──
REGOLE["CARLTON"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── COCKTAIL: LED → color, SP1 → config_dimensioni (D), SP3 → singolo ──
REGOLE["COCKTAIL"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"COCKTAIL_(LED|SP1|SP3)"),
    "saltare": lambda r: "SP3" in r["Descrizione"],
    "assi":    ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── CORTE: color + config_tipo (luci) ──
REGOLE["CORTE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── CROWN: color + config_dimensioni (diametro, token in descrizione) ──
REGOLE["CROWN"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── DIAMOND: config_tipo (luci) — 1 solo colore (TRASPARENT) ──
REGOLE["DIAMOND"] = {
    "assi": ["config_tipo"],
    "valori": {
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── DORICA: SP1 e SP3 separati, solo color ──
REGOLE["DORICA"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"DORICA_(SP\d+)"),
    "assi":    ["color"],
    "valori":  {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
    "saltare": lambda r: pd.isna(r["Finitura"]),
}

# ── DUBAI: color + config_tipo (luci) ──
REGOLE["DUBAI"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── DYNAMITE: ROUND e SQUARE separati, color + config_tipo (luci) ──
REGOLE["DYNAMITE"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"DYNAMITE_SP\d+_(ROUND|SQUARE)"),
    "assi":    ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── EQUINOXE:
#   SP1        → color + config_dimensioni (D15/D20/D25)
#   SP3+SP6    → color + config_tipo (3, 6 sorgenti)
#   SP8+SP12   → color + config_tipo (8, 12 sorgenti)
# ──
def _equinoxe_gruppo(r):
    spx = token_from_desc(r["Descrizione"], r"EQUINOXE_(SP\d+)")
    if spx == "SP1":
        return "SP1"
    elif spx in ("SP3", "SP6"):
        return "SP3-SP6"
    else:
        return "SP8-SP12"

def _equinoxe_assi_valori(spx_gruppo):
    if spx_gruppo == "SP1":
        return (
            ["color", "config_dimensioni"],
            {
                "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
            }
        )
    else:
        return (
            ["color", "config_tipo"],
            {
                "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_tipo": lambda r: luci_label(r["Luci"]),
            }
        )

# Per EQUINOXE usiamo una regola speciale con assi/valori dinamici per gruppo
REGOLE["EQUINOXE"] = {
    "gruppo":         _equinoxe_gruppo,
    "_assi_dinamici": _equinoxe_assi_valori,  # usato nel main per override assi/valori
    "assi":           ["color", "config_dimensioni"],  # fallback
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
    "saltare": lambda r: pd.isna(r["Finitura"]),
}

# ── ERIS: ogni ERIS-N → singolo (color unico per forma) ──
REGOLE["ERIS"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"(ERIS-\d)"),
    "assi":    ["color"],
    "valori":  {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
}

# ── FILO: gestione manuale sottogruppi ──
# SP1 standard (BIANCO 2700K) → singolo
# SP1 LONG WIRE (BIANCO/NERO/OTTONE 3000K) → color
# SP12 (BIANCO 2700K + 3000K) → config_temperatura
REGOLE["FILO"] = {
    "gruppo": lambda r: (
        "SP1_STD"       if "SP1" in r["Descrizione"] and "LONG" not in r["Descrizione"] and "BIANCO" in r["Descrizione"] else
        "SP1_LONG_WIRE" if "LONG" in r["Descrizione"] else
        "SP12"
    ),
    "assi": ["color", "config_temperatura_colore"],
    "valori": {
        "color":                     lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_temperatura_colore":  lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── FIRENZE: color + config_tipo (luci) ──
REGOLE["FIRENZE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── FLAM: color (dopo aggiornamento CSV finitura) ──
REGOLE["FLAM"] = {
    "assi":   ["color"],
    "valori": {"color": lambda r: finitura_label(str(r["Finitura"]).capitalize())},
    "saltare": lambda r: pd.isna(r["Finitura"]),
}

# ── FLORIAN: color + config_tipo (luci) ──
REGOLE["FLORIAN"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── FLUT: color + config_dimensioni (diametro) ──
REGOLE["FLUT"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── GEMINI: color + config_dimensioni + config_temperatura + config_dimmer ──
REGOLE["GEMINI"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore", "config_dimmer"],
    "valori": {
        "color":                     lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":          lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore":  lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
        "config_dimmer":       lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI/PUSH)")),
    },
}

# ── GIOCONDA: color + config_tipo (luci) ──
REGOLE["GIOCONDA"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── KALIQUE: ogni KALIQUE-N → config_dimensioni (D18/D28) + color ──
REGOLE["KALIQUE"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"(KALIQUE-\d)"),
    "assi":    ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── LINGOTTO: color + config_tipo (luci) ──
REGOLE["LINGOTTO"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── LOOK: da fare dopo ──
# ── MAPA / MAPA CLEAR / MAPA MINI: da fare dopo ──

# ── MINT: ogni MINT-N → color (singolo per forma) ──
REGOLE["MINT"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"(MINT-\d)"),
    "assi":    ["color"],
    "valori":  {"color": lambda r: finitura_label(r["Finitura"].capitalize())},
}

# ── MR JACK: color + config_dimensioni (diametro) ──
REGOLE["MR JACK"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── NAPOLEON: color + config_tipo (luci) ──
REGOLE["NAPOLEON"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── NEMO: SP1 → color + config_dimensioni (D), SP5 → singolo ──
REGOLE["NEMO"] = {
    "gruppo":  lambda r: token_from_desc(r["Descrizione"], r"NEMO_(SP\d+)"),
    "saltare": lambda r: "SP5" in r["Descrizione"],
    "assi":    ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── NET: color + config_dimensioni (diametro) ──
REGOLE["NET"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── NODI: color + config_tipo (luci) ──
REGOLE["NODI"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── ORACLE: color + config_dimensioni (diametro) ──
REGOLE["ORACLE"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── ORACLE SLIM: color + config_dimensioni + config_temperatura ──
REGOLE["ORACLE SLIM"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "color":                     lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":          lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore":  lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)_"),
    },
}

# ── OZ: color + config_dimensioni + config_temperatura ──
REGOLE["OZ"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "color":                     lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":          lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore":  lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)$"),
    },
}

# ── PASHA': color + config_tipo (luci) ──
REGOLE["PASHA'"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── PEGASO: color + config_tipo (luci) ──
REGOLE["PEGASO"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── PERLAGE: color + config_tipo (luci) ──
REGOLE["PERLAGE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── PERLINE: color + config_tipo (luci) ──
REGOLE["PERLINE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── PLISSE': color + config_dimensioni (diametro) ──
REGOLE["PLISSE'"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── SOFT: color + config_tipo (luci) ──
REGOLE["SOFT"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── TUBE: color + config_dimensioni (diametro) ──
REGOLE["TUBE"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── TUBIX: config_dimensioni (altezza dal codice D050/075/100) ──
_TUBIX_DIM = {"050": "Altezza 64.5cm", "075": "Altezza 113cm", "100": "Altezza 134.5cm"}
REGOLE["TUBIX"] = {
    "assi": ["config_dimensioni"],
    "valori": {
        "config_dimensioni": lambda r: _TUBIX_DIM.get(
            token_from_desc(r["Descrizione"], r"TUBIX_SP_D(\d+)"), ""
        ),
    },
}

# ── YURTA: color + config_dimensioni (diametro) ──
REGOLE["YURTA"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── MAPA: SP1 → config_dimensioni (diametro), PENDEL → config_attacco + config_dimensioni (altezza) ──
REGOLE["MAPA"] = {
    "gruppo": lambda r: (
        "SP1"          if "SP1" in r["Descrizione"] else
        "PENDEL_BIG"   if "LED_BIG" in r["Descrizione"] else
        "PENDEL_SMALL" if "LED_SMALL" in r["Descrizione"] else
        "PENDEL"
    ),
    "assi": ["config_attacco_lamp", "config_dimensioni"],
    "valori": {
        "config_attacco_lamp": lambda r: (
            ""  if "SP1" in r["Descrizione"] or "LED" in r["Descrizione"]
            else token_from_desc(r["Descrizione"], r"PENDEL_(E14|E27|G4|G9)")
        ),
        "config_dimensioni": lambda r: (
            dim_from_col(r["Dimensione Articolo"], "D") if "SP1" in r["Descrizione"]
            else altezza_from_col(r["Dimensione Articolo"])
        ),
    },
}

# ── LOOK ──
def _look_gruppo(r):
    desc = r["Descrizione"]
    if "PL1" in desc:                          return "PL1"
    if "SP1_D04" in desc or "SP1_D12" in desc: return "SKIP"
    if "LED" in desc:
        luci = int(r["Luci"])
        if luci > 1:                           return "LED_DROP"
        if "ROUND" in desc:                    return "LED_SP1_ROUND"
        if "SQUARE" in desc:                   return "LED_SP1_SQUARE"
    if "ROUND" in desc:                        return "SP1_ROUND"
    if "SQUARE" in desc:                       return "SP1_SQUARE"
    return "SKIP"

def _look_dim(r):
    import re
    desc = r["Descrizione"]
    d = re.search(r'_D(\d+)_', desc)
    h = re.search(r'_H(\d+)_', desc)
    gruppo = _look_gruppo(r)
    d_cm = mm_to_cm(int(d.group(1)) * 10) if d else ""
    h_cm = mm_to_cm(int(h.group(1)) * 10) if h else ""
    if gruppo in ("SP1_ROUND", "LED_SP1_ROUND"):
        return f"Diametro {d_cm}cm - Altezza {h_cm}cm" if d_cm and h_cm else ""
    if gruppo in ("SP1_SQUARE", "LED_SP1_SQUARE"):
        return f"Larghezza {d_cm}cm" if d_cm else ""
    return ""

def _look_assi_valori(gruppo_key):
    if gruppo_key == "LED_SP1_ROUND":
        return (
            ["color", "config_dimensioni", "config_dimmer"],
            {
                "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_dimensioni": _look_dim,
                "config_dimmer":    lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI/PUSH)")),
            }
        )
    if gruppo_key == "LED_SP1_SQUARE":
        return (
            ["color", "config_dimensioni"],
            {
                "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_dimensioni": _look_dim,
            }
        )
    if gruppo_key == "LED_DROP":
        return (
            ["color", "config_tipo", "config_temperatura_colore"],
            {
                "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_tipo":              lambda r: luci_label(r["Luci"]),
                "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)_"),
            }
        )
    if gruppo_key == "SP1_ROUND":
        return (
            ["color", "config_dimensioni"],
            {
                "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_dimensioni": _look_dim,
            }
        )
    if gruppo_key == "SP1_SQUARE":
        return (
            ["color", "config_dimensioni"],
            {
                "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
                "config_dimensioni": _look_dim,
            }
        )
    # PL1 e SKIP → singoli/saltati
    return ([], {})

REGOLE["LOOK"] = {
    "gruppo":         _look_gruppo,
    "_assi_dinamici": _look_assi_valori,
    "assi":           [],
    "valori":         {},
    "saltare":        lambda r: _look_gruppo(r) == "SKIP",
}

# ── MAPA MINI e MAPA CLEAR: saltare ──
REGOLE["MAPA MINI"]  = {"assi": [], "valori": {}, "saltare": lambda r: True}
REGOLE["MAPA CLEAR"] = {"assi": [], "valori": {}, "saltare": lambda r: True}




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

    varianti = load_categoria(CSV_PATH, CATEGORIA)

    semplici      = []
    famiglie_skip = []
    famiglie_ok   = []

    for famiglia, g_fam in varianti.groupby("Famiglia Articolo"):

        # Famiglie escluse
        if famiglia in FAMIGLIE_DA_SALTARE:
            continue

        # Escludi finiture da saltare
        g_fam = g_fam[~g_fam["Finitura"].isin(FINITURE_DA_SALTARE)].copy()
        if g_fam.empty:
            continue

        # Regola non ancora definita
        if famiglia not in REGOLE:
            famiglie_skip.append(famiglia)
            continue

        regola = REGOLE[famiglia]
        saltare_fn = regola.get("saltare")

        # Calcola chiave di raggruppamento
        gruppo_fn = regola.get("gruppo", lambda r: famiglia)
        g_fam["_gruppo"] = g_fam.apply(gruppo_fn, axis=1)

        for gruppo_key, gruppo in g_fam.groupby("_gruppo"):

            # Famiglie con assi/valori dinamici per gruppo (es. EQUINOXE)
            if "_assi_dinamici" in regola:
                assi_def, valori_override = regola["_assi_dinamici"](gruppo_key)
                regola_gruppo = {**regola, "assi": assi_def, "valori": valori_override}
            else:
                assi_def = regola["assi"]
                regola_gruppo = regola

            saltare_fn = regola_gruppo.get("saltare")

            # Determina assi attivi per questo gruppo
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
                                 attribute_set_id)
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


# ════════════════════════════════════════════