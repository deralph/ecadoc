"""Billing and subscription management service"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any

import stripe

from modules.config.settings import settings
from modules.database.models import db_manager, SubscriptionPlan, UserSubscription


class BillingService:
    def __init__(self, db=None, stripe_client=None):
        self.db = db or db_manager
        self.stripe = stripe_client or stripe
        if settings.STRIPE_API_KEY:
            self.stripe.api_key = settings.STRIPE_API_KEY
        self.db.ensure_default_subscription_plans()

    def list_plans(self):
        plans = self.db.get_active_subscription_plans()
        return [self._plan_to_dict(plan) for plan in plans]

    def _plan_to_dict(self, plan: SubscriptionPlan) -> Dict[str, Any]:
        return {
            "plan_code": plan.plan_code,
            "name": plan.name,
            "interval_months": plan.interval_months,
            "amount_cents": plan.amount_cents,
            "stripe_price_id": plan.stripe_price_id,
            "is_active": plan.is_active,
        }

    def create_checkout_session(self, user_id: int, plan_code: str, success_url: str, cancel_url: str) -> Dict[str, Any]:
        plan = self.db.get_subscription_plan(plan_code)
        if not plan or not plan.stripe_price_id:
            raise ValueError("Plan is not configured with a Stripe price")

        if not settings.STRIPE_API_KEY:
            raise ValueError("Stripe API key is not configured")

        session = self.stripe.checkout.Session.create(
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            metadata={
                "user_id": str(user_id),
                "plan_code": plan.plan_code,
            },
        )

        self.db.record_subscription_event("checkout.session.created", {"session_id": session.get("id"), "user_id": user_id}, None)

        return {"checkout_url": session.get("url"), "session_id": session.get("id")}

    def _timestamp_to_datetime(self, value) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.utcfromtimestamp(value)
        except Exception:
            return None

    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise ValueError("Stripe webhook secret is not configured")
        if not signature:
            raise ValueError("Missing Stripe signature header")

        event = self.stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})

        self.db.record_subscription_event(event_type, event)

        if event_type == "checkout.session.completed":
            metadata = data.get("metadata", {})
            plan_code = metadata.get("plan_code")
            user_id = metadata.get("user_id")
            subscription_id = data.get("subscription")
            customer_id = data.get("customer")
            if not plan_code or not user_id or not subscription_id:
                raise ValueError("Checkout session missing metadata")

            subscription = self.stripe.Subscription.retrieve(subscription_id)
            self.db.create_or_update_user_subscription(
                user_id=int(user_id),
                plan_code=plan_code,
                stripe_subscription_id=subscription_id,
                stripe_customer_id=customer_id,
                status=subscription.get("status", "active"),
                current_period_start=self._timestamp_to_datetime(subscription.get("current_period_start")),
                current_period_end=self._timestamp_to_datetime(subscription.get("current_period_end")),
                cancel_at_period_end=subscription.get("cancel_at_period_end", False),
                cancellation_effective_date=self._timestamp_to_datetime(subscription.get("cancel_at")),
            )

        elif event_type in {"customer.subscription.updated", "invoice.paid"}:
            subscription_id = data.get("id") or data.get("subscription")
            if subscription_id:
                current_start = self._timestamp_to_datetime(data.get("current_period_start"))
                current_end = self._timestamp_to_datetime(data.get("current_period_end"))
                self.db.update_subscription_status(
                    subscription_id,
                    data.get("status", "active"),
                    current_period_start=current_start,
                    current_period_end=current_end,
                    cancel_at_period_end=data.get("cancel_at_period_end"),
                    cancellation_effective_date=self._timestamp_to_datetime(data.get("cancel_at")),
                )

        elif event_type == "customer.subscription.deleted":
            subscription_id = data.get("id")
            if subscription_id:
                self.db.update_subscription_status(subscription_id, data.get("status", "canceled"))

        return {"received": True}

    def get_subscription_summary(self, user_id: int) -> Dict[str, Any]:
        subscription = self.db.get_user_subscription_by_user(user_id)
        if not subscription:
            return {"status": "inactive", "plan": None}

        plan = self.db.get_subscription_plan(subscription.plan_code)
        return {
            "status": subscription.status,
            "plan": self._plan_to_dict(plan) if plan else None,
            "current_period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        }

    def create_billing_portal_session(self, user_id: int, return_url: str) -> Dict[str, Any]:
        if not settings.STRIPE_API_KEY:
            raise ValueError("Stripe API key is not configured")

        subscription = self.db.get_user_subscription_by_user(user_id)
        if not subscription or not subscription.stripe_customer_id:
            raise ValueError("Active subscription not found")

        session = self.stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=return_url,
        )

        return {"portal_url": session.get("url")}


billing_service = BillingService()
