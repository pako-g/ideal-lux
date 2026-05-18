import os
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
import urllib3
import time

# Disabilita il warning SSL per certificati self-signed (solo sviluppo locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

MAGENTO_BASE_URL = os.getenv("MAGENTO_BASE_URL")

RETRY_DELAY      = 1.0
MAX_RETRIES      = 3


# ─────────────────────────────────────────────
# OAUTH SESSION
# ─────────────────────────────────────────────
def get_oauth_session() -> OAuth1Session:
    """
    Recupero oauth session di magento
    :return: session
    """
    session = OAuth1Session(
        client_key=os.getenv("MAGENTO_CONSUMER_KEY"),
        client_secret=os.getenv("MAGENTO_CONSUMER_SECRET"),
        resource_owner_key=os.getenv("MAGENTO_ACCESS_TOKEN"),
        resource_owner_secret=os.getenv("MAGENTO_TOKEN_SECRET"),
        signature_method="HMAC-SHA256",
    )

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

    :param session:
    :param attribute_code:
    :return: dict:
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


# ───────────────────────────────────────────────
#
# ───────────────────────────────────────────────
def get_attribute_info(session: OAuth1Session, attribute_code: str) -> dict:
    """Restituisce attribute_id numerico e mappa opzioni per un attributo."""
    url = f"{MAGENTO_BASE_URL}/rest/V1/products/attributes/{attribute_code}"

    resp = session.get(url, verify=False)
    resp.raise_for_status()
    data = resp.json()
    options = {
        opt["value"]: opt["label"]
        for opt in data.get("options", [])
        if opt.get("value")
    }
    return {
        "attribute_id": str(data["attribute_id"]),
        "options": options,
    }

# ───────────────────────────────────────────────
# RECUPERO ATTRIBUTE_SET_ID DA ATTRIBUTE_SET_NAME
# ───────────────────────────────────────────────
def get_attribute_set_id(session: OAuth1Session, name: str) -> int:
    """

    :param session:
    :param name:
    :return:
    """
    url = f"{MAGENTO_BASE_URL}/rest/V1/eav/attribute-sets/list"
    resp = session.get(url, params={
        "searchCriteria[filter_groups][0][filters][0][field]": "attribute_set_name",
        "searchCriteria[filter_groups][0][filters][0][value]": name,
    }, verify=False)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return items[0]["attribute_set_id"] if items else None



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
# STEP 5 — ASSOCIA SEMPLICI AL CONFIGURABILE
# ─────────────────────────────────────────────
def linka_semplici(session: OAuth1Session, links: list) -> None:
    """
    POST /rest/V1/configurable-products/{config_sku}/child
    per ogni semplice da associare.
    """
    for item in links:
        config_sku = item["config_sku"]
        child_skus = item["child_skus"]
        print(f"\n  🔗  Associo semplici a  {config_sku}  ({len(child_skus)} prodotti)")

        for sku in child_skus:
            endpoint = f"configurable-products/{config_sku}/child"
            try:
                api_post(session, endpoint, {"childSku": sku})
                print(f"       ✅  {sku}")
            except RuntimeError as e:
                print(f"       ❌  {sku}  —  {e}")
            time.sleep(RETRY_DELAY)