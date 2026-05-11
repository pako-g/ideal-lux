"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Legge: ./file/aline_simple_products.json
Scrive: ./file/configurable_products.json

Logica:
  - Raggruppa i semplici per sottofamiglia (stesso modello/dimensione)
  - Per ogni gruppo crea un configurabile con i dati base
  - configurable_product_options e linking semplici → gestiti a runtime da magento_import.py
  - SKU configurabile: IL-CONFIG-001, IL-CONFIG-002, ...
  - Titolo: "Ideal Lux <Modello> [Led] <Categoria>"
"""

import json
import re
import os
from pathlib import Path
from dotenv import load_dotenv
import re
import base64
from pathlib import Path
import pandas as pd
from requests_oauthlib import OAuth1Session
import warnings
warnings.filterwarnings("ignore")

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

INPUT_JSON       = "./file/aline_simple_products.json"
OUTPUT_JSON      = "./file/configurable_products.json"
CSV_PATH = "./file/giacenzeECommerce.csv"
MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")

ATTRIBUTE_SET_ID = 263
WEBSITE_IDS      = [1]

# Attributi che NON sono assi di variazione del configurabile
ESCLUDI_DA_CONFIG = {"lamp_ean", "manufacturer", "url_key"}

CATEGORIE_FISSE = ["Marchi", "Ideal Lux", "Illuminazione"]


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
# UTILITY: COSTRUZIONE CATEGORIE
# ─────────────────────────────────────────────
def build_categorie_map(session: OAuth1Session) -> dict:
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
# UTILITY: COSTRUZIONE TITOLO CONFIGURABILE
# ─────────────────────────────────────────────

def build_titolo(nome_semplice: str) -> str:
    """
    Ricava il titolo del configurabile dal nome di un prodotto semplice.

    Esempi:
      "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
      → "Ideal Lux Agos Pt H60 Led Lampada Da Terra"

      "Ideal Lux A-line sp1 d13-Bianco-GU10 Lampada da Parete"
      → "Ideal Lux A-Line Sp1 D13 Lampada Da Parete"
    """
    nome = nome_semplice.strip()

    # 1. Presenza LED
    is_led = bool(re.search(r'\bLED\b', nome, re.IGNORECASE))

    # 2. Categoria lampada in fondo (es. "Lampada Da Terra", "Lampada Da Parete" …)
    cat_match = re.search(r'(Lampada\s+[Dd]a\s+\w+)', nome, re.IGNORECASE)
    categoria = cat_match.group(0).title() if cat_match else ""

    # 3. Rimuovi la parte dopo il trattino (varianti: colore, attacco)
    nome_pulito = re.split(r'-[A-Z]', nome)[0].strip()

    # 4. Rimuovi la categoria dalla parte pulita
    if categoria:
        nome_pulito = re.sub(re.escape(categoria), '', nome_pulito, flags=re.IGNORECASE).strip()

    # 5. Rimuovi temperature (3000k, 4000k, 2700k-5700k) e "LED"
    nome_pulito = re.sub(r'\b\d{4}[Kk](?:-\d{4}[Kk])?\b', '', nome_pulito)
    nome_pulito = re.sub(r'\bLED\b', '', nome_pulito, flags=re.IGNORECASE)
    nome_pulito = re.sub(r'\s{2,}', ' ', nome_pulito).strip()

    # 6. Titolizza ogni token
    modello_str = " ".join(t[0].upper() + t[1:] for t in nome_pulito.split() if t)

    # 7. Componi titolo finale
    led_str = " Led" if is_led else ""
    return f"{modello_str}{led_str} {categoria}".strip()


# ─────────────────────────────────────────────
# UTILITY: ATTRIBUTI CONFIGURABILI
# ─────────────────────────────────────────────

def get_config_attribute_codes(semplici: list) -> list:
    """
    Raccoglie tutti gli attribute_code dei semplici del gruppo,
    escludendo quelli non configurabili.
    """
    codes = set()
    for s in semplici:
        for attr in s["product"]["custom_attributes"]:
            code = attr["attribute_code"]
            if code not in ESCLUDI_DA_CONFIG:
                codes.add(code)
    return sorted(codes)


# ─────────────────────────────────────────────
# UTILITY: CONVERTE MM IN CM E NORMALIZZA
# ─────────────────────────────────────────────
def converti_dimensione(dim_str: str) -> str:
    """
    Converte "D 135 x H 600 mm" → "Ø13.5cm x H60cm"
    Gestisce D, H, L, P
    """
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
# BUILD PRODOTTO CONFIGURABILE
# ─────────────────────────────────────────────
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


def build_configurable(config_sku: str, semplici: list, df: pd.DataFrame, attacco_menu_map: dict, categorie_map: dict) -> dict:
    """
    Costruisce il dict del prodotto configurabile da salvare nel JSON.

    Contiene solo i dati base del prodotto + metadati per magento_import.py:
      _child_skus  → SKU dei semplici da associare
      _attr_codes  → codici attributo da risolvere a runtime (attribute_id numerico)
    """

    skus_gruppo = [s["product"]["sku"] for s in semplici]
    righe_gruppo = df[df["Nr"].astype(str).str.endswith(tuple(str(s) for s in skus_gruppo))]

    ip_vals = righe_gruppo["IP"].dropna().astype(int).unique().tolist()
    is_esterno = any(v >= 44 for v in ip_vals)
    ambiente = "Esterni" if is_esterno else "Interni"

    titolo = build_titolo(semplici[0]["product"]["name"])
    titolo = f"{titolo} per {ambiente}"

    url_key    = re.sub(r"[^a-z0-9]+", "-", titolo.lower()).strip("-")
    child_skus = [s["product"]["sku"] for s in semplici]
    attr_codes = get_config_attribute_codes(semplici)

    # Recupera manufacturer dal primo semplice
    manufacturer_val = next(
        (a["value"] for a in semplici[0]["product"]["custom_attributes"]
         if a["attribute_code"] == "manufacturer"),
        None
    )

    # Raccoglie le immagini di tutti i semplici del gruppo
    media_entries = []
    for s in semplici:
        nome_s = s["product"]["name"]
        sku_s = s["product"]["sku"]
        slug = re.sub(r"[^a-z0-9]+", "-", nome_s.lower()).strip("-")
        path = Path(f"./file/images/{slug}-{sku_s}.jpg")
        if path.exists():
            media_entries.append({
                "media_type": "image",
                "label": nome_s.replace("-", " "),
                "position": len(media_entries) + 1,
                "disabled": False,
                "types": ["image", "small_image", "thumbnail"] if len(media_entries) == 0 else [],
                "content": {
                    "base64_encoded_data": base64.b64encode(path.read_bytes()).decode("utf-8"),
                    "type": "image/jpeg",
                    "name": path.name,
                },
            })

    primo_sku = semplici[0]["product"]["sku"]
    riga = df[df["Nr"].astype(str) == str(primo_sku)]
    lamp_val = "1" if not riga.empty and str(riga.iloc[0]["LampadinaInclusa"]).strip().lower() == "si" else "0"

    skus_gruppo = [s["product"]["sku"] for s in semplici]
    righe_gruppo = df[df["Nr"].astype(str).str.endswith(tuple(str(s) for s in skus_gruppo))]
    dimmer_val = "1" if (righe_gruppo["Dimmer"].str.strip().str.lower() == "si").any() else "0"

    dimensioni = righe_gruppo["Dimensione Articolo"].dropna().str.strip().unique().tolist()
    dimensioni = [converti_dimensione(d) for d in dimensioni if d]
    dimensioni_val = " - ".join(dimensioni)

    materiali_raw = righe_gruppo["Materiale"].dropna().str.strip()
    materiali_set = set()
    for m in materiali_raw:
        for parte in m.split(","):
            sigla = parte.strip()
            materiali_set.add(MATERIALI_MAP.get(sigla, sigla))
    materiali_val = ", ".join(sorted(materiali_set))

    watt_vals = righe_gruppo["Watt"].dropna().str.strip().unique().tolist()
    watt_vals = [w for w in watt_vals if w]

    def formatta_watt(w: str, luci: int) -> str:
        # Estrai il numero di watt dalla stringa es. "G9 max 1 x 15W" → "15"
        match = re.search(r'(\d+)\s*W', w, re.IGNORECASE)
        if not match:
            return w
        num_w = match.group(1)
        return f"{luci} x {num_w}W" if luci > 1 else f"{num_w}W"

    watt_formattati = set()
    for _, riga in righe_gruppo.iterrows():
        w = str(riga["Watt"]).strip()
        luci = int(riga["Luci"]) if pd.notna(riga["Luci"]) else 1
        watt_formattati.add(formatta_watt(w, luci))

    watt_val = " - ".join(sorted(watt_formattati))

    ip_vals = righe_gruppo["IP"].dropna().astype(str).str.strip().unique().tolist()
    ip_vals = [f"IP{int(float(v))}" for v in ip_vals if v and v != "nan"]
    ip_val = " - ".join(ip_vals)

    attacchi = righe_gruppo["Attacco Portalampada"].dropna().str.strip().unique().tolist()
    attacchi = [a for a in attacchi if a and a in attacco_menu_map]
    attacco_menu_val = attacco_menu_map[attacchi[0]] if len(attacchi) == 1 else ""

    cat_nome = "Lampade da Terra per Esterni" if ambiente == "Esterni" else "Lampade da Terra"
    nomi_cat = CATEGORIE_FISSE + [cat_nome]
    print(categorie_map.keys())
    category_ids = [categorie_map[n] for n in nomi_cat if n in categorie_map]


    return {
        "product": {
            "sku": config_sku,
            "name": titolo,
            "attribute_set_id": ATTRIBUTE_SET_ID,
            "status": 1,
            "visibility": 4,          # Catalog, Search
            "type_id": "configurable",
            "weight": 0,
            "extension_attributes": {
                "website_ids": WEBSITE_IDS,
                "category_links": [
                    {"position": i, "category_id": str(cat_id)}
                    for i, cat_id in enumerate(category_ids)
                ],
            },
            "custom_attributes": [
                {"attribute_code": "url_key", "value": url_key},
                {"attribute_code": "manufacturer", "value": manufacturer_val},
                {"attribute_code": "lamp_lampadina", "value": lamp_val},
                {"attribute_code": "lamp_dimmer", "value": dimmer_val},
                {"attribute_code": "lamp_dimensioni", "value": dimensioni_val},
                {"attribute_code": "lamp_materiali_costruzione", "value": materiali_val},
                {"attribute_code": "lamp_max_potenza", "value": watt_val},
                {"attribute_code": "lamp_grado_protezione", "value": ip_val},
                {"attribute_code": "lamp_attacco_lamp_menu", "value": attacco_menu_val},
            ],
            "media_gallery_entries": media_entries,
        },
        "_child_skus": child_skus,    # usato da magento_import.py per il linking
        "_attr_codes": attr_codes,    # risolti in attribute_id numerico a runtime
    }


# ─────────────────────────────────────────────
# RAGGRUPPAMENTO SEMPLICI → SOTTOFAMIGLIE
# ─────────────────────────────────────────────

def estrai_sottofamiglia(nome: str) -> str:
    """
    Chiave di raggruppamento dal nome del prodotto semplice.

    Es.: "Ideal Lux Agos pt h60 3000k Lampada Da Terra-Antracite-LED"
         → "ideal lux agos pt h60 lampada da terra"
    """
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
# MAIN
# ─────────────────────────────────────────────

def main():
    with open(INPUT_JSON, encoding="utf-8") as f:
        semplici_tutti = json.load(f)

    print(f"📦  Prodotti semplici letti: {len(semplici_tutti)}")

    df = pd.read_csv(CSV_PATH, sep=";")

    session = get_oauth_session()

    attacco_menu_map = get_attribute_options(session, "lamp_attacco_lamp_menu")
    categorie_map = build_categorie_map(session)

    gruppi = raggruppa_per_sottofamiglia(semplici_tutti)
    print(f"🔗  Gruppi (configurabili) trovati: {len(gruppi)}\n")

    configurabili = []
    for idx, (key, gruppo) in enumerate(sorted(gruppi.items()), start=1):
        config_sku = f"IL-CONFIG-{idx:03d}"
        config     = build_configurable(config_sku, gruppo, df, attacco_menu_map, categorie_map)
        configurabili.append(config)

        print(
            f"  [{config_sku}]  {config['product']['name']}\n"
            f"           attributi varianti : {config['_attr_codes']}\n"
            f"           semplici ({len(config['_child_skus'])}): {config['_child_skus']}\n"
        )

    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(configurabili, f, ensure_ascii=False, indent=2)

    print(f"✅  {OUTPUT_JSON}  ({len(configurabili)} configurabili generati)")


if __name__ == "__main__":
    main()
