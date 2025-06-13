from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, users, inbox, ai, templates, webhooks, shopify, twilio, gmail, stripe

app = FastAPI(title="Attentify API")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["Inbox"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["Templates"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(shopify.router, prefix="/api/v1/shopify", tags=["Shopify"])
app.include_router(twilio.router, prefix="/api/v1/twilio", tags=["Twilio"])
app.include_router(gmail.router, prefix="/api/v1/gmail", tags=["Gmail"])
app.include_router(stripe.router, prefix="/api/v1/stripe", tags=["Stripe"])

@app.get("/health")
def health_check():
    return {"status": "ok"}