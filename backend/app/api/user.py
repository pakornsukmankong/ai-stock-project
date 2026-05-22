from fastapi import APIRouter, HTTPException, Depends
from app.core.database import get_supabase_client
from app.core.auth import get_current_user_id
from app.schemas.user import ConnectLineRequest, UpdateNotificationPreferenceRequest

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get user profile."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .execute()
        )

        if not response.data:
            user_data = await _ensure_user_exists(supabase, user_id)
            return {"user": user_data}

        return {"user": response.data[0]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect-line")
async def connect_line(request: ConnectLineRequest, user_id: str = Depends(get_current_user_id)):
    """Connect LINE account to user profile."""
    try:
        supabase = get_supabase_client()

        await _ensure_user_exists(supabase, user_id)

        response = (
            supabase.table("users")
            .update({"line_user_id": request.line_user_id})
            .eq("id", user_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "LINE account connected successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/disconnect-line")
async def disconnect_line(user_id: str = Depends(get_current_user_id)):
    """Disconnect LINE account from user profile."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("users")
            .update({"line_user_id": None})
            .eq("id", user_id)
            .execute()
        )

        return {"message": "LINE account disconnected"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/notification-preference")
async def update_notification_preference(
    request: UpdateNotificationPreferenceRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update minimum confidence level for notifications."""
    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("users")
            .update({"min_confidence": request.min_confidence})
            .eq("id", user_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": f"Notification preference set to: {request.min_confidence}"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _ensure_user_exists(supabase, user_id: str) -> dict:
    """Ensure user record exists in users table. Create if missing."""
    response = (
        supabase.table("users")
        .select("*")
        .eq("id", user_id)
        .execute()
    )

    if response.data:
        return response.data[0]

    try:
        auth_user = supabase.auth.admin.get_user_by_id(user_id)
        email = auth_user.user.email if auth_user.user else f"{user_id}@unknown"
    except Exception:
        email = f"{user_id}@unknown"

    insert_response = (
        supabase.table("users")
        .insert({"id": user_id, "email": email})
        .execute()
    )

    try:
        supabase.table("watchlists").insert({"user_id": user_id}).execute()
    except Exception:
        pass

    return insert_response.data[0] if insert_response.data else {"id": user_id, "email": email}
