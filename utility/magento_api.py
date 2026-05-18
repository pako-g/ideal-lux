import os
import time
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import urllib3

# Disabilita il warning SSL per certificati self-signed (solo sviluppo locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")

RETRY_DELAY = 1.0
MAX_RETRIES = 3


# ─────────────────────────────────────────────
# OAUTH SESSION
# ─────────────────────────────────────────────

def get_oauth_session() -> OAuth1Session:
    session = OAuth1Session(
        client_key=os.getenv("MAGENTO_CONSUMER_KEY"),
        client_secret=os.getenv("MAGENTO_CONSUMER_SECRET"),
        resource_owner_key=os.getenv("MAGENTO_ACCESS_TOKEN"),
        resource_owner_secret=os.getenv("MAGENTO_TOKEN_SECRET"),
        signature_method="HMAC-SHA256",
    )
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    return session


# ─────────────────────────────────────────────
# HTTP HELPERS (con retry)
# ─────────────────────────────────────────────

def api_get(session: OAuth1Session, endpoint: str, params: dict = None) -> dict:
    """GET con retry su errori temporanei (5xx)."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/{endpoint}"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.get(url, params=params, verify=False)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            print(f"    ⚠️  {resp.status_code} — retry {attempt}/{MAX_RETRIES}...")
            time.sleep(RETRY_DELAY * attempt)
            continue
        raise RuntimeError(
            f"GET /rest/V1/{endpoint} → {resp.status_code}\n{resp.text}"
        )


def api_post(session: OAuth1Session, endpoint: str, payload: dict) -> dict:
    """POST con retry su errori temporanei (5xx)."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/{endpoint}"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.post(url, json=payload, verify=False)
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            print(f"    ⚠️  {resp.status_code} — retry {attempt}/{MAX_RETRIES}...")
            time.sleep(RETRY_DELAY * attempt)
            continue
        raise RuntimeError(
            f"POST /rest/V1/{endpoint} → {resp.status_code}\n{resp.text}"
        )


# ─────────────────────────────────────────────
# ATTRIBUTI
# ─────────────────────────────────────────────

def _fetch_attribute(session: OAuth1Session, attribute_code: str) -> dict:
    """Chiamata HTTP base per un attributo — usata internamente."""
    return api_get(session, f"products/attributes/{attribute_code}")


def get_attribute_options(session: OAuth1Session, attribute_code: str) -> dict:
    """
    Restituisce {label: id} per un attributo select.

    Esempio:
      get_attribute_options(session, "color") → {"Bianco": "49", "Nero": "50"}
    """
    data = _fetch_attribute(session, attribute_code)
    return {
        opt["label"]: opt["value"]
        for opt in data.get("options", [])
        if opt["label"] and opt["value"]
    }


def get_attribute_info(session: OAuth1Session, attribute_code: str) -> dict:
    """
    Restituisce attribute_id numerico e mappa opzioni {id: label}.

    Esempio:
      get_attribute_info(session, "color") → {"attribute_id": "93", "options": {"49": "Bianco", ...}}
    """
    data = _fetch_attribute(session, attribute_code)
    return {
        "attribute_id": str(data["attribute_id"]),
        "options": {
            opt["value"]: opt["label"]
            for opt in data.get("options", [])
            if opt.get("value")
        },
    }


def get_attribute_set_id(session: OAuth1Session, name: str) -> int:
    """Restituisce l'attribute_set_id per nome."""
    data = api_get(session, "eav/attribute-sets/list", params={
        "searchCriteria[filter_groups][0][filters][0][field]": "attribute_set_name",
        "searchCriteria[filter_groups][0][filters][0][value]": name,
    })
    items = data.get("items", [])
    return items[0]["attribute_set_id"] if items else None


# ─────────────────────────────────────────────
# CATEGORIE
# ─────────────────────────────────────────────

def build_categorie_map(session: OAuth1Session) -> dict:
    """Restituisce {nome_categoria: id} percorrendo l'albero Magento."""
    data = api_get(session, "categories")
    categorie_map = {}

    def scorri(nodo):
        categorie_map[nodo["name"]] = nodo["id"]
        for figlio in nodo.get("children_data", []):
            scorri(figlio)

    scorri(data)
    return categorie_map


# ─────────────────────────────────────────────
# LINKING SEMPLICI → CONFIGURABILE
# ─────────────────────────────────────────────

def linka_semplici(session: OAuth1Session, links: list) -> dict[str, bool]:
    """
    Associa i prodotti semplici al configurabile via
    POST /rest/V1/configurable-products/{config_sku}/child.

    Restituisce {child_sku: True/False} con l'esito di ogni link.
    """
    risultati: dict[str, bool] = {}

    for item in links:
        config_sku = item["config_sku"]
        child_skus = item["child_skus"]
        print(f"\n  🔗  Associo semplici a  {config_sku}  ({len(child_skus)} prodotti)")

        for sku in child_skus:
            try:
                api_post(session, f"configurable-products/{config_sku}/child", {"childSku": sku})
                print(f"       ✅  {sku}")
                risultati[sku] = True
            except RuntimeError as e:
                print(f"       ❌  {sku}  —  {e}")
                risultati[sku] = False
            time.sleep(RETRY_DELAY)

    return risultati