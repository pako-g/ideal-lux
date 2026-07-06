"""
Generatore JSON — Prodotti SEMPLICI Magento
Categoria: Lampada da soffitto
Output: simple_products_lampada_da_soffitto.json

90 famiglie, 550 SKU totali (filtro su "Categoria Articolo" == "Lampada da soffitto")
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
CATEGORIA          = "Lampada da soffitto"
OUTPUT_PATH        = "./file/simple_products_lampada_da_soffitto.json"
MARCA              = "Ideal Lux"
ATTRIBUTE_SET_NAME = "Ideal-Lux"
WEBSITE_IDS        = [1]


# ─────────────────────────────────────────────
# FAMIGLIE DA SALTARE COMPLETAMENTE
# ─────────────────────────────────────────────

FAMIGLIE_DA_SALTARE: set[str] = set()

FINITURE_DA_SALTARE: set[str] = set()


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
    "Trasparent":       "Trasparente",
    "Color":            "Colorato",
}

DIMMER_LABEL = {
    "ON-OFF":    "On/Off",
    "DALI/PUSH": "Dimmer Dali / Push",
    "DALI":      "Dimmer Dali",
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
            "valori": {"color": lambda r, _f=f: finitura_label(r["Finitura"].capitalize())},
        }

def _solo_diametro(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_dimensioni"],
            "valori": {"config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D")},
        }

def _solo_luci(*famiglie):
    for f in famiglie:
        REGOLE[f] = {
            "assi":   ["config_tipo"],
            "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
        }


# ════════════════════════════════════════════
# STEP 1 — SINGLETONS ASSOLUTI
# (11 famiglie, 11 SKU — 1 solo SKU per famiglia)
# ════════════════════════════════════════════

_solo_colore(
    "BIRDS", "CANDY", "DAISY", "MAGNOLIA", "MAPA",
    "OAK", "OCTOPUS", "RAIN", "RELAX", "ROYAL", "TRIUMPH",
)


# ════════════════════════════════════════════
# STEP 2 — SOLO COLORE
# (1 asse: color)
# ════════════════════════════════════════════

_solo_colore(
    "ANGOLO", "CARLTON", "GUN", "KUBIKO", "MARTINEZ",
    "MIX-UP", "MOONLIGHT", "MOUSE", "PLAY", "SPOT",
    "TOBY", "WINERY",
)


# ════════════════════════════════════════════
# STEP 3 — SOLO DIMENSIONI (diametro o lunghezza)
# ════════════════════════════════════════════

# Solo diametro (1 finitura, varianti per D)
_solo_diametro(
    "ARMONY", "ATRIUM", "CLOUD", "COTTON",
    "IRIDE", "LEVEL", "LUNA", "SQUISH", "TOPICO",
)

# Solo luci (1 finitura, varianti per numero sorgenti)
_solo_luci(
    "ADMIRAL", "ARIZONA", "CELINE", "COMPO", "COSMOPOLITAN",
    "GEKO", "GLORY", "GOURMET", "MARACAS", "NEVE",
    "OBY", "OVALINO", "ROMA", "SIMPLY", "TOTEM",
)

# SET UP: varianti MPL1 / MPL4 → luci
REGOLE["SET UP"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
}

# COROLLA: due modelli (COROLLA-1 / COROLLA-2) → singleton per modello
REGOLE["COROLLA"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"(COROLLA-\d)"),
    "assi":   [],
    "valori": {},
}

# LUMIERE: due modelli (LUMIERE-1 / LUMIERE-2) → singleton per modello
REGOLE["LUMIERE"] = {
    "gruppo": lambda r: token_from_desc(r["Descrizione"], r"(LUMIERE-\d)"),
    "assi":   [],
    "valori": {},
}

# BUBBLE: AP2 (parete) e PL1 (soffitto) — stesso catalogo, unico colore
REGOLE["BUBBLE"] = {
    "assi":   ["config_tipo"],
    "valori": {"config_tipo": lambda r: luci_label(r["Luci"])},
}

# CARTA: AP1 (D20) + PL (D30, D40) — diametro come asse
REGOLE["CARTA"] = {
    "assi":   ["config_dimensioni"],
    "valori": {"config_dimensioni": lambda r: dim_from_desc(r["Descrizione"])},
}


# ════════════════════════════════════════════
# STEP 4 — COLORE + 1 ASSE
# ════════════════════════════════════════════

# ── STEP 4A — COLORE + DIMENSIONI ──

# ATLAS: color + luci (PL3 / PL5)
REGOLE["ATLAS"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# BLOOM: color + diametro (D22 / D30)
REGOLE["BLOOM"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_desc(r["Descrizione"]),
    },
}

# CLIO: color (ANTRACITE, BIANCO, NERO — 1 solo SKU per colore)
_solo_colore("CLIO")

# DUBAI: color + luci (PL3/6/24)
REGOLE["DUBAI"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# GLIM: color + luci (PL1/2/4)
REGOLE["GLIM"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# HERMES: color + diametro (D60 / D90)
REGOLE["HERMES"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# KING: color + luci (PL3/5/9)
REGOLE["KING"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# LINGOTTO: color + luci (PL1/2/4)
REGOLE["LINGOTTO"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# NODI: color + luci (PL5/9)
REGOLE["NODI"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# PASHA': color + luci (PL6/10/14)
REGOLE["PASHA'"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# PERLAGE: color + luci (PL6/9/10/18)
REGOLE["PERLAGE"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# PLANET: color + diametro (D30/40/50/60)
REGOLE["PLANET"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# PROFILO: color + luci (PL2/4)
REGOLE["PROFILO"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# RAY: color + diametro (D30/40/60)
REGOLE["RAY"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# SHELL: color + luci (PL3/4/6)
REGOLE["SHELL"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ZIGGY: color + diametro (D030/045/060/080)
REGOLE["ZIGGY"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}

# ── STEP 4B — COLORE + TEMPERATURA COLORE ──

# SNOW: solo temperatura (1 colore)
REGOLE["SNOW"] = {
    "assi": ["config_temperatura_colore"],
    "valori": {
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# HALO: diametro + temperatura (1 colore — BIANCO)
REGOLE["HALO"] = {
    "assi": ["config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "config_dimensioni":         lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# SMARTIES: diametro + luci (1 colore — BIANCO)
# SMARTIES_PL1_D33 / PL2_D42 / PL3_D50 / PL3_D60 → dim + luci
REGOLE["SMARTIES"] = {
    "assi": ["config_dimensioni", "config_tipo"],
    "valori": {
        "config_dimensioni": lambda r: dim_from_desc(r["Descrizione"]),
        "config_tipo":       lambda r: luci_label(r["Luci"]),
    },
}


# ════════════════════════════════════════════
# STEP 5 — COLORE + DIMENSIONI + TEMPERATURA / DIMMER
# (famiglie con 3 assi)
# ════════════════════════════════════════════

# ── FLY: color + diametro + temperatura ──
# FLY_PL_D35_BIANCO_2700K / D35_BIANCO_3000K / D35_NERO_2700K …
REGOLE["FLY"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── GEMINI: color + diametro + temperatura + dimmer ──
# GEMINI_PL_D042_ON-OFF_BIANCO_3000K  /  _DALI_…
REGOLE["GEMINI"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore", "config_dimmer"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: dim_from_desc(r["Descrizione"]),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
        "config_dimmer":            lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI)(?:_|$)")),
    },
}

# ── LIKA: color + potenza + temperatura ──
# LIKA_PL_06W_3000K_BIANCO / 12W_3000K / 18W_3000K
def _normalizza_watt(raw: str) -> str:
    """Converte "06W" / "6W" → "6 Watt", "12W" → "12 Watt", ecc."""
    m = re.match(r"^0*(\d+)W$", raw)
    return f"{m.group(1)} Watt" if m else raw

def _lika_potenza(r) -> str:
    raw = token_from_desc(r["Descrizione"], r"_(\d+W)_")
    return _normalizza_watt(raw) if raw else ""

REGOLE["LIKA"] = {
    "assi": ["color", "config_potenza", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_potenza":           _lika_potenza,
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)_"),
    },
}

# ── NITRO: color + diametro + temperatura ──
# NITRO_PL_D04_ROUND_BIANCO_2700K / D08_ROUND / D09_ROUND / D10_ROUND
REGOLE["NITRO"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: dim_from_desc(r["Descrizione"]),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── OZ: color + diametro + temperatura + dimmer ──
# OZ_PL_D040_ON-OFF_BIANCO_3000K / D060_DALI_BIANCO / …
REGOLE["OZ"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore", "config_dimmer"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
        "config_dimmer":            lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI)(?:_|$)")),
    },
}

# ── ORACLE SLIM: color + diametro + temperatura + dimmer ──
# ORACLE_SLIM_PL_D050_ROUND_2700K_ON-OFF_BI / _NE / …
REGOLE["ORACLE SLIM"] = {
    "assi": ["color", "config_dimensioni", "config_temperatura_colore", "config_dimmer"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)_"),
        "config_dimmer":            lambda r: dimmer_label(token_from_desc(r["Descrizione"], r"_(ON-OFF|DALI)(?:_|$|[A-Z])")),
    },
}

# ── UNIVERSAL: diametro + forma + temperatura (1 colore — BIANCO) ──
# UNIVERSAL_PL_D17_ROUND_2700K / _SQUARE_2700K / D22_ROUND / …
REGOLE["UNIVERSAL"] = {
    "assi": ["config_dimensioni", "config_tipo", "config_temperatura_colore"],
    "valori": {
        "config_dimensioni":         lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
        "config_tipo":               lambda r: token_from_desc(r["Descrizione"], r"_(ROUND|SQUARE)_").capitalize(),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}


# ════════════════════════════════════════════
# STEP 6 — FAMIGLIE COMPLESSE / CON SOTTOGRUPPI
# ════════════════════════════════════════════

# ── BINOMIO: gruppo(AP1 / PL_standard / LED_PL), color + luci ──
# AP1: solo colore (parete, no config_tipo perché 1 sola luce)
# PL standard (PL2/4): color + luci
# LED PL (LED_PL4/6): color + luci
def _binomio_gruppo(r):
    desc = r["Descrizione"]
    if "AP1" in desc:
        return "AP"
    if "LED" in desc:
        return "LED_PL"
    return "PL"

REGOLE["BINOMIO"] = {
    "gruppo": _binomio_gruppo,
    "assi":   ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── DYNAMITE: sottogruppi per shape (AP1_ROUND / AP1_MINI_ROUND / PL_LINEAR / PL_SQUARE / PL_ROUND) ──
# AP1_ROUND e AP1_MINI_ROUND: color (arrivano dalla parete, qui sono soffitto da catalogo)
# PL4_ROUND / PL4_SQUARE: color
# PL3/4_LINEAR_ROUND / LINEAR_SQUARE: color + config_tipo (Round/Square)
def _dynamite_gruppo(r):
    desc = r["Descrizione"]
    if "AP1_MINI" in desc:
        return "AP1_MINI"
    if "AP1" in desc:
        return "AP1"
    if "LINEAR" in desc:
        return "LINEAR"
    if "PL4_ROUND" in desc:
        return "PL_ROUND"
    if "PL4_SQUARE" in desc:
        return "PL_SQUARE"
    return "OTHER"

REGOLE["DYNAMITE"] = {
    "gruppo": _dynamite_gruppo,
    "assi":   ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: token_from_desc(r["Descrizione"], r"LINEAR_(ROUND|SQUARE)").capitalize(),
    },
}

# ── FRAME: color + forma + temperatura ──
# FRAME_PL_CERCHIO_BIANCO_2700K / FRAME_PL_QUADRATO_BIANCO_2700K
REGOLE["FRAME"] = {
    "assi": ["color", "config_tipo", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo":              lambda r: token_from_desc(r["Descrizione"], r"PL_(CERCHIO|QUADRATO)_").capitalize(),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── LOOK (soffitto): sottogruppi LED (D30/H200, D30/H400) e non-LED (H95) ──
# LOOK_LED_PL1_ROUND_D30_H200_ON-OFF_BIANCO_3000K → color + dim(H) + temp
# LOOK_PL1_H95_BIANCO → color (1 dimensione unica)
def _look_gruppo(r):
    return "LED" if "LED" in r["Descrizione"] else "STD"

REGOLE["LOOK"] = {
    "gruppo": _look_gruppo,
    "assi":   ["color", "config_dimensioni", "config_temperatura_colore"],
    "valori": {
        "color":                    lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni":         lambda r: altezza_from_col(r["Dimensione Articolo"]),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── MIB: forma + temperatura (1 colore — BIANCO) ──
# MIB_PL_ROUND_3000K / MIB_PL_ROUND_4000K / MIB_PL_SQUARE_3000K / MIB_PL_SQUARE_4000K
REGOLE["MIB"] = {
    "assi": ["config_tipo", "config_temperatura_colore"],
    "valori": {
        "config_tipo":               lambda r: token_from_desc(r["Descrizione"], r"PL_(ROUND|SQUARE)_").capitalize(),
        "config_temperatura_colore": lambda r: token_from_desc(r["Descrizione"], r"_(\d{4}K)(?:_|$)"),
    },
}

# ── MOOD: color + forma + diametro ──
# MOOD_PL1_D09_ROUND_BIANCO / _SQUARE_BIANCO / D15_ROUND_BIANCO / …
REGOLE["MOOD"] = {
    "assi": ["color", "config_tipo", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo":      lambda r: token_from_desc(r["Descrizione"], r"_(ROUND|SQUARE)_").capitalize(),
        "config_dimensioni": lambda r: dim_from_desc(r["Descrizione"]),
    },
}

# ── NINFEA: saltare AP2, PL → color + luci ──
REGOLE["NINFEA"] = {
    "saltare": lambda r: "AP2" in r["Descrizione"],
    "assi":    ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── OCEAN: color + luci ──
# OCEAN_PL2_TRASPARENTE / OCEAN_PL3_COLOR / OCEAN_PL3_TRASPARENTE
REGOLE["OCEAN"] = {
    "assi": ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── RUDY: AP → saltati (Descrizione 2 = LAMPADA DA PARETE, gestiti dallo script parete)
# PL_ROUND / PL_SQUARE: BIANCO+NERO × PL3+PL4 → 2 configurabili (asse: color + config_tipo)
def _rudy_gruppo(r):
    shape = token_from_desc(r["Descrizione"], r"PL\d_(ROUND|SQUARE)_")
    return f"PL_{shape}"

REGOLE["RUDY"] = {
    "saltare": lambda r: str(r["Descrizione 2"]).upper() == "LAMPADA DA PARETE",
    "gruppo":  _rudy_gruppo,
    "assi":    ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: luci_label(r["Luci"]),
    },
}

# ── SPIKE: sottogruppi LED (color) e PL1 ROUND/SQUARE (color + forma) ──
# SPIKE_LED_PL_BIANCO/NERO/OTTONE → color
# SPIKE_PL1_ROUND_xxx / SPIKE_PL1_SQUARE_xxx → color + config_tipo
def _spike_gruppo(r):
    return "LED" if "LED" in r["Descrizione"] else "PL1"

REGOLE["SPIKE"] = {
    "gruppo": _spike_gruppo,
    "assi":   ["color", "config_tipo"],
    "valori": {
        "color":       lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo": lambda r: token_from_desc(r["Descrizione"], r"PL1_(ROUND|SQUARE)_").capitalize(),
    },
}

# ── TECHO: color + forma + diametro ──
# TECHO_PL1_D09_ROUND_BIANCO / _SQUARE_BIANCO / D15_ROUND_BIANCO / …
REGOLE["TECHO"] = {
    "assi": ["color", "config_tipo", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_tipo":      lambda r: token_from_desc(r["Descrizione"], r"_(ROUND|SQUARE)_").capitalize(),
        "config_dimensioni": lambda r: dim_from_desc(r["Descrizione"]),
    },
}

# ── URANO: color + dimensione (BIG / SMALL → dim da colonna) ──
# URANO_PL1_BIG_BIANCO / URANO_PL1_SMALL_BIANCO → 2 diametri
REGOLE["URANO"] = {
    "assi": ["color", "config_dimensioni"],
    "valori": {
        "color":            lambda r: finitura_label(r["Finitura"].capitalize()),
        "config_dimensioni": lambda r: dim_from_col(r["Dimensione Articolo"], "D"),
    },
}


# ─────────────────────────────────────────────
# LOAD & NORMALIZZA CSV
# ─────────────────────────────────────────────

def _normalizza_df(df: pd.DataFrame) -> pd.DataFrame:
    df["sku"] = df["Nr"].astype(str).str[-6:]
    df["prezzo"] = (
        df["Prezzo Al Pubblico"].astype(str)
        .str.replace(r"\s", "", regex=True)
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

    parti = [f"{MARCA} {modello} Lampada Da Soffitto"]

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