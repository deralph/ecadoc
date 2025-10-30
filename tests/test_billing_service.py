from types import SimpleNamespace
import uuid

import pytest

from modules.billing.service import BillingService
from modules.config import settings
from modules.database.models import DatabaseManager


class MockStripe:
    def __init__(self):
        self.created_session = None
        self.portal_session = None
        self.subscription = {
            "id": "sub_test",
            "status": "active",
            "current_period_start": 1_700_000_000,
            "current_period_end": 1_700_000_000 + 86400,
            "cancel_at_period_end": False,
            "cancel_at": None,
        }
        self.checkout = SimpleNamespace(Session=SimpleNamespace(create=self._create_session))
        self.billing_portal = SimpleNamespace(Session=SimpleNamespace(create=self._create_portal))
        self.Subscription = SimpleNamespace(retrieve=self._retrieve_subscription)
        self.Webhook = SimpleNamespace(construct_event=self._construct_event)
        self.event = {}

    def _create_session(self, **kwargs):
        self.created_session = kwargs
        return {"id": "cs_test", "url": "https://stripe.test/checkout"}

    def _create_portal(self, **kwargs):
        self.portal_session = kwargs
        return {"url": "https://stripe.test/portal"}

    def _retrieve_subscription(self, subscription_id):
        return self.subscription

    def _construct_event(self, payload, signature, secret):
        return self.event


def create_billing_service(tmp_path_factory):
    settings.STRIPE_API_KEY = "sk_test"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    db_path = tmp_path_factory.mktemp("db") / "billing.db"
    db = DatabaseManager(db_name=str(db_path))
    mock_stripe = MockStripe()
    service = BillingService(db=db, stripe_client=mock_stripe)
    db.upsert_subscription_plan("plan_semiannual", "Semi Annual", 6, 6000, "price_semiannual")
    email = f"bill+{uuid.uuid4().hex}@example.com"
    user_id = db.create_user("Bill", "User", email, "password123")
    return service, mock_stripe, db, user_id


def test_checkout_session_creates_metadata(tmp_path_factory):
    service, mock_stripe, db, user_id = create_billing_service(tmp_path_factory)

    session = service.create_checkout_session(user_id, "plan_semiannual", "https://success", "https://cancel")
    assert session["checkout_url"] == "https://stripe.test/checkout"
    assert mock_stripe.created_session["metadata"]["plan_code"] == "plan_semiannual"

    mock_stripe.event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"plan_code": "plan_semiannual", "user_id": str(user_id)},
                "subscription": "sub_test",
                "customer": "cus_test",
            }
        },
    }

    response = service.handle_webhook(b"{}", "sig_test")
    assert response["received"] is True

    summary = service.get_subscription_summary(user_id)
    assert summary["status"] == "active"
    assert summary["plan"]["plan_code"] == "plan_semiannual"
