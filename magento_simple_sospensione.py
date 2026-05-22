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

def finitura_label(finitura: str) -> str:
    label = str(finitura).capitalize()
    return FINITURA_LABEL.get(label, label)

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
                 attribute_set_id: int) -> dict:

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

            # Determina assi attivi per questo gruppo
            assi_def = regola["assi"]

            # Assi con valore unico nel gruppo → non sono configurabili (prodotto singolo)
            assi_attivi = []
            for asse in assi_def:
                fn = regola["valori"].get(asse)
                if fn is None:
                    continue
                valori_gruppo = set(fn(r) for _, r in gruppo.iterrows() if pd.notna(r.get("Finitura", None)) or asse != "color")
                if len(valori_gruppo) > 1:
                    assi_attivi.append(asse)
                # Se il gruppo ha 1 solo prodotto, nessun asse è configurabile
                # ma lo includiamo comunque come standalone

            for _, row in gruppo.iterrows():
                # Applica filtro saltare
                if saltare_fn and saltare_fn(row):
                    continue
                semplici.append(
                    build_simple(row, assi_attivi, regola,
                                 color_map, attacco_map, dimensioni_map,
                                 manufacturer_map, tipo_map, temp_map,
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