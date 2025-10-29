"""Billing API endpoints"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from modules.billing.service import billing_service


router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    user_id: int
    plan_code: str
    success_url: str
    cancel_url: str


class PortalRequest(BaseModel):
    user_id: int
    return_url: str


@router.get("/plans")
def list_plans():
    return {"plans": billing_service.list_plans()}


@router.post("/checkout")
def create_checkout(payload: CheckoutRequest):
    try:
        return billing_service.create_checkout_session(
            user_id=payload.user_id,
            plan_code=payload.plan_code,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    try:
        return billing_service.handle_webhook(payload, signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/subscription")
def subscription_summary(user_id: int):
    try:
        return billing_service.get_subscription_summary(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/portal")
def create_portal_session(payload: PortalRequest):
    try:
        return billing_service.create_billing_portal_session(payload.user_id, payload.return_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
