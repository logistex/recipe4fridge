import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import psycopg2.pool
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _database_url():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    try:
        return st.secrets["DATABASE_URL"]
    except (FileNotFoundError, KeyError):
        st.error("DATABASE_URL이 설정되지 않았습니다. .env 또는 Streamlit secrets를 확인해주세요.")
        st.stop()


@st.cache_resource
def _connection_pool():
    """프로세스당 커넥션 풀 하나. 쿼리마다 새로 연결(TCP+TLS 핸드셰이크)하는 비용을 없앤다.

    Streamlit은 세션마다 별도 스레드에서 스크립트를 실행하므로 스레드 안전한 풀을 쓴다.
    keepalives는 풀에 오래 놀고 있던 커넥션이 서버 쪽에서 끊기는 것을 줄이기 위한 설정.
    """
    return psycopg2.pool.ThreadedConnectionPool(
        1,
        5,
        _database_url(),
        cursor_factory=psycopg2.extras.RealDictCursor,
        keepalives=1,
        keepalives_idle=30,
    )


@contextmanager
def get_connection():
    pool = _connection_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    finally:
        # putconn은 트랜잭션이 남아있으면 롤백하고, 끊어진 커넥션은 닫아 풀에서 제거한다.
        pool.putconn(conn)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT,
                    nickname TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Google 로그인 사용자는 비밀번호가 없으므로, 기존에 NOT NULL로 만들어진
            # 테이블이 있다면 nullable로 완화한다 (이미 nullable이면 no-op).
            cur.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
            # 레시피 추천 기본 조건(프로필에서 설정, 레시피 화면 기본값으로 사용).
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_cuisine TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_difficulty TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_time TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_servings TEXT")
            # 사용자가 프로필에서 고른 AI 모델 목록(JSON 배열 문자열). NULL/빈 값이면 전체 무료 모델 사용.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS selected_vision_models TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS selected_text_models TEXT")
            cur.execute(
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
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            return cur.fetchone() is not None


def create_user(email, password_hash, nickname):
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, password_hash, nickname, created_at) VALUES (%s, %s, %s, %s, %s)",
                (user_id, email, password_hash, nickname, _now()),
            )
    return user_id


def get_user_by_email(email):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_or_create_google_user(email, nickname):
    """Google 로그인 사용자를 이메일로 조회하고, 처음 로그인이면 비밀번호 없이 새로 만든다."""
    user = get_user_by_email(email)
    if user:
        return user
    user_id = create_user(email, None, nickname)
    return get_user_by_id(user_id)


def update_nickname(user_id, nickname):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET nickname = %s WHERE id = %s", (nickname, user_id))


def update_recipe_preferences(user_id, cuisine, difficulty, time_pref, servings):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET default_cuisine = %s, default_difficulty = %s, default_time = %s, default_servings = %s
                WHERE id = %s
                """,
                (cuisine, difficulty, time_pref, servings, user_id),
            )


def update_model_selection(user_id, vision_model_ids, text_model_ids):
    """모델 선택을 저장한다. 빈 리스트를 넘기면 NULL로 저장되어 '전체 사용'으로 취급된다."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET selected_vision_models = %s, selected_text_models = %s WHERE id = %s",
                (
                    json.dumps(vision_model_ids, ensure_ascii=False) if vision_model_ids else None,
                    json.dumps(text_model_ids, ensure_ascii=False) if text_model_ids else None,
                    user_id,
                ),
            )


def parse_model_id_list(raw):
    """users.selected_vision_models/selected_text_models(JSON 문자열)를 리스트로 파싱한다.

    비어있거나 잘못된 값이면 None을 반환한다 (호출부에서 '전체 사용'으로 해석).
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, list) and parsed else None


def save_recipe(user_id, recipe):
    recipe_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO saved_recipes
                    (id, user_id, name, used_ingredients, missing_ingredients, steps, cook_time_minutes, saved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM saved_recipes WHERE user_id = %s ORDER BY saved_at DESC", (user_id,)
            )
            rows = cur.fetchall()
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
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM saved_recipes WHERE id = %s AND user_id = %s", (recipe_id, user_id)
            )
            return cur.rowcount > 0
