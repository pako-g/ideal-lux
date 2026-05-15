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
OUTPUT_PATH     = "./file/simple_products.json"
MARCA           = "Ideal Lux"
ATTRIBUTE_SET_ID = 264      # adatta al tuo Attribute Set in Magento
WEBSITE_IDS     = [1]
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")


# ─────────────────────────────────────────────
# OAUTH SESSION
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
    raw = descrizione.replace("_" + str(finitura) if pd.notna(finitura) else "", "").replace("_", " ").lower()
    # Non includere token di dimensione (h60, d30 ecc.) e temperatura (3000k, 4000k)
    raw = re.sub(r'\b[hdlp]\d+\b', '', raw)
    raw = re.sub(r'\b\d{4}k(?:-\d{4}k)?\b', '', raw)
    raw = re.sub(r'\s{2,}', ' ', raw).strip()
    return raw[0].upper() + raw[1:] if raw else raw

def mm_to_cm(val_mm: int) -> str:
    """600 → '60', 655 → '65.5', 125 → '12.5'"""
    cm = val_mm / 10
    return str(int(cm)) if cm == int(cm) else str(cm)

# Famiglie dove la dimensione nella descrizione è D ma va letta come Lunghezza
FAMIGLIE_LUNGHEZZA = {"SASSO"}

FINITURA_LABEL = {
    "Coffee":   "Caffè",
    "Nickel":   "Nichel",
    "Ambra sfumato": "Ambra",
    "Fume' sfumato": "Fumé",
    "Fume'": "Fumé"
}

FAMIGLIE_SENZA_DIMENSIONE = {"DRIFTWOOD", "BINOMIO"}

def estrai_dimensione(descrizione: str, finitura: str, famiglia: str,
                      famiglia_varianti: pd.DataFrame) -> str:

    if famiglia in FAMIGLIE_SENZA_DIMENSIONE:
        return ""

    def estrai_misura(dim_str, prefix):
        m = re.search(rf'{prefix}\s+(\d+)', str(dim_str))
        return int(m.group(1)) if m else None

    # Determina il prefisso dalla descrizione (D o H) ma il valore da Dimensione Articolo
    modello = descrizione.replace("_" + str(finitura) if pd.notna(finitura) else "", "")
    match = re.search(r'_(D\d+|H\d+)$', modello)

    if match:
        prefix = match.group(1)[0]  # "D" o "H"
        dim_str = famiglia_varianti.loc[
            famiglia_varianti["Descrizione"] == descrizione,
            "Dimensione Articolo"
        ].iloc[0]

        if prefix == "D":
            val = estrai_misura(dim_str, "D")
            if val:
                label = "Diametro"
            else:
                val = estrai_misura(dim_str, "L")
                label = "Lunghezza"
        else:
            val = estrai_misura(dim_str, prefix)
            label = "Altezza" if prefix == "H" else prefix

        return f"{label} {mm_to_cm(val)}cm" if val else ""

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
            return f"{label} {mm_to_cm(val)}cm" if val else ""

    return ""

FAMIGLIE_TIPO = {
    "EDO":       r'_(?:PT1_)(ROUND|SQUARE)_',
    "ESSENCE":   r'_PT_(ROUND|SQUARE)_',
    "TWIGGY":    r'_(LINE|SPHERE)_',
}
TIPO_LABEL = {
    "Round":  "Rotondo",
    "Square": "Quadrato",
    "Line":   "Linea",
    "Sphere": "Sfera",
}

FAMIGLIE_SOLO_COLORE = {"DRIFTWOOD"}

def estrai_tipo(descrizione: str, famiglia: str) -> str:
    if famiglia in FAMIGLIE_SOLO_COLORE:
        return ""
    pattern = FAMIGLIE_TIPO.get(famiglia, "")
    if not pattern:
        return ""
    match = re.search(pattern, descrizione)
    if not match:
        return ""
    tipo = match.group(1).capitalize()
    return TIPO_LABEL.get(tipo, tipo)


def estrai_temperatura(descrizione: str) -> str:
    match = re.search(r'_(\d{4}K(?:-\d{4}K)?)(?:_|$)', descrizione)
    return match.group(1) if match else ""


def build_nome_semplice(modello: str, finitura: str, attacco: str, tipo: str = "",
                        categoria: str = "", dimensione: str = "", temperatura: str = "") -> str:
    cat_str      = f" {categoria.title()}" if categoria else ""
    finitura_str = str(finitura).capitalize() if finitura and pd.notna(finitura) else ""
    finitura_str = FINITURA_LABEL.get(finitura_str, finitura_str)
    attacco_str  = str(attacco) if attacco else ""
    modello_str  = modello[0].upper() + modello[1:] if modello else ""
    dimensione_str = dimensione.replace(" ", "-") if dimensione else ""
    tokens = [t for t in [f"{modello_str}{cat_str}", tipo, finitura_str,
                          dimensione_str, temperatura, attacco_str] if t]
    return f"{MARCA} " + "-".join(tokens)


def build_url_key(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


IMG_DIR  = Path("./file/images")
BASE_URL = "./file/images/"

def build_image_entry(nome: str, sku: str) -> dict | None:
    filename = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") + f"-{sku}.jpg"
    if not (IMG_DIR / filename).exists():
        return None
    return {
        "media_type": "image",
        "label":      nome,
        "position":   1,
        "disabled":   False,
        "types":      ["image", "small_image", "thumbnail"],
        "content": {
            "type": "image/jpeg",
            "name": filename,
            "url":  f"{BASE_URL}/{filename}",
        }
    }


# ─────────────────────────────────────────────
# BUILD PRODOTTO SEMPLICE
# ─────────────────────────────────────────────

def build_simple(row: pd.Series, color_map: dict, attacco_map: dict,
                 dimensioni_map: dict, manufacturer_map: dict,
                 tipo_map: dict, temp_map: dict,
                 famiglia_varianti: pd.DataFrame) -> dict:

    famiglia   = row["Famiglia Articolo"]
    print(famiglia)
    dimensione = estrai_dimensione(row["Descrizione"], row["Finitura"],
                                   famiglia, famiglia_varianti)
    tipo       = estrai_tipo(row["Descrizione"], famiglia)
    temperatura = estrai_temperatura(row["Descrizione"])
    modello    = estrai_modello(row["Descrizione"], row["Finitura"])

    # Calcola quali attributi variano nel gruppo
    attacchi_gruppo = set(str(r["Attacco Portalampada"]) for _, r in famiglia_varianti.iterrows())
    dimensioni_gruppo = set(estrai_dimensione(r["Descrizione"], r["Finitura"], famiglia, famiglia_varianti) for _, r in
                            famiglia_varianti.iterrows())
    tipi_gruppo = set(estrai_tipo(r["Descrizione"], famiglia) for _, r in famiglia_varianti.iterrows())
    temp_gruppo = set(estrai_temperatura(r["Descrizione"]) for _, r in famiglia_varianti.iterrows())

    attacco_val = row["Attacco Portalampada"]

    finitura_nome = row["Finitura"] if pd.notna(row["Finitura"]) else ""
    attacco_nome = str(attacco_val) if len(attacchi_gruppo) > 1 else ""
    dimensione_nome = dimensione if len(dimensioni_gruppo) > 1 else ""
    tipo_nome = tipo if len(tipi_gruppo) > 1 else ""
    temperatura_nome = temperatura if len(temp_gruppo) > 1 else ""

    nome = build_nome_semplice(modello, finitura_nome, attacco_nome, tipo_nome,
                               row["Categoria Articolo"], dimensione_nome, temperatura_nome)

    img_entry = build_image_entry(nome, row["sku"])

    if pd.notna(row["Finitura"]):
        finitura_label = row["Finitura"].capitalize()
        finitura_label = FINITURA_LABEL.get(finitura_label, finitura_label)
        color_id = color_map[finitura_label]
    else:
        color_id = ""


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

    # Tieni solo gli attributi config_ e color che variano nel gruppo
    attrs_varianti = []
    for attr in attrs_config:
        code = attr["attribute_code"]
        valori_gruppo = set()
        for _, r in famiglia_varianti.iterrows():
            # Ricalcola il valore per ogni riga del gruppo
            if code == "color":
                fin = r["Finitura"]
                if pd.notna(fin):
                    fin_label = fin.capitalize()
                    fin_label = FINITURA_LABEL.get(fin_label, fin_label)
                    valori_gruppo.add(color_map.get(fin_label, ""))
            elif code == "config_attacco_lamp":
                valori_gruppo.add(str(r["Attacco Portalampada"]))
            elif code == "config_dimensioni":
                valori_gruppo.add(estrai_dimensione(r["Descrizione"], r["Finitura"],
                                                    row["Famiglia Articolo"], famiglia_varianti))
            elif code == "config_tipo":
                valori_gruppo.add(estrai_tipo(r["Descrizione"], row["Famiglia Articolo"]))
            elif code == "config_temperatura_colore":
                valori_gruppo.add(estrai_temperatura(r["Descrizione"]))

        if len(valori_gruppo) > 1:
            attrs_varianti.append(attr)

    attrs_config = attrs_varianti

    return {
        "product": {
            "sku":              f"IL-{row['sku']}",
            "name":             nome,
            "attribute_set_id": ATTRIBUTE_SET_ID,
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
                }
            },
            "custom_attributes": attrs_config + [
                {"attribute_code": "lamp_ean",      "value": str(row["Nr"])},
                {"attribute_code": "manufacturer",  "value": manufacturer_id},
                {"attribute_code": "url_key",       "value": build_url_key(nome) + "-" + row["sku"]},
            ],
            "media_gallery_entries": [img_entry] if img_entry else [],
        }
    }




# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    Path("./file").mkdir(exist_ok=True)

    # 1. Connessione OAuth e recupero mappe attributi
    session = get_oauth_session()

    color_map        = get_attribute_options(session, "color")
    attacco_map      = get_attribute_options(session, "config_attacco_lamp")
    dimensioni_map   = get_attribute_options(session, "config_dimensioni")
    tipo_map         = get_attribute_options(session, "config_tipo")
    temp_map         = get_attribute_options(session, "config_temperatura_colore")
    manufacturer_map = get_attribute_options(session, "manufacturer")

    print("🎨  Opzioni color recuperate da Magento:")
    for label, opt_id in color_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni config_attacco_lamp recuperate da Magento:")
    for label, opt_id in attacco_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni config_dimensioni recuperate da Magento:")
    for label, opt_id in dimensioni_map.items():
        print(f"     {label} → {opt_id}")
    print()

    print("🔌  Opzioni manufacturer recuperate da Magento:")
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

    # 3. Calcola sottofamiglia per separare modelli diversi nella stessa famiglia
    FAMIGLIE_CONFIG_TIPO = {"EDO", "ESSENCE", "TWIGGY", "DRIFTWOOD"}

    def calcola_sottofamiglia(descrizione: str, famiglia: str, finitura: str) -> str:
        if famiglia in FAMIGLIE_CONFIG_TIPO:
            return famiglia
        finitura_str = "" if str(finitura) == "nan" else "_" + str(finitura)
        core = str(descrizione).replace(famiglia + "_", "").replace(finitura_str, "")
        core = re.sub(r'_(D\d+|H\d+|L\d+|\d{4}K[^_]*).*$', '', core)
        core = re.sub(r'^(D\d+|H\d+|L\d+|\d{4}K[^_]*).*$', '', core)
        sottomodello = core.strip("_")
        return f"{famiglia}_{sottomodello}" if sottomodello else famiglia

    varianti["sottofamiglia"] = varianti.apply(
        lambda r: calcola_sottofamiglia(r["Descrizione"], r["Famiglia Articolo"], str(r["Finitura"])),
        axis=1
    )

    print(varianti[varianti["Famiglia Articolo"] == "SIRIO"][
              ["Descrizione", "sottofamiglia", "Attacco Portalampada"]].to_string())

    # 4. Genera prodotti semplici
    semplici = []
    for sottofamiglia, gruppo in varianti.groupby("sottofamiglia"):
        for _, row in gruppo.iterrows():
            semplici.append(
                build_simple(row, color_map, attacco_map, dimensioni_map,
                             manufacturer_map, tipo_map, temp_map, gruppo)
            )

    # 5. Salva JSON
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
            f"           color={ca.get('color', '-')}  "
            f"dimensioni={ca.get('config_dimensioni', '-')}  "
            f"attacco={ca.get('config_attacco_lamp', '-')}  "
            f"tipo={ca.get('config_tipo', '-')}  "
            f"temp={ca.get('config_temperatura_colore', '-')}  "
            f"€{p['price']}  qty={p['extension_attributes']['stock_item']['qty']}\n"
        )