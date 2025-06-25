from fastapi import APIRouter, FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import quote
import hmac, hashlib, requests
import os

router = APIRouter()

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_REDIRECT_URI = os.getenv("SHOPIFY_REDIRECT_URI", "http://localhost:8000/api/v1/shopify/callback")
SHOPIFY_SCOPE = "read_orders,write_orders,read_customers,write_customers"

#/api/v1/shopify/auth
@router.get("/auth")
def shopify_auth(request: Request):
    """
    Redirect user to Shopify OAuth consent page
    """
    shop = request.query_params.get("shop")
    if not shop:
        raise HTTPException(status_code=400, detail="Missing 'shop' parameter")

    # Generate the install URL
    install_url = (
        f"https://{shop}/admin/oauth/authorize?client_id={SHOPIFY_API_KEY}"
        f"&scope={quote(SHOPIFY_SCOPE)}&redirect_uri={quote(SHOPIFY_REDIRECT_URI)}"
    )
    
    return RedirectResponse(install_url)

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
        {"$set": {"access_token": access_token}},
        upsert=True
    )

    return {"message": "OAuth successful", "shop": shop, "access_token": access_token}

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