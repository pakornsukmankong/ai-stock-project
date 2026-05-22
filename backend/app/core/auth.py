from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.database import get_supabase_client


security = HTTPBearer()


async def get_current_user_id(request: Request) -> str:
    """Extract and verify user from Supabase JWT token.

    Reads the Authorization header, verifies the token with Supabase,
    and returns the authenticated user's ID.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.replace("Bearer ", "")

    try:
        supabase = get_supabase_client()
        response = supabase.auth.get_user(token)

        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return response.user.id

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")
