import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db")


@contextmanager
def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_recipes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                name TEXT,
                used_ingredients TEXT,
                missing_ingredients TEXT,
                steps TEXT,
                cook_time_minutes INTEGER,
                saved_at TEXT NOT NULL
            )
            """
        )


def _now():
    return datetime.now(timezone.utc).isoformat()


def email_exists(email):
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        return row is not None


def create_user(email, password_hash, nickname):
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, nickname, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, password_hash, nickname, _now()),
        )
    return user_id


def get_user_by_email(email):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_nickname(user_id, nickname):
    with get_connection() as conn:
        conn.execute("UPDATE users SET nickname = ? WHERE id = ?", (nickname, user_id))


def save_recipe(user_id, recipe):
    recipe_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO saved_recipes
                (id, user_id, name, used_ingredients, missing_ingredients, steps, cook_time_minutes, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recipe_id,
                user_id,
                recipe.get("name"),
                json.dumps(recipe.get("used_ingredients") or [], ensure_ascii=False),
                json.dumps(recipe.get("missing_ingredients") or [], ensure_ascii=False),
                json.dumps(recipe.get("steps") or [], ensure_ascii=False),
                recipe.get("cook_time_minutes"),
                _now(),
            ),
        )
    return recipe_id


def list_recipes(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_recipes WHERE user_id = ? ORDER BY saved_at DESC", (user_id,)
        ).fetchall()
    recipes = []
    for row in rows:
        recipe = dict(row)
        recipe["used_ingredients"] = json.loads(recipe["used_ingredients"] or "[]")
        recipe["missing_ingredients"] = json.loads(recipe["missing_ingredients"] or "[]")
        recipe["steps"] = json.loads(recipe["steps"] or "[]")
        recipes.append(recipe)
    return recipes


def delete_recipe(user_id, recipe_id):
    """user_id가 일치하는 경우에만 삭제한다 (권한 검사)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM saved_recipes WHERE id = ? AND user_id = ?", (recipe_id, user_id)
        )
        return cursor.rowcount > 0
