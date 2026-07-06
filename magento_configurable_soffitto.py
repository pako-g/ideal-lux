"""
Generatore JSON — Prodotti CONFIGURABILI Magento
Categoria: Lampada da soffitto
Output: configurable_products_lampada_da_soffitto.json

Importa REGOLE direttamente da magento_simple_soffitto.py
CONFIG_SKU_START = 479  (parete termina a 478)
"""

import json
import re
import sys
import pandas as pd
from pathlib import Path
from utility.magento_api import (
    get_oauth_session, get_attribute_set_id,
    get_attribute_options, build_attr_map, build_categorie_map,
)

# Importa REGOLE e helpers dal simple
from magento_simple_soffitto import (
    REGOLE, FAMIGLIE_DA_SALTARE, FINITURE_DA_SALTARE,
    load_categoria, finitura_label, luci_label,
    dim_from_col, dim_from_desc, altezza_from_col,
    token_from_desc, build_url_key,
    MARCA,
)


# ─────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────

CSV_PATH           = "./file/giacenzeECommerce.csv"
CATEGORIA          = "Lampada da soffitto"
OUTPUT_PATH        = "./file/configurable_products_lampada_da_soffitto.json"
ATTRIBUTE_SET_NAME = "Ideal-Lux"
WEBSITE_IDS        = [1]
CATEGORIA_MAGENTO  = "Lampade da Soffitto"

CONFIG_SKU_START   = 479   # parete termina a IL-CONFIG-478


# ─────────────────────────────────────────────
# CONFERMA INTERATTIVA CONFIG_SKU_START
# ─────────────────────────────────────────────

def conferma_sku_start(start: int) -> int:
    print(f"\n⚙️  CONFIG_SKU_START impostato a: {start}")
    risposta = input("   Confermi? (invio = sì, oppure digita il nuovo valore): ").strip()
    if risposta == "":
        return start
    try:
        return int(risposta)
    except ValueError:
        print("   Valore non valido, uso il default.")
        return start


# ─────────────────────────────────────────────
# NOME CONFIGURABILE
# ─────────────────────────────────────────────

def build_nome_config(famiglia: str, gruppo_key: str, assi: list,
                      regola: dict, gruppo: pd.DataFrame) -> str:
    """
    Costruisce il nome del configurabile a partire dalla famiglia
    e dai valori comuni del gruppo.
    """
    nome_base = f"{MARCA} {famiglia.capitalize()} Lampada Da Soffitto"

    # Aggiunge il gruppo_key se informativo (es. LED, PL_ROUND, AP_SQUARE…)
    if gruppo_key != famiglia and not gruppo_key.startswith(famiglia):
        nome_base += f" {gruppo_key.replace('_', ' ').capitalize()}"

    return nome_base


# ─────────────────────────────────────────────
# BUILD CONFIGURABILE
# ─────────────────────────────────────────────

def build_configurable(famiglia: str, gruppo_key: str, gruppo: pd.DataFrame,
                       assi_attivi: list, regola: dict,
                       attr_map: dict, attribute_set_id: int,
                       categoria_id: int, config_sku: str,
                       child_skus: list) -> dict:

    nome = build_nome_config(famiglia, gruppo_key, assi_attivi, regola, gruppo)

    # Prezzo minimo tra i figli
    prezzi = gruppo["prezzo"].dropna()
    prezzo = float(prezzi.min()) if not prezzi.empty else 0.0

    # Attributi configurabili
    configurable_options = []
    for asse in assi_attivi:
        if asse not in attr_map:
            continue
        info = attr_map[asse]
        fn   = regola["valori"].get(asse)
        if fn is None:
            continue

        saltare_fn = regola.get("saltare")
        valori_ids = []
        seen = set()
        for _, row in gruppo.iterrows():
            if saltare_fn and saltare_fn(row):
                continue
            val_label = fn(row)
            if not val_label or val_label in seen:
                continue
            seen.add(val_label)
            # cerca id nella mappa opzioni {id: label}
            val_id = next(
                (k for k, v in info["options"].items() if v == val_label),
                None
            )
            if val_id:
                valori_ids.append({"value_index": int(val_id)})

        if valori_ids:
            configurable_options.append({
                "attribute_id":  info["attribute_id"],
                "code":          asse,
                "label":         asse.replace("_", " ").title(),
                "position":      assi_attivi.index(asse),
                "values":        valori_ids,
            })

    return {
        "product": {
            "sku":              config_sku,
            "name":             nome,
            "attribute_set_id": attribute_set_id,
            "price":            prezzo,
            "status":           1,
            "visibility":       4,
            "type_id":          "configurable",
            "weight":           0,
            "extension_attributes": {
                "website_ids":   WEBSITE_IDS,
                "category_links": [{"category_id": str(categoria_id), "position": 0}],
                "configurable_product_options": configurable_options,
                "configurable_product_links":   [],
            },
            "custom_attributes": [
                {"attribute_code": "url_key", "value": build_url_key(nome)},
            ],
            "media_gallery_entries": [],
        },
        "_child_skus": child_skus,
        "_attr_codes": assi_attivi,
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    Path("./file").mkdir(exist_ok=True)

    config_sku_start = conferma_sku_start(CONFIG_SKU_START)

    session = get_oauth_session()

    attribute_set_id = get_attribute_set_id(session, ATTRIBUTE_SET_NAME)
    categorie_map    = build_categorie_map(session)
    categoria_id     = categorie_map.get(CATEGORIA_MAGENTO)
    if not categoria_id:
        print(f"❌  Categoria '{CATEGORIA_MAGENTO}' non trovata in Magento.")
        sys.exit(1)

    varianti = load_categoria(CSV_PATH, CATEGORIA)

    configurabili = []
    famiglie_skip = []
    sku_counter   = config_sku_start

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

        regola    = REGOLE[famiglia]
        gruppo_fn = regola.get("gruppo", lambda r: famiglia)
        g_fam["_gruppo"] = g_fam.apply(gruppo_fn, axis=1)

        for gruppo_key, gruppo in g_fam.groupby("_gruppo"):

            assi_def    = regola["assi"]
            saltare_fn  = regola.get("saltare")

            # Filtra saltati
            if saltare_fn:
                gruppo = gruppo[~gruppo.apply(saltare_fn, axis=1)].copy()
            if gruppo.empty:
                continue

            # Determina assi attivi (quelli con >1 valore distinto nel gruppo)
            assi_attivi = []
            for asse in assi_def:
                fn = regola["valori"].get(asse)
                if fn is None:
                    continue
                valori_gruppo = set(fn(r) for _, r in gruppo.iterrows())
                valori_gruppo.discard("")
                if len(valori_gruppo) > 1:
                    assi_attivi.append(asse)

            # Nessun asse attivo → prodotto singleton, niente configurabile
            if not assi_attivi:
                continue

            child_skus = [f"IL-{r['sku']}" for _, r in gruppo.iterrows()]
            config_sku = f"IL-CONFIG-{sku_counter}"
            sku_counter += 1

            print(f"  {config_sku}  {famiglia} / {gruppo_key}  "
                  f"({len(child_skus)} figli, assi: {assi_attivi})")

            configurabili.append(
                build_configurable(
                    famiglia, gruppo_key, gruppo,
                    assi_attivi, regola,
                    {},                  # attr_map — popolato dopo
                    attribute_set_id,
                    categoria_id,
                    config_sku,
                    child_skus,
                )
            )

    # Recupera attribute_id e opzioni per tutti gli assi usati
    print(f"\n🔍  Recupero attributi configurabili...")
    attr_map = build_attr_map(session, configurabili)

    # Rigenera i configurabili con attr_map popolato
    sku_counter   = config_sku_start
    configurabili_finali = []

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
        gruppo_fn = regola.get("gruppo", lambda r: famiglia)
        g_fam["_gruppo"] = g_fam.apply(gruppo_fn, axis=1)

        for gruppo_key, gruppo in g_fam.groupby("_gruppo"):

            assi_def   = regola["assi"]
            saltare_fn = regola.get("saltare")

            if saltare_fn:
                gruppo = gruppo[~gruppo.apply(saltare_fn, axis=1)].copy()
            if gruppo.empty:
                continue

            assi_attivi = []
            for asse in assi_def:
                fn = regola["valori"].get(asse)
                if fn is None:
                    continue
                valori_gruppo = set(fn(r) for _, r in gruppo.iterrows())
                valori_gruppo.discard("")
                if len(valori_gruppo) > 1:
                    assi_attivi.append(asse)

            if not assi_attivi:
                continue

            child_skus = [f"IL-{r['sku']}" for _, r in gruppo.iterrows()]
            config_sku = f"IL-CONFIG-{sku_counter}"
            sku_counter += 1

            configurabili_finali.append(
                build_configurable(
                    famiglia, gruppo_key, gruppo,
                    assi_attivi, regola,
                    attr_map,
                    attribute_set_id,
                    categoria_id,
                    config_sku,
                    child_skus,
                )
            )

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(configurabili_finali, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {OUTPUT_PATH}")
    print(f"    Configurabili generati: {len(configurabili_finali)}")
    print(f"    SKU range: IL-CONFIG-{config_sku_start} → IL-CONFIG-{sku_counter - 1}")

    if famiglie_skip:
        print(f"\n⚠️  Famiglie senza regola ({len(famiglie_skip)}):")
        for f in sorted(set(famiglie_skip)):
            print(f"     - {f}")