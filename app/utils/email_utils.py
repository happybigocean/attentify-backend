def gmail_account_helper(gmail_account) -> dict:
    return {
        "id": str(gmail_account["_id"]),
        "email": gmail_account["email"],
        "access_token": gmail_account["access_token"],
        "refresh_token": gmail_account["refresh_token"],
        "token_type": gmail_account.get("token_type", "Bearer"),
        "expires_at": gmail_account["expires_at"],
        "client_id": gmail_account["client_id"],
        "client_secret": gmail_account["client_secret"],
        "status": gmail_account.get("status", "connected"),
    }