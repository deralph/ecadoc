"""Profile endpoints"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from modules.profile.service import profile_service


router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/avatar")
async def upload_avatar(user_id: int = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    try:
        return profile_service.save_avatar(user_id, file.filename, file.content_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/avatar")
def get_avatar(user_id: int):
    avatar = profile_service.get_avatar(user_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar
