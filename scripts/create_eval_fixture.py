#!/usr/bin/env python3
"""
Create the TechMart Enterprise synthetic schema fixture for SQLens benchmarking.

Generates a 75-table SQLite database across 7 business domains with a realistic
mix of declared and implicit foreign key relationships (~40% declared, ~60% implicit).

Output: tests/evals/fixtures/techmart.db
"""

import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "tests" / "evals" / "fixtures" / "techmart.db"

# ---------------------------------------------------------------------------
# Schema DDL — 75 tables across 7 domains
# ---------------------------------------------------------------------------

TABLES_DDL: list[str] = []

# ===== DOMAIN: users (10 tables) ===========================================
TABLES_DDL += [
    # 1
    """CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        country_code TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )""",
    # 2
    """CREATE TABLE user_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        bio TEXT,
        avatar_url TEXT,
        updated_at TEXT
    )""",
    # 3
    """CREATE TABLE user_addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        street TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT,
        country TEXT,
        is_default INTEGER DEFAULT 0
    )""",
    # 4 — abbreviated usr_id, NO declared FK
    """CREATE TABLE user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usr_id INTEGER NOT NULL,
        pref_key TEXT NOT NULL,
        pref_value TEXT
    )""",
    # 5 — no declared FK
    """CREATE TABLE user_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_token TEXT NOT NULL,
        ip_address TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT
    )""",
    # 6 — no declared FK
    """CREATE TABLE login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        success INTEGER NOT NULL,
        ip_addr TEXT,
        attempted_at TEXT NOT NULL
    )""",
    # 7
    """CREATE TABLE auth_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        token_type TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    # 8
    """CREATE TABLE roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    )""",
    # 9
    """CREATE TABLE user_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        role_id INTEGER NOT NULL REFERENCES roles(id),
        assigned_at TEXT NOT NULL
    )""",
    # 10 — no declared FK
    """CREATE TABLE password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        reset_token TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT
    )""",
]

# ===== DOMAIN: products (12 tables) ========================================
TABLES_DDL += [
    # 11
    """CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        parent_id INTEGER,
        slug TEXT
    )""",
    # 12
    """CREATE TABLE brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        logo_url TEXT,
        country TEXT,
        founded_year INTEGER
    )""",
    # 13 — brand_id no FK
    """CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        category_id INTEGER REFERENCES categories(id),
        brand_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )""",
    # 14
    """CREATE TABLE product_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES products(id),
        sku TEXT NOT NULL UNIQUE,
        variant_name TEXT,
        price_delta REAL DEFAULT 0,
        stock_qty INTEGER DEFAULT 0
    )""",
    # 15 — self-ref parent_id already handled, no FK on category_hierarchy
    """CREATE TABLE category_hierarchy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ancestor_id INTEGER NOT NULL,
        descendant_id INTEGER NOT NULL,
        depth INTEGER NOT NULL
    )""",
    # 16 — no declared FK
    """CREATE TABLE product_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        image_url TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        is_primary INTEGER DEFAULT 0
    )""",
    # 17
    """CREATE TABLE tag_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE
    )""",
    # 18 — no declared FKs
    """CREATE TABLE product_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL
    )""",
    # 19
    """CREATE TABLE warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT,
        country TEXT,
        capacity INTEGER
    )""",
    # 20 — no declared FKs
    """CREATE TABLE inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_variant_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        qty INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    )""",
    # 21 — product_id no FK
    """CREATE TABLE warehouse_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
        product_id INTEGER NOT NULL,
        stock_level INTEGER DEFAULT 0,
        last_counted_at TEXT
    )""",
    # 22 — no declared FK
    """CREATE TABLE price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        old_price REAL NOT NULL,
        new_price REAL NOT NULL,
        changed_at TEXT NOT NULL
    )""",
]

# ===== DOMAIN: sales (11 tables) ===========================================
TABLES_DDL += [
    # 23 — abbreviated columns
    """CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'pending',
        total_amt REAL NOT NULL,
        shipping_amt REAL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    # 24 — product_id no FK, abbreviated
    """CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        product_id INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        unit_price REAL NOT NULL
    )""",
    # 25 — changed_by is user meaning, no FK
    """CREATE TABLE order_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        old_status TEXT,
        new_status TEXT NOT NULL,
        changed_at TEXT NOT NULL,
        changed_by INTEGER
    )""",
    # 26 — no declared FK
    """CREATE TABLE carts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT
    )""",
    # 27 — no declared FKs
    """CREATE TABLE cart_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cart_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        added_at TEXT NOT NULL
    )""",
    # 28 — no declared FK
    """CREATE TABLE wishlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT,
        created_at TEXT NOT NULL
    )""",
    # 29 — no declared FKs
    """CREATE TABLE wishlist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wishlist_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        added_at TEXT NOT NULL
    )""",
    # 30
    """CREATE TABLE returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'requested',
        requested_at TEXT NOT NULL
    )""",
    # 31 — order_item_id no FK
    """CREATE TABLE return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER NOT NULL REFERENCES returns(id),
        order_item_id INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        condition TEXT
    )""",
    # 32
    """CREATE TABLE coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        discount_pct REAL NOT NULL,
        valid_from TEXT,
        valid_until TEXT,
        is_active INTEGER DEFAULT 1,
        max_uses INTEGER
    )""",
    # 33 — order_id and user_id no FK
    """CREATE TABLE coupon_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        coupon_id INTEGER NOT NULL REFERENCES coupons(id),
        order_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        used_at TEXT NOT NULL
    )""",
]

# ===== DOMAIN: finance (10 tables) =========================================
TABLES_DDL += [
    # 34
    """CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id),
        method TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        processed_at TEXT
    )""",
    # 35
    """CREATE TABLE refunds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id INTEGER NOT NULL REFERENCES payments(id),
        amount REAL NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )""",
    # 36 — no declared FK, abbreviated
    """CREATE TABLE invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        invoice_number TEXT NOT NULL UNIQUE,
        total REAL NOT NULL,
        tax_amt REAL DEFAULT 0,
        issued_at TEXT NOT NULL
    )""",
    # 37
    """CREATE TABLE invoice_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        description TEXT NOT NULL,
        qty INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        line_total REAL NOT NULL
    )""",
    # 38 — no FKs
    """CREATE TABLE ledger_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_code TEXT NOT NULL,
        debit_amt REAL DEFAULT 0,
        credit_amt REAL DEFAULT 0,
        description TEXT,
        entry_date TEXT NOT NULL
    )""",
    # 39 — submitted_by is user FK by meaning
    """CREATE TABLE expense_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submitted_by INTEGER NOT NULL,
        department TEXT NOT NULL,
        total_amt REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        submitted_at TEXT NOT NULL
    )""",
    # 40
    """CREATE TABLE expense_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL REFERENCES expense_reports(id),
        description TEXT NOT NULL,
        amt REAL NOT NULL,
        receipt_url TEXT
    )""",
    # 41
    """CREATE TABLE tax_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT NOT NULL,
        region TEXT,
        rate_pct REAL NOT NULL,
        effective_from TEXT NOT NULL
    )""",
    # 42 — no declared FK
    """CREATE TABLE billing_addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        street TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        country TEXT
    )""",
    # 43
    """CREATE TABLE payment_methods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id),
        method_type TEXT NOT NULL,
        last_four TEXT,
        is_default INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
]

# ===== DOMAIN: marketing (10 tables) =======================================
TABLES_DDL += [
    # 44
    """CREATE TABLE campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        channel TEXT,
        budget_amt REAL,
        start_date TEXT,
        end_date TEXT,
        status TEXT NOT NULL DEFAULT 'draft'
    )""",
    # 45 — user_id no FK
    """CREATE TABLE campaign_clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
        user_id INTEGER,
        clicked_at TEXT NOT NULL,
        landing_url TEXT
    )""",
    # 46 — no declared FK
    """CREATE TABLE email_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        body_template TEXT,
        sent_count INTEGER DEFAULT 0
    )""",
    # 47 — no declared FKs
    """CREATE TABLE email_sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_campaign_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL,
        opened_at TEXT,
        clicked_at TEXT
    )""",
    # 48 — no declared FK
    """CREATE TABLE ad_impressions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        impressions INTEGER NOT NULL DEFAULT 0,
        clicks INTEGER NOT NULL DEFAULT 0,
        spend_amt REAL DEFAULT 0,
        recorded_date TEXT NOT NULL
    )""",
    # 49 — no declared FKs
    """CREATE TABLE conversion_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        campaign_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        revenue_amt REAL DEFAULT 0,
        converted_at TEXT NOT NULL
    )""",
    # 50
    """CREATE TABLE utm_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        created_at TEXT NOT NULL
    )""",
    # 51 — no declared FK
    """CREATE TABLE promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        campaign_id INTEGER,
        discount_pct REAL NOT NULL,
        max_redemptions INTEGER,
        active INTEGER DEFAULT 1
    )""",
    # 52
    """CREATE TABLE ab_test_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_name TEXT NOT NULL,
        variant_name TEXT NOT NULL,
        traffic_pct REAL,
        is_control INTEGER DEFAULT 0
    )""",
    # 53 — no declared FK
    """CREATE TABLE ab_test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        variant_id INTEGER NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        sample_size INTEGER,
        recorded_at TEXT NOT NULL
    )""",
]

# ===== DOMAIN: analytics (10 tables) =======================================
TABLES_DDL += [
    # 54 — no declared FKs
    """CREATE TABLE page_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        url TEXT NOT NULL,
        referrer TEXT,
        session_id INTEGER,
        viewed_at TEXT NOT NULL
    )""",
    # 55 — no declared FK
    """CREATE TABLE event_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_name TEXT NOT NULL,
        event_data TEXT,
        created_at TEXT NOT NULL
    )""",
    # 56 — session_id refers to user_sessions conceptually
    """CREATE TABLE session_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        metadata TEXT
    )""",
    # 57
    """CREATE TABLE funnel_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        funnel_name TEXT NOT NULL,
        step_order INTEGER NOT NULL,
        step_name TEXT NOT NULL,
        description TEXT
    )""",
    # 58 — no declared FKs
    """CREATE TABLE funnel_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        funnel_step_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        entered_at TEXT NOT NULL,
        completed_at TEXT
    )""",
    # 59
    """CREATE TABLE cohort_definitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        criteria TEXT,
        created_at TEXT NOT NULL
    )""",
    # 60 — user_id no FK
    """CREATE TABLE cohort_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cohort_id INTEGER NOT NULL REFERENCES cohort_definitions(id),
        user_id INTEGER NOT NULL,
        joined_at TEXT NOT NULL
    )""",
    # 61
    """CREATE TABLE metrics_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        dimension TEXT,
        recorded_date TEXT NOT NULL
    )""",
    # 62
    """CREATE TABLE metrics_weekly (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        dimension TEXT,
        week_start TEXT NOT NULL
    )""",
    # 63 — owner_id is user FK by meaning
    """CREATE TABLE dashboard_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        owner_id INTEGER,
        config_json TEXT,
        created_at TEXT NOT NULL
    )""",
]

# ===== DOMAIN: ops (8 tables) ==============================================

# We need 4 more tables to reach 75: 10+12+11+10+10+10+8 = 71. Actually
# let's count: 10+12+11+10+10+10+8 = 71. We need 4 more. The spec says 75
# tables across 7 domains with the counts given. Let me recount:
# users: 10, products: 12, sales: 11, finance: 10, marketing: 10,
# analytics: 10, ops: 8 => that's 71. We need 4 more to hit 75.
# I'll add 4 extra ops tables to round out to 75 (or adjust). Actually,
# re-reading the spec: the 7 domains sum to 71. The spec says "75 tables
# across 7 business domains". Let me add 4 more ops tables to reach 75.

TABLES_DDL += [
    # 64 — no declared FK
    """CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        created_at TEXT NOT NULL
    )""",
    # 65
    """CREATE TABLE error_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        error_type TEXT NOT NULL,
        message TEXT NOT NULL,
        stack_trace TEXT,
        occurred_at TEXT NOT NULL
    )""",
    # 66
    """CREATE TABLE system_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT NOT NULL,
        status TEXT NOT NULL,
        cpu_pct REAL,
        memory_pct REAL,
        checked_at TEXT NOT NULL
    )""",
    # 67
    """CREATE TABLE alert_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        condition TEXT NOT NULL,
        threshold REAL,
        channel TEXT,
        is_active INTEGER DEFAULT 1
    )""",
    # 68
    """CREATE TABLE alert_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id INTEGER NOT NULL REFERENCES alert_rules(id),
        triggered_at TEXT NOT NULL,
        resolved_at TEXT,
        severity TEXT NOT NULL DEFAULT 'warning'
    )""",
    # 69
    """CREATE TABLE feature_flags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flag_name TEXT NOT NULL UNIQUE,
        is_enabled INTEGER DEFAULT 0,
        rollout_pct REAL DEFAULT 0,
        updated_at TEXT
    )""",
    # 70 — updated_by is user FK by meaning
    """CREATE TABLE config_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT NOT NULL UNIQUE,
        setting_value TEXT,
        updated_at TEXT,
        updated_by INTEGER
    )""",
    # 71
    """CREATE TABLE migration_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version TEXT NOT NULL,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        rollback_at TEXT
    )""",
    # --- 4 additional ops tables to reach 75 ---
    # 72
    """CREATE TABLE scheduled_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_name TEXT NOT NULL,
        cron_expression TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        last_run_at TEXT,
        next_run_at TEXT,
        created_by INTEGER
    )""",
    # 73
    """CREATE TABLE job_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        error_message TEXT
    )""",
    # 74
    """CREATE TABLE notification_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        channel TEXT NOT NULL,
        subject TEXT,
        body_template TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    # 75
    """CREATE TABLE notification_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER,
        user_id INTEGER,
        channel TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        delivered INTEGER DEFAULT 0
    )""",
]

# ---------------------------------------------------------------------------
# Sample data inserts
# ---------------------------------------------------------------------------

INSERTS: list[str] = []

# --- DOMAIN: users ---------------------------------------------------------
INSERTS += [
    # users (5 core users + extras)
    """INSERT INTO users (email, first_name, last_name, country_code, is_active, created_at) VALUES
        ('alice.chen@example.com', 'Alice', 'Chen', 'US', 1, '2025-01-15 08:30:00'),
        ('bob.martinez@example.com', 'Bob', 'Martinez', 'US', 1, '2025-02-01 10:00:00'),
        ('carol.smith@example.com', 'Carol', 'Smith', 'GB', 1, '2025-02-20 14:22:00'),
        ('dave.jones@example.com', 'Dave', 'Jones', 'CA', 1, '2025-03-10 09:15:00'),
        ('eve.nguyen@example.com', 'Eve', 'Nguyen', 'AU', 1, '2025-03-25 16:45:00'),
        ('frank.weber@example.com', 'Frank', 'Weber', 'DE', 0, '2025-04-01 11:00:00'),
        ('grace.lee@example.com', 'Grace', 'Lee', 'KR', 1, '2025-04-12 07:30:00'),
        ('hank.patel@example.com', 'Hank', 'Patel', 'IN', 1, '2025-05-05 13:20:00'),
        ('iris.silva@example.com', 'Iris', 'Silva', 'BR', 1, '2025-05-18 10:10:00'),
        ('jack.tanaka@example.com', 'Jack', 'Tanaka', 'JP', 1, '2025-06-01 15:00:00')""",

    # user_profiles
    """INSERT INTO user_profiles (user_id, bio, avatar_url, updated_at) VALUES
        (1, 'Tech enthusiast and gadget lover', 'https://cdn.techmart.io/avatars/alice.jpg', '2025-01-15 09:00:00'),
        (2, 'DIY electronics hobbyist', 'https://cdn.techmart.io/avatars/bob.jpg', '2025-02-01 10:30:00'),
        (3, 'Professional photographer', 'https://cdn.techmart.io/avatars/carol.jpg', '2025-02-21 08:00:00'),
        (4, 'Software engineer by day, gamer by night', 'https://cdn.techmart.io/avatars/dave.jpg', '2025-03-10 09:30:00'),
        (5, 'Fitness tracker addict', 'https://cdn.techmart.io/avatars/eve.jpg', '2025-03-25 17:00:00')""",

    # user_addresses
    """INSERT INTO user_addresses (user_id, street, city, state, zip_code, country, is_default) VALUES
        (1, '123 Main St', 'San Francisco', 'CA', '94102', 'US', 1),
        (1, '456 Oak Ave', 'San Jose', 'CA', '95110', 'US', 0),
        (2, '789 Elm Blvd', 'Austin', 'TX', '73301', 'US', 1),
        (3, '10 King''s Road', 'London', NULL, 'SW1A 1AA', 'GB', 1),
        (4, '55 Maple Dr', 'Toronto', 'ON', 'M5V 2T6', 'CA', 1),
        (5, '42 Harbour St', 'Sydney', 'NSW', '2000', 'AU', 1)""",

    # user_preferences (abbreviated usr_id, no FK)
    """INSERT INTO user_preferences (usr_id, pref_key, pref_value) VALUES
        (1, 'theme', 'dark'),
        (1, 'notifications', 'email'),
        (2, 'theme', 'light'),
        (2, 'currency', 'USD'),
        (3, 'language', 'en-GB'),
        (3, 'theme', 'dark'),
        (4, 'notifications', 'push'),
        (5, 'currency', 'AUD'),
        (5, 'theme', 'auto')""",

    # user_sessions (no FK)
    """INSERT INTO user_sessions (user_id, session_token, ip_address, started_at, ended_at) VALUES
        (1, 'sess_abc123def456', '192.168.1.10', '2025-06-01 08:00:00', '2025-06-01 09:30:00'),
        (1, 'sess_ghi789jkl012', '192.168.1.10', '2025-06-02 10:00:00', NULL),
        (2, 'sess_mno345pqr678', '10.0.0.5', '2025-06-01 11:00:00', '2025-06-01 12:00:00'),
        (3, 'sess_stu901vwx234', '172.16.0.3', '2025-06-02 14:00:00', NULL),
        (4, 'sess_yza567bcd890', '192.168.2.20', '2025-06-03 09:00:00', '2025-06-03 11:00:00'),
        (5, 'sess_efg123hij456', '10.1.1.15', '2025-06-03 16:00:00', NULL)""",

    # login_attempts (no FK)
    """INSERT INTO login_attempts (user_id, success, ip_addr, attempted_at) VALUES
        (1, 1, '192.168.1.10', '2025-06-01 08:00:00'),
        (1, 1, '192.168.1.10', '2025-06-02 10:00:00'),
        (2, 0, '10.0.0.5', '2025-06-01 10:55:00'),
        (2, 1, '10.0.0.5', '2025-06-01 11:00:00'),
        (3, 1, '172.16.0.3', '2025-06-02 14:00:00'),
        (6, 0, '203.0.113.50', '2025-06-03 03:15:00'),
        (6, 0, '203.0.113.50', '2025-06-03 03:16:00')""",

    # auth_tokens
    """INSERT INTO auth_tokens (user_id, token_type, expires_at, created_at) VALUES
        (1, 'access', '2025-06-02 08:00:00', '2025-06-01 08:00:00'),
        (1, 'refresh', '2025-07-01 08:00:00', '2025-06-01 08:00:00'),
        (2, 'access', '2025-06-02 11:00:00', '2025-06-01 11:00:00'),
        (3, 'access', '2025-06-03 14:00:00', '2025-06-02 14:00:00'),
        (4, 'access', '2025-06-04 09:00:00', '2025-06-03 09:00:00'),
        (5, 'access', '2025-06-04 16:00:00', '2025-06-03 16:00:00')""",

    # roles
    """INSERT INTO roles (name, description) VALUES
        ('admin', 'Full system administrator'),
        ('customer', 'Standard customer account'),
        ('support', 'Customer support representative'),
        ('manager', 'Store manager'),
        ('analyst', 'Data analyst with read-only access')""",

    # user_roles
    """INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES
        (1, 2, '2025-01-15 08:30:00'),
        (2, 2, '2025-02-01 10:00:00'),
        (3, 2, '2025-02-20 14:22:00'),
        (4, 2, '2025-03-10 09:15:00'),
        (5, 2, '2025-03-25 16:45:00'),
        (7, 1, '2025-04-12 07:30:00'),
        (8, 3, '2025-05-05 13:20:00'),
        (9, 4, '2025-05-18 10:10:00'),
        (10, 5, '2025-06-01 15:00:00')""",

    # password_resets (no FK)
    """INSERT INTO password_resets (user_id, reset_token, expires_at, used_at) VALUES
        (2, 'rst_abc123', '2025-06-01 12:00:00', '2025-06-01 11:05:00'),
        (6, 'rst_def456', '2025-06-03 04:15:00', NULL),
        (3, 'rst_ghi789', '2025-05-15 10:00:00', '2025-05-15 09:30:00'),
        (1, 'rst_jkl012', '2025-04-20 18:00:00', '2025-04-20 17:45:00'),
        (5, 'rst_mno345', '2025-06-10 08:00:00', NULL)""",
]

# --- DOMAIN: products ------------------------------------------------------
INSERTS += [
    # categories
    """INSERT INTO categories (name, parent_id, slug) VALUES
        ('Electronics', NULL, 'electronics'),
        ('Computers', 1, 'computers'),
        ('Smartphones', 1, 'smartphones'),
        ('Audio', 1, 'audio'),
        ('Accessories', NULL, 'accessories'),
        ('Cables & Adapters', 5, 'cables-adapters'),
        ('Cases & Covers', 5, 'cases-covers'),
        ('Wearables', 1, 'wearables'),
        ('Gaming', NULL, 'gaming'),
        ('Home Office', NULL, 'home-office')""",

    # brands
    """INSERT INTO brands (name, logo_url, country, founded_year) VALUES
        ('TechPro', 'https://cdn.techmart.io/brands/techpro.png', 'US', 2010),
        ('SoundWave', 'https://cdn.techmart.io/brands/soundwave.png', 'JP', 2005),
        ('PixelCraft', 'https://cdn.techmart.io/brands/pixelcraft.png', 'KR', 2015),
        ('SwiftCharge', 'https://cdn.techmart.io/brands/swiftcharge.png', 'CN', 2018),
        ('ErgoDesk', 'https://cdn.techmart.io/brands/ergodesk.png', 'DE', 2012),
        ('GameForge', 'https://cdn.techmart.io/brands/gameforge.png', 'US', 2008)""",

    # products (brand_id no FK)
    """INSERT INTO products (name, price, category_id, brand_id, is_active, created_at) VALUES
        ('TechPro Laptop 15"', 1299.99, 2, 1, 1, '2025-01-01 00:00:00'),
        ('SoundWave Pro Headphones', 249.99, 4, 2, 1, '2025-01-10 00:00:00'),
        ('PixelCraft Ultra Phone', 899.99, 3, 3, 1, '2025-02-01 00:00:00'),
        ('SwiftCharge 65W Adapter', 39.99, 6, 4, 1, '2025-02-15 00:00:00'),
        ('ErgoDesk Standing Desk', 599.99, 10, 5, 1, '2025-03-01 00:00:00'),
        ('TechPro Wireless Mouse', 49.99, 5, 1, 1, '2025-03-10 00:00:00'),
        ('GameForge Controller', 69.99, 9, 6, 1, '2025-03-20 00:00:00'),
        ('SoundWave Earbuds', 129.99, 4, 2, 1, '2025-04-01 00:00:00'),
        ('PixelCraft Phone Case', 29.99, 7, 3, 1, '2025-04-10 00:00:00'),
        ('TechPro USB-C Hub', 79.99, 6, 1, 1, '2025-04-20 00:00:00'),
        ('SwiftCharge Power Bank', 59.99, 5, 4, 1, '2025-05-01 00:00:00'),
        ('GameForge Gaming Headset', 159.99, 9, 6, 1, '2025-05-15 00:00:00'),
        ('ErgoDesk Monitor Arm', 149.99, 10, 5, 1, '2025-05-20 00:00:00'),
        ('TechPro Smartwatch', 299.99, 8, 1, 1, '2025-06-01 00:00:00'),
        ('SoundWave Bluetooth Speaker', 89.99, 4, 2, 1, '2025-06-10 00:00:00')""",

    # product_variants
    """INSERT INTO product_variants (product_id, sku, variant_name, price_delta, stock_qty) VALUES
        (1, 'TP-LAP15-8G', '8GB RAM', 0, 50),
        (1, 'TP-LAP15-16G', '16GB RAM', 200.00, 30),
        (1, 'TP-LAP15-32G', '32GB RAM', 500.00, 10),
        (2, 'SW-HP-BLK', 'Black', 0, 100),
        (2, 'SW-HP-WHT', 'White', 0, 75),
        (3, 'PC-UP-128', '128GB', 0, 60),
        (3, 'PC-UP-256', '256GB', 100.00, 40),
        (5, 'ED-SD-NAT', 'Natural Wood', 0, 20),
        (5, 'ED-SD-BLK', 'Matte Black', 50.00, 15),
        (7, 'GF-CTR-BLK', 'Black', 0, 200),
        (7, 'GF-CTR-WHT', 'White', 0, 150),
        (14, 'TP-SW-42', '42mm', 0, 80),
        (14, 'TP-SW-46', '46mm', 30.00, 60)""",

    # category_hierarchy (no FKs)
    """INSERT INTO category_hierarchy (ancestor_id, descendant_id, depth) VALUES
        (1, 1, 0), (1, 2, 1), (1, 3, 1), (1, 4, 1), (1, 8, 1),
        (5, 5, 0), (5, 6, 1), (5, 7, 1),
        (9, 9, 0), (10, 10, 0),
        (2, 2, 0), (3, 3, 0), (4, 4, 0), (6, 6, 0), (7, 7, 0), (8, 8, 0)""",

    # product_images (no FK)
    """INSERT INTO product_images (product_id, image_url, sort_order, is_primary) VALUES
        (1, 'https://cdn.techmart.io/products/laptop-front.jpg', 1, 1),
        (1, 'https://cdn.techmart.io/products/laptop-side.jpg', 2, 0),
        (2, 'https://cdn.techmart.io/products/headphones-main.jpg', 1, 1),
        (3, 'https://cdn.techmart.io/products/phone-front.jpg', 1, 1),
        (3, 'https://cdn.techmart.io/products/phone-back.jpg', 2, 0),
        (5, 'https://cdn.techmart.io/products/desk-main.jpg', 1, 1),
        (7, 'https://cdn.techmart.io/products/controller-main.jpg', 1, 1),
        (14, 'https://cdn.techmart.io/products/smartwatch-main.jpg', 1, 1)""",

    # tag_definitions
    """INSERT INTO tag_definitions (name, slug) VALUES
        ('Bestseller', 'bestseller'),
        ('New Arrival', 'new-arrival'),
        ('Sale', 'sale'),
        ('Premium', 'premium'),
        ('Eco-Friendly', 'eco-friendly'),
        ('Limited Edition', 'limited-edition'),
        ('Staff Pick', 'staff-pick')""",

    # product_tags (no FKs)
    """INSERT INTO product_tags (product_id, tag_id) VALUES
        (1, 1), (1, 4), (2, 1), (2, 7), (3, 2), (3, 4),
        (5, 5), (7, 2), (8, 3), (14, 2), (14, 6), (15, 7)""",

    # warehouses
    """INSERT INTO warehouses (name, city, country, capacity) VALUES
        ('West Coast Hub', 'Los Angeles', 'US', 50000),
        ('East Coast Hub', 'New Jersey', 'US', 45000),
        ('EU Central', 'Frankfurt', 'DE', 30000),
        ('APAC Hub', 'Singapore', 'SG', 25000),
        ('UK Warehouse', 'Birmingham', 'GB', 20000)""",

    # inventory (no FKs)
    """INSERT INTO inventory (product_variant_id, warehouse_id, qty, updated_at) VALUES
        (1, 1, 25, '2025-06-01 06:00:00'),
        (1, 2, 20, '2025-06-01 06:00:00'),
        (2, 1, 15, '2025-06-01 06:00:00'),
        (3, 1, 5, '2025-06-01 06:00:00'),
        (4, 1, 40, '2025-06-01 06:00:00'),
        (4, 3, 30, '2025-06-01 06:00:00'),
        (6, 2, 35, '2025-06-01 06:00:00'),
        (7, 2, 20, '2025-06-01 06:00:00'),
        (8, 3, 10, '2025-06-01 06:00:00'),
        (10, 1, 100, '2025-06-01 06:00:00'),
        (12, 4, 40, '2025-06-01 06:00:00'),
        (13, 4, 30, '2025-06-01 06:00:00')""",

    # warehouse_inventory (product_id no FK)
    """INSERT INTO warehouse_inventory (warehouse_id, product_id, stock_level, last_counted_at) VALUES
        (1, 1, 45, '2025-06-01 07:00:00'),
        (1, 2, 40, '2025-06-01 07:00:00'),
        (1, 6, 60, '2025-06-01 07:00:00'),
        (2, 1, 20, '2025-06-01 07:00:00'),
        (2, 3, 55, '2025-06-01 07:00:00'),
        (3, 2, 30, '2025-06-01 07:00:00'),
        (3, 5, 10, '2025-06-01 07:00:00'),
        (4, 14, 70, '2025-06-01 07:00:00'),
        (5, 2, 25, '2025-06-01 07:00:00')""",

    # price_history (no FK)
    """INSERT INTO price_history (product_id, old_price, new_price, changed_at) VALUES
        (1, 1399.99, 1299.99, '2025-03-01 00:00:00'),
        (2, 279.99, 249.99, '2025-04-15 00:00:00'),
        (3, 949.99, 899.99, '2025-05-01 00:00:00'),
        (8, 149.99, 129.99, '2025-05-20 00:00:00'),
        (11, 69.99, 59.99, '2025-06-01 00:00:00'),
        (5, 649.99, 599.99, '2025-04-01 00:00:00')""",
]

# --- DOMAIN: sales ---------------------------------------------------------
INSERTS += [
    # orders
    """INSERT INTO orders (user_id, status, total_amt, shipping_amt, created_at) VALUES
        (1, 'delivered', 1499.99, 0.00, '2025-03-15 10:30:00'),
        (2, 'delivered', 289.98, 9.99, '2025-04-01 14:00:00'),
        (3, 'shipped', 899.99, 0.00, '2025-05-10 11:20:00'),
        (1, 'delivered', 129.98, 5.99, '2025-05-20 09:00:00'),
        (4, 'processing', 669.98, 0.00, '2025-06-01 16:30:00'),
        (5, 'pending', 299.99, 12.99, '2025-06-05 08:45:00'),
        (2, 'delivered', 79.99, 4.99, '2025-04-20 12:00:00'),
        (3, 'cancelled', 49.99, 5.99, '2025-05-25 15:30:00')""",

    # order_items (product_id no FK)
    """INSERT INTO order_items (order_id, product_id, qty, unit_price) VALUES
        (1, 1, 1, 1499.99),
        (2, 2, 1, 249.99),
        (2, 4, 1, 39.99),
        (3, 3, 1, 899.99),
        (4, 8, 1, 129.99),
        (5, 5, 1, 599.99),
        (5, 7, 1, 69.99),
        (6, 14, 1, 299.99),
        (7, 10, 1, 79.99),
        (8, 6, 1, 49.99)""",

    # order_status_history (changed_by no FK)
    """INSERT INTO order_status_history (order_id, old_status, new_status, changed_at, changed_by) VALUES
        (1, NULL, 'pending', '2025-03-15 10:30:00', NULL),
        (1, 'pending', 'processing', '2025-03-15 11:00:00', 8),
        (1, 'processing', 'shipped', '2025-03-16 09:00:00', 8),
        (1, 'shipped', 'delivered', '2025-03-19 14:00:00', NULL),
        (2, NULL, 'pending', '2025-04-01 14:00:00', NULL),
        (2, 'pending', 'processing', '2025-04-01 14:30:00', 8),
        (2, 'processing', 'delivered', '2025-04-04 10:00:00', NULL),
        (3, NULL, 'pending', '2025-05-10 11:20:00', NULL),
        (3, 'pending', 'shipped', '2025-05-11 08:00:00', 8),
        (5, NULL, 'pending', '2025-06-01 16:30:00', NULL),
        (5, 'pending', 'processing', '2025-06-02 09:00:00', 9),
        (8, NULL, 'pending', '2025-05-25 15:30:00', NULL),
        (8, 'pending', 'cancelled', '2025-05-26 10:00:00', 3)""",

    # carts (no FK)
    """INSERT INTO carts (user_id, created_at, updated_at) VALUES
        (1, '2025-06-05 10:00:00', '2025-06-05 10:15:00'),
        (2, '2025-06-04 09:00:00', '2025-06-04 09:30:00'),
        (4, '2025-06-06 14:00:00', NULL),
        (5, '2025-06-05 08:00:00', '2025-06-05 08:45:00'),
        (7, '2025-06-06 11:00:00', NULL)""",

    # cart_items (no FKs)
    """INSERT INTO cart_items (cart_id, product_id, qty, added_at) VALUES
        (1, 15, 1, '2025-06-05 10:05:00'),
        (1, 11, 2, '2025-06-05 10:10:00'),
        (2, 12, 1, '2025-06-04 09:10:00'),
        (3, 1, 1, '2025-06-06 14:05:00'),
        (4, 13, 1, '2025-06-05 08:30:00'),
        (5, 3, 1, '2025-06-06 11:05:00')""",

    # wishlists (no FK)
    """INSERT INTO wishlists (user_id, name, created_at) VALUES
        (1, 'My Wishlist', '2025-02-01 00:00:00'),
        (2, 'Gaming Setup', '2025-03-01 00:00:00'),
        (3, 'Photography Gear', '2025-03-15 00:00:00'),
        (5, 'Fitness Tech', '2025-04-01 00:00:00')""",

    # wishlist_items (no FKs)
    """INSERT INTO wishlist_items (wishlist_id, product_id, added_at) VALUES
        (1, 14, '2025-02-01 00:00:00'),
        (1, 5, '2025-02-15 00:00:00'),
        (2, 7, '2025-03-01 00:00:00'),
        (2, 12, '2025-03-05 00:00:00'),
        (3, 3, '2025-03-15 00:00:00'),
        (4, 14, '2025-04-01 00:00:00'),
        (4, 8, '2025-04-10 00:00:00')""",

    # returns
    """INSERT INTO returns (order_id, reason, status, requested_at) VALUES
        (2, 'Defective earbud cushion', 'approved', '2025-04-10 09:00:00'),
        (4, 'Changed mind', 'denied', '2025-05-25 11:00:00'),
        (7, 'Wrong item received', 'completed', '2025-04-25 14:00:00')""",

    # return_items (order_item_id no FK)
    """INSERT INTO return_items (return_id, order_item_id, qty, condition) VALUES
        (1, 2, 1, 'defective'),
        (2, 5, 1, 'like_new'),
        (3, 9, 1, 'unopened')""",

    # coupons
    """INSERT INTO coupons (code, discount_pct, valid_from, valid_until, is_active, max_uses) VALUES
        ('WELCOME10', 10.0, '2025-01-01', '2025-12-31', 1, 1000),
        ('SUMMER20', 20.0, '2025-06-01', '2025-08-31', 1, 500),
        ('VIP30', 30.0, '2025-01-01', '2025-12-31', 1, 50),
        ('FLASH15', 15.0, '2025-05-01', '2025-05-07', 0, 200),
        ('HOLIDAY25', 25.0, '2025-12-01', '2025-12-31', 1, 300)""",

    # coupon_usage (order_id and user_id no FK)
    """INSERT INTO coupon_usage (coupon_id, order_id, user_id, used_at) VALUES
        (1, 1, 1, '2025-03-15 10:30:00'),
        (1, 2, 2, '2025-04-01 14:00:00'),
        (4, 4, 1, '2025-05-20 09:00:00'),
        (1, 5, 4, '2025-06-01 16:30:00'),
        (2, 6, 5, '2025-06-05 08:45:00')""",
]

# --- DOMAIN: finance -------------------------------------------------------
INSERTS += [
    # payments
    """INSERT INTO payments (order_id, method, amount, status, processed_at) VALUES
        (1, 'credit_card', 1499.99, 'completed', '2025-03-15 10:31:00'),
        (2, 'credit_card', 289.98, 'completed', '2025-04-01 14:01:00'),
        (3, 'paypal', 899.99, 'completed', '2025-05-10 11:21:00'),
        (4, 'credit_card', 129.98, 'completed', '2025-05-20 09:01:00'),
        (5, 'debit_card', 669.98, 'completed', '2025-06-01 16:31:00'),
        (6, 'credit_card', 299.99, 'pending', NULL),
        (7, 'credit_card', 79.99, 'completed', '2025-04-20 12:01:00'),
        (8, 'paypal', 49.99, 'refunded', '2025-05-25 15:31:00')""",

    # refunds
    """INSERT INTO refunds (payment_id, amount, reason, status, created_at) VALUES
        (2, 249.99, 'Defective item returned', 'completed', '2025-04-12 10:00:00'),
        (8, 49.99, 'Order cancelled', 'completed', '2025-05-26 11:00:00'),
        (7, 79.99, 'Wrong item shipped', 'completed', '2025-04-27 09:00:00')""",

    # invoices (no FK)
    """INSERT INTO invoices (order_id, invoice_number, total, tax_amt, issued_at) VALUES
        (1, 'INV-2025-0001', 1499.99, 127.50, '2025-03-15 10:31:00'),
        (2, 'INV-2025-0002', 289.98, 24.65, '2025-04-01 14:01:00'),
        (3, 'INV-2025-0003', 899.99, 76.50, '2025-05-10 11:21:00'),
        (4, 'INV-2025-0004', 129.98, 11.05, '2025-05-20 09:01:00'),
        (5, 'INV-2025-0005', 669.98, 56.95, '2025-06-01 16:31:00'),
        (7, 'INV-2025-0006', 79.99, 6.80, '2025-04-20 12:01:00')""",

    # invoice_lines
    """INSERT INTO invoice_lines (invoice_id, description, qty, unit_price, line_total) VALUES
        (1, 'TechPro Laptop 15" - 16GB RAM', 1, 1499.99, 1499.99),
        (2, 'SoundWave Pro Headphones - Black', 1, 249.99, 249.99),
        (2, 'SwiftCharge 65W Adapter', 1, 39.99, 39.99),
        (3, 'PixelCraft Ultra Phone - 256GB', 1, 899.99, 899.99),
        (4, 'SoundWave Earbuds', 1, 129.99, 129.99),
        (5, 'ErgoDesk Standing Desk - Matte Black', 1, 599.99, 599.99),
        (5, 'GameForge Controller - Black', 1, 69.99, 69.99),
        (6, 'TechPro USB-C Hub', 1, 79.99, 79.99)""",

    # ledger_entries (no FKs)
    """INSERT INTO ledger_entries (account_code, debit_amt, credit_amt, description, entry_date) VALUES
        ('4000', 1499.99, 0, 'Sale - Order 1', '2025-03-15'),
        ('1200', 0, 1499.99, 'AR - Order 1', '2025-03-15'),
        ('4000', 289.98, 0, 'Sale - Order 2', '2025-04-01'),
        ('5000', 0, 249.99, 'Refund - Order 2 item', '2025-04-12'),
        ('4000', 899.99, 0, 'Sale - Order 3', '2025-05-10'),
        ('4000', 129.98, 0, 'Sale - Order 4', '2025-05-20'),
        ('4000', 669.98, 0, 'Sale - Order 5', '2025-06-01'),
        ('6000', 1200.00, 0, 'Marketing expense - Q2', '2025-06-01'),
        ('7000', 3500.00, 0, 'Warehouse rent - June', '2025-06-01')""",

    # expense_reports (submitted_by = user FK by meaning)
    """INSERT INTO expense_reports (submitted_by, department, total_amt, status, submitted_at) VALUES
        (8, 'Support', 250.00, 'approved', '2025-05-15 10:00:00'),
        (9, 'Operations', 1200.00, 'pending', '2025-06-01 14:00:00'),
        (7, 'Engineering', 450.00, 'approved', '2025-05-20 11:00:00'),
        (10, 'Analytics', 180.00, 'rejected', '2025-06-03 09:00:00')""",

    # expense_items
    """INSERT INTO expense_items (report_id, description, amt, receipt_url) VALUES
        (1, 'Customer support software license', 150.00, 'https://receipts.techmart.io/r/001.pdf'),
        (1, 'Headset for support calls', 100.00, 'https://receipts.techmart.io/r/002.pdf'),
        (2, 'Warehouse shelving units', 800.00, 'https://receipts.techmart.io/r/003.pdf'),
        (2, 'Packing supplies', 400.00, 'https://receipts.techmart.io/r/004.pdf'),
        (3, 'Cloud hosting overage', 300.00, 'https://receipts.techmart.io/r/005.pdf'),
        (3, 'Development tools subscription', 150.00, 'https://receipts.techmart.io/r/006.pdf'),
        (4, 'Analytics dashboard addon', 180.00, 'https://receipts.techmart.io/r/007.pdf')""",

    # tax_rates
    """INSERT INTO tax_rates (country, region, rate_pct, effective_from) VALUES
        ('US', 'CA', 8.5, '2025-01-01'),
        ('US', 'TX', 6.25, '2025-01-01'),
        ('US', 'NY', 8.0, '2025-01-01'),
        ('GB', NULL, 20.0, '2025-01-01'),
        ('DE', NULL, 19.0, '2025-01-01'),
        ('AU', NULL, 10.0, '2025-01-01'),
        ('CA', 'ON', 13.0, '2025-01-01'),
        ('JP', NULL, 10.0, '2025-01-01')""",

    # billing_addresses (no FK)
    """INSERT INTO billing_addresses (user_id, street, city, state, zip, country) VALUES
        (1, '123 Main St', 'San Francisco', 'CA', '94102', 'US'),
        (2, '789 Elm Blvd', 'Austin', 'TX', '73301', 'US'),
        (3, '10 King''s Road', 'London', NULL, 'SW1A 1AA', 'GB'),
        (4, '55 Maple Dr', 'Toronto', 'ON', 'M5V 2T6', 'CA'),
        (5, '42 Harbour St', 'Sydney', 'NSW', '2000', 'AU')""",

    # payment_methods
    """INSERT INTO payment_methods (user_id, method_type, last_four, is_default, created_at) VALUES
        (1, 'visa', '4242', 1, '2025-01-15 08:30:00'),
        (1, 'mastercard', '5555', 0, '2025-03-01 10:00:00'),
        (2, 'visa', '1234', 1, '2025-02-01 10:00:00'),
        (3, 'paypal', NULL, 1, '2025-02-20 14:22:00'),
        (4, 'visa', '9876', 1, '2025-03-10 09:15:00'),
        (5, 'mastercard', '4321', 1, '2025-03-25 16:45:00')""",
]

# --- DOMAIN: marketing -----------------------------------------------------
INSERTS += [
    # campaigns
    """INSERT INTO campaigns (name, channel, budget_amt, start_date, end_date, status) VALUES
        ('Spring Launch 2025', 'social', 15000.00, '2025-03-01', '2025-04-30', 'completed'),
        ('Summer Sale', 'email', 8000.00, '2025-06-01', '2025-08-31', 'active'),
        ('Back to School', 'search', 12000.00, '2025-08-01', '2025-09-15', 'draft'),
        ('Holiday Blitz', 'multi', 25000.00, '2025-11-15', '2025-12-31', 'draft'),
        ('Product Launch - Smartwatch', 'social', 10000.00, '2025-05-25', '2025-06-30', 'active'),
        ('Referral Program', 'referral', 5000.00, '2025-01-01', '2025-12-31', 'active')""",

    # campaign_clicks (user_id no FK)
    """INSERT INTO campaign_clicks (campaign_id, user_id, clicked_at, landing_url) VALUES
        (1, 1, '2025-03-10 14:22:00', 'https://techmart.io/spring-sale'),
        (1, 3, '2025-03-12 09:15:00', 'https://techmart.io/spring-sale'),
        (1, NULL, '2025-03-15 16:30:00', 'https://techmart.io/spring-sale'),
        (2, 2, '2025-06-02 10:00:00', 'https://techmart.io/summer-deals'),
        (2, 5, '2025-06-03 11:30:00', 'https://techmart.io/summer-deals'),
        (5, 1, '2025-05-28 08:00:00', 'https://techmart.io/smartwatch-launch'),
        (5, 4, '2025-06-01 13:00:00', 'https://techmart.io/smartwatch-launch'),
        (6, 2, '2025-04-15 10:00:00', 'https://techmart.io/refer-a-friend')""",

    # email_campaigns (no FK)
    """INSERT INTO email_campaigns (campaign_id, subject, body_template, sent_count) VALUES
        (1, 'Spring is Here! New Tech Arrivals', '<html>Spring collection...</html>', 5000),
        (2, 'Hot Summer Deals - Up to 30% Off', '<html>Summer sale...</html>', 8000),
        (2, 'Last Chance: Summer Sale Ends Soon', '<html>Final days...</html>', 7500),
        (5, 'Introducing the TechPro Smartwatch', '<html>Smartwatch launch...</html>', 3000),
        (6, 'Share the Love, Earn Rewards', '<html>Referral program...</html>', 10000)""",

    # email_sends (no FKs)
    """INSERT INTO email_sends (email_campaign_id, user_id, sent_at, opened_at, clicked_at) VALUES
        (1, 1, '2025-03-05 08:00:00', '2025-03-05 10:30:00', '2025-03-05 10:35:00'),
        (1, 2, '2025-03-05 08:00:00', '2025-03-05 14:00:00', NULL),
        (1, 3, '2025-03-05 08:00:00', NULL, NULL),
        (2, 1, '2025-06-01 08:00:00', '2025-06-01 09:00:00', '2025-06-01 09:05:00'),
        (2, 4, '2025-06-01 08:00:00', '2025-06-01 12:00:00', '2025-06-01 12:10:00'),
        (2, 5, '2025-06-01 08:00:00', '2025-06-01 16:00:00', NULL),
        (4, 1, '2025-05-28 08:00:00', '2025-05-28 08:30:00', '2025-05-28 08:35:00'),
        (4, 5, '2025-05-28 08:00:00', '2025-05-28 10:00:00', '2025-05-28 10:05:00'),
        (5, 2, '2025-04-01 08:00:00', '2025-04-01 11:00:00', NULL),
        (5, 3, '2025-04-01 08:00:00', NULL, NULL)""",

    # ad_impressions (no FK)
    """INSERT INTO ad_impressions (campaign_id, platform, impressions, clicks, spend_amt, recorded_date) VALUES
        (1, 'facebook', 150000, 4500, 3000.00, '2025-03-15'),
        (1, 'instagram', 120000, 3600, 2500.00, '2025-03-15'),
        (1, 'twitter', 80000, 1600, 1500.00, '2025-03-15'),
        (2, 'facebook', 200000, 6000, 4000.00, '2025-06-05'),
        (2, 'google', 180000, 5400, 3500.00, '2025-06-05'),
        (5, 'instagram', 95000, 3800, 2000.00, '2025-06-01'),
        (5, 'tiktok', 250000, 7500, 3000.00, '2025-06-01')""",

    # conversion_events (no FKs)
    """INSERT INTO conversion_events (user_id, campaign_id, event_type, revenue_amt, converted_at) VALUES
        (1, 1, 'purchase', 1499.99, '2025-03-15 10:30:00'),
        (2, 1, 'purchase', 289.98, '2025-04-01 14:00:00'),
        (3, 5, 'signup', 0, '2025-05-08 11:00:00'),
        (4, 5, 'purchase', 669.98, '2025-06-01 16:30:00'),
        (5, 2, 'purchase', 299.99, '2025-06-05 08:45:00'),
        (2, 6, 'referral', 0, '2025-04-15 10:00:00')""",

    # utm_tracking
    """INSERT INTO utm_tracking (url, utm_source, utm_medium, utm_campaign, created_at) VALUES
        ('https://techmart.io/spring-sale', 'facebook', 'cpc', 'spring_launch_2025', '2025-03-01 00:00:00'),
        ('https://techmart.io/spring-sale', 'instagram', 'social', 'spring_launch_2025', '2025-03-01 00:00:00'),
        ('https://techmart.io/summer-deals', 'google', 'cpc', 'summer_sale', '2025-06-01 00:00:00'),
        ('https://techmart.io/summer-deals', 'email', 'newsletter', 'summer_sale', '2025-06-01 00:00:00'),
        ('https://techmart.io/smartwatch-launch', 'instagram', 'social', 'smartwatch_launch', '2025-05-25 00:00:00'),
        ('https://techmart.io/refer-a-friend', 'direct', 'referral', 'referral_program', '2025-01-01 00:00:00')""",

    # promo_codes (no FK)
    """INSERT INTO promo_codes (code, campaign_id, discount_pct, max_redemptions, active) VALUES
        ('SPRING15', 1, 15.0, 200, 0),
        ('SUM25', 2, 25.0, 100, 1),
        ('WATCH10', 5, 10.0, 500, 1),
        ('FRIEND20', 6, 20.0, 1000, 1),
        ('FLASH50', NULL, 50.0, 10, 0)""",

    # ab_test_variants
    """INSERT INTO ab_test_variants (test_name, variant_name, traffic_pct, is_control) VALUES
        ('checkout_flow', 'control', 50.0, 1),
        ('checkout_flow', 'single_page', 50.0, 0),
        ('product_page_layout', 'control', 33.3, 1),
        ('product_page_layout', 'gallery_first', 33.3, 0),
        ('product_page_layout', 'reviews_first', 33.4, 0),
        ('pricing_display', 'control', 50.0, 1),
        ('pricing_display', 'savings_highlight', 50.0, 0)""",

    # ab_test_results (no FK)
    """INSERT INTO ab_test_results (variant_id, metric_name, metric_value, sample_size, recorded_at) VALUES
        (1, 'conversion_rate', 3.2, 15000, '2025-06-01'),
        (2, 'conversion_rate', 4.1, 15000, '2025-06-01'),
        (1, 'avg_order_value', 185.50, 15000, '2025-06-01'),
        (2, 'avg_order_value', 192.30, 15000, '2025-06-01'),
        (3, 'time_on_page', 45.2, 10000, '2025-06-01'),
        (4, 'time_on_page', 52.8, 10000, '2025-06-01'),
        (5, 'time_on_page', 48.1, 10000, '2025-06-01'),
        (6, 'click_through_rate', 12.5, 8000, '2025-06-01'),
        (7, 'click_through_rate', 15.8, 8000, '2025-06-01')""",
]

# --- DOMAIN: analytics -----------------------------------------------------
INSERTS += [
    # page_views (no FKs)
    """INSERT INTO page_views (user_id, url, referrer, session_id, viewed_at) VALUES
        (1, '/', 'https://google.com', 1, '2025-06-01 08:00:00'),
        (1, '/products/1', '/', 1, '2025-06-01 08:02:00'),
        (1, '/cart', '/products/1', 1, '2025-06-01 08:05:00'),
        (2, '/', 'https://facebook.com', 3, '2025-06-01 11:00:00'),
        (2, '/products/2', '/', 3, '2025-06-01 11:03:00'),
        (3, '/', NULL, 4, '2025-06-02 14:00:00'),
        (3, '/categories/electronics', '/', 4, '2025-06-02 14:01:00'),
        (4, '/products/5', 'https://instagram.com', 5, '2025-06-03 09:00:00'),
        (5, '/', 'https://techmart.io/summer-deals', 6, '2025-06-03 16:00:00'),
        (5, '/products/14', '/', 6, '2025-06-03 16:02:00'),
        (NULL, '/', 'https://google.com', NULL, '2025-06-04 10:00:00'),
        (NULL, '/about', '/', NULL, '2025-06-04 10:01:00')""",

    # event_tracking (no FK)
    """INSERT INTO event_tracking (user_id, event_name, event_data, created_at) VALUES
        (1, 'add_to_cart', '{"product_id": 15, "qty": 1}', '2025-06-05 10:05:00'),
        (1, 'add_to_cart', '{"product_id": 11, "qty": 2}', '2025-06-05 10:10:00'),
        (2, 'search', '{"query": "gaming headset"}', '2025-06-04 09:05:00'),
        (2, 'add_to_cart', '{"product_id": 12, "qty": 1}', '2025-06-04 09:10:00'),
        (4, 'product_view', '{"product_id": 1}', '2025-06-06 14:03:00'),
        (5, 'wishlist_add', '{"product_id": 14}', '2025-06-05 08:30:00'),
        (NULL, 'page_error', '{"url": "/checkout", "code": 500}', '2025-06-04 22:00:00')""",

    # session_events
    """INSERT INTO session_events (session_id, event_type, timestamp, metadata) VALUES
        (1, 'page_view', '2025-06-01 08:00:00', '{"url": "/"}'),
        (1, 'click', '2025-06-01 08:02:00', '{"element": "product_card"}'),
        (1, 'page_view', '2025-06-01 08:02:01', '{"url": "/products/1"}'),
        (3, 'page_view', '2025-06-01 11:00:00', '{"url": "/"}'),
        (3, 'search', '2025-06-01 11:01:00', '{"query": "headphones"}'),
        (4, 'page_view', '2025-06-02 14:00:00', '{"url": "/"}'),
        (5, 'page_view', '2025-06-03 09:00:00', '{"url": "/products/5"}'),
        (6, 'page_view', '2025-06-03 16:00:00', '{"url": "/"}'),
        (6, 'click', '2025-06-03 16:02:00', '{"element": "promo_banner"}')""",

    # funnel_steps
    """INSERT INTO funnel_steps (funnel_name, step_order, step_name, description) VALUES
        ('purchase', 1, 'visit', 'User visits the site'),
        ('purchase', 2, 'product_view', 'User views a product page'),
        ('purchase', 3, 'add_to_cart', 'User adds item to cart'),
        ('purchase', 4, 'checkout', 'User begins checkout'),
        ('purchase', 5, 'payment', 'User completes payment'),
        ('signup', 1, 'landing', 'User hits landing page'),
        ('signup', 2, 'form_start', 'User starts signup form'),
        ('signup', 3, 'form_complete', 'User submits signup form'),
        ('signup', 4, 'email_verify', 'User verifies email')""",

    # funnel_progress (no FKs)
    """INSERT INTO funnel_progress (funnel_step_id, user_id, entered_at, completed_at) VALUES
        (1, 1, '2025-06-01 08:00:00', '2025-06-01 08:00:01'),
        (2, 1, '2025-06-01 08:02:00', '2025-06-01 08:02:01'),
        (3, 1, '2025-06-01 08:05:00', '2025-06-01 08:05:01'),
        (1, 2, '2025-06-01 11:00:00', '2025-06-01 11:00:01'),
        (2, 2, '2025-06-01 11:03:00', '2025-06-01 11:03:01'),
        (1, 4, '2025-06-03 09:00:00', '2025-06-03 09:00:01'),
        (2, 4, '2025-06-03 09:01:00', '2025-06-03 09:01:01'),
        (3, 4, '2025-06-03 09:05:00', NULL),
        (6, 7, '2025-04-12 07:00:00', '2025-04-12 07:00:01'),
        (7, 7, '2025-04-12 07:01:00', '2025-04-12 07:05:00'),
        (8, 7, '2025-04-12 07:05:00', '2025-04-12 07:06:00'),
        (9, 7, '2025-04-12 07:10:00', '2025-04-12 07:15:00')""",

    # cohort_definitions
    """INSERT INTO cohort_definitions (name, criteria, created_at) VALUES
        ('Early Adopters', 'signup_date < 2025-02-01', '2025-03-01 00:00:00'),
        ('High Spenders', 'total_spend > 500', '2025-04-01 00:00:00'),
        ('Inactive 30d', 'last_active < now() - 30d', '2025-05-01 00:00:00'),
        ('Mobile Users', 'primary_device = mobile', '2025-05-15 00:00:00'),
        ('Repeat Buyers', 'order_count >= 2', '2025-06-01 00:00:00')""",

    # cohort_members (user_id no FK)
    """INSERT INTO cohort_members (cohort_id, user_id, joined_at) VALUES
        (1, 1, '2025-03-01 00:00:00'),
        (1, 2, '2025-03-01 00:00:00'),
        (2, 1, '2025-04-01 00:00:00'),
        (2, 4, '2025-06-02 00:00:00'),
        (3, 6, '2025-06-01 00:00:00'),
        (4, 3, '2025-05-15 00:00:00'),
        (4, 5, '2025-05-15 00:00:00'),
        (5, 1, '2025-06-01 00:00:00'),
        (5, 2, '2025-06-01 00:00:00')""",

    # metrics_daily
    """INSERT INTO metrics_daily (metric_name, metric_value, dimension, recorded_date) VALUES
        ('revenue', 1499.99, 'total', '2025-03-15'),
        ('revenue', 289.98, 'total', '2025-04-01'),
        ('orders', 1, 'count', '2025-03-15'),
        ('orders', 1, 'count', '2025-04-01'),
        ('active_users', 45, 'dau', '2025-06-01'),
        ('active_users', 52, 'dau', '2025-06-02'),
        ('active_users', 48, 'dau', '2025-06-03'),
        ('page_views', 1250, 'total', '2025-06-01'),
        ('page_views', 1380, 'total', '2025-06-02'),
        ('conversion_rate', 3.5, 'pct', '2025-06-01')""",

    # metrics_weekly
    """INSERT INTO metrics_weekly (metric_name, metric_value, dimension, week_start) VALUES
        ('revenue', 4589.93, 'total', '2025-03-10'),
        ('revenue', 1009.96, 'total', '2025-04-14'),
        ('revenue', 1699.96, 'total', '2025-05-19'),
        ('orders', 3, 'count', '2025-03-10'),
        ('orders', 3, 'count', '2025-04-14'),
        ('new_users', 12, 'count', '2025-06-02'),
        ('churn_rate', 2.1, 'pct', '2025-06-02'),
        ('avg_session_duration', 8.5, 'minutes', '2025-06-02')""",

    # dashboard_configs (owner_id = user FK by meaning)
    """INSERT INTO dashboard_configs (name, owner_id, config_json, created_at) VALUES
        ('Executive Overview', 7, '{"widgets": ["revenue_chart", "order_funnel", "user_growth"]}', '2025-04-01 00:00:00'),
        ('Marketing Dashboard', 9, '{"widgets": ["campaign_roi", "conversion_funnel", "channel_mix"]}', '2025-05-01 00:00:00'),
        ('Support Metrics', 8, '{"widgets": ["ticket_volume", "response_time", "satisfaction"]}', '2025-05-15 00:00:00'),
        ('Product Analytics', 10, '{"widgets": ["top_products", "inventory_levels", "price_trends"]}', '2025-06-01 00:00:00'),
        ('My Sales View', 1, '{"widgets": ["my_orders", "spending_history"]}', '2025-06-05 00:00:00')""",
]

# --- DOMAIN: ops -----------------------------------------------------------
INSERTS += [
    # audit_log (no FK)
    """INSERT INTO audit_log (user_id, action, entity_type, entity_id, created_at) VALUES
        (7, 'create', 'product', 14, '2025-06-01 00:00:00'),
        (7, 'update', 'product', 8, '2025-05-20 00:00:00'),
        (9, 'update', 'order', 5, '2025-06-02 09:00:00'),
        (8, 'update', 'order', 8, '2025-05-26 10:00:00'),
        (7, 'delete', 'coupon', 4, '2025-05-08 00:00:00'),
        (1, 'update', 'user_profile', 1, '2025-06-01 09:00:00'),
        (9, 'create', 'campaign', 5, '2025-05-25 00:00:00'),
        (10, 'create', 'dashboard_config', 4, '2025-06-01 00:00:00')""",

    # error_log
    """INSERT INTO error_log (error_type, message, stack_trace, occurred_at) VALUES
        ('DatabaseError', 'Connection pool exhausted', 'Traceback: ...pool.py:120...', '2025-06-01 02:30:00'),
        ('ValidationError', 'Invalid email format', 'Traceback: ...validators.py:45...', '2025-06-02 11:00:00'),
        ('TimeoutError', 'Payment gateway timeout', 'Traceback: ...payments.py:89...', '2025-06-03 14:30:00'),
        ('NotFoundError', 'Product not found: id=999', 'Traceback: ...products.py:23...', '2025-06-04 09:15:00'),
        ('AuthError', 'Invalid refresh token', 'Traceback: ...auth.py:67...', '2025-06-04 22:00:00'),
        ('RateLimitError', 'API rate limit exceeded', 'Traceback: ...middleware.py:34...', '2025-06-05 03:00:00')""",

    # system_health
    """INSERT INTO system_health (service_name, status, cpu_pct, memory_pct, checked_at) VALUES
        ('api-gateway', 'healthy', 35.2, 62.1, '2025-06-05 12:00:00'),
        ('order-service', 'healthy', 28.7, 55.3, '2025-06-05 12:00:00'),
        ('payment-service', 'degraded', 78.4, 85.2, '2025-06-05 12:00:00'),
        ('search-service', 'healthy', 42.1, 48.9, '2025-06-05 12:00:00'),
        ('email-service', 'healthy', 15.3, 32.7, '2025-06-05 12:00:00'),
        ('analytics-worker', 'healthy', 55.8, 71.4, '2025-06-05 12:00:00'),
        ('cache-service', 'healthy', 12.1, 88.5, '2025-06-05 12:00:00')""",

    # alert_rules
    """INSERT INTO alert_rules (name, condition, threshold, channel, is_active) VALUES
        ('High CPU', 'cpu_pct > threshold', 80.0, 'slack', 1),
        ('High Memory', 'memory_pct > threshold', 90.0, 'slack', 1),
        ('Error Rate Spike', 'error_rate > threshold', 5.0, 'pagerduty', 1),
        ('Payment Failures', 'payment_fail_rate > threshold', 2.0, 'pagerduty', 1),
        ('Low Inventory', 'stock_qty < threshold', 10.0, 'email', 1),
        ('Service Down', 'status == unhealthy', 1.0, 'pagerduty', 1)""",

    # alert_history
    """INSERT INTO alert_history (rule_id, triggered_at, resolved_at, severity) VALUES
        (1, '2025-06-05 12:05:00', '2025-06-05 12:30:00', 'warning'),
        (3, '2025-06-01 02:30:00', '2025-06-01 03:00:00', 'critical'),
        (4, '2025-06-03 14:30:00', '2025-06-03 15:00:00', 'critical'),
        (5, '2025-06-01 07:00:00', NULL, 'info'),
        (2, '2025-05-28 18:00:00', '2025-05-28 18:15:00', 'warning')""",

    # feature_flags
    """INSERT INTO feature_flags (flag_name, is_enabled, rollout_pct, updated_at) VALUES
        ('new_checkout_flow', 1, 50.0, '2025-06-01 00:00:00'),
        ('dark_mode', 1, 100.0, '2025-05-01 00:00:00'),
        ('ai_recommendations', 1, 25.0, '2025-06-03 00:00:00'),
        ('one_click_buy', 0, 0.0, '2025-05-15 00:00:00'),
        ('social_login', 1, 100.0, '2025-04-01 00:00:00'),
        ('loyalty_points', 1, 10.0, '2025-06-05 00:00:00')""",

    # config_settings (updated_by = user FK by meaning)
    """INSERT INTO config_settings (setting_key, setting_value, updated_at, updated_by) VALUES
        ('site_name', 'TechMart', '2025-01-01 00:00:00', 7),
        ('maintenance_mode', 'false', '2025-06-01 00:00:00', 7),
        ('max_cart_items', '50', '2025-03-01 00:00:00', 7),
        ('default_currency', 'USD', '2025-01-01 00:00:00', 7),
        ('support_email', 'support@techmart.io', '2025-01-01 00:00:00', 8),
        ('analytics_enabled', 'true', '2025-02-01 00:00:00', 10),
        ('tax_calculation', 'automatic', '2025-04-01 00:00:00', 9)""",

    # migration_history
    """INSERT INTO migration_history (version, name, applied_at, rollback_at) VALUES
        ('001', 'initial_schema', '2025-01-01 00:00:00', NULL),
        ('002', 'add_user_profiles', '2025-01-15 00:00:00', NULL),
        ('003', 'add_product_variants', '2025-02-01 00:00:00', NULL),
        ('004', 'add_analytics_tables', '2025-03-01 00:00:00', NULL),
        ('005', 'add_marketing_tables', '2025-04-01 00:00:00', NULL),
        ('006', 'add_expense_tracking', '2025-05-01 00:00:00', NULL),
        ('007', 'add_feature_flags', '2025-05-15 00:00:00', NULL),
        ('008', 'add_ab_testing', '2025-06-01 00:00:00', NULL)""",

    # scheduled_jobs (created_by = user FK by meaning)
    """INSERT INTO scheduled_jobs (job_name, cron_expression, is_active, last_run_at, next_run_at, created_by) VALUES
        ('daily_metrics_rollup', '0 2 * * *', 1, '2025-06-05 02:00:00', '2025-06-06 02:00:00', 7),
        ('weekly_report_email', '0 8 * * 1', 1, '2025-06-02 08:00:00', '2025-06-09 08:00:00', 10),
        ('inventory_sync', '*/30 * * * *', 1, '2025-06-05 12:30:00', '2025-06-05 13:00:00', 9),
        ('expired_session_cleanup', '0 3 * * *', 1, '2025-06-05 03:00:00', '2025-06-06 03:00:00', 7),
        ('price_update_check', '0 */6 * * *', 0, '2025-06-05 06:00:00', NULL, 9)""",

    # job_executions (no FK)
    """INSERT INTO job_executions (job_id, status, started_at, finished_at, error_message) VALUES
        (1, 'success', '2025-06-05 02:00:00', '2025-06-05 02:03:22', NULL),
        (1, 'success', '2025-06-04 02:00:00', '2025-06-04 02:02:58', NULL),
        (2, 'success', '2025-06-02 08:00:00', '2025-06-02 08:01:15', NULL),
        (3, 'success', '2025-06-05 12:30:00', '2025-06-05 12:30:45', NULL),
        (3, 'failed', '2025-06-05 12:00:00', '2025-06-05 12:00:12', 'Connection timeout to warehouse API'),
        (4, 'success', '2025-06-05 03:00:00', '2025-06-05 03:00:08', NULL),
        (5, 'success', '2025-06-05 06:00:00', '2025-06-05 06:01:30', NULL)""",

    # notification_templates
    """INSERT INTO notification_templates (name, channel, subject, body_template, created_at) VALUES
        ('order_confirmation', 'email', 'Order Confirmed - #{order_id}', 'Your order has been confirmed...', '2025-01-01 00:00:00'),
        ('shipping_update', 'email', 'Your Order is on the Way!', 'Great news! Your order #{order_id}...', '2025-01-01 00:00:00'),
        ('password_reset', 'email', 'Reset Your Password', 'Click the link below to reset...', '2025-01-01 00:00:00'),
        ('low_stock_alert', 'slack', NULL, 'Low stock alert: {product} has {qty} units', '2025-03-01 00:00:00'),
        ('new_review', 'push', 'New Review on {product}', 'A customer left a review...', '2025-04-01 00:00:00'),
        ('promo_announcement', 'email', '{campaign_name} - Special Offer!', 'Don''t miss out on...', '2025-05-01 00:00:00')""",

    # notification_log (no FKs)
    """INSERT INTO notification_log (template_id, user_id, channel, sent_at, delivered) VALUES
        (1, 1, 'email', '2025-03-15 10:32:00', 1),
        (1, 2, 'email', '2025-04-01 14:02:00', 1),
        (2, 1, 'email', '2025-03-16 09:01:00', 1),
        (2, 3, 'email', '2025-05-11 08:01:00', 1),
        (3, 2, 'email', '2025-06-01 11:00:00', 1),
        (3, 6, 'email', '2025-06-03 03:15:00', 0),
        (4, NULL, 'slack', '2025-06-01 07:01:00', 1),
        (6, 1, 'email', '2025-06-01 08:00:00', 1),
        (6, 4, 'email', '2025-06-01 08:00:00', 1),
        (6, 5, 'email', '2025-06-01 08:00:00', 1)""",
]


# ---------------------------------------------------------------------------
# FK analysis helpers
# ---------------------------------------------------------------------------

def count_declared_fks(conn: sqlite3.Connection) -> int:
    """Count declared FOREIGN KEY constraints across all tables."""
    count = 0
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for (table_name,) in cursor.fetchall():
        fk_cursor = conn.execute(f"PRAGMA foreign_key_list({table_name})")
        count += len(fk_cursor.fetchall())
    return count


# Columns that imply a FK relationship but have no declared constraint.
# Each tuple: (table, column, likely_target_table)
IMPLICIT_FK_OPPORTUNITIES = [
    ("user_preferences", "usr_id", "users"),
    ("user_sessions", "user_id", "users"),
    ("login_attempts", "user_id", "users"),
    ("password_resets", "user_id", "users"),
    ("products", "brand_id", "brands"),
    ("categories", "parent_id", "categories"),
    ("category_hierarchy", "ancestor_id", "categories"),
    ("category_hierarchy", "descendant_id", "categories"),
    ("product_images", "product_id", "products"),
    ("product_tags", "product_id", "products"),
    ("product_tags", "tag_id", "tag_definitions"),
    ("inventory", "product_variant_id", "product_variants"),
    ("inventory", "warehouse_id", "warehouses"),
    ("warehouse_inventory", "product_id", "products"),
    ("price_history", "product_id", "products"),
    ("order_items", "product_id", "products"),
    ("order_status_history", "changed_by", "users"),
    ("carts", "user_id", "users"),
    ("cart_items", "cart_id", "carts"),
    ("cart_items", "product_id", "products"),
    ("wishlists", "user_id", "users"),
    ("wishlist_items", "wishlist_id", "wishlists"),
    ("wishlist_items", "product_id", "products"),
    ("return_items", "order_item_id", "order_items"),
    ("coupon_usage", "order_id", "orders"),
    ("coupon_usage", "user_id", "users"),
    ("invoices", "order_id", "orders"),
    ("billing_addresses", "user_id", "users"),
    ("expense_reports", "submitted_by", "users"),
    ("ledger_entries", "account_code", "—standalone—"),
    ("campaign_clicks", "user_id", "users"),
    ("email_campaigns", "campaign_id", "campaigns"),
    ("email_sends", "email_campaign_id", "email_campaigns"),
    ("email_sends", "user_id", "users"),
    ("ad_impressions", "campaign_id", "campaigns"),
    ("conversion_events", "user_id", "users"),
    ("conversion_events", "campaign_id", "campaigns"),
    ("promo_codes", "campaign_id", "campaigns"),
    ("ab_test_results", "variant_id", "ab_test_variants"),
    ("page_views", "user_id", "users"),
    ("page_views", "session_id", "user_sessions"),
    ("event_tracking", "user_id", "users"),
    ("session_events", "session_id", "user_sessions"),
    ("funnel_progress", "funnel_step_id", "funnel_steps"),
    ("funnel_progress", "user_id", "users"),
    ("cohort_members", "user_id", "users"),
    ("dashboard_configs", "owner_id", "users"),
    ("audit_log", "user_id", "users"),
    ("config_settings", "updated_by", "users"),
    ("notification_log", "template_id", "notification_templates"),
    ("notification_log", "user_id", "users"),
    ("job_executions", "job_id", "scheduled_jobs"),
    ("scheduled_jobs", "created_by", "users"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Ensure output directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Idempotent: remove old DB
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")

    # Create all tables
    for ddl in TABLES_DDL:
        conn.execute(ddl)
    conn.commit()

    # Insert sample data
    for stmt in INSERTS:
        conn.execute(stmt)
    conn.commit()

    # ---- Summary ----------------------------------------------------------
    table_count_row = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()
    table_count = table_count_row[0] if table_count_row else 0

    total_rows = 0
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [r[0] for r in cursor.fetchall()]
    for tbl in tables:
        row_count = conn.execute(f"SELECT count(*) FROM [{tbl}]").fetchone()[0]
        total_rows += row_count

    declared_fks = count_declared_fks(conn)
    # Filter implicit opportunities to only those that are real FK-like references
    implicit_count = len([
        opp for opp in IMPLICIT_FK_OPPORTUNITIES
        if opp[2] != "—standalone—"
    ])

    conn.close()

    print(f"\n{'='*60}")
    print("TechMart Enterprise — Fixture Summary")
    print(f"{'='*60}")
    print(f"Database:            {DB_PATH}")
    print(f"Tables:              {table_count}")
    print(f"Total rows:          {total_rows}")
    print(f"Declared FKs:        {declared_fks}")
    print(f"Implicit FK opps:    {implicit_count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
