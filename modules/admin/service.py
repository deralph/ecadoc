"""Administrative metrics service"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any, List

from modules.database.models import db_manager, SubscriptionPlan, UserSubscription


class AdminMetricsService:
    """Provides aggregated datasets for the admin dashboard"""

    RANGE_DEFAULTS = {
        "30d": 30,
        "90d": 90,
        "365d": 365,
    }

    def __init__(self, db=None):
        self.db = db or db_manager

    def _resolve_days(self, range_key: str) -> int:
        return self.RANGE_DEFAULTS.get(range_key, 30)

    def _plan_lookup(self) -> Dict[str, SubscriptionPlan]:
        return {plan.plan_code: plan for plan in self.db.get_active_subscription_plans()}

    def _calculate_mrr(self, subscriptions: List[UserSubscription], plans: Dict[str, SubscriptionPlan]) -> float:
        mrr = 0.0
        for sub in subscriptions:
            plan = plans.get(sub.plan_code)
            if not plan or plan.amount_cents is None or plan.amount_cents == 0:
                continue
            if plan.interval_months == 0:
                continue
            monthly = plan.amount_cents / 100.0 / plan.interval_months
            mrr += monthly
        return round(mrr, 2)

    def _build_timeseries(self, start: datetime, end: datetime, user_records, project_records, canceled_subs):
        labels: List[str] = []
        new_users: List[int] = []
        new_projects: List[int] = []
        churn: List[int] = []

        user_map = {}
        for row in user_records:
            created = row.get("created_at")
            if not created:
                continue
            key = created.date()
            user_map[key] = user_map.get(key, 0) + 1

        project_map = {}
        for row in project_records:
            created = row.get("created_at")
            if not created:
                continue
            key = created.date()
            project_map[key] = project_map.get(key, 0) + 1

        churn_map = {}
        for sub in canceled_subs:
            if not sub.updated_at:
                continue
            key = sub.updated_at.date()
            churn_map[key] = churn_map.get(key, 0) + 1

        cursor = start
        while cursor <= end:
            labels.append(cursor.strftime("%Y-%m-%d"))
            new_users.append(user_map.get(cursor.date(), 0))
            new_projects.append(project_map.get(cursor.date(), 0))
            churn.append(churn_map.get(cursor.date(), 0))
            cursor += timedelta(days=1)

        return {
            "labels": labels,
            "new_users": new_users,
            "new_projects": new_projects,
            "cancellations": churn,
        }

    def get_overview(self, range_key: str = "30d") -> Dict[str, Any]:
        days = self._resolve_days(range_key)
        end = datetime.utcnow()
        start = end - timedelta(days=days - 1)

        user_records = self.db.get_users_created_since(start)
        project_records = self.db.get_projects_created_since(start)
        subscriptions = self.db.list_user_subscriptions()
        active_subs = [s for s in subscriptions if s.status in ("active", "trialing")]
        canceled_subs = [s for s in subscriptions if s.status in ("canceled", "unpaid", "past_due") and s.updated_at and s.updated_at >= start]

        plans = self._plan_lookup()
        mrr = self._calculate_mrr(active_subs, plans)

        churn_rate = 0.0
        if active_subs:
            churn_rate = round((len(canceled_subs) / len(active_subs)) * 100, 2)

        timeseries = self._build_timeseries(start, end, user_records, project_records, canceled_subs)

        return {
            "range": range_key,
            "generated_at": end.isoformat(),
            "totals": {
                "active_users": self.db.count_total_users(),
                "new_projects": len(project_records),
                "active_subscriptions": len(active_subs),
                "mrr": mrr,
                "churn_rate": churn_rate,
            },
            "timeseries": timeseries,
        }


admin_metrics_service = AdminMetricsService()
