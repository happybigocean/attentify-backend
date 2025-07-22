def gmail_account_helper(account: dict) -> dict:
    return {
        "id": str(account["_id"]),
        "user_id": str(account["user_id"]),
        "email": account["email"],
        "access_token": account["access_token"],
        "refresh_token": account["refresh_token"],
        "token_type": account.get("token_type", "Bearer"),
        "expires_at": account["expires_at"],
        "client_id": account["client_id"],
        "client_secret": account["client_secret"],
        "status": account.get("status", "connected"),
        "scope": account.get("scope"),
        "token_issued_at": account.get("token_issued_at"),
        "is_primary": account.get("is_primary", False),
        "provider": account.get("provider", "google"),
    }