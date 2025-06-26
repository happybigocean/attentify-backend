from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode
import hmac, hashlib, requests, base64
import os
from typing import List

router = APIRouter()

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_REDIRECT_URI = os.getenv("SHOPIFY_REDIRECT_URI", "http://localhost:8000/api/v1/shopify/callback")
SHOPIFY_SCOPE = "read_orders,write_orders,read_customers,write_customers"
SHOPIFY_INSTALL_URL=os.getenv("SHOPIFY_INSTALL_URL")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

class ShopifyAuthHelper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def build_authorization_url(self, shop: str, redirect_uri: str):
        params = {
            "client_id": self.client_id,
            "scope": "read_orders,write_products",  # adjust your scopes
            "redirect_uri": redirect_uri,
            "state": "secure_random_state",  # implement CSRF protection!
        }
        return f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"

    async def exchange_code_for_access_token(self, shop: str, code: str):
        import httpx
        url = f"https://{shop}/admin/oauth/access_token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data)
            r.raise_for_status()
            return r.json()["access_token"]
        
shopify_auth_helper = ShopifyAuthHelper(SHOPIFY_API_KEY, SHOPIFY_API_SECRET)       

#/api/v1/shopify/auth
@router.get("/auth")
def shopify_auth(request: Request):
    """
    Redirect user to Shopify OAuth consent page
    """
    #shop = request.query_params.get("shop")
    #if not shop:
    #    raise HTTPException(status_code=400, detail="Missing 'shop' parameter")

    # Generate the install URL
    #install_url = (
    #    f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}"
    #    f"&scope={quote(SHOPIFY_SCOPE)}&redirect_uri={quote(SHOPIFY_REDIRECT_URI)}"
    #)

    return RedirectResponse(SHOPIFY_INSTALL_URL)

#/api/v1/shopify/callback
@router.get("/callback")
def shopify_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get("shop")
    code = params.get("code")
    hmac_received = params.get("hmac")

    if not shop or not code or not hmac_received:
        raise HTTPException(status_code=400, detail="Missing parameters")

    # Verify HMAC
    sorted_params = "&".join(
        f"{k}={v}" for k, v in sorted(params.items()) if k != "hmac"
    )
    generated_hmac = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        sorted_params.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(generated_hmac, hmac_received):
        raise HTTPException(status_code=400, detail="Invalid HMAC")

    # Exchange code for access token
    token_url = f"https://{shop}/admin/oauth/access_token"
    data = {
        "client_id": SHOPIFY_API_KEY,
        "client_secret": SHOPIFY_API_SECRET,
        "code": code
    }

    response = requests.post(token_url, json=data)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Token exchange failed")

    access_token = response.json().get("access_token")

    db = request.app.state.db
    db.shopify_cred.update_one(
        {"shop": shop},
        {"$set": {
            "access_token": access_token, 
            "status": "connected"
            }
        },
        upsert=True
    )

    redirect_frontend_url = f"{FRONTEND_URL}/shopify/success?shop={shop}"
    return RedirectResponse(url=redirect_frontend_url)

@router.get("/install")
def shopify_install(request: Request):
    params = dict(request.query_params)
    shop = params.get("shop")
    hmac = params.get("hmac")
    if not shop or not hmac:
        raise HTTPException(status_code=400, detail="Missing 'shop' or 'hmac' parameter")
    redirect_uri = f"{BACKEND_URL}/api/v1/shopify/callback"
    auth_url = shopify_auth_helper.build_authorization_url(shop, redirect_uri)
    return RedirectResponse(url=auth_url)

def decode_host_func(base64_host: str) -> str:
    try:
        padded = base64_host + "=" * ((4 - len(base64_host) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return decoded_bytes.decode("utf-8")
    except Exception as ex:
        print(f"Error decoding Base64 host: {ex}")
        return ""
    
#/api/v1/shopify/orders
@router.get("/orders")
def get_shopify_orders(request: Request):
    shop = request.query_params.get("shop")
    if not shop:
        raise HTTPException(status_code=400, detail="Missing 'shop' parameter")

    db = request.app.state.db
    shopify_cred = db.shopify_cred.find_one({"shop": shop})
    if not shopify_cred or "access_token" not in shopify_cred:
        raise HTTPException(status_code=401, detail="Shop not authenticated")

    access_token = shopify_cred["access_token"]
    orders_url = f"https://{shop}/admin/api/2024-10/orders.json"

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    response = requests.get(orders_url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch orders")

    return response.json()

@router.get("/", response_model=List[dict])
async def list_shopify_cred(request: Request):
    db = request.app.state.db
    creds_cursor = db.shopify_cred.find()
    creds = []
    async for cred in creds_cursor:

        if '_id' in cred:
            cred['_id'] = str(cred['_id'])

        creds.append(cred)
    return creds