from fastapi import APIRouter, Request, HTTPException, Header, status, BackgroundTasks, Depends, Query
from fastapi.responses import RedirectResponse, JSONResponse
from urllib.parse import urlencode
import hmac, hashlib, requests, base64
import os
from typing import List, Dict
from datetime import datetime
import json
from bson import ObjectId
from app.services.shopify_service import (
    get_all_shopify_creds,
    fetch_orders_from_shop,
    upsert_orders,
)

from app.db.mongodb import get_database
from app.core.security import get_current_user

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
def shopify_auth(request: Request, user_id: str = Query(...)):
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

    request.session["user_id"] = user_id
    return RedirectResponse(url=SHOPIFY_INSTALL_URL)

@router.get("/install")
def shopify_install(
    request: Request, 
):
    params = dict(request.query_params)
    shop = params.get("shop")
    hmac = params.get("hmac")
    if not shop or not hmac:
        raise HTTPException(status_code=400, detail="Missing 'shop' or 'hmac' parameter")
    
    redirect_uri = f"{BACKEND_URL}/api/v1/shopify/callback"
    auth_url = shopify_auth_helper.build_authorization_url(shop, redirect_uri)
    return RedirectResponse(url=auth_url)

#/api/v1/shopify/callback
@router.get("/callback")
def shopify_callback(request: Request):
    params = dict(request.query_params)
    shop = params.get("shop")
    code = params.get("code")
    hmac_received = params.get("hmac")
    user_id = request.session.get("user_id")

    if not shop or not code or not hmac_received or not user_id:
        raise HTTPException(status_code=400, detail="Missing parameters")

    # HMAC verification
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

    # Register webhook
    register_shopify_webhook(shop, access_token)

    db = request.app.state.db
    db.shopify_cred.update_one(
        {"shop": shop, "user_id": ObjectId(user_id)},
        {
            "$set": {
                "shop": shop,  # ← add this
                "access_token": access_token,
                "status": "connected",
                "user_id": ObjectId(user_id)
            }
        },
        upsert=True
    )

    redirect_frontend_url = f"{FRONTEND_URL}/shopify/success?shop={shop}"
    return RedirectResponse(url=redirect_frontend_url)

def decode_host_func(base64_host: str) -> str:
    try:
        padded = base64_host + "=" * ((4 - len(base64_host) % 4) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return decoded_bytes.decode("utf-8")
    except Exception as ex:
        print(f"Error decoding Base64 host: {ex}")
        return ""
    
#/api/v1/shopify/orders
@router.get("/orders1")
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
async def list_shopify_cred(request: Request, current_user: dict = Depends(get_current_user)) :
    db = request.app.state.db
    cursor = db.shopify_cred.find({"user_id": current_user["_id"]})
    docs = []
    async for doc in cursor:
        doc['_id'] = str(doc['_id'])
        doc['user_id'] = str(doc['user_id'])  # Convert ObjectId to string
        docs.append(doc)
    return docs

# Register Shopify Webhook
def register_shopify_webhook(shop: str, access_token: str):
    webhook_url = f"https://{shop}/admin/api/2024-10/webhooks.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    data = {
        "webhook": {
            "topic": "orders/create",
            "address": f"{BACKEND_URL}/api/v1/shopify/webhook/orders_create",
            "format": "json"
        }
    }
    try:
        response = requests.post(webhook_url, json=data, headers=headers)
    except requests.RequestException as e:
        print(f"[!] Webhook request exception: {e}")
        return False

    if response.status_code == 201:
        print(f"[✓] Webhook registered for {shop}")
    else:
        print(f"[!] Webhook failed: {response.status_code} {response.text}")

    return response.status_code == 201

@router.post("/webhook/orders_create")
async def shopify_orders_create_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(...),
    x_shopify_shop_domain: str = Header(...)
):
    try:
        raw_body = await request.body()

        # --- HMAC Verification ---
        computed_hmac = base64.b64encode(
            hmac.new(
                SHOPIFY_API_SECRET.encode("utf-8"),
                raw_body,
                hashlib.sha256
            ).digest()
        ).decode()
        print(f"[✓] x_shopify_hmac_sha256: {x_shopify_hmac_sha256}")
        print(f"[✓] Computed HMAC: {computed_hmac}")
        # Shopify sends the HMAC header as base64 (case-insensitive)
        if not hmac.compare_digest(computed_hmac, x_shopify_hmac_sha256):
            print("[!] Invalid HMAC received")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC")
        
        data = json.loads(raw_body)
        print(f"[✓] x_shopify_shop_domain: {x_shopify_shop_domain}")
        order_document = {
            "shop": x_shopify_shop_domain,
            "order_id": data["id"],
            "order_number": data.get("order_number"),
            "name": data.get("name"),
            "created_at": data.get("created_at"),
            "customer": {
                "id": data.get("customer", {}).get("id"),
                "email": data.get("customer", {}).get("email"),
                "name": f"{data.get('customer', {}).get('first_name', '')} {data.get('customer', {}).get('last_name', '')}".strip(),
                "phone": data.get("customer", {}).get("phone"),
                "default_address": {
                    "address1": data.get("customer", {}).get("default_address", {}).get("address1"),
                    "address2": data.get("customer", {}).get("default_address", {}).get("address2"),
                    "city": data.get("customer", {}).get("default_address", {}).get("city"),
                    "province": data.get("customer", {}).get("default_address", {}).get("province"),
                    "country": data.get("customer", {}).get("default_address", {}).get("country"),
                    "zip": data.get("customer", {}).get("default_address", {}).get("zip"),
                }
            },
            "shipping_address": data.get("shipping_address", {}),
            "billing_address": data.get("billing_address", {}),
            "line_items": [
                {
                    "product_id": item.get("product_id"),
                    "name": item.get("name"),
                    "quantity": item.get("quantity"),
                    "price": item.get("price")
                } for item in data.get("line_items", [])
            ],
            "total_price": data.get("total_price"),
            "payment_status": data.get("financial_status"),
            "fulfillment_status": data.get("fulfillment_status"),
            "updated_at": data.get("updated_at")
        }

        db = await get_database()
        # async Motor: must await db operations
        print(f"[✓] Inserting/updating order: {order_document['order_id']} in shop: {order_document['shop']}")
        if not await db.orders.find_one({"order_id": order_document["order_id"]}):
            print(f"[✓] Order {order_document['order_id']} not found, inserting new document.")
            await db.orders.insert_one(order_document)

        return {"success": True}
    except Exception as e:
        print(f"[!] Error processing webhook: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook processing failed: {str(e)}")
    
# Endpoint: Get all orders (for all stores)
@router.get("/orders", response_model=List[dict])
async def get_orders(request: Request):
    db = request.app.state.db
    # Use async for to iterate, or to_list() to get list at once
    orders_cursor = db.orders.find({}, {"_id": 0})
    orders = await orders_cursor.to_list(length=1000)  # or whatever max size you want
    return orders

# Endpoint: Sync orders from all stores
@router.post("/orders/sync")
def sync_orders(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_stores_orders)
    return {"msg": "Sync started."}

# Background job: fetch and upsert all orders for all stores
async def sync_all_stores_orders():
    db = await get_database()
    creds = await get_all_shopify_creds(db)
    for cred in creds:
        shop = cred.get("shop")
        access_token = cred.get("access_token")
        if not shop or not access_token:
            continue
        try:
            orders = await fetch_orders_from_shop(shop, access_token)
            await upsert_orders(db, shop, orders)
        except Exception as e:
            print(f"Error syncing {shop}: {e}")
