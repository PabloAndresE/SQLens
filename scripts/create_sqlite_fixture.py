#!/usr/bin/env python3
"""Create the SQLite ecommerce fixture database for integration tests.

Run: python scripts/create_sqlite_fixture.py
Creates: tests/fixtures/ecommerce.db
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "ecommerce.db"


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # -- Schema: 10 tables with real FKs --

    cur.executescript("""
    CREATE TABLE countries (
        id          INTEGER PRIMARY KEY,
        code        TEXT    NOT NULL UNIQUE,
        name        TEXT    NOT NULL
    );

    CREATE TABLE users (
        id          INTEGER PRIMARY KEY,
        email       TEXT    NOT NULL UNIQUE,
        first_name  TEXT    NOT NULL,
        last_name   TEXT    NOT NULL,
        country_id  INTEGER NOT NULL REFERENCES countries(id),
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL
    );

    CREATE TABLE categories (
        id          INTEGER PRIMARY KEY,
        name        TEXT    NOT NULL UNIQUE,
        description TEXT
    );

    CREATE TABLE products (
        id          INTEGER PRIMARY KEY,
        name        TEXT    NOT NULL,
        price       REAL    NOT NULL,
        category_id INTEGER NOT NULL REFERENCES categories(id),
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT    NOT NULL
    );

    CREATE TABLE orders (
        id              INTEGER PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id),
        status          TEXT    NOT NULL DEFAULT 'pending',
        total_amount    REAL    NOT NULL DEFAULT 0,
        shipping_amount REAL    NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL
    );

    CREATE TABLE order_items (
        id          INTEGER PRIMARY KEY,
        order_id    INTEGER NOT NULL REFERENCES orders(id),
        product_id  INTEGER NOT NULL REFERENCES products(id),
        quantity    INTEGER NOT NULL,
        unit_price  REAL    NOT NULL
    );

    CREATE TABLE payments (
        id          INTEGER PRIMARY KEY,
        order_id    INTEGER NOT NULL REFERENCES orders(id),
        method      TEXT    NOT NULL,
        amount      REAL    NOT NULL,
        status      TEXT    NOT NULL DEFAULT 'pending',
        created_at  TEXT    NOT NULL
    );

    CREATE TABLE reviews (
        id          INTEGER PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        product_id  INTEGER NOT NULL REFERENCES products(id),
        rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment     TEXT,
        created_at  TEXT    NOT NULL
    );

    CREATE TABLE coupons (
        id              INTEGER PRIMARY KEY,
        code            TEXT    NOT NULL UNIQUE,
        discount_pct    REAL    NOT NULL,
        valid_from      TEXT    NOT NULL,
        valid_until     TEXT    NOT NULL,
        is_active       INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE audit_log (
        id          INTEGER PRIMARY KEY,
        user_id     INTEGER REFERENCES users(id),
        action      TEXT    NOT NULL,
        entity_type TEXT    NOT NULL,
        entity_id   INTEGER,
        created_at  TEXT    NOT NULL
    );
    """)

    # -- Sample data --

    cur.executemany(
        "INSERT INTO countries (id, code, name) VALUES (?, ?, ?)",
        [
            (1, "EC", "Ecuador"),
            (2, "US", "United States"),
            (3, "MX", "Mexico"),
            (4, "CO", "Colombia"),
            (5, "AR", "Argentina"),
        ],
    )

    cur.executemany(
        "INSERT INTO users (id, email, first_name, last_name,"
        " country_id, is_active, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "alice@example.com", "Alice", "Smith", 2, 1, "2025-01-15T10:00:00"),
            (2, "bob@example.com", "Bob", "García", 1, 1, "2025-02-20T14:30:00"),
            (3, "carol@example.com", "Carol", "López", 3, 1, "2025-03-10T09:00:00"),
            (4, "david@example.com", "David", "Martinez", 4, 0, "2025-04-05T16:00:00"),
            (5, "eve@example.com", "Eve", "Johnson", 2, 1, "2025-05-01T08:30:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO categories (id, name, description) VALUES (?, ?, ?)",
        [
            (1, "Electronics", "Electronic devices and accessories"),
            (2, "Books", "Physical and digital books"),
            (3, "Clothing", "Apparel and fashion"),
        ],
    )

    cur.executemany(
        "INSERT INTO products (id, name, price, category_id,"
        " is_active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "Laptop Pro", 1299.99, 1, 1, "2025-01-01T00:00:00"),
            (2, "Wireless Mouse", 29.99, 1, 1, "2025-01-01T00:00:00"),
            (3, "Python Handbook", 45.00, 2, 1, "2025-01-01T00:00:00"),
            (4, "T-Shirt Basic", 19.99, 3, 1, "2025-01-01T00:00:00"),
            (5, "USB-C Hub", 49.99, 1, 0, "2025-02-15T00:00:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO orders (id, user_id, status, total_amount,"
        " shipping_amount, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "completed", 1329.98, 15.00, "2025-03-01T12:00:00"),
            (2, 2, "completed", 74.99, 5.00, "2025-03-10T14:00:00"),
            (3, 3, "pending", 45.00, 0.00, "2025-03-15T09:30:00"),
            (4, 1, "shipped", 19.99, 5.00, "2025-03-20T16:00:00"),
            (5, 5, "completed", 29.99, 0.00, "2025-03-25T11:00:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO order_items (id, order_id, product_id,"
        " quantity, unit_price) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, 1, 1, 1299.99),
            (2, 1, 2, 1, 29.99),
            (3, 2, 2, 1, 29.99),
            (4, 2, 3, 1, 45.00),
            (5, 3, 3, 1, 45.00),
            (6, 4, 4, 1, 19.99),
            (7, 5, 2, 1, 29.99),
        ],
    )

    cur.executemany(
        "INSERT INTO payments (id, order_id, method, amount,"
        " status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "credit_card", 1344.98, "completed", "2025-03-01T12:01:00"),
            (2, 2, "paypal", 79.99, "completed", "2025-03-10T14:01:00"),
            (3, 4, "credit_card", 24.99, "completed", "2025-03-20T16:01:00"),
            (4, 5, "debit_card", 29.99, "completed", "2025-03-25T11:01:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO reviews (id, user_id, product_id, rating,"
        " comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, 1, 5, "Amazing laptop!", "2025-03-05T10:00:00"),
            (2, 2, 2, 4, "Good mouse, solid build", "2025-03-15T10:00:00"),
            (3, 3, 3, 5, "Great reference book", "2025-03-20T10:00:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO coupons (id, code, discount_pct, valid_from,"
        " valid_until, is_active) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "WELCOME10", 10.0, "2025-01-01", "2025-12-31", 1),
            (2, "SUMMER20", 20.0, "2025-06-01", "2025-08-31", 0),
        ],
    )

    cur.executemany(
        "INSERT INTO audit_log (id, user_id, action, entity_type,"
        " entity_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, 1, "login", "user", 1, "2025-03-01T11:59:00"),
            (2, 1, "purchase", "order", 1, "2025-03-01T12:00:00"),
            (3, 2, "login", "user", 2, "2025-03-10T13:55:00"),
            (4, 2, "purchase", "order", 2, "2025-03-10T14:00:00"),
        ],
    )

    conn.commit()
    conn.close()
    print(f"Created {DB_PATH} with 10 tables and sample data.")


if __name__ == "__main__":
    main()
