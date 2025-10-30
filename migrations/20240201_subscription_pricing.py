"""Migration script to normalize subscription pricing"""
from modules.database.models import db_manager


def drop_legacy_columns():
    conn = db_manager.get_connection()
    cur = conn.cursor()

    statements = []

    if db_manager.use_rds:
        if db_manager.is_postgres:
            statements.extend(
                [
                    "ALTER TABLE subscription_plans DROP COLUMN IF EXISTS price_monthly",
                    "ALTER TABLE subscription_plans DROP COLUMN IF EXISTS price_quarterly",
                ]
            )
        else:
            statements.extend(
                [
                    "ALTER TABLE subscription_plans DROP COLUMN IF EXISTS price_monthly",
                    "ALTER TABLE subscription_plans DROP COLUMN IF EXISTS price_quarterly",
                ]
            )
    else:
        statements.extend(
            [
                "ALTER TABLE subscription_plans DROP COLUMN price_monthly",
                "ALTER TABLE subscription_plans DROP COLUMN price_quarterly",
            ]
        )

    for statement in statements:
        try:
            cur.execute(statement)
            conn.commit()
            print(f"Executed: {statement}")
        except Exception as exc:
            print(f"Skipping '{statement}': {exc}")

    conn.close()


def main():
    print("Running subscription pricing migration...")
    drop_legacy_columns()
    print("Normalizing subscription schema...")
    db_manager.ensure_subscription_schema()
    db_manager.ensure_default_subscription_plans()
    print("✓ Migration complete. Plans normalized to semi-annual and annual options.")


if __name__ == "__main__":
    main()
