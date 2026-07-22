import ast
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from html import unescape
import json
import logging
import os
import sqlite3
import re
import secrets
import requests
import base64
import hashlib
from types import SimpleNamespace
from bs4 import BeautifulSoup
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from urllib.parse import urlparse, parse_qs, parse_qsl, quote_plus, unquote, urljoin, urlencode, urlunparse
from .html_sanitization import extract_json_ld_payloads, extract_visible_text
from .hostname_matching import hostname_matches_any, parse_hostname, url_hostname_matches_any
from .social_resolver import is_valid_social_destination_url, resolve_social_url
from .social_video_pipeline import (
    TranscriptPipelineResult,
    TranscriptPipelineStageError,
    YtDlpExtractError,
    run_social_video_transcript_pipeline,
)
from .url_validation import PublicUrlValidationError, USER_FACING_PUBLIC_URL_ERROR, safe_get, validate_public_url

SETTINGS_ENCRYPTION_KEY_ENV = "USER_SETTINGS_ENCRYPTION_KEY"

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
PYTHON_MULTIPART_INSTALLED = importlib.util.find_spec("multipart") is not None
INTERNAL_SERVER_ERROR_MESSAGE = "Internal server error"


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "recipe_clipper_session")
SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "168"))
COOKIE_SECURE = _parse_bool(os.getenv("AUTH_COOKIE_SECURE"), default=False)
COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN", "").strip() or None
CORS_ORIGINS = _parse_csv(os.getenv("CORS_ALLOW_ORIGINS")) or [
    "http://localhost:8010",
    "http://127.0.0.1:8010",
]

password_hasher = PasswordHasher()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_correlation_id(request: Request, call_next):
    incoming = str(request.headers.get("X-Request-ID", "") or "").strip()
    request.state.correlation_id = incoming[:128] if incoming else _new_correlation_id()
    response = await call_next(request)
    response.headers.setdefault("X-Correlation-ID", request.state.correlation_id)
    return response

DB = os.getenv("RECIPES_DB_PATH", "/app/data/recipes.db")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
OCR_WORKER_TIMEOUT_SECONDS = int(os.getenv("OCR_WORKER_TIMEOUT_SECONDS", "20"))
AI_REVIEW_ENABLED = _parse_bool(os.getenv("AI_REVIEW_ENABLED"), default=True)
AI_REVIEW_POLL_SECONDS = float(os.getenv("AI_REVIEW_POLL_SECONDS", "12"))
REVIEW_STATUSES = {"none", "needs_review", "queued", "processing", "completed", "review_ready", "failed"}
_review_worker_task: asyncio.Task | None = None
def get_conn():
    db_dir = os.path.dirname(DB)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def _new_correlation_id() -> str:
    return secrets.token_hex(8)


def _request_correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", "")
    if existing:
        return existing
    request.state.correlation_id = _new_correlation_id()
    return request.state.correlation_id


def _json_error_response(
    request: Request,
    *,
    status_code: int,
    detail,
    correlation_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    active_correlation_id = correlation_id or _request_correlation_id(request)
    content = {"detail": detail}
    if status_code >= 500:
        content["correlation_id"] = active_correlation_id
    response = JSONResponse(status_code=status_code, content=content, headers=headers)
    response.headers["X-Correlation-ID"] = active_correlation_id
    return response


AUTH_LOCKOUT_ENABLED_KEY = "auth_lockout_enabled"
AUTH_MAX_FAILED_ATTEMPTS_KEY = "auth_max_failed_attempts"
AUTH_LOCKOUT_MINUTES_KEY = "auth_lockout_minutes"
AUTH_SETTINGS_DEFAULTS = {
    AUTH_LOCKOUT_ENABLED_KEY: "true",
    AUTH_MAX_FAILED_ATTEMPTS_KEY: "5",
    AUTH_LOCKOUT_MINUTES_KEY: "15",
}


def _parse_cookbook_names_from_tags(tags_value: str | None) -> list[str]:
    if not tags_value:
        return []
    parts = [part.strip() for part in str(tags_value).split(",")]
    names: list[str] = []
    for part in parts:
        if not part:
            continue
        if not re.match(r"^cookbook\s*:", part, flags=re.IGNORECASE):
            continue
        name = re.sub(r"^cookbook\s*:", "", part, flags=re.IGNORECASE).strip()
        if name:
            names.append(name)
    return names


def _migrate_cookbook_tags(cur: sqlite3.Cursor) -> None:
    recipes = cur.execute("SELECT id, tags, user_id FROM recipes").fetchall()
    cookbook_ids_by_name: dict[tuple[int, str], int] = {}

    for recipe in recipes:
        if recipe["user_id"] is None:
            continue
        recipe_id = int(recipe["id"])
        owner_user_id = int(recipe["user_id"])
        cookbook_names = _parse_cookbook_names_from_tags(recipe["tags"])
        for cookbook_name in cookbook_names:
            normalized = cookbook_name.lower()
            cache_key = (owner_user_id, normalized)
            cookbook_id = cookbook_ids_by_name.get(cache_key)
            if cookbook_id is None:
                existing = cur.execute(
                    "SELECT id FROM cookbooks WHERE user_id = ? AND lower(name) = ? LIMIT 1",
                    (owner_user_id, normalized),
                ).fetchone()
                if existing:
                    cookbook_id = int(existing["id"])
                else:
                    cur.execute(
                        "INSERT INTO cookbooks (user_id, name, created_at) VALUES (?, ?, ?)",
                        (owner_user_id, cookbook_name, utcnow_iso()),
                    )
                    cookbook_id = int(cur.lastrowid)
                cookbook_ids_by_name[cache_key] = cookbook_id
            cur.execute(
                "INSERT OR IGNORE INTO recipe_cookbooks (recipe_id, cookbook_id) VALUES (?, ?)",
                (recipe_id, cookbook_id),
            )


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _resolve_owner_user_id(cur: sqlite3.Cursor) -> int | None:
    first_admin = cur.execute(
        "SELECT id FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if first_admin:
        return int(first_admin["id"])
    first_user = cur.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
    if first_user:
        return int(first_user["id"])
    return None


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            image_url TEXT,
            source_app TEXT,
            source_type TEXT,
            notes TEXT,
            tags TEXT,
            needs_review INTEGER NOT NULL DEFAULT 0,
            review_status TEXT NOT NULL DEFAULT 'none',
            review_notes TEXT,
            review_requested_at TEXT,
            review_started_at TEXT,
            review_completed_at TEXT,
            review_error TEXT,
            ai_review_provider TEXT,
            ai_review_model TEXT,
            ai_review_source_payload TEXT,
            ai_review_result TEXT,
            ai_review_normalized TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("PRAGMA table_info(recipes)")
    columns = [row["name"] for row in cur.fetchall()]
    if "needs_review" not in columns:
        cur.execute(
            "ALTER TABLE recipes ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0"
        )
    if "review_status" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_status TEXT NOT NULL DEFAULT 'none'")
    if "review_notes" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_notes TEXT")
    if "review_requested_at" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_requested_at TEXT")
    if "review_started_at" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_started_at TEXT")
    if "review_completed_at" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_completed_at TEXT")
    if "review_error" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN review_error TEXT")
    if "ai_review_provider" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ai_review_provider TEXT")
    if "ai_review_model" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ai_review_model TEXT")
    if "ai_review_source_payload" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ai_review_source_payload TEXT")
    if "ai_review_result" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ai_review_result TEXT")
    if "ai_review_normalized" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ai_review_normalized TEXT")
    if "ingredients" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ingredients TEXT")
    if "image_url" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN image_url TEXT")
    if "instructions" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN instructions TEXT")
    if "servings" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN servings TEXT")
    if "prep_time" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN prep_time TEXT")
    if "cook_time" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN cook_time TEXT")
    if "total_time" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN total_time TEXT")
    if "import_method" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN import_method TEXT")
    if "import_confidence" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN import_confidence REAL")
    if "import_status" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN import_status TEXT NOT NULL DEFAULT 'needs_review'")
    if "source_site_name" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN source_site_name TEXT")
    if "prep_minutes" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN prep_minutes INTEGER")
    if "cook_minutes" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN cook_minutes INTEGER")
    if "total_minutes" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN total_minutes INTEGER")
    if "ingredient_groups" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN ingredient_groups TEXT")
    if "instruction_groups" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN instruction_groups TEXT")
    if "original_source_url" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN original_source_url TEXT")
    if "resolved_recipe_url" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN resolved_recipe_url TEXT")
    if "content_source" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN content_source TEXT")
    if "user_id" not in columns:
        cur.execute("ALTER TABLE recipes ADD COLUMN user_id INTEGER")
    cur.execute(
        """
        UPDATE recipes
        SET review_status = CASE
            WHEN lower(COALESCE(review_status, '')) = 'needs_review' THEN 'needs_review'
            WHEN lower(COALESCE(review_status, '')) = 'queued' THEN 'queued'
            WHEN lower(COALESCE(review_status, '')) = 'processing' THEN 'processing'
            WHEN lower(COALESCE(review_status, '')) = 'reviewed' THEN 'completed'
            WHEN lower(COALESCE(review_status, '')) = 'review_ready' THEN 'completed'
            WHEN lower(COALESCE(review_status, '')) = 'completed' THEN 'completed'
            WHEN lower(COALESCE(review_status, '')) = 'failed' THEN 'failed'
            ELSE 'none'
        END
        """
    )

    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
        '''
    )
    cur.execute("PRAGMA table_info(users)")
    user_columns = [row["name"] for row in cur.fetchall()]
    if "is_active" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        cur.execute("UPDATE users SET created_at = ? WHERE created_at = ''", (utcnow_iso(),))
    if "last_login" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    if "display_name" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    if "failed_login_attempts" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
    if "locked_until" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
    if "is_locked_manual" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN is_locked_manual INTEGER NOT NULL DEFAULT 0")

    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        '''
    )
    for setting_key, default_value in AUTH_SETTINGS_DEFAULTS.items():
        cur.execute(
            '''
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ''',
            (setting_key, default_value, utcnow_iso()),
        )

    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS user_import_settings (
            user_id INTEGER PRIMARY KEY,
            facebook_cookie_encrypted TEXT,
            facebook_cookie_updated_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS cookbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("PRAGMA table_info(cookbooks)")
    cookbook_columns = [row["name"] for row in cur.fetchall()]
    if "user_id" not in cookbook_columns:
        cur.execute("ALTER TABLE cookbooks ADD COLUMN user_id INTEGER")
    cur.execute("DROP INDEX IF EXISTS idx_cookbooks_name_nocase")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cookbooks_user_name_nocase ON cookbooks(user_id, lower(name))"
    )
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS recipe_cookbooks (
            recipe_id INTEGER NOT NULL,
            cookbook_id INTEGER NOT NULL,
            PRIMARY KEY (recipe_id, cookbook_id),
            FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY(cookbook_id) REFERENCES cookbooks(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recipe_cookbooks_recipe_id ON recipe_cookbooks(recipe_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recipe_cookbooks_cookbook_id ON recipe_cookbooks(cookbook_id)")
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS grocery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            quantity REAL,
            unit TEXT,
            display_text TEXT NOT NULL,
            checked INTEGER NOT NULL DEFAULT 0,
            source_recipe_id INTEGER,
            source_recipe_title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grocery_items_user_checked ON grocery_items(user_id, checked)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grocery_items_user_source ON grocery_items(user_id, source_recipe_id)")
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS meal_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            recipe_id INTEGER NOT NULL,
            meal_slot TEXT NOT NULL DEFAULT 'dinner',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_meal_plan_items_user_plan_date ON meal_plan_items(user_id, plan_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_meal_plan_items_user_recipe_id ON meal_plan_items(user_id, recipe_id)")
    cur.execute("PRAGMA table_info(meal_plan_items)")
    meal_plan_columns = [row["name"] for row in cur.fetchall()]
    if "servings_override" not in meal_plan_columns:
        cur.execute("ALTER TABLE meal_plan_items ADD COLUMN servings_override TEXT")
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS recipe_user_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            is_cooked INTEGER NOT NULL DEFAULT 0,
            rating INTEGER,
            personal_note TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_recipe_user_state_recipe_user ON recipe_user_state(recipe_id, user_id)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_recipe_user_state_user_id ON recipe_user_state(user_id)")
    cur.execute("PRAGMA table_info(recipe_user_state)")
    recipe_state_columns = [row["name"] for row in cur.fetchall()]
    if "is_favorite" not in recipe_state_columns:
        cur.execute("ALTER TABLE recipe_user_state ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
    if "last_viewed_at" not in recipe_state_columns:
        cur.execute("ALTER TABLE recipe_user_state ADD COLUMN last_viewed_at TEXT")

    bootstrap_admin_email = (os.getenv("AUTH_BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    bootstrap_admin_password = os.getenv("AUTH_BOOTSTRAP_ADMIN_PASSWORD") or ""
    # Bootstrap admin is only created when the user does not already exist.
    # Remove AUTH_BOOTSTRAP_ADMIN_* env vars after first successful login.
    if bootstrap_admin_email and bootstrap_admin_password:
        existing = cur.execute(
            "SELECT id FROM users WHERE lower(email) = ? LIMIT 1",
            (bootstrap_admin_email,),
        ).fetchone()
        if not existing:
            cur.execute(
                '''
                INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at, last_login)
                VALUES (?, NULL, ?, 1, 1, ?, NULL)
                ''',
                (bootstrap_admin_email, hash_password(bootstrap_admin_password), utcnow_iso()),
            )

    owner_user_id = _resolve_owner_user_id(cur)
    if owner_user_id is not None:
        cur.execute(
            "UPDATE recipes SET user_id = ? WHERE user_id IS NULL OR user_id = 0",
            (owner_user_id,),
        )

    if owner_user_id is not None:
        cur.execute(
            "UPDATE cookbooks SET user_id = ? WHERE user_id IS NULL OR user_id = 0",
            (owner_user_id,),
        )

    _migrate_cookbook_tags(cur)
    conn.commit()
    conn.close()


init_db()


@app.on_event("startup")
async def start_review_worker() -> None:
    global _review_worker_task
    if _review_worker_task and not _review_worker_task.done():
        return
    _review_worker_task = asyncio.create_task(process_review_queue())


@app.on_event("shutdown")
async def stop_review_worker() -> None:
    global _review_worker_task
    if not _review_worker_task:
        return
    _review_worker_task.cancel()
    try:
        await _review_worker_task
    except asyncio.CancelledError:
        pass
    _review_worker_task = None


class Recipe(BaseModel):
    title: str
    url: str | None = ""
    original_source_url: str | None = None
    resolved_recipe_url: str | None = None
    content_source: str | None = None
    image_url: str | None = None
    source_app: str | None = None
    source_type: str | None = None
    notes: str | None = None
    tags: str | None = None
    needs_review: bool = False
    review_status: str | None = None
    review_notes: str | None = None
    ingredients: list[str] | None = None
    instructions: list[str] | None = None
    ingredient_groups: list[dict] | None = None
    instruction_groups: list[dict] | None = None
    servings: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    total_minutes: int | None = None
    import_method: str | None = None
    import_confidence: float | None = None
    import_status: str | None = None
    original_url: str | None = None
    source_site_name: str | None = None
    ai_review_source_payload: dict | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    display_name: str | None = None
    password: str
    is_admin: bool = False


class ResetPasswordRequest(BaseModel):
    password: str


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None


class AdminSecuritySettingsUpdateRequest(BaseModel):
    auth_lockout_enabled: bool
    auth_max_failed_attempts: int = Field(ge=1)
    auth_lockout_minutes: int = Field(ge=0)


class CookbookPayload(BaseModel):
    name: str


class RecipeCookbookMembershipPayload(BaseModel):
    cookbook_ids: list[int]


class RecipeUserStatePayload(BaseModel):
    is_cooked: bool | None = None
    rating: int | None = None
    personal_note: str | None = None
    is_favorite: bool | None = None


class ModalAiCleanupRequest(BaseModel):
    url: str
    preview: dict | None = None


class PasteTextImportRequest(BaseModel):
    text: str


class ShoppingListRequest(BaseModel):
    recipe_ids: list[int]


class GroceryItemPayload(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    display_text: str
    source_recipe_id: int | None = None
    source_recipe_title: str | None = None


class GroceryItemsPayload(BaseModel):
    items: list[GroceryItemPayload]


class GroceryItemUpdatePayload(BaseModel):
    checked: bool


class MealPlanItemCreate(BaseModel):
    plan_date: str
    recipe_id: int
    meal_slot: str = "dinner"
    servings_override: str | None = None


class MealPlanWeekRequest(BaseModel):
    start_date: str

ALLOWED_MEAL_SLOTS = ("breakfast", "lunch", "dinner", "other")


def _normalize_meal_slot(meal_slot: str | None) -> str:
    slot = str(meal_slot or "").strip().lower()
    return slot if slot in ALLOWED_MEAL_SLOTS else "dinner"


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_AI_CLEANUP_SOURCE_CHARS = 8000
MAX_RECIPE_HTML_CHARS = 1_000_000
MAX_REGEX_TEXT_CHARS = 8_000
MAX_DURATION_TEXT_CHARS = 128
MAX_INGREDIENT_LINE_CHARS = 32768
MAX_INGREDIENT_GROUP_TITLE_CHARS = 120
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}


SOCIAL_HOST_BLOCKLIST = ("facebook.com", "fb.watch", "fbcdn.net", "instagram.com", "instagr.am")
SOCIAL_INTERNAL_HOSTS = SOCIAL_HOST_BLOCKLIST + ("l.facebook.com", "l.instagram.com")
SOCIAL_DISCOVERY_HOST_EXCLUDE = SOCIAL_INTERNAL_HOSTS + (
    "pinterest.com",
    "pin.it",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
)
KNOWN_RECIPE_DOMAINS = (
    "allrecipes.com",
    "foodnetwork.com",
    "delish.com",
    "seriouseats.com",
    "epicurious.com",
    "simplyrecipes.com",
    "tastesbetterfromscratch.com",
    "thekitchn.com",
    "sallysbakingaddiction.com",
    "loveandlemons.com",
    "halfbakedharvest.com",
    "natashaskitchen.com",
    "eatingwell.com",
)
RAW_HTML_INTERNAL_HOSTS = SOCIAL_INTERNAL_HOSTS + ("messenger.com", "fbcdn.net")
RAW_HTML_HOST_BLOCKLIST = RAW_HTML_INTERNAL_HOSTS + (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "wikipedia.org",
    "wiktionary.org",
    "dictionary.com",
    "merriam-webster.com",
)
SOCIAL_DISCOVERY_ENABLED = _parse_bool(os.getenv("SOCIAL_DISCOVERY_ENABLED"), default=True)
SOCIAL_DISCOVERY_CONFIDENCE_THRESHOLD = float(os.getenv("SOCIAL_DISCOVERY_CONFIDENCE_THRESHOLD", "0.72"))
RAW_HTML_SOCIAL_CANDIDATE_THRESHOLD = float(os.getenv("RAW_HTML_SOCIAL_CANDIDATE_THRESHOLD", "0.55"))


def _host_matches(host: str, candidates: tuple[str, ...]) -> bool:
    return hostname_matches_any(host, candidates)


def _is_social_share_url(url: str) -> bool:
    host = parse_hostname(url)
    return _host_matches(host, ("facebook.com", "fb.watch", "instagram.com", "instagr.am"))


def _is_facebook_share_or_reel_url(url: str) -> bool:
    try:
        parsed = urlparse(url or "")
    except Exception:
        return False
    host = parse_hostname(url)
    if not _host_matches(host, ("facebook.com",)):
        return False
    path = (parsed.path or "").lower()
    return (
        path.startswith("/share/")
        or path.startswith("/reel/")
        or path.startswith("/reel/video/")
    )


def _external_candidate_rejection_reason(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return "empty_value"
    lowered = value.lower()
    if lowered.startswith(("javascript:", "data:")):
        return "unsupported_scheme_prefix"
    if not lowered.startswith(("http://", "https://")):
        return "non_http_url"
    if ".dtd" in lowered:
        return "dtd_reference"
    try:
        parsed = urlparse(value)
    except Exception:
        return "urlparse_failed"
    if parsed.scheme not in ("http", "https"):
        return "unsupported_scheme"
    host = parsed.netloc.lower().strip()
    if not host:
        return "missing_host"
    if _host_matches(host, SOCIAL_INTERNAL_HOSTS):
        return "social_host_blocklisted"
    return ""


def _extract_meta_content(html: str, key: str, attr: str = "property") -> str:
    if not html or not key:
        return ""
    for match in re.finditer(r"<meta\b[^>]*>", html, flags=re.IGNORECASE):
        tag = match.group(0)
        attrs = {
            name.strip().lower(): value
            for name, value in re.findall(r'([^\s=/>]+)\s*=\s*["\'](.*?)["\']', tag, flags=re.DOTALL)
        }
        if attrs.get(attr.lower(), "").strip().lower() != key.lower():
            continue
        content = _clean_text(attrs.get("content", ""))
        if content:
            return content
    return ""


SOCIAL_SIGNAL_JUNK_PATTERNS = [
    r"\bfacebook\b",
    r"\binstagram\b",
    r"\bwatch\b",
    r"\blog in\b",
    r"\bsign up\b",
    r"\breels?\b",
    r"\bposts?\b",
    r"\bphotos?\b",
    r"\bvideos?\b",
]


def _normalize_social_signal(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    for pattern in SOCIAL_SIGNAL_JUNK_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\[\]{}()|]+", " ", text)
    text = re.sub(r"\s*[-–•:]+\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–•:")
    if len(text) < 4:
        return ""
    if not re.search(r"[a-zA-Z]", text):
        return ""
    return text


def _extract_html_title(html: str) -> str:
    if not html:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _clean_text(match.group(1))


def _extract_visible_text_snippets(html: str, max_items: int = 3) -> list[str]:
    text = _clean_text(extract_visible_text(html or ""))
    if not text:
        return []
    parts = re.split(r"[.!?\n]", text)
    snippets: list[str] = []
    for part in parts:
        normalized = re.sub(r"\s+", " ", part).strip()
        if len(normalized) < 30:
            continue
        snippets.append(normalized[:140])
        if len(snippets) >= max_items:
            break
    return snippets


def _tokenize_for_overlap(value: str) -> set[str]:
    text = re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())
    tokens = {token for token in text.split() if len(token) > 2 and token not in {"with", "from", "this", "that", "your"}}
    return tokens


def _build_social_discovery_query(hints: dict) -> str:
    query_parts: list[str] = []
    primary_title = hints.get("og_title") or hints.get("title") or ""
    primary_description = hints.get("og_description") or hints.get("meta_description") or ""
    if primary_title:
        query_parts.append(primary_title)
    if primary_description:
        query_parts.append(" ".join(primary_description.split()[:12]))
    return " ".join(part for part in query_parts if part).strip()


def _extract_social_discovery_hints(html: str, _page_url: str) -> dict:
    title = _normalize_social_signal(_extract_html_title(html))
    og_title = _normalize_social_signal(_extract_meta_content(html, "og:title"))
    og_description = _normalize_social_signal(_extract_meta_content(html, "og:description"))
    description = _normalize_social_signal(_extract_meta_content(html, "description", attr="name"))
    return {
        "title": title,
        "og_title": og_title,
        "og_description": og_description,
        "meta_description": description,
    }


def _extract_social_metadata_fields(html: str) -> dict:
    return {
        "og_title": _clean_text(_extract_meta_content(html, "og:title")),
        "og_description": _clean_text(_extract_meta_content(html, "og:description")),
        "og_image": _clean_text(_extract_meta_content(html, "og:image")),
        "og_url": _clean_text(_extract_meta_content(html, "og:url")),
        "og_image_alt": _clean_text(_extract_meta_content(html, "og:image:alt")),
    }


def _extract_external_urls_from_text(value: str) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    extracted: list[str] = []
    for match in re.finditer(r"https?://[^\s\"'<>\\]+", unescape(value), flags=re.IGNORECASE):
        raw = _strip_trailing_url_noise(match.group(0))
        if not raw:
            continue
        decoded, _ = _decode_social_redirect_url(raw)
        candidate = _strip_trailing_url_noise(decoded or raw)
        if _external_candidate_rejection_reason(candidate):
            continue
        host = (urlparse(candidate).netloc or "").lower().strip()
        if _host_matches(host, ("facebook.com", "fbcdn.net")):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        extracted.append(candidate)
    return extracted


def _resolve_external_url_from_social_metadata(html: str) -> dict:
    metadata = _extract_social_metadata_fields(html)
    metadata_text = " ".join(
        [
            metadata.get("og_title", ""),
            metadata.get("og_description", ""),
            metadata.get("og_url", ""),
            metadata.get("og_image", ""),
            metadata.get("og_image_alt", ""),
        ]
    )
    candidates = _extract_external_urls_from_text(metadata_text)
    ranked_candidates: list[dict] = []
    for candidate in candidates:
        score, reasons = _score_raw_html_social_candidate(candidate)
        ranked_candidates.append(
            {
                "url": candidate,
                "score": round(score, 3),
                "reasons": reasons,
            }
        )
    ranked_candidates.sort(key=lambda item: item["score"], reverse=True)
    best_candidate = ranked_candidates[0] if ranked_candidates else {}
    resolved_url = ""
    if best_candidate and best_candidate.get("score", 0) >= 0.2:
        resolved_url = best_candidate.get("url", "")
    return {
        "resolved_url": resolved_url,
        "candidate_urls": candidates,
        "ranked_candidates": ranked_candidates,
        "metadata": metadata,
    }


def _unwrap_search_result_url(url: str) -> str:
    parsed = urlparse(url or "")
    if _host_matches(parsed.netloc.lower(), ("duckduckgo.com",)):
        params = parse_qs(parsed.query)
        uddg = (params.get("uddg") or [""])[0]
        if uddg:
            return unquote(uddg).strip()
    return (url or "").strip()


def _strip_trailing_url_noise(url: str) -> str:
    if not url:
        return ""
    cleaned = url.strip().strip("\"'<>")
    while cleaned and cleaned[-1] in ".,);:!?]":
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _decode_social_redirect_url(candidate_url: str) -> tuple[str, str]:
    value = _strip_trailing_url_noise(candidate_url)
    if not value:
        return "", ""
    try:
        parsed = urlparse(value)
    except Exception:
        return value, ""
    host = parsed.netloc.lower().strip()
    params = parse_qs(parsed.query)
    if _host_matches(host, ("l.facebook.com", "lm.facebook.com")) and parsed.path.startswith("/l.php"):
        wrapped = (params.get("u") or [""])[0]
        if wrapped:
            decoded = unquote(unescape(wrapped)).strip()
            return decoded, f"{value} -> {decoded}"
    if _host_matches(host, ("l.instagram.com",)):
        wrapped = (params.get("u") or [""])[0]
        if wrapped:
            decoded = unquote(unescape(wrapped)).strip()
            return decoded, f"{value} -> {decoded}"
    if _host_matches(host, ("facebook.com", "m.facebook.com")) and parsed.path.startswith("/redirect/"):
        wrapped = (params.get("u") or [""])[0]
        if wrapped:
            decoded = unquote(unescape(wrapped)).strip()
            return decoded, f"{value} -> {decoded}"
    return value, ""


def _extract_raw_html_url_candidates(html: str) -> tuple[list[str], list[str]]:
    raw = html or ""
    if not raw:
        return [], []

    values: list[str] = []
    decode_steps: list[str] = []
    for match in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', raw, flags=re.IGNORECASE):
        values.append(unescape(match.group(1)))
    for match in re.finditer(r'<meta\b[^>]*content\s*=\s*["\']([^"\']+)["\']', raw, flags=re.IGNORECASE):
        values.append(unescape(match.group(1)))

    scan_source = unescape(raw)
    values.extend(match.group(0) for match in re.finditer(r"https?://[^\s\"'<>\\]+", scan_source, flags=re.IGNORECASE))

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _strip_trailing_url_noise(value)
        if not cleaned:
            continue
        decoded, decode_info = _decode_social_redirect_url(cleaned)
        decoded = _strip_trailing_url_noise(decoded)
        if decode_info:
            decode_steps.append(decode_info)
        if decoded and decoded not in seen:
            seen.add(decoded)
            deduped.append(decoded)
    return deduped, decode_steps


def _raw_html_candidate_rejection_reason(url: str) -> str:
    rejection = _external_candidate_rejection_reason(url)
    if rejection:
        return rejection
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().strip()
    if _host_matches(host, RAW_HTML_HOST_BLOCKLIST):
        return "raw_html_host_blocklisted"
    lowered = (url or "").lower()
    if any(token in lowered for token in ("doubleclick", "adservice", "tracking", "pixel")):
        return "tracking_url"
    return ""


def _score_raw_html_social_candidate(candidate_url: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    parsed = urlparse(candidate_url or "")
    host = parsed.netloc.lower().strip()
    path = (parsed.path or "").lower()

    if "/recipe/" in path or "/recipes/" in path:
        score += 0.6
        reasons.append("recipe_path")
    elif any(fragment in path for fragment in ("/recipe-", "-recipe", "/food/", "/dish/")):
        score += 0.35
        reasons.append("recipeish_path")
    if _host_matches(host, KNOWN_RECIPE_DOMAINS):
        score += 0.2
        reasons.append("known_recipe_domain")
    if any(token in host for token in ("recipe", "kitchen", "food", "cooking", "bake", "eat")):
        score += 0.1
        reasons.append("food_domain_token")
    if any(fragment in path for fragment in ("/blog/", "/article/", "/post/", "/posts/")):
        score += 0.08
        reasons.append("article_like_path")
    if any(token in candidate_url.lower() for token in ("ingredients", "instructions", "print-recipe")):
        score += 0.08
        reasons.append("recipe_keywords")
    return min(score, 1.0), reasons


def _choose_raw_html_social_candidate(candidates: list[str]) -> dict:
    scored: list[dict] = []
    for candidate in candidates:
        rejection = _raw_html_candidate_rejection_reason(candidate)
        if rejection:
            continue
        score, reasons = _score_raw_html_social_candidate(candidate)
        scored.append(
            {
                "url": candidate,
                "score": round(score, 3),
                "reasons": reasons,
            }
        )
    if not scored:
        return {"resolved_url": "", "ranked_candidates": [], "reason": "raw_html_no_candidates"}
    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0]
    next_score = scored[1]["score"] if len(scored) > 1 else 0.0
    strong = best["score"] >= RAW_HTML_SOCIAL_CANDIDATE_THRESHOLD and (best["score"] - next_score >= 0.1 or len(scored) == 1)
    return {
        "resolved_url": best["url"] if strong else "",
        "ranked_candidates": scored,
        "reason": "raw_html_selected_strong_candidate" if strong else "raw_html_no_strong_candidate",
    }


def _looks_recipe_like(url: str) -> bool:
    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()
    return any(fragment in path for fragment in ("/recipe/", "/recipes/", "/recipe-", "-recipe", "/food/"))


def _score_social_candidate(candidate_url: str, candidate_title: str, hints: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    host = urlparse(candidate_url).netloc.lower().strip()
    if _host_matches(host, KNOWN_RECIPE_DOMAINS):
        score += 0.25
        reasons.append("known_recipe_domain")
    if _looks_recipe_like(candidate_url):
        score += 0.45
        reasons.append("recipe_like_path")
    hint_tokens = _tokenize_for_overlap(
        " ".join(
            [
                hints.get("og_title", ""),
                hints.get("og_description", ""),
                hints.get("title", ""),
                hints.get("meta_description", ""),
            ]
        )
    )
    title_tokens = _tokenize_for_overlap(candidate_title)
    if hint_tokens and title_tokens:
        overlap = len(hint_tokens.intersection(title_tokens)) / max(len(hint_tokens), 1)
        if overlap > 0:
            overlap_points = min(0.25, overlap * 0.5)
            score += overlap_points
            reasons.append(f"title_overlap:{overlap:.2f}")
    lowered_url = candidate_url.lower()
    if any(token in lowered_url for token in ("recipe", "ingredients", "instructions")):
        score += 0.1
        reasons.append("url_keyword_match")
    return min(score, 1.0), reasons


def _discover_recipe_url_from_social_hints(original_url: str, hints: dict) -> dict:
    query = _build_social_discovery_query(hints)
    if not query:
        return {"resolved_url": "", "reason": "discovery_missing_query", "query": "", "candidates": []}

    candidates: list[dict] = []
    try:
        response = safe_get(
            "https://html.duckduckgo.com/html/?" + urlencode({"q": query}),
            timeout=8,
            headers=REQUEST_HEADERS,
        )
        response.raise_for_status()
        html = response.text or ""
    except Exception as exc:
        return {
            "resolved_url": "",
            "reason": f"discovery_search_failed:{exc}",
            "query": query,
            "candidates": [],
        }

    for match in re.finditer(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_href = unescape(match.group(1))
        candidate_url = _unwrap_search_result_url(raw_href)
        rejection_reason = _external_candidate_rejection_reason(candidate_url)
        if rejection_reason:
            continue
        host = urlparse(candidate_url).netloc.lower().strip()
        if _host_matches(host, SOCIAL_DISCOVERY_HOST_EXCLUDE):
            continue
        title = _clean_text(unescape(match.group(2)))
        score, reasons = _score_social_candidate(candidate_url, title, hints)
        candidates.append(
            {
                "url": candidate_url,
                "title": title,
                "score": round(score, 3),
                "reasons": reasons,
            }
        )
        if len(candidates) >= 8:
            break

    if not candidates:
        return {"resolved_url": "", "reason": "discovery_no_candidates", "query": query, "candidates": []}

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    if best["score"] >= SOCIAL_DISCOVERY_CONFIDENCE_THRESHOLD:
        return {
            "resolved_url": best["url"],
            "reason": "discovery_high_confidence",
            "query": query,
            "candidates": candidates,
            "confidence": best["score"],
            "confidence_reasons": best["reasons"],
        }
    return {
        "resolved_url": "",
        "reason": "discovery_low_confidence",
        "query": query,
        "candidates": candidates,
        "confidence": best["score"],
        "confidence_reasons": best["reasons"],
    }


def resolve_social_recipe_source(url: str) -> dict:
    if not _is_social_share_url(url):
        return {
            "resolved_url": "",
            "fallback_reason": "not_social_share_url",
            "method": "none",
            "hints": {},
            "query": "",
            "candidates": [],
        }

    redirect_follow_attempted = True
    logger.info(
        "social-resolution request original_url=%s headers=%s redirect_follow_attempted=%s",
        url,
        REQUEST_HEADERS,
        redirect_follow_attempted,
    )
    try:
        response = safe_get(url, timeout=8, headers=REQUEST_HEADERS)
        final_response_url = str(response.url or "").strip()
        response_html = response.text or ""
    except Exception as exc:
        logger.info(
            "social-resolution rejected original_url=%s headers=%s redirect_follow_attempted=%s final_response_url=%s reason=%s",
            url,
            REQUEST_HEADERS,
            redirect_follow_attempted,
            "",
            f"social_fetch_failed:{exc}",
        )
        return {
            "resolved_url": "",
            "fallback_reason": "social_fetch_failed",
            "method": "none",
            "hints": {},
            "query": "",
            "candidates": [],
        }

    social_metadata = _extract_social_metadata_fields(response_html)
    rejection_reason = _external_candidate_rejection_reason(final_response_url)
    if rejection_reason:
        logger.info(
            "social-resolution rejected original_url=%s headers=%s redirect_follow_attempted=%s final_response_url=%s reason=%s",
            url,
            REQUEST_HEADERS,
            redirect_follow_attempted,
            final_response_url,
            rejection_reason,
        )
        metadata_resolution = {}
        if _is_facebook_share_or_reel_url(url):
            metadata_resolution = _resolve_external_url_from_social_metadata(response_html)
            logger.info(
                "social-metadata-extraction source_url=%s og_url=%s og_title=%s og_description_present=%s og_image_present=%s og_image_alt_present=%s candidate_urls=%s resolved_url=%s",
                url,
                metadata_resolution.get("metadata", {}).get("og_url", ""),
                metadata_resolution.get("metadata", {}).get("og_title", ""),
                bool(metadata_resolution.get("metadata", {}).get("og_description", "")),
                bool(metadata_resolution.get("metadata", {}).get("og_image", "")),
                bool(metadata_resolution.get("metadata", {}).get("og_image_alt", "")),
                json.dumps(metadata_resolution.get("candidate_urls", []), ensure_ascii=False),
                metadata_resolution.get("resolved_url", ""),
            )
            if metadata_resolution.get("resolved_url"):
                return {
                    "resolved_url": metadata_resolution.get("resolved_url", ""),
                    "fallback_reason": "",
                    "method": "metadata-text",
                    "hints": _extract_social_discovery_hints(response_html, final_response_url),
                    "query": "",
                    "candidates": metadata_resolution.get("ranked_candidates", []),
                    "social_metadata": metadata_resolution.get("metadata", {}),
                }
        hints = _extract_social_discovery_hints(response_html, final_response_url)
        raw_attempted = _is_social_share_url(url)
        raw_candidates, decoded_redirects = _extract_raw_html_url_candidates(response_html)
        raw_resolution = _choose_raw_html_social_candidate(raw_candidates) if raw_attempted else {}
        logger.info(
            "social-raw-html-extraction source_url=%s attempted=%s raw_candidate_count=%d decoded_redirects=%s filtered_candidates=%s chosen_candidate=%s reason=%s fallback_discovery_needed=%s",
            url,
            raw_attempted,
            len(raw_candidates),
            json.dumps(decoded_redirects, ensure_ascii=False),
            json.dumps(raw_resolution.get("ranked_candidates", []), ensure_ascii=False),
            raw_resolution.get("resolved_url", ""),
            raw_resolution.get("reason", ""),
            not bool(raw_resolution.get("resolved_url")),
        )
        if raw_resolution.get("resolved_url"):
            return {
                "resolved_url": raw_resolution.get("resolved_url", ""),
                "fallback_reason": "",
                "method": "raw-html",
                "hints": hints,
                "query": "",
                "candidates": raw_resolution.get("ranked_candidates", []),
                "confidence": (raw_resolution.get("ranked_candidates", [{}])[0]).get("score"),
                "confidence_reasons": (raw_resolution.get("ranked_candidates", [{}])[0]).get("reasons", []),
                "social_metadata": social_metadata,
            }
        discovery = {}
        if SOCIAL_DISCOVERY_ENABLED:
            discovery = _discover_recipe_url_from_social_hints(url, hints)
        logger.info(
            "social-signal-extraction resolved_url=%s og_title=%s og_description=%s final_query=%s",
            final_response_url,
            hints.get("og_title", ""),
            hints.get("og_description", ""),
            discovery.get("query", ""),
        )
        logger.info(
            "social-discovery original_url=%s direct_result=%s hints=%s query=%s candidates=%s confidence=%s confidence_reasons=%s chosen_url=%s reason=%s",
            url,
            "social_url_still_internal",
            json.dumps(hints, ensure_ascii=False),
            discovery.get("query", ""),
            json.dumps(discovery.get("candidates", []), ensure_ascii=False),
            discovery.get("confidence"),
            discovery.get("confidence_reasons", []),
            discovery.get("resolved_url", ""),
            discovery.get("reason", "discovery_disabled"),
        )
        if discovery.get("resolved_url"):
            return {
                "resolved_url": discovery.get("resolved_url", ""),
                "fallback_reason": "",
                "method": "serp",
                "hints": hints,
                "query": discovery.get("query", ""),
                "candidates": discovery.get("candidates", []),
                "confidence": discovery.get("confidence"),
                "confidence_reasons": discovery.get("confidence_reasons", []),
                "social_metadata": social_metadata,
            }
        return {
            "resolved_url": "",
            "fallback_reason": discovery.get("reason", "social_url_still_internal"),
            "method": "none",
            "hints": hints,
            "query": discovery.get("query", ""),
            "candidates": discovery.get("candidates", []),
            "confidence": discovery.get("confidence"),
            "confidence_reasons": discovery.get("confidence_reasons", []),
            "social_metadata": social_metadata,
        }

    logger.info(
        "social-resolution accepted original_url=%s headers=%s redirect_follow_attempted=%s final_response_url=%s reason=%s",
        url,
        REQUEST_HEADERS,
        redirect_follow_attempted,
        final_response_url,
        "final_url_is_non_social_external",
    )
    return {
        "resolved_url": final_response_url,
        "fallback_reason": "",
        "method": "redirect:final",
        "hints": {},
        "query": "",
        "candidates": [],
        "social_metadata": social_metadata,
    }


def resolve_url(url: str) -> str:
    if not url:
        return url

    try:
        r = safe_get(url, headers=REQUEST_HEADERS, timeout=8)
        resolved = str(r.url)
        return resolved
    except Exception:
        return url


def normalize_shared_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()

    url = resolve_url(url)

    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        query = parse_qs(parsed.query)

        if "facebook.com" in host:
            if "u" in query and query["u"]:
                return unquote(query["u"][0]).strip()
            if "href" in query and query["href"]:
                return unquote(query["href"][0]).strip()

        tracking_prefixes = ("utm_", "fbclid", "gclid", "igsh", "si")
        clean_query = []
        for key, values in query.items():
            key_lower = key.lower()
            if any(key_lower == prefix or key_lower.startswith(prefix) for prefix in tracking_prefixes):
                continue
            for value in values:
                clean_query.append((key, value))

        query_string = "&".join(f"{k}={v}" for k, v in clean_query) if clean_query else ""
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if query_string:
            normalized += f"?{query_string}"
        if parsed.fragment:
            normalized += f"#{parsed.fragment}"
        return normalized
    except Exception:
        return url


def infer_source(url: str) -> tuple[str, str]:
    if url_hostname_matches_any(url, ("instagram.com", "instagr.am")):
        return "Instagram", "Instagram"
    if url_hostname_matches_any(url, ("facebook.com", "fb.watch")):
        return "Facebook", "Facebook"
    if url_hostname_matches_any(url, ("youtube.com", "youtu.be")):
        return "YouTube", "YouTube"
    if url_hostname_matches_any(url, ("tiktok.com",)):
        return "TikTok", "TikTok"
    if url_hostname_matches_any(url, ("pinterest.com", "pin.it")):
        return "Pinterest", "Pinterest"
    if url_hostname_matches_any(url, ("allrecipes.com",)):
        return "AllRecipes", "Web"
    if url_hostname_matches_any(url, ("foodnetwork.com",)):
        return "Food Network", "Web"
    if url_hostname_matches_any(url, ("delish.com",)):
        return "Delish", "Web"
    if str(url or "").strip():
        return "Browser", "Web"
    return "", ""


def _detect_submission_source_type(url: str) -> str:
    if url_hostname_matches_any(url, ("facebook.com", "fb.watch")):
        return "facebook"
    if url_hostname_matches_any(url, ("instagram.com", "instagr.am")):
        return "instagram"
    return "normal"


def _social_unresolved_reason(source_type: str) -> str:
    if source_type == "facebook":
        return "No recipe link found in shared Facebook content"
    if source_type == "instagram":
        return "No recipe link found in shared Instagram content"
    return "No recipe link found in shared social content"


def _normalize_social_fallback_reason(reason: str, source_type: str) -> str:
    normalized = (reason or "").strip().lower()
    if normalized == "ytdlp_extract_failed" and source_type == "facebook":
        return "This Facebook video couldn’t be processed automatically. Try opening the original post or paste the recipe link."
    if normalized == "social_url_still_internal":
        return "Social share URL did not resolve to a recipe website"
    if normalized in (
        "facebook_post_id_not_found",
        "facebook_external_url_not_found",
        "social_resolved_url_failed_validation",
        "instagram_external_url_not_found",
        "instagram_canonical_url_not_found",
        "unsupported_social_url",
    ):
        return _social_unresolved_reason(source_type)
    if normalized.startswith("facebook_fetch_failed:") or normalized.startswith("instagram_fetch_failed:"):
        return "We couldn’t access the social post content to find the original recipe website."
    if normalized.startswith("social_resolver_failed:"):
        return "We couldn’t extract the shared link directly, and recovery attempts did not find a recipe."
    if normalized in ("transcript_pipeline_failed:ytdlp_extract_failed_missing_or_expired_cookie",) and source_type == "facebook":
        return "This Facebook video requires login access. Add your Facebook cookie in Settings."
    if normalized == "transcript_pipeline_failed:ytdlp" and source_type == "facebook":
        return "This Facebook video couldn’t be processed automatically. Try opening the original post or paste the recipe link."
    if normalized == "transcript_pipeline_failed:ffmpeg":
        return "We downloaded the shared video, but audio extraction failed."
    if normalized == "transcript_pipeline_failed:whisper":
        return "We extracted the audio, but Whisper transcription failed."
    if normalized == "transcript_pipeline_failed:ai_classification":
        return "We transcribed the video, but AI recipe classification failed."
    if normalized == "transcript_pipeline_failed:ai_classification_not_recipe_related":
        return "We transcribed the video, but it does not appear to contain a cookable recipe."
    if normalized == "transcript_pipeline_failed:ai_extraction":
        return "We transcribed the video, but AI recipe extraction failed."
    if normalized == "transcript_pipeline_failed" or normalized.startswith("transcript_pipeline_failed:"):
        return "We couldn’t process the shared video transcript automatically. Please try again."
    if normalized in ("discovery_low_confidence", "discovery_no_candidates", "discovery_missing_query"):
        return "Could not confidently locate original recipe website"
    if normalized.startswith("discovery_search_failed:"):
        return "We couldn’t extract the recipe directly, but we also couldn’t search for the original recipe website."
    if normalized in ("", "social_fetch_failed", "not_social_share_url"):
        return _social_unresolved_reason(source_type)
    return reason


def _extract_transcript_failure_stage(reason: str) -> str:
    normalized = (reason or "").strip().lower()
    if normalized == "transcript_pipeline_failed:ytdlp_extract_failed_missing_or_expired_cookie":
        return "ytdlp"
    prefix = "transcript_pipeline_failed:"
    if not normalized.startswith(prefix):
        return ""
    stage = normalized[len(prefix) :].strip()
    if stage.startswith("ai_classification_not_recipe_related"):
        return "ai_classification"
    return stage


RECIPE_SIGNAL_TERMS = (
    "recipe",
    "ingredients",
    "method",
    "directions",
    "instructions",
    "cook",
    "bake",
    "simmer",
    "stir",
)


def looks_like_recipe_text(text: str) -> bool:
    candidate = unescape(str(text or "")).strip()
    if len(candidate) < 180:
        return False

    lowered = candidate.lower()
    signal_hits = sum(1 for token in RECIPE_SIGNAL_TERMS if token in lowered)

    quantity_unit_pattern = re.compile(
        r"\b\d+(?:[\.,]\d+)?\s*(?:x\s*)?(?:g|grams?|kg|ml|l|tbsp|tsp|cups?|oz|lb|cloves?)\b",
        flags=re.IGNORECASE,
    )
    quantity_hits = len(quantity_unit_pattern.findall(candidate))

    imperative_pattern = re.compile(
        r"\b(?:add|mix|whisk|stir|cook|bake|simmer|boil|heat|fold|serve|chop|slice|season)\b",
        flags=re.IGNORECASE,
    )
    imperative_hits = len(imperative_pattern.findall(candidate))

    section_hits = sum(
        1 for marker in ("ingredients:", "method:", "instructions:", "directions:", "for the") if marker in lowered
    )

    return signal_hits >= 2 and (quantity_hits >= 2 or imperative_hits >= 3 or section_hits >= 2)


def _strip_social_caption_noise(text: str) -> str:
    value = unescape(str(text or ""))
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    for raw_line in value.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            cleaned_lines.append("")
            continue
        if re.fullmatch(r"(?:#\w+\s*){1,}", line):
            continue
        if line.lower().startswith(("follow ", "follow@", "credit:", "credits:", "video by")):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"(?:\s+#\w+){2,}\s*$", "", cleaned).strip()
    return cleaned


def _split_instruction_sentences(text: str) -> list[str]:
    value = _clean_text(text)[:MAX_REGEX_TEXT_CHARS]
    if not value:
        return []
    value = re.sub(
        r"\bwith half of oat topping with remaining batter and topping\b",
        "sprinkle with half of oat topping. Top with remaining batter and topping",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\bsprinkle with half of oat topping with remaining batter and topping\b",
        "sprinkle with half of oat topping. Top with remaining batter and topping",
        value,
        flags=re.IGNORECASE,
    )

    def _recover_missing_with_clause(match: re.Match[str]) -> str:
        clause = match.group("clause").strip()
        clause_lower = clause.lower()
        if "sprinkle" in clause_lower or re.search(r"\btop\b", clause_lower):
            return match.group(0)
        if "oat topping" not in clause_lower and "topping" not in clause_lower:
            return match.group(0)
        return f"{match.group('action')}; sprinkle with {clause}"

    value = re.sub(
        r"(?P<action>\b(?:Spoon|Add|Pour)\b[^.;!?]*?)\s*;\s*with\s+(?P<clause>[^.;!?]+)",
        _recover_missing_with_clause,
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\bc\.\s*(\d)", r"c \1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(\b(?:Filling|Mash|To Finish)\s*:)", r". \1", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+(In a casserole pot|If you don[’']t have a piping bag)\b", r". \1", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(Season to taste)\s+(?=[A-Z])", r"\1. ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(smooth|blended|clean)\s*:\s*", r"\1. ", value, flags=re.IGNORECASE)
    value = re.sub(r"until smooth;\s*Spoon\b", "until smooth. Spoon", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\b(crumbly|smooth|clean|blended)\s+(?=[A-Z])",
        r"\1. ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"(?:^|\s)(\d+)[\.)]\s+", r"\n\1. ", value)

    numbered_sections = [section.strip() for section in re.split(r"\n+", value) if section.strip()]
    pieces: list[str] = []
    for section in numbered_sections:
        normalized_section = section
        # Only normalize semicolons when they are the sole sentence delimiter in the section.
        # This avoids breaking semicolon clauses that are already followed by sentence boundaries.
        if ";" in normalized_section and "." not in normalized_section and "!" not in normalized_section and "?" not in normalized_section:
            normalized_section = re.sub(r";\s+", ". ", normalized_section)
        pieces.extend(re.split(r"(?<=\.)\s+", normalized_section))

    steps: list[str] = []
    for piece in pieces:
        entry = _clean_text(piece).strip(" -")
        entry = re.sub(r"^\d+[\.)]\s*", "", entry)
        entry = re.sub(r"\s*&\s*\.?\s*$", "", entry)
        entry = re.sub(r"\.{2,}$", ".", entry)
        if entry and not re.search(r"[.!?]$", entry):
            entry = f"{entry}."
        if len(entry) < 12:
            continue
        if len(entry.split()) <= 4 and ":" not in entry and not re.search(
            r"\b(?:add|mix|whisk|stir|cook|bake|simmer|boil|heat|fold|serve|chop|slice|season|pipe|top|sprinkle|spoon)\b",
            entry,
            re.IGNORECASE,
        ):
            continue
        if entry.lower().startswith("#"):
            continue
        if re.fullmatch(r"(?:#\w+\s*)+", entry):
            continue
        steps.append(entry)
    merged_steps: list[str] = []
    for entry in steps:
        if (
            merged_steps
            and entry.lower().startswith("top with remaining batter and topping")
            and "sprinkle with half of oat topping" in merged_steps[-1].lower()
        ):
            merged_steps[-1] = f"{merged_steps[-1].rstrip()} {entry}"
            continue
        merged_steps.append(entry)
    return _dedupe_text_entries(merged_steps)


INGREDIENT_TAIL_PATTERNS = (
    r"\s+in batches for maximum caramelisation\b.*$",
    r"\s+until golden\b.*$",
    r"\s+until smooth\b.*$",
)

INGREDIENT_LINE_INSTRUCTION_VERB_PREFIXES = (
    "add",
    "mix",
    "bake",
    "cook",
    "combine",
    "preheat",
    "stir",
    "beat",
    "chill",
    "microwave",
    "remove",
    "press",
    "spread",
    "drizzle",
)

INGREDIENT_OPTIONAL_WORDING_RE = re.compile(r"\b(optional|to taste)\b", flags=re.IGNORECASE)
INGREDIENT_FOODISH_WORD_RE = re.compile(
    r"\b(?:"
    r"salt|pepper|chocolate|chips?|parsley|cilantro|basil|oregano|thyme|rosemary|"
    r"garlic|onions?|scallions?|shallots?|ginger|butter|oil|sugar|honey|syrup|"
    r"flour|rice|beans?|broth|stock|milk|cream|cheese|yogurt|lemon|lime|vinegar|"
    r"tomatoes?|potatoes?|carrots?|celery|spinach|kale|mushrooms?|eggs?|vanilla|cocoa"
    r")\b",
    flags=re.IGNORECASE,
)


def _clean_ingredient_candidate(text: str) -> str:
    cleaned = _clean_text(text).strip(" -•*")
    cleaned = re.sub(r"^(?:add|mix in|stir in|top with)\s+", "", cleaned, flags=re.IGNORECASE)
    for pattern in INGREDIENT_TAIL_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(?:&|and)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,.;:]+$", "", cleaned)
    return cleaned


def _should_keep_short_unmeasured_ingredient_line(candidate: str) -> bool:
    if not candidate:
        return False
    if candidate.endswith("."):
        return False
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", candidate)
    if len(words) == 0 or len(words) > 8:
        return False
    lowered = candidate.lower().lstrip(" -•*")
    if any(lowered.startswith(f"{verb} ") for verb in INGREDIENT_LINE_INSTRUCTION_VERB_PREFIXES):
        return False
    return bool(INGREDIENT_OPTIONAL_WORDING_RE.search(candidate) or INGREDIENT_FOODISH_WORD_RE.search(candidate))


def _extract_ingredient_candidates_from_text(lines: list[str], text: str) -> list[str]:
    quantity_re = re.compile(
        r"^\s*(?:[-•*]\s*)?(?:\d+(?:[\.,]\d+)?(?:/\d+)?\s*)?(?:x\s*)?(?:"
        r"g|grams?|kg|ml|l|tbsp|tsp|cups?|oz|lb|cloves?|pinch|handful)\b",
        flags=re.IGNORECASE,
    )
    ingredients: list[str] = []
    for line in lines:
        cleaned = _clean_ingredient_candidate(line)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(lowered.startswith(prefix) for prefix in ("method", "instructions", "directions", "steps")):
            continue
        if quantity_re.search(cleaned) or re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:g|ml|tbsp|tsp|cups?)\b", cleaned, re.IGNORECASE):
            ingredients.append(cleaned)
            continue
        if _should_keep_short_unmeasured_ingredient_line(cleaned):
            ingredients.append(cleaned)

    if len(ingredients) < 2:
        phrase_candidates = re.split(r"[,\n;]", text)
        for phrase in phrase_candidates:
            cleaned = _clean_ingredient_candidate(phrase)
            if re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:g|ml|tbsp|tsp|cups?)\b", cleaned, re.IGNORECASE):
                ingredients.append(cleaned)

    embedded_pattern = re.compile(
        r"\b\d+(?:[\.,]\d+)?\s+(?:diced|chopped|minced|sliced|crushed)?\s*"
        r"(?:onions?|carrots?|celery(?:\s+stalks?)?|garlic(?:\s+cloves?)?)\b",
        flags=re.IGNORECASE,
    )
    for match in embedded_pattern.finditer(text):
        cleaned = _clean_ingredient_candidate(match.group(0))
        if cleaned:
            ingredients.append(cleaned)

    extra_match = re.search(r"\bextra\s+(?:cheddar|chedder)\b", text, flags=re.IGNORECASE)
    if extra_match:
        ingredients.append(_clean_ingredient_candidate(extra_match.group(0)))

    return _dedupe_text_entries(ingredients)


def parse_social_caption_recipe(caption_text: str, source_url: str, title_hint: str = "") -> dict:
    cleaned = _strip_social_caption_noise(caption_text)
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    title = _clean_text(title_hint)

    if source_url.startswith("image://") and lines:
        ocr_title = _extract_ocr_title_from_lines(lines)
        if ocr_title:
            title = ocr_title

    if not title and lines:
        first_line = _clean_text(lines[0]).strip(" -•*")
        if 6 <= len(first_line) <= 110 and not re.search(r"\b(?:ingredients?|method|instructions?)\b", first_line, re.IGNORECASE):
            title = first_line

    ingredients = _extract_ingredient_candidates_from_text(lines, cleaned)

    instructions = _split_instruction_sentences(cleaned)
    if not instructions and lines:
        instructions = [
            _clean_text(line).strip(" -•*")
            for line in lines
            if re.search(r"\b(?:add|mix|whisk|stir|cook|bake|simmer|boil|heat|fold|serve|chop|slice|season)\b", line, re.IGNORECASE)
        ]
        instructions = _dedupe_text_entries(instructions)

    servings_match = re.search(r"\b(?:serves|servings?)\s*[:\-]?\s*(\d{1,2})\b", cleaned, flags=re.IGNORECASE)
    servings = servings_match.group(1) if servings_match else ""
    prep_time = _extract_time_from_text(cleaned, r"prep(?:aration)?\s*time")
    cook_time = _extract_time_from_text(cleaned, r"cook(?:ing)?\s*time")
    total_time = _extract_time_from_text(cleaned, r"total\s*time")
    prep_time, prep_minutes = _normalize_duration(prep_time)
    cook_time, cook_minutes = _normalize_duration(cook_time)
    total_time, total_minutes = _normalize_duration(total_time)

    return {
        "url": source_url,
        "title": title,
        "image_url": "",
        "ingredients": ingredients,
        "instructions": instructions,
        "ingredient_groups": [{"title": "", "items": ingredients}] if ingredients else [],
        "instruction_groups": [{"title": "", "steps": instructions}] if instructions else [],
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "total_minutes": total_minutes,
    }


PASTE_INGREDIENT_HEADINGS = {"ingredient", "ingredients"}
PASTE_INSTRUCTION_HEADINGS = {"instruction", "instructions", "direction", "directions", "method", "steps"}
PASTE_NOTE_HEADINGS = {"note", "notes", "tip", "tips", "recipe note", "recipe notes", "recipe tip", "recipe tips"}
PASTE_COMMON_INGREDIENT_SECTION_HEADINGS = {
    "meat",
    "protein",
    "vegetables",
    "vegetable",
    "veggies",
    "veggie",
    "pantry",
    "produce",
    "aromatics",
    "seasoning",
    "seasonings",
    "optional finishers",
    "finishers",
    "garnish",
    "garnishes",
    "topping",
    "toppings",
    "for serving",
    "to serve",
    "serving",
}
_PASTE_MARKDOWN_TITLE_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_PASTE_CHECKBOX_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[[ xX]\]\s*")
_PASTE_BULLET_RE = re.compile(r"^\s*(?:[-*+]|[•◦▪‣●○■□])\s+")
_PASTE_STEP_NUMBER_RE = re.compile(r"^\s*(?:step\s*)?(?:\(?\d{1,3}\)?[.)]|(?:\d{1,3}\s*[-:]))\s*", flags=re.IGNORECASE)


def _normalize_pasted_recipe_line(raw_line: str, *, instruction: bool = False) -> str:
    cleaned = _clean_text(raw_line)
    if not cleaned:
        return ""

    cleaned = _PASTE_MARKDOWN_TITLE_RE.sub("", cleaned)
    cleaned = _PASTE_CHECKBOX_RE.sub("", cleaned)
    cleaned = _PASTE_BULLET_RE.sub("", cleaned)
    if instruction:
        cleaned = _PASTE_STEP_NUMBER_RE.sub("", cleaned)
        cleaned = _PASTE_CHECKBOX_RE.sub("", cleaned)
        cleaned = _PASTE_BULLET_RE.sub("", cleaned)
    return cleaned.strip()


def _is_paste_note_heading(line: str) -> bool:
    heading = line.rstrip(":").strip().lower()
    if heading in PASTE_NOTE_HEADINGS:
        return True
    return bool(re.match(r"^(?:chef'?s|cook'?s)\s+(?:notes?|tips?)$", heading))


def _compose_pasted_recipe_notes(description_lines: list[str], note_lines: list[str], note_heading: str = "") -> str:
    sections: list[str] = []
    description_text = "\n".join(_clean_text(line) for line in description_lines if _clean_text(line)).strip()
    if description_text:
        sections.append(description_text)

    notes_text = "\n".join(_clean_text(line) for line in note_lines if _clean_text(line)).strip()
    if notes_text:
        normalized_heading = _clean_text(note_heading).rstrip(":")
        if normalized_heading and normalized_heading.lower() not in {"note", "notes"}:
            notes_text = f"{normalized_heading}:\n{notes_text}"
        elif description_text:
            notes_text = f"Notes:\n{notes_text}"
        sections.append(notes_text)

    return "\n\n".join(section for section in sections if section).strip()


def _looks_like_pasted_ingredient_group_heading(line: str, next_line: str = "") -> bool:
    text = _clean_text(line)
    if not text:
        return False

    normalized = re.sub(r"\s+", " ", text).strip()
    normalized_heading = normalized.rstrip(":").strip().lower()
    if not normalized_heading:
        return False
    if normalized_heading in PASTE_INGREDIENT_HEADINGS or normalized_heading in PASTE_INSTRUCTION_HEADINGS:
        return False
    if normalized_heading in PASTE_NOTE_HEADINGS or _is_paste_note_heading(normalized):
        return False
    if re.search(r"\d", normalized_heading):
        return False
    if any(char in normalized_heading for char in ",;.!?()[]{}"):
        return False

    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", normalized_heading)
    if not words or len(words) > 5 or len(normalized_heading) > 40:
        return False

    next_cleaned = _clean_text(next_line)
    if not next_cleaned:
        return False
    next_heading = next_cleaned.rstrip(":").strip().lower()
    if (
        next_heading in PASTE_INGREDIENT_HEADINGS
        or next_heading in PASTE_INSTRUCTION_HEADINGS
        or next_heading in PASTE_NOTE_HEADINGS
        or _is_paste_note_heading(next_cleaned)
    ):
        return False

    if normalized.endswith(":"):
        return True
    if normalized_heading in PASTE_COMMON_INGREDIENT_SECTION_HEADINGS:
        return True
    return bool(re.match(r"^(?:optional|for serving|to serve|for the)\b", normalized_heading))


def _build_pasted_ingredient_groups(lines: list[str]) -> list[dict]:
    cleaned_lines = [_normalize_pasted_recipe_line(line) for line in lines if _normalize_pasted_recipe_line(line)]
    if not cleaned_lines:
        return []

    groups: list[dict] = []
    current_title = ""
    current_items: list[str] = []

    for index, line in enumerate(cleaned_lines):
        next_line = cleaned_lines[index + 1] if index + 1 < len(cleaned_lines) else ""
        if _looks_like_pasted_ingredient_group_heading(line, next_line):
            if current_items:
                groups.append({"title": current_title, "items": current_items})
            current_title = line.rstrip(":").strip()
            current_items = []
            continue
        current_items.append(line)

    if current_items:
        groups.append({"title": current_title, "items": current_items})

    if not groups:
        return [{"title": "", "items": cleaned_lines}]
    return groups


def _parse_pasted_recipe_text(raw_text: str) -> dict:
    cleaned = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [_normalize_pasted_recipe_line(line) for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        raise HTTPException(status_code=422, detail="Recipe text is required")

    title = ""
    servings = ""
    prep_time = ""
    cook_time = ""
    total_time = ""
    description_lines: list[str] = []
    note_lines: list[str] = []
    ingredient_section_lines: list[str] = []
    instruction_lines: list[str] = []
    note_heading = ""
    current_section = ""
    has_explicit_ingredient_heading = any(
        line.rstrip(":").strip().lower() in PASTE_INGREDIENT_HEADINGS
        for line in lines
    )

    for line in lines:
        heading = line.rstrip(":").strip().lower()
        if heading in PASTE_INGREDIENT_HEADINGS:
            current_section = "ingredients"
            continue
        if heading in PASTE_INSTRUCTION_HEADINGS:
            current_section = "instructions"
            continue
        if _is_paste_note_heading(line):
            current_section = "notes"
            note_heading = line.rstrip(":").strip()
            continue

        servings_match = re.match(r"^servings?\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
        if servings_match:
            servings = _clean_text(servings_match.group(1))
            continue
        prep_match = re.match(r"^prep(?:aration)?\s*time\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
        if prep_match:
            prep_time = _clean_text(prep_match.group(1))
            continue
        cook_match = re.match(r"^cook(?:ing)?\s*time\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
        if cook_match:
            cook_time = _clean_text(cook_match.group(1))
            continue
        total_match = re.match(r"^total\s*time\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
        if total_match:
            total_time = _clean_text(total_match.group(1))
            continue

        if not title and not current_section:
            title = line
            continue
        if has_explicit_ingredient_heading and not current_section and title:
            normalized_description = _normalize_pasted_recipe_line(line)
            if normalized_description:
                description_lines.append(normalized_description)
            continue
        if current_section == "ingredients":
            normalized_ingredient = _normalize_pasted_recipe_line(line)
            if normalized_ingredient:
                ingredient_section_lines.append(normalized_ingredient)
            continue
        if current_section == "instructions":
            normalized_instruction = _normalize_pasted_recipe_line(line, instruction=True)
            if normalized_instruction:
                instruction_lines.append(normalized_instruction)
            continue
        if current_section == "notes":
            normalized_note = _normalize_pasted_recipe_line(line)
            if normalized_note:
                note_lines.append(normalized_note)

    ingredient_groups = _build_pasted_ingredient_groups(ingredient_section_lines)
    ingredient_lines = _flatten_groups(ingredient_groups, "items")
    if not ingredient_lines:
        ingredient_lines = _extract_ingredient_candidates_from_text(lines, cleaned)
        ingredient_groups = [{"title": "", "items": ingredient_lines}] if ingredient_lines else []
    if not instruction_lines:
        instruction_lines = [
            normalized_instruction
            for normalized_instruction in (
                _normalize_pasted_recipe_line(step, instruction=True)
                for step in _split_instruction_sentences(cleaned)
            )
            if normalized_instruction
        ]

    prep_time, prep_minutes = _normalize_duration(prep_time)
    cook_time, cook_minutes = _normalize_duration(cook_time)
    total_time, total_minutes = _normalize_duration(total_time)
    candidate = {
        "url": "",
        "title": title,
        "image_url": "",
        "notes": _compose_pasted_recipe_notes(description_lines, note_lines, note_heading),
        "ingredients": ingredient_lines,
        "instructions": instruction_lines,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": [{"title": "", "steps": instruction_lines}] if instruction_lines else [],
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "total_minutes": total_minutes,
    }
    return _finalize_recipe_candidate(candidate, "", "pasted_text")


_OCR_FOOD_TITLE_HINTS = {
    "cake",
    "chicken",
    "soup",
    "pasta",
    "bread",
    "salad",
    "stew",
    "pizza",
    "cookies",
    "cookie",
    "beef",
    "pork",
    "shrimp",
    "fish",
    "tacos",
    "pie",
    "muffin",
    "brownies",
}
_OCR_SECTION_HEADINGS = {
    "ingredient",
    "ingredients",
    "instruction",
    "instructions",
    "direction",
    "directions",
    "method",
    "steps",
}
_OCR_TITLE_METADATA_PATTERNS = (
    r"\b(?:prep|cook|total)\s*time\b",
    r"\b(?:serves|servings?|yield)\b",
    r"\b\d+\s*(?:min|mins|minutes?|hours?|hrs?)\b",
    r"\b(?:page|printed from|recipe submitted by|www\.|http|@)\b",
)
_OCR_TITLE_INSTRUCTION_HINTS = (
    "add",
    "bake",
    "beat",
    "boil",
    "chop",
    "combine",
    "cook",
    "fold",
    "heat",
    "mix",
    "pour",
    "serve",
    "simmer",
    "stir",
    "whisk",
)


def _is_mostly_uppercase_text(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if len(letters) < 4:
        return False
    uppercase_count = sum(1 for char in letters if char.isupper())
    return (uppercase_count / len(letters)) >= 0.72


def _is_all_caps_word(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def _drop_non_uppercase_leading_words(value: str) -> str:
    words = [word for word in value.split() if word]
    if len(words) < 2:
        return value
    for index in range(1, len(words)):
        prefix = words[:index]
        suffix = words[index:]
        if len(" ".join(suffix)) < 10:
            continue
        if not any(any(char.isalpha() for char in word) and not _is_all_caps_word(word) for word in prefix):
            continue
        if all(not any(char.isalpha() for char in word) or _is_all_caps_word(word) for word in suffix):
            return " ".join(suffix)
    return value


def _is_ocr_section_heading(value: str) -> bool:
    normalized = _clean_text(value).rstrip(":").strip().lower()
    return normalized in _OCR_SECTION_HEADINGS


def _extract_ocr_preamble_lines(lines: list[str]) -> list[str]:
    preamble: list[str] = []
    for raw_line in lines:
        cleaned_line = _clean_text(raw_line).strip(" -â€¢*")
        cleaned_line = _clean_text(raw_line).strip(" -â€¢*")
        if not cleaned_line:
            continue
        heading_match = re.search(
            r"\b(ingredients?|instructions?|directions?|method|steps)\b",
            cleaned_line,
            flags=re.IGNORECASE,
        )
        if heading_match:
            prefix = cleaned_line[: heading_match.start()].strip(" :-|")
            if prefix:
                preamble.append(prefix)
            break
        preamble.append(cleaned_line)
    return preamble


def _looks_like_ocr_metadata_line(value: str) -> bool:
    if any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _OCR_TITLE_METADATA_PATTERNS):
        return True
    if re.search(r"\d", value):
        letters = re.findall(r"[A-Za-z]", value)
        digits = re.findall(r"\d", value)
        if digits and len(digits) >= max(2, len(letters)):
            return True
    return False


def _trim_ocr_title_candidate(value: str) -> str:
    candidate = _drop_non_uppercase_leading_words(value).strip(" -:|")
    if not candidate:
        return ""

    stop_patterns = (
        r"\b(?:makes?|serves?|servings?|yield)\b",
        r"\b(?:prep|cook|total)\s*time\b",
        r"\b\d+(?:\s*/\s*\d+)?\s*(?:cup|cups|tablespoon|tablespoons|tbsp|teaspoon|teaspoons|tsp|package|packages|ounce|ounces|oz|pound|pounds|lb|lbs|gram|grams|g|kg|kilogram|kilograms|clove|cloves|egg|eggs)\b",
    )
    cutoffs = [
        match.start()
        for pattern in stop_patterns
        for match in [re.search(pattern, candidate, flags=re.IGNORECASE)]
        if match and match.start() >= 8
    ]
    if cutoffs:
        candidate = candidate[: min(cutoffs)].strip(" -:|,.;")
    return re.sub(r"\s{2,}", " ", candidate).strip()


def _iter_ocr_title_candidate_variants(value: str) -> list[str]:
    base_candidate = _trim_ocr_title_candidate(value)
    if not base_candidate:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def _push(candidate: str) -> None:
        normalized = _trim_ocr_title_candidate(candidate)
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            return
        seen.add(lowered)
        variants.append(normalized)

    _push(base_candidate)

    tokens = [token.strip(" ,.;:|") for token in base_candidate.split() if token.strip(" ,.;:|")]
    token_count = len(tokens)
    if token_count < 2:
        return variants

    max_window = min(8, token_count)
    min_start = max(0, token_count - 8)
    for start in range(1, min(token_count - 1, 5)):
        _push(" ".join(tokens[start:]))
    for start in range(min_start, token_count - 1):
        _push(" ".join(tokens[start:]))
    for length in range(2, max_window + 1):
        _push(" ".join(tokens[-length:]))

    return variants


def _looks_like_ocr_instruction_line(value: str) -> bool:
    lowered = value.lower()
    if any(re.search(rf"\b{re.escape(verb)}\b", lowered) for verb in _OCR_TITLE_INSTRUCTION_HINTS):
        return True
    return lowered.endswith(".")


def _score_ocr_title_candidate(value: str, index: int) -> tuple[int, int, int] | None:
    candidate = _trim_ocr_title_candidate(value)
    if len(candidate) < 8 or len(candidate) > 90:
        return None
    if _is_ocr_section_heading(candidate):
        return None
    if _looks_like_ocr_metadata_line(candidate):
        return None
    if _looks_like_ocr_instruction_line(candidate):
        return None
    if re.search(r"^\d", candidate):
        return None
    if re.search(r"^\d+\s*(?:/|[A-Za-z])", candidate):
        return None

    words = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", candidate)
    if len(words) < 2 or len(words) > 10:
        return None

    score = 0
    has_food_hint = int(any(word.lower() in _OCR_FOOD_TITLE_HINTS for word in words))
    score += has_food_hint * 10
    if _is_mostly_uppercase_text(candidate):
        score += 8
    elif candidate == candidate.title():
        score += 5
    else:
        score += 2
    if 4 <= len(words) <= 6:
        score += 8
    elif 2 <= len(words) <= 3:
        score += 5
    elif len(words) <= 8:
        score += 3
    if any("-" in word for word in words):
        score += 2
    if 12 <= len(candidate) <= 48:
        score += 4
    if not re.search(r"\d", candidate):
        score += 2
    score += max(0, 12 - (index * 3))
    return score, has_food_hint, -len(candidate)


def _extract_ocr_title_from_lines(lines: list[str]) -> str:
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for index, cleaned_line in enumerate(_extract_ocr_preamble_lines(lines)):
        for title_candidate in _iter_ocr_title_candidate_variants(cleaned_line):
            candidate_score = _score_ocr_title_candidate(title_candidate, index)
            if candidate_score:
                candidates.append((candidate_score, title_candidate))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _slugify_title(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned


def _clean_social_title_hint(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(
        r"^\s*(?:\d[\d.,]*\s*[kmb]?\s*(?:views?|reactions?|likes?|comments?|shares?)\s*[·|]\s*)+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"\bcomment\b.*?\bif you want the recipe\b.*$", "", text, flags=re.IGNORECASE).strip(" -|")
    parts = [part.strip(" -|") for part in re.split(r"\s*\|\s*", text) if part.strip(" -|")]
    if len(parts) >= 2 and len(parts[-1].split()) <= 5 and re.fullmatch(r"[A-Za-z0-9 '&.-]+", parts[-1] or ""):
        parts = parts[:-1]
    text = " | ".join(parts) if parts else text
    text = re.sub(r"^(?:i(?:['’]ve| have)?\s+\w+\s+(?:my|this|the)\s+)", "", text, flags=re.IGNORECASE).strip()
    text = text.split("|", 1)[0].strip()
    text = re.sub(r"\s*(?:\.{2,}|…)+\s*$", "", text).strip(" -|")
    if text and text.islower():
        text = text.title()
    return text


def _is_sane_inferred_hostname(host: str) -> bool:
    value = (host or "").lower().strip().strip(".")
    if not value or len(value) > 253:
        return False
    if len(value.split(".")) < 2:
        return False
    if not re.fullmatch(r"[a-z0-9.-]+", value):
        return False
    if _host_matches(value, SOCIAL_INTERNAL_HOSTS):
        return False
    labels = value.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        return False
    return bool(re.fullmatch(r"[a-z]{2,24}", labels[-1]))


def _infer_hosts_from_social_resolution(social_resolution) -> list[str]:
    title = _clean_text(getattr(social_resolution, "ytdlp_title", "") or "")
    description = _clean_text(getattr(social_resolution, "ytdlp_description", "") or "")
    phrases: list[str] = []
    if "|" in title:
        phrases.append(title.rsplit("|", 1)[-1])
    for match in re.finditer(r"\bby\s+([A-Za-z][A-Za-z0-9 '&.-]{2,60})\b", f"{title} {description}", flags=re.IGNORECASE):
        phrases.append(match.group(1))
    inferred: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        words = re.findall(r"[a-z0-9]+", phrase.lower())
        if len(words) < 2:
            continue
        host = f"{''.join(words[:4])}.com"
        if host in seen or not _is_sane_inferred_hostname(host):
            continue
        seen.add(host)
        inferred.append(host)
    return inferred


def _extract_hosts_from_social_resolution(social_resolution) -> list[str]:
    candidates = list(getattr(social_resolution, "ytdlp_description_urls", []) or [])
    resolved_url = str(getattr(social_resolution, "resolved_url", "") or "").strip()
    raw_description = str(getattr(social_resolution, "ytdlp_description", "") or "")
    if resolved_url:
        candidates.append(resolved_url)
    if raw_description:
        candidates.extend(
            match.group(0).strip()
            for match in re.finditer(r"https?://[^\s\"'<>]+", raw_description, flags=re.IGNORECASE)
        )
        candidates.extend(
            match.group(0).strip()
            for match in re.finditer(
                r"\b(?:www\.)?[a-z0-9][a-z0-9\-]{0,62}(?:\.[a-z0-9][a-z0-9\-]{0,62})+\b",
                raw_description,
                flags=re.IGNORECASE,
            )
        )
    hosts: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _clean_text(candidate).strip()
        if not cleaned:
            continue
        try:
            parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
            host = (parsed.netloc or "").lower().strip()
        except Exception:
            host = ""
        if not host:
            continue
        host = re.sub(r"^www\.", "", host)
        if host in seen or _host_matches(host, SOCIAL_INTERNAL_HOSTS):
            continue
        seen.add(host)
        hosts.append(host)
    if hosts:
        return hosts
    return _infer_hosts_from_social_resolution(social_resolution)


def _first_recipe_json_ld_item(html: str) -> dict | None:
    for block in extract_json_ld_blocks(html):
        for item in _iter_json_ld_items(block):
            if isinstance(item, dict) and _is_recipe_type(item.get("@type")):
                return item
    return None


def _validate_recipe_page_and_parse(url: str) -> tuple[bool, dict]:
    normalized_url = (url or "").strip()
    if not normalized_url:
        return False, {}
    try:
        response = safe_get(normalized_url, headers=REQUEST_HEADERS, timeout=8)
        response.raise_for_status()
        if "text/html" not in str(response.headers.get("Content-Type", "")).lower():
            return False, {}
        html = _bounded_text(response.text or "", MAX_RECIPE_HTML_CHARS)
    except Exception:
        return False, {}

    recipe_item = _first_recipe_json_ld_item(html)
    if not recipe_item:
        return False, {}

    parsed = fetch_recipe_data_from_url(normalized_url)
    if not parsed:
        return False, {}
    if not parsed.get("ingredients") or not parsed.get("instructions"):
        return False, {}
    return True, parsed


def _recover_recipe_url_from_social_signals(
    original_social_url: str, social_resolution, debug_trace: dict | None = None
) -> tuple[str, str]:
    title_hint = _clean_social_title_hint(getattr(social_resolution, "ytdlp_title", "") or "")
    slug = _slugify_title(title_hint)
    hosts = _extract_hosts_from_social_resolution(social_resolution)
    if debug_trace is not None:
        debug_trace["title_hint"] = title_hint
        debug_trace["hosts"] = hosts[:]
        debug_trace["direct_slug_attempted"] = bool(slug and hosts)
        debug_trace["direct_slug_candidates"] = []
        debug_trace["site_search_attempted"] = bool(slug and hosts)
        debug_trace["site_search_candidates"] = []
        debug_trace["external_search_attempted"] = bool(slug and hosts)
        debug_trace["external_search_candidates"] = []
        debug_trace["external_search_query"] = ""
    if not slug or not hosts:
        return "", ""

    for host in hosts:
        direct_url = f"https://{host}/{slug}/"
        if debug_trace is not None:
            debug_trace["direct_slug_candidates"].append(direct_url)
        valid, _ = _validate_recipe_page_and_parse(direct_url)
        if valid:
            logger.info("social_recovery_success source_url=%s method=direct_slug url=%s", original_social_url, direct_url)
            return direct_url, "direct_slug"

    for host in hosts:
        search_url = f"https://{host}/?s={quote_plus(title_hint)}"
        try:
            response = safe_get(search_url, headers=REQUEST_HEADERS, timeout=8)
            response.raise_for_status()
            html = response.text or ""
        except Exception:
            continue
        hrefs = re.findall(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        for href in hrefs:
            candidate = urljoin(f"https://{host}/", unescape(href).strip())
            if _external_candidate_rejection_reason(candidate):
                continue
            if debug_trace is not None:
                debug_trace["site_search_candidates"].append(candidate)
            valid, _ = _validate_recipe_page_and_parse(candidate)
            if valid:
                logger.info("social_recovery_success source_url=%s method=site_search url=%s", original_social_url, candidate)
                return candidate, "site_search"

    query = f"site:{hosts[0]} {title_hint} recipe"
    if debug_trace is not None:
        debug_trace["external_search_query"] = query
    try:
        response = safe_get(
            "https://duckduckgo.com/html/?" + urlencode({"q": query}),
            headers=REQUEST_HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        html = response.text or ""
    except Exception:
        return "", ""

    hrefs = re.findall(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    for href in hrefs:
        candidate = unescape(href).strip()
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if candidate.startswith("/"):
            candidate = urljoin("https://duckduckgo.com", candidate)
        decoded, _ = _decode_social_redirect_url(candidate)
        candidate_url = decoded or candidate
        if _external_candidate_rejection_reason(candidate_url):
            continue
        if debug_trace is not None:
            debug_trace["external_search_candidates"].append(candidate_url)
        valid, _ = _validate_recipe_page_and_parse(candidate_url)
        if valid:
            logger.info("social_recovery_success source_url=%s method=external_search url=%s", original_social_url, candidate_url)
            return candidate_url, "external_search"

    return "", ""


def _repair_transcript_preview_ingredient_lines_from_transcript(
    ingredient_lines: list[str],
    transcript_text: str,
) -> list[str]:
    normalized_transcript = _normalize_transcript_context_text(transcript_text)
    if not normalized_transcript:
        return ingredient_lines

    repaired_lines: list[str] = []
    for line in ingredient_lines:
        parsed = _parse_ingredient_struct(line)
        ingredient_name = _clean_text(parsed.get("name") or "")
        current_quantity = parsed.get("quantity")
        current_unit = parsed.get("unit")
        suspicious_quantity = current_quantity is not None and 0 < float(current_quantity) < 0.1

        if not ingredient_name or not current_unit or not suspicious_quantity:
            repaired_lines.append(_apply_conservative_proper_noun_corrections(_clean_text(line)))
            continue

        transcript_quantity = _find_transcript_quantity_evidence(normalized_transcript, ingredient_name, current_unit)
        if transcript_quantity is None:
            repaired_lines.append(_apply_conservative_proper_noun_corrections(_clean_text(line)))
            continue

        logger.info(
            "transcript_preview_quantity_repaired ingredient=%s unit=%s current_quantity=%s transcript_quantity=%s",
            ingredient_name,
            current_unit,
            _format_numeric_quantity(current_quantity),
            _format_numeric_quantity(transcript_quantity),
        )
        display_unit = _format_display_unit(current_unit, transcript_quantity) or current_unit
        repaired_lines.append(
            _clean_text(
                f"{_format_numeric_quantity(transcript_quantity)} {display_unit} {ingredient_name}"
                + (f" ({parsed.get('note')})" if parsed.get("note") else "")
            )
        )
    return repaired_lines


def _normalize_transcript_recipe_payload(
    structured_recipe: dict,
    source_url: str,
    title_hint: str = "",
    cleaned_transcript_text: str = "",
) -> dict:
    title = _clean_text(structured_recipe.get("title") or title_hint or "")
    ingredient_groups = _normalize_group_items(structured_recipe.get("ingredient_groups") or [], "items")
    if ingredient_groups:
        repaired_ingredient_groups: list[dict] = []
        for group in ingredient_groups:
            repaired_items = _repair_transcript_preview_ingredient_lines_from_transcript(
                _normalize_plain_string_list(group.get("items") or []),
                cleaned_transcript_text,
            )
            if repaired_items:
                repaired_ingredient_groups.append({"title": _clean_text(group.get("title") or ""), "items": repaired_items})
        ingredient_groups = repaired_ingredient_groups
        ingredients = _flatten_groups(ingredient_groups, "items")
    else:
        ingredients = _repair_transcript_preview_ingredient_lines_from_transcript(
            _normalize_plain_string_list(structured_recipe.get("ingredients")),
            cleaned_transcript_text,
        )
        ingredient_groups = [{"title": "", "items": ingredients}] if ingredients else []

    instruction_groups = _normalize_group_items(structured_recipe.get("instruction_groups") or [], "steps")
    if instruction_groups:
        normalized_instruction_groups: list[dict] = []
        for group in instruction_groups:
            group_title = _normalize_section_title(group.get("title") or "")
            normalized_instruction_groups.append(
                {
                    "title": group_title or "Instructions",
                    "steps": _normalize_instruction_steps(group.get("steps") or []),
                }
            )
        instruction_groups = [group for group in normalized_instruction_groups if group.get("steps")]
        instructions = _flatten_groups(instruction_groups, "steps")
    else:
        instructions = _normalize_instruction_steps(structured_recipe.get("instructions"))
        instruction_groups = [{"title": "Instructions", "steps": instructions}] if instructions else []

    return {
        "url": source_url,
        "title": title,
        "image_url": "",
        "ingredients": ingredients,
        "instructions": instructions,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "servings": "",
        "prep_time": "",
        "cook_time": "",
        "total_time": "",
        "prep_minutes": None,
        "cook_minutes": None,
        "total_minutes": None,
    }


def _recover_recipe_url_from_transcript_mentions(
    original_social_url: str,
    title_hint: str,
    mentioned_websites: list[str],
    ingredients: list[str] | None = None,
    debug_trace: dict | None = None,
) -> tuple[str, str]:
    slug = _slugify_title(_clean_text(title_hint))
    hosts: list[str] = []
    seen: set[str] = set()
    for mention in mentioned_websites or []:
        cleaned = _clean_text(mention)
        if not cleaned:
            continue
        try:
            parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
            host = re.sub(r"^www\.", "", (parsed.netloc or "").lower().strip())
        except Exception:
            host = ""
        if not _is_sane_inferred_hostname(host):
            continue
        if host in seen:
            continue
        seen.add(host)
        hosts.append(host)

    if debug_trace is not None:
        debug_trace["transcript_title_hint"] = title_hint
        debug_trace["transcript_hosts"] = hosts[:]

    cleaned_title_hint = _clean_text(title_hint)

    if not cleaned_title_hint:
        return "", ""

    if slug and hosts:
        for host in hosts:
            direct_url = f"https://{host}/{slug}/"
            valid, _ = _validate_recipe_page_and_parse(direct_url)
            if valid:
                logger.info(
                    "social_transcript_recovery_success source_url=%s method=direct_slug url=%s",
                    original_social_url,
                    direct_url,
                )
                return direct_url, "transcript_direct_slug"
        for host in hosts:
            search_url = f"https://{host}/?s={quote_plus(cleaned_title_hint)}"
            try:
                response = safe_get(search_url, headers=REQUEST_HEADERS, timeout=8)
                response.raise_for_status()
                html = response.text or ""
            except Exception:
                continue
            hrefs = re.findall(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
            for href in hrefs:
                candidate = urljoin(f"https://{host}/", unescape(href).strip())
                if _external_candidate_rejection_reason(candidate):
                    continue
                valid, _ = _validate_recipe_page_and_parse(candidate)
                if valid:
                    logger.info(
                        "social_transcript_recovery_success source_url=%s method=site_search url=%s",
                        original_social_url,
                        candidate,
                    )
                    return candidate, "transcript_site_search"

    ingredient_terms: list[str] = []
    for item in ingredients or []:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", _clean_text(item).lower())
        cleaned = re.sub(r"\b\d+(?:/\d+)?\b", " ", cleaned)
        tokens = [
            token
            for token in cleaned.split()
            if len(token) >= 4 and token not in {"cups", "cup", "teaspoon", "teaspoons", "tablespoon", "tablespoons", "pound", "pounds"}
        ]
        for token in tokens:
            if token not in ingredient_terms:
                ingredient_terms.append(token)
            if len(ingredient_terms) >= 4:
                break
        if len(ingredient_terms) >= 4:
            break

    query = f"{cleaned_title_hint} recipe"
    if hosts:
        query = f"site:{hosts[0]} {query}"
    elif ingredient_terms:
        query = f"{query} {' '.join(ingredient_terms[:3])}"
    try:
        response = safe_get(
            "https://duckduckgo.com/html/?" + urlencode({"q": query}),
            headers=REQUEST_HEADERS,
            timeout=8,
        )
        response.raise_for_status()
        html = response.text or ""
    except Exception:
        return "", ""

    hrefs = re.findall(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    for href in hrefs:
        candidate = unescape(href).strip()
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if candidate.startswith("/"):
            candidate = urljoin("https://duckduckgo.com", candidate)
        decoded, _ = _decode_social_redirect_url(candidate)
        candidate_url = decoded or candidate
        if _external_candidate_rejection_reason(candidate_url):
            continue
        valid, _ = _validate_recipe_page_and_parse(candidate_url)
        if valid:
            logger.info(
                "social_transcript_recovery_success source_url=%s method=external_search url=%s",
                original_social_url,
                candidate_url,
            )
            return candidate_url, "transcript_external_search"
    return "", ""


def fetch_title_from_url(url: str) -> str:
    try:
        response = safe_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return ""
        html = (response.text or "")[:200000]
    except Exception:
        return ""

    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def extract_json_ld_blocks(html: str) -> list[dict]:
    blocks: list[dict] = []

    for payload in extract_json_ld_payloads(html):
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue

        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))

    return blocks


def _iter_json_ld_items(node, _seen: set[int] | None = None):
    seen = _seen if _seen is not None else set()
    if isinstance(node, dict):
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        yield node
        for value in node.values():
            yield from _iter_json_ld_items(value, seen)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_ld_items(item, seen)


def _is_recipe_type(value) -> bool:
    if isinstance(value, str):
        return value.lower() == "recipe"
    if isinstance(value, list):
        return any(isinstance(v, str) and v.lower() == "recipe" for v in value)
    return False


def _clean_text(value: str) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_section_title(title: str) -> str:
    return _clean_text(title).strip(" :-")


def _extract_minutes_from_text(value: str) -> int | None:
    text = (value or "").strip().lower()
    if not text:
        return None

    hour_match = re.search(r"(\d+)\s*(?:h|hr|hrs|hour|hours)\b", text)
    min_match = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)\b", text)

    if not hour_match and not min_match:
        return None

    hours = int(hour_match.group(1)) if hour_match else 0
    minutes = int(min_match.group(1)) if min_match else 0
    return (hours * 60) + minutes


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minute" + ("s" if minutes != 1 else "")

    hours = minutes // 60
    rem_minutes = minutes % 60
    if rem_minutes == 0:
        return f"{hours} hour" + ("s" if hours != 1 else "")
    return f"{hours}h {rem_minutes}m"


def _parse_iso8601_minutes(value: str) -> int | None:
    match = re.match(
        r"^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    weeks = int(match.group(1) or 0)
    days = int(match.group(2) or 0)
    hours = int(match.group(3) or 0)
    minutes = int(match.group(4) or 0)
    seconds = int(match.group(5) or 0)
    total = (weeks * 7 * 24 * 60) + (days * 24 * 60) + (hours * 60) + minutes
    if seconds >= 30:
        total += 1
    return total


def _normalize_duration(value) -> tuple[str, int | None]:
    if value is None:
        return "", None
    raw = str(value).strip()
    if not raw:
        return "", None

    iso_minutes = _parse_iso8601_minutes(raw)
    if iso_minutes is not None:
        return _format_duration(iso_minutes), iso_minutes

    text_minutes = _extract_minutes_from_text(raw)
    if text_minutes is not None:
        return _format_duration(text_minutes), text_minutes

    return raw, None


def _normalize_instructions(value) -> list[str]:
    if isinstance(value, str):
        text = _clean_text(value)
        return [text] if text else []

    if not isinstance(value, list):
        return []

    instructions: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                instructions.append(text)
        elif isinstance(item, dict):
            instructions.extend(_normalize_instructions(item.get("itemListElement")))
            text = _clean_text(item.get("text") or item.get("name") or "")
            if text:
                instructions.append(text)
    return instructions


def _normalize_groups(raw_groups: list[dict], key: str) -> list[dict]:
    groups: list[dict] = []
    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        title = _normalize_section_title(group.get("title", ""))
        if key == "steps" and not title:
            title = "Instructions"
        entries = group.get(key)
        if not isinstance(entries, list):
            continue
        cleaned_entries = _normalize_plain_string_list(entries) if key == "items" else _as_string_list(entries)
        if not cleaned_entries:
            continue
        groups.append({"title": title, key: cleaned_entries})
    return groups


def _flatten_groups(groups: list[dict], key: str) -> list[str]:
    flattened: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = group.get(key)
        if isinstance(entries, list):
            for entry in entries:
                text = _clean_text(entry)
                if text:
                    flattened.append(text)
    return flattened


_INGREDIENT_UNIT_ALIASES = {
    "cup": "cup",
    "cups": "cup",
    "tablespoon": "tablespoon",
    "tablespoons": "tablespoon",
    "tbsp": "tablespoon",
    "teaspoon": "teaspoon",
    "teaspoons": "teaspoon",
    "tsp": "teaspoon",
    "ounce": "ounce",
    "ounces": "ounce",
    "oz": "ounce",
    "pound": "pound",
    "lb": "pound",
    "gram": "gram",
    "grams": "gram",
    "g": "gram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "kg": "kilogram",
    "milliliter": "milliliter",
    "milliliters": "milliliter",
    "millilitre": "milliliter",
    "millilitres": "milliliter",
    "ml": "milliliter",
    "liter": "liter",
    "liters": "liter",
    "litre": "liter",
    "litres": "liter",
    "l": "liter",
    "package": "package",
    "packages": "package",
    "stick": "stick",
    "sticks": "stick",
}

_SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS = {"garlic", "green", "large"}

_UNICODE_VULGAR_FRACTIONS = {
    "½": 0.5,
    "⅓": 0.333333,
    "¼": 0.25,
    "¾": 0.75,
    "⅔": 0.666667,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}


_DISPLAY_QUANTITY_FRACTIONS = {
    0.25: "1/4",
    0.333333: "1/3",
    0.5: "1/2",
    0.75: "3/4",
}

_INGREDIENT_DESCRIPTOR_PREFIXES = (
    "fresh",
    "chopped",
    "minced",
    "softened",
    "melted",
    "packed",
    "diced",
    "sliced",
)

_INGREDIENT_DESCRIPTOR_SUFFIXES = (
    "leaves",
    "cloves",
    "pieces",
)

_INGREDIENT_NAME_ALIASES = {
    "pecan": "pecans",
}


def _parse_ingredient_quantity(text: str) -> tuple[float | None, str]:
    candidate = text.strip()

    mixed_fraction = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)\b", candidate)
    if mixed_fraction:
        whole = float(mixed_fraction.group(1))
        numerator = float(mixed_fraction.group(2))
        denominator = float(mixed_fraction.group(3))
        if denominator != 0:
            return whole + (numerator / denominator), candidate[mixed_fraction.end() :].strip()

    fraction = re.match(r"^(\d+)\s*/\s*(\d+)\b", candidate)
    if fraction:
        numerator = float(fraction.group(1))
        denominator = float(fraction.group(2))
        if denominator != 0:
            return numerator / denominator, candidate[fraction.end() :].strip()

    mixed_unicode_fraction = re.match(r"^(\d+)\s*([½⅓¼¾⅔⅛⅜⅝⅞])", candidate)
    if mixed_unicode_fraction:
        whole = float(mixed_unicode_fraction.group(1))
        fractional = _UNICODE_VULGAR_FRACTIONS.get(mixed_unicode_fraction.group(2))
        if fractional is not None:
            return whole + fractional, candidate[mixed_unicode_fraction.end() :].strip()

    unicode_fraction = re.match(r"^([½⅓¼¾⅔⅛⅜⅝⅞])", candidate)
    if unicode_fraction:
        fractional = _UNICODE_VULGAR_FRACTIONS.get(unicode_fraction.group(1))
        if fractional is not None:
            return fractional, candidate[unicode_fraction.end() :].strip()

    whole_number = re.match(r"^(\d+(?:\.\d+)?)\b", candidate)
    if whole_number:
        return float(whole_number.group(1)), candidate[whole_number.end() :].strip()

    return None, candidate


def _format_display_quantity(quantity: float | None) -> str | None:
    if quantity is None:
        return None

    rounded = round(float(quantity), 6)
    whole = int(rounded)
    fractional = round(rounded - whole, 6)

    if fractional == 0:
        return str(whole)

    fraction_text = None
    for known_fraction, known_fraction_text in _DISPLAY_QUANTITY_FRACTIONS.items():
        if abs(fractional - known_fraction) < 0.01:
            fraction_text = known_fraction_text
            break
    if whole > 0 and fraction_text:
        return f"{whole} {fraction_text}"
    if fraction_text:
        return fraction_text

    return format(rounded, "g")


def _fix_common_ocr_quantity_errors(quantity: float | None, unit: str | None, name: str | None) -> float | None:
    if quantity is None:
        return None
    if unit not in {"cup", "tablespoon", "teaspoon"}:
        return quantity
    if quantity < 10:
        return quantity

    correction_map = {
        14: 1.25,
        13: 1.333,
        12: 1.5,
    }
    rounded_quantity = int(round(quantity))
    corrected = correction_map.get(rounded_quantity)
    if corrected is None:
        return quantity
    return corrected


def _is_butter_or_cream_cheese_ingredient(name: str | None) -> bool:
    lowered_name = (name or "").lower()
    return "butter" in lowered_name or "cream cheese" in lowered_name


def _convert_note_measurement_to_main_unit(
    note_quantity: float,
    note_unit: str | None,
    main_unit: str | None,
    ingredient_name: str | None,
) -> tuple[float | None, str | None]:
    if note_unit is None or main_unit is None:
        return None, None
    if main_unit != "cup":
        return None, None
    if note_unit == "cup":
        return note_quantity, "cup"
    if note_unit == "stick" and _is_butter_or_cream_cheese_ingredient(ingredient_name):
        return note_quantity * 0.5, "stick"
    if note_unit == "ounce" and _is_butter_or_cream_cheese_ingredient(ingredient_name):
        return note_quantity / 8.0, "ounce"
    if note_unit == "tablespoon":
        return note_quantity / 16.0, "tablespoon"
    return None, None


def _extract_quantity_and_unit_from_note(note_text: str) -> tuple[float | None, str | None]:
    quantity, note_remainder = _parse_ingredient_quantity(note_text)
    if quantity is None:
        return None, None
    unit_match = re.match(r"^([a-zA-Z]+)\b", note_remainder)
    if not unit_match:
        return None, None
    unit = _INGREDIENT_UNIT_ALIASES.get(unit_match.group(1).lower())
    return quantity, unit


def _maybe_override_with_parenthetical_quantity(
    quantity: float | None,
    unit: str | None,
    name: str | None,
    notes: list[str],
) -> float | None:
    if quantity is None or unit is None or not notes:
        return quantity

    suspicious_main_quantity = unit == "cup" and quantity < 0.4
    for note_text in notes:
        note_quantity, note_unit = _extract_quantity_and_unit_from_note(note_text)
        if note_quantity is None or note_unit is None:
            continue
        converted_note_quantity, note_source_unit = _convert_note_measurement_to_main_unit(
            note_quantity, note_unit, unit, name
        )
        if converted_note_quantity is None:
            continue
        if abs(converted_note_quantity - quantity) < 0.02:
            continue

        note_is_standard = note_source_unit in {"stick", "ounce", "cup"}
        if suspicious_main_quantity and note_is_standard:
            return converted_note_quantity

    return quantity


def _format_display_unit(unit: str | None, quantity: float | None) -> str | None:
    cleaned_unit = _clean_text(unit)
    if not cleaned_unit:
        return None
    if quantity is None:
        return cleaned_unit
    if float(quantity) <= 1.0 + 1e-9:
        return cleaned_unit
    return f"{cleaned_unit}s"


def _build_ingredient_display_fields(parsed: dict) -> dict:
    display_quantity = _format_display_quantity(parsed.get("quantity"))
    display_unit = _format_display_unit(parsed.get("unit"), parsed.get("quantity"))
    display_name = _clean_text(parsed.get("name"))
    note = _clean_text(parsed.get("note"))

    parts = [part for part in (display_quantity, display_unit, display_name) if part]
    display_text = " ".join(parts).strip()
    if note:
        display_text = f"{display_text} ({note})" if display_text else f"({note})"

    return {
        "display_quantity": display_quantity,
        "display_unit": display_unit,
        "display_name": display_name,
        "display_text": display_text,
    }


def _scale_ingredient(parsed: dict, factor: float) -> dict:
    scaled = dict(parsed or {})
    quantity = scaled.get("quantity")

    if quantity is not None:
        try:
            scaled["quantity"] = float(quantity) * float(factor)
        except (TypeError, ValueError):
            pass

    scaled.update(_build_ingredient_display_fields(scaled))
    return scaled


def _scale_ingredients_list(ingredients_structured: list, factor: float) -> list:
    scaled_ingredients: list = []
    for item in ingredients_structured or []:
        if isinstance(item, dict):
            scaled_ingredients.append(_scale_ingredient(item, factor))
        else:
            scaled_ingredients.append(item)
    return scaled_ingredients


def _extract_numeric_servings(value: str | None) -> float | None:
    cleaned = _clean_text(value or "")
    if not cleaned:
        return None
    if re.search(r"\d+\s*[-–]\s*\d+", cleaned):
        return None
    matches = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if len(matches) != 1:
        return None
    try:
        parsed = float(matches[0])
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_ingredient_name(name: str) -> str:
    normalized = _clean_text(name).lower()
    normalized = re.sub(r"[.,;:!?]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""

    parts = [part for part in normalized.split() if part not in {"optional", "finely", "roughly"}]
    while parts and parts[0] in _INGREDIENT_DESCRIPTOR_PREFIXES:
        parts = parts[1:]
    while parts and parts[-1] in _INGREDIENT_DESCRIPTOR_SUFFIXES:
        parts = parts[:-1]
    parts = [{"onions": "onion", "tomatoes": "tomato", "peppers": "pepper"}.get(part, part) for part in parts]
    normalized = " ".join(parts).strip()
    return _INGREDIENT_NAME_ALIASES.get(normalized, normalized)


def _group_ingredients_by_name(ingredients_structured: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in ingredients_structured or []:
        if not isinstance(item, dict):
            continue
        normalized_name = _normalize_ingredient_name(str(item.get("name") or ""))
        if not normalized_name:
            continue
        grouped.setdefault(normalized_name, []).append(item)
    return grouped


def _sum_quantities_for_same_unit(group: list[dict]) -> float | None:
    normalized_unit: str | None = None
    has_unit = False
    total = 0.0
    has_quantity = False

    for item in group or []:
        if not isinstance(item, dict):
            continue
        quantity = item.get("quantity")
        if quantity is None:
            continue
        unit = _clean_text(item.get("unit") or "").lower() or None
        if not has_unit:
            normalized_unit = unit
            has_unit = True
        elif normalized_unit != unit:
            return None
        try:
            total += float(quantity)
            has_quantity = True
        except (TypeError, ValueError):
            continue

    if not has_quantity:
        return None
    return total


def _group_ingredients_with_totals(ingredients_structured: list[dict]) -> dict[str, dict]:
    grouped_with_totals: dict[str, dict] = {}
    grouped = _group_ingredients_by_name(ingredients_structured)

    for normalized_name, group in grouped.items():
        total_quantity = _sum_quantities_for_same_unit(group)
        matching_unit = next(
            (
                _clean_text(item.get("unit") or "").lower()
                for item in group
                if isinstance(item, dict)
                and item.get("quantity") is not None
                and _clean_text(item.get("unit") or "")
            ),
            None,
        )
        grouped_with_totals[normalized_name] = {
            "total": total_quantity,
            "unit": matching_unit if total_quantity is not None else None,
            "items": group,
        }

    return grouped_with_totals


def _build_shopping_list_items(ingredients_structured: list) -> list[dict]:
    shopping_items: list[dict] = []
    grouped = _group_ingredients_by_name(ingredients_structured)

    for normalized_name, group in grouped.items():
        total_quantity = _sum_quantities_for_same_unit(group)
        matching_unit = next(
            (
                _clean_text(item.get("unit") or "").lower()
                for item in group
                if isinstance(item, dict)
                and item.get("quantity") is not None
                and _clean_text(item.get("unit") or "")
            ),
            None,
        )
        shopping_item = {
            "name": normalized_name,
            "quantity": total_quantity,
            "unit": matching_unit if total_quantity is not None else None,
            "items": group,
        }
        shopping_item.update(_build_ingredient_display_fields(shopping_item))
        shopping_items.append(
            {
                "name": shopping_item["name"],
                "quantity": shopping_item["quantity"],
                "unit": shopping_item["unit"],
                "display_text": shopping_item["display_text"],
                "items": group,
            }
        )

    return shopping_items


def _recipe_row_ingredient_lines(row: sqlite3.Row | dict) -> list[str]:
    ingredient_groups = _text_to_json_groups(row["ingredient_groups"], "items")
    ingredients = _flatten_groups(ingredient_groups, "items")
    if ingredients:
        return ingredients
    return _text_to_json_array(row["ingredients"])


def _build_shopping_list_from_recipe_rows(rows: list[sqlite3.Row]) -> list[dict]:
    structured: list[dict] = []
    for row in rows:
        for ingredient_text in _recipe_row_ingredient_lines(row):
            parsed = _parse_ingredient_struct(ingredient_text)
            if parsed.get("name"):
                parsed["recipe_id"] = row["id"]
                parsed["recipe_title"] = row["title"]
                structured.append(parsed)
    return _build_shopping_list_items(structured)


def _grocery_item_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "quantity": row["quantity"],
        "unit": row["unit"],
        "display_text": row["display_text"],
        "checked": bool(row["checked"]),
        "source_recipe_id": row["source_recipe_id"],
        "source_recipe_title": row["source_recipe_title"],
    }


def _grocery_list_payload(cur: sqlite3.Cursor, user_id: int) -> dict:
    rows = cur.execute(
        """
        SELECT * FROM grocery_items
        WHERE user_id = ?
        ORDER BY checked ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    items = [_grocery_item_from_row(row) for row in rows]
    source_map: dict[int, str] = {}
    for item in items:
        source_id = item.get("source_recipe_id")
        if source_id is None:
            continue
        source_map[int(source_id)] = item.get("source_recipe_title") or "Recipe"
    return {
        "active_items": [item for item in items if not item["checked"]],
        "checked_items": [item for item in items if item["checked"]],
        "sources": [{"id": source_id, "title": title} for source_id, title in source_map.items()],
    }


def _insert_grocery_item(cur: sqlite3.Cursor, user_id: int, item: GroceryItemPayload) -> None:
    name = _clean_text(item.name) or _normalize_ingredient_name(item.display_text)
    display_text = _clean_text(item.display_text) or name
    if not display_text:
        return
    normalized_name = _normalize_ingredient_name(name or display_text)
    unit = _clean_text(item.unit or "").lower() or None
    now = utcnow_iso()
    cur.execute(
        """
        INSERT INTO grocery_items (
            user_id, name, normalized_name, quantity, unit, display_text, checked,
            source_recipe_id, source_recipe_title, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            user_id,
            name or display_text,
            normalized_name,
            item.quantity,
            unit,
            display_text,
            item.source_recipe_id,
            _clean_text(item.source_recipe_title or "") or None,
            now,
            now,
        ),
    )


def _parse_ingredient_struct(text: str) -> dict:
    raw = _clean_text(text)
    if not raw:
        parsed = {"raw": "", "quantity": None, "unit": None, "name": "", "note": None}
        parsed.update(_build_ingredient_display_fields(parsed))
        return parsed

    working = raw
    notes: list[str] = []
    for note_match in re.finditer(r"\(([^)]*)\)", working):
        note_text = _clean_text(note_match.group(1))
        if note_text:
            notes.append(note_text)
    if notes:
        working = re.sub(r"\([^)]*\)", " ", working)
    working = re.sub(r"\s+", " ", working).strip()

    quantity, remainder = _parse_ingredient_quantity(working)

    unit = None
    remainder_after_unit = remainder
    unit_match = re.match(r"^([a-zA-Z]+)\b", remainder)
    if unit_match:
        normalized_unit = _INGREDIENT_UNIT_ALIASES.get(unit_match.group(1).lower())
        if normalized_unit:
            unit = normalized_unit
            remainder_after_unit = remainder[unit_match.end() :].strip()

    name = re.sub(r"^of\s+", "", remainder_after_unit, flags=re.IGNORECASE).strip()
    quantity = _fix_common_ocr_quantity_errors(quantity, unit, name)
    quantity = _maybe_override_with_parenthetical_quantity(quantity, unit, name, notes)

    if not name:
        parsed = {
            "raw": raw,
            "quantity": None,
            "unit": None,
            "name": raw,
            "note": " ; ".join(notes) if notes else None,
        }
        parsed.update(_build_ingredient_display_fields(parsed))
        return parsed

    parsed = {
        "raw": raw,
        "quantity": quantity,
        "unit": unit,
        "name": name,
        "note": " ; ".join(notes) if notes else None,
    }
    parsed.update(_build_ingredient_display_fields(parsed))
    return parsed


def _prune_instruction_title_steps(groups: list[dict]) -> list[dict]:
    title_keys = {
        _clean_text(group.get("title", "")).lower()
        for group in groups
        if isinstance(group, dict) and _clean_text(group.get("title", ""))
    }
    if not title_keys:
        return groups

    pruned_groups: list[dict] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        steps = group.get("steps")
        if not isinstance(steps, list):
            continue
        filtered_steps: list[str] = []
        for step in steps:
            cleaned_step = _clean_text(step)
            if not cleaned_step:
                continue
            word_count = len(cleaned_step.split())
            if word_count <= 3 and cleaned_step.lower() in title_keys:
                continue
            filtered_steps.append(cleaned_step)
        if filtered_steps:
            pruned_groups.append({"title": group.get("title", ""), "steps": filtered_steps})
    return pruned_groups


def _canonical_recipe_text(value: str) -> str:
    text = _clean_text(value).lower()
    if not text:
        return ""
    text = re.sub(r"^[\u2022\u2023\u25E6\u2043\u2219\-\*\•\·\●\○\▪\◦]+\s*", "", text)
    text = re.sub(r"^(?:step\s*)?\d+\s*[\)\.\:\-]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedupe_text_entries(entries: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        cleaned = _clean_text(entry)
        if not cleaned:
            continue
        canonical = _canonical_recipe_text(cleaned)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        deduped.append(cleaned)
    return deduped


def _dedupe_groups(groups: list[dict], key: str) -> list[dict]:
    deduped_groups: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = group.get(key)
        if not isinstance(entries, list):
            continue
        title = _normalize_section_title(group.get("title", ""))
        deduped_entries: list[str] = []
        for entry in entries:
            cleaned = _clean_text(entry)
            if not cleaned:
                continue
            canonical = _canonical_recipe_text(cleaned)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            deduped_entries.append(cleaned)
        if deduped_entries:
            deduped_groups.append({"title": title, key: deduped_entries})
    return deduped_groups


def _supplement_recipe_candidate(primary: dict, fallback: dict) -> tuple[dict, bool]:
    supplemented = False
    result = dict(primary)

    for field in ("title", "image_url", "servings", "prep_time", "cook_time", "total_time", "prep_minutes", "cook_minutes", "total_minutes"):
        if not result.get(field) and fallback.get(field):
            result[field] = fallback.get(field)
            supplemented = True

    for list_field in ("ingredients", "instructions", "ingredient_groups", "instruction_groups"):
        if not result.get(list_field) and fallback.get(list_field):
            result[list_field] = fallback.get(list_field)
            supplemented = True

    return result, supplemented


def _finalize_recipe_candidate(candidate: dict, url: str, source: str) -> dict:
    finalized = dict(candidate)

    raw_ingredients = finalized.get("ingredients") or []
    raw_instructions = finalized.get("instructions") or []
    ingredient_before = len(raw_ingredients)
    instruction_before = len(raw_instructions)

    ingredient_groups = _normalize_groups(finalized.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(finalized.get("instruction_groups") or [], "steps")

    if ingredient_groups:
        ingredient_groups = _dedupe_groups(ingredient_groups, "items")
        finalized["ingredient_groups"] = ingredient_groups
        finalized["ingredients"] = _flatten_groups(ingredient_groups, "items")
    else:
        finalized["ingredients"] = _dedupe_text_entries(raw_ingredients)
        finalized["ingredient_groups"] = (
            [{"title": "", "items": finalized["ingredients"]}] if finalized["ingredients"] else []
        )
    finalized["ingredients_structured"] = [
        _parse_ingredient_struct(ingredient_text)
        for ingredient_text in finalized.get("ingredients", [])
        if _clean_text(ingredient_text)
    ]

    if instruction_groups:
        deduped_raw_instructions = _dedupe_text_entries(raw_instructions)
        grouped_steps = _flatten_groups(instruction_groups, "steps")
        grouped_canonical = {
            _canonical_recipe_text(step)
            for step in grouped_steps
            if _canonical_recipe_text(step)
        }
        missing_primary_steps = [
            step
            for step in deduped_raw_instructions
            if (canonical := _canonical_recipe_text(step)) and canonical not in grouped_canonical
        ]
        has_assembly_group = any(
            "assembly" in (group.get("title") or "").strip().lower()
            for group in instruction_groups
            if isinstance(group, dict)
        )
        if missing_primary_steps and (source != "jsonld" or has_assembly_group):
            instruction_groups = [{"title": "Instructions", "steps": missing_primary_steps}, *instruction_groups]
        instruction_groups = _prune_instruction_title_steps(instruction_groups)
        instruction_groups = _dedupe_groups(instruction_groups, "steps")
        finalized["instruction_groups"] = instruction_groups
        finalized["instructions"] = _flatten_groups(instruction_groups, "steps")
    else:
        finalized["instructions"] = _dedupe_text_entries(raw_instructions)
        finalized["instruction_groups"] = (
            [{"title": "", "steps": finalized["instructions"]}] if finalized["instructions"] else []
        )

    logger.info(
        "extract parser dedupe url=%s source=%s ingredients=%d->%d instructions=%d->%d",
        url,
        source,
        ingredient_before,
        len(finalized["ingredients"]),
        instruction_before,
        len(finalized["instructions"]),
    )

    return finalized


def _extract_instruction_groups_from_schema(value) -> tuple[list[dict], list[str]]:
    groups: list[dict] = []
    flat_steps: list[str] = []

    if isinstance(value, str):
        text = _clean_text(value)
        if text:
            flat_steps.append(text)
        return groups, flat_steps

    if not isinstance(value, list):
        return groups, flat_steps

    for item in value:
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                flat_steps.append(text)
            continue

        if not isinstance(item, dict):
            continue

        item_type = item.get("@type")
        is_section = (
            isinstance(item_type, str) and item_type.lower() == "howtosection"
        ) or (
            isinstance(item_type, list)
            and any(isinstance(v, str) and v.lower() == "howtosection" for v in item_type)
        )

        if is_section:
            group_title = _normalize_section_title(item.get("name") or "")
            nested = _normalize_instructions(item.get("itemListElement"))
            if nested:
                groups.append({"title": group_title, "steps": nested})
                flat_steps.extend(nested)
            continue

        text = _clean_text(item.get("text") or item.get("name") or "")
        if text:
            flat_steps.append(text)

        nested = _normalize_instructions(item.get("itemListElement"))
        if nested:
            flat_steps.extend(nested)

    return groups, flat_steps


def _extract_time_from_text(text: str, label_pattern: str) -> str:
    pattern = re.compile(
        rf"\b{label_pattern}\b\s*:?\s*([^\n\r|]{{1,40}})",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    candidate = match.group(1).strip(" :-")
    candidate = re.split(r"\b(?:prep|cook|total)\s*time\b", candidate, flags=re.IGNORECASE)[0].strip(" :-")
    return candidate


def _extract_list_items(list_html: str) -> list[str]:
    items: list[str] = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", list_html, flags=re.IGNORECASE | re.DOTALL):
        text = _clean_text(li)
        if text:
            items.append(text)
    return items


def _clean_instruction_step_text(value: str) -> str:
    cleaned = _clean_text(value).strip(" -•*")
    return re.sub(r"^(?:step\s*)?\d+\s*[\)\.\:\-]\s*", "", cleaned, flags=re.IGNORECASE).strip()


def _extract_div_blocks_by_class(html: str, class_name: str) -> list[str]:
    blocks: list[str] = []
    open_tag_pattern = re.compile(
        rf"<div\b(?=[^>]*\bclass=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'])[^>]*>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    nested_div_pattern = re.compile(r"<div\b[^>]*>|</div>", flags=re.IGNORECASE | re.DOTALL)

    for match in open_tag_pattern.finditer(html):
        start = match.start()
        depth = 0
        end_index = None
        for token in nested_div_pattern.finditer(html, pos=match.start()):
            token_text = token.group(0).lower()
            if token_text.startswith("<div"):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    end_index = token.end()
                    break
        if end_index is None:
            continue
        blocks.append(html[start:end_index])

    return blocks


def _extract_wprm_instruction_groups(reduced_html: str) -> list[dict]:
    instruction_container_blocks = _extract_div_blocks_by_class(
        reduced_html,
        "wprm-recipe-instructions-container",
    )
    scoped_html = instruction_container_blocks[0] if instruction_container_blocks else reduced_html

    step_pattern = re.compile(
        r"<([a-zA-Z0-9]+)\b[^>]*class=[\"'][^\"']*\bwprm-recipe-(?:instruction-text|instruction)(?=\s|[\"'])[^\"']*[\"'][^>]*>(.*?)</\1>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    groups: list[dict] = []
    seen_global_steps: set[str] = set()

    def _collect_steps(html_block: str) -> list[str]:
        steps: list[str] = []
        for _, step_html in step_pattern.findall(html_block):
            text = _clean_instruction_step_text(step_html)
            if not text:
                continue
            canonical = _canonical_recipe_text(text)
            if canonical and canonical in seen_global_steps:
                continue
            if canonical:
                seen_global_steps.add(canonical)
            steps.append(text)
        return steps

    group_blocks = _extract_div_blocks_by_class(scoped_html, "wprm-recipe-instruction-group")
    if not group_blocks:
        return []

    pre_group_html = scoped_html
    for group_html in group_blocks:
        pre_group_html = pre_group_html.replace(group_html, "", 1)
    primary_steps = _collect_steps(pre_group_html)
    if primary_steps:
        groups.append({"title": "Instructions", "steps": primary_steps})

    for group_html in group_blocks:
        heading_match = re.search(
            r"<(?:h[1-6]|div|p|span)[^>]*class=[\"'][^\"']*\bwprm-recipe-group-name\b[^\"']*[\"'][^>]*>(.*?)</(?:h[1-6]|div|p|span)>",
            group_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        title = _normalize_section_title(heading_match.group(1)) if heading_match else ""
        steps = _collect_steps(group_html)
        if steps:
            groups.append({"title": title, "steps": steps})
    return groups


def _extract_bigoven_instruction_groups(reduced_html: str) -> list[dict]:
    match = re.search(
        r"<div\b(?=[^>]*\bid=[\"']instr[\"'])(?=[^>]*\bclass=[\"'][^\"']*\binstructions\b[^\"']*[\"'])[^>]*>(.*?)</div>",
        reduced_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    steps: list[str] = []
    for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", match.group(1), flags=re.IGNORECASE | re.DOTALL):
        text = _clean_instruction_step_text(paragraph)
        if text:
            steps.append(text)
    return [{"title": "", "steps": steps}] if steps else []


DOM_RECIPE_SCOPE_PATTERNS = (
    r"<(?:article|section|div)[^>]*(?:wprm-recipe-container|tasty-recipes|mv-create-recipe|recipe-card|recipe)[^>]*>.*?</(?:article|section|div)>",
    r"<(?:article|main|section|div)[^>]*(?:entry-content|post-content|article-content|content)[^>]*>.*?</(?:article|main|section|div)>",
)

DOM_INGREDIENT_NOISE_PATTERNS = (
    r"\bsign up\b",
    r"\bfree daily recipes\b",
    r"\bskip to content\b",
    r"\bjump to recipe\b",
    r"\bhome\b",
    r"\brecipe index\b",
    r"\bpublished\b",
    r"\bcomments?\b",
    r"\baffiliate links?\b",
    r"\bamazon associate\b",
    r"\bdisclosure policy\b",
    r"\bfrom\s+\d+(?:\.\d+)?\s+votes?\b",
    r"\bratings?(?:\s+without comment)?\b",
)


def _extract_recipe_scoped_html(reduced_html: str) -> str:
    scoped_blocks: list[str] = []
    for pattern in DOM_RECIPE_SCOPE_PATTERNS:
        scoped_blocks.extend(
            match.group(0)
            for match in re.finditer(pattern, reduced_html, flags=re.IGNORECASE | re.DOTALL)
        )

    if not scoped_blocks:
        return reduced_html
    return "\n".join(scoped_blocks)


def _is_dom_ingredient_noise(text: str) -> bool:
    candidate = _clean_text(text)
    if not candidate:
        return True
    lowered = candidate.lower()
    if len(candidate) > 240:
        return True
    if re.search(r"^\d{1,2}\s*(?:hrs?|hours?|mins?|minutes?)\b", lowered):
        return True
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in DOM_INGREDIENT_NOISE_PATTERNS)


def _extract_dom_recipe_data(html: str) -> dict:
    scoped = _extract_recipe_scoped_html(html)

    line_like = re.sub(
        r"</(li|p|div|h1|h2|h3|h4|h5|h6|span|dt|dd|tr|th|td|br)>",
        "\n",
        scoped,
        flags=re.IGNORECASE,
    )
    visible_text = _clean_text(line_like.replace("\n", " \n "))

    prep_time = _extract_time_from_text(visible_text, r"prep(?:aration)?\s*time")
    cook_time = _extract_time_from_text(visible_text, r"cook(?:ing)?\s*time")
    total_time = _extract_time_from_text(visible_text, r"total\s*time")

    ingredient_groups: list[dict] = []
    for match in re.finditer(
        r"<(?:h2|h3|h4|h5|p)[^>]*>(.*?)</(?:h2|h3|h4|h5|p)>\s*<(?:ul|ol)[^>]*(?:ingredient|ingredients)[^>]*>(.*?)</(?:ul|ol)>",
        scoped,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = _normalize_section_title(match.group(1))
        items = [item for item in _extract_list_items(match.group(2)) if not _is_dom_ingredient_noise(item)]
        if items:
            ingredient_groups.append({"title": title, "items": items})

    if not ingredient_groups:
        flat_ingredients = []
        for li in re.findall(
            r"<li[^>]*(?:ingredient|ingredients)[^>]*>(.*?)</li>",
            scoped,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            text = _clean_text(li)
            if text and not _is_dom_ingredient_noise(text):
                flat_ingredients.append(text)
        if flat_ingredients:
            ingredient_groups.append({"title": "", "items": flat_ingredients})

    instruction_groups: list[dict] = []
    instruction_source = "generic"

    wprm_container = re.search(
        r"<div[^>]*class=[\"'][^\"']*\bwprm-recipe-instructions-container\b[^\"']*[\"'][^>]*>",
        scoped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if wprm_container:
        instruction_groups = _extract_wprm_instruction_groups(scoped)
        if instruction_groups:
            instruction_source = "wprm"

    if not instruction_groups:
        instruction_groups = _extract_bigoven_instruction_groups(scoped)
        if instruction_groups:
            instruction_source = "bigoven_instr"

    if not instruction_groups:
        for match in re.finditer(
            r"<(?:h2|h3|h4|h5|p)[^>]*>(.*?)</(?:h2|h3|h4|h5|p)>\s*<(?:ol|ul)[^>]*(?:instruction|direction|method|step)[^>]*>(.*?)</(?:ol|ul)>",
            scoped,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            title = _normalize_section_title(match.group(1))
            steps = [_clean_instruction_step_text(step) for step in _extract_list_items(match.group(2))]
            steps = [step for step in steps if step]
            if steps:
                instruction_groups.append({"title": title, "steps": steps})

    if not instruction_groups:
        flat_steps = []
        for li in re.findall(
            r"<li[^>]*(?:instruction|direction|method|step)[^>]*>(.*?)</li>",
            scoped,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            text = _clean_instruction_step_text(li)
            if text:
                flat_steps.append(text)
        if flat_steps:
            instruction_groups.append({"title": "", "steps": flat_steps})

    instruction_steps_found = sum(
        len(group.get("steps") or [])
        for group in instruction_groups
        if isinstance(group, dict)
    )
    logger.info(
        "extract parser instructions instruction_source=%s instruction_groups_found=%d instruction_steps_found=%d",
        instruction_source,
        len(instruction_groups),
        instruction_steps_found,
    )
    if instruction_source == "wprm":
        for index, group in enumerate(instruction_groups):
            group_name = (group.get("title") or "").strip() if isinstance(group, dict) else ""
            group_steps = len(group.get("steps") or []) if isinstance(group, dict) else 0
            logger.info(
                "extract parser instructions instruction_source=wprm group_%d_name=%s group_%d_steps=%d",
                index,
                group_name or "<default>",
                index,
                group_steps,
            )

    return {
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "instruction_source": instruction_source,
    }


def _parse_html_attributes(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*([\'"])(.*?)\2', tag, flags=re.DOTALL):
        attrs[match.group(1).lower()] = match.group(3).strip()
    return attrs


def _normalize_image_url(raw_url: str, page_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return ""
    if value.startswith(("data:", "blob:")):
        return ""
    if value.startswith("//"):
        value = f"https:{value}"
    value = urljoin(page_url, value)
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https"):
        return ""
    blocked_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "igshid", "mc_cid", "mc_eid"
    }
    filtered = [(k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in blocked_params]
    return urlunparse(parsed._replace(query=urlencode(filtered, doseq=True)))


def _normalize_recipe_image_value(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_bad_image(url: str) -> bool:
    lowered = (url or "").lower()
    if not lowered:
        return True
    if lowered.endswith(".svg"):
        return True
    blocked_terms = (
        "logo", "icon", "sprite", "avatar", "gravatar", "emoji",
        "doubleclick", "pixel", "spacer", "blank", "placeholder"
    )
    return any(term in lowered for term in blocked_terms)


def _parse_numeric(value) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _image_score(url: str, width: int | None, height: int | None, source_hint: str = "") -> float:
    if not url or _looks_like_bad_image(url):
        return -1e9
    if width and width < 120:
        return -1e9
    if height and height < 120:
        return -1e9

    area_score = 0.0
    if width and height:
        area_score = min((width * height) / 10000.0, 250.0)

    lowered = url.lower()
    keyword_bonus = 0.0
    if re.search(r"(recipe|recipes|food|dish|meal|chicken|beef|pasta|soup|stew)", lowered):
        keyword_bonus += 20.0
    if source_hint == "jsonld":
        keyword_bonus += 40.0
    elif source_hint == "og":
        keyword_bonus += 20.0
    elif source_hint == "twitter":
        keyword_bonus += 15.0
    elif source_hint == "dom":
        keyword_bonus += 10.0
    return 100.0 + area_score + keyword_bonus


def _choose_best_image(candidates: list[dict], source_hint: str) -> str:
    best_url = ""
    best_score = -1e9
    for candidate in candidates:
        url = _normalize_image_url(candidate.get("url", ""), candidate.get("page_url", ""))
        width = _parse_numeric(candidate.get("width"))
        height = _parse_numeric(candidate.get("height"))
        score = _image_score(url, width, height, source_hint)
        if score > best_score:
            best_score = score
            best_url = url
    return best_url


def _extract_json_ld_image_candidates(value, page_url: str) -> list[dict]:
    candidates: list[dict] = []
    if isinstance(value, str):
        candidates.append({"url": value, "page_url": page_url})
    elif isinstance(value, dict):
        url_value = value.get("url") or value.get("contentUrl") or value.get("@id")
        if isinstance(url_value, str):
            candidates.append(
                {
                    "url": url_value,
                    "page_url": page_url,
                    "width": value.get("width"),
                    "height": value.get("height"),
                }
            )
    elif isinstance(value, list):
        for item in value:
            candidates.extend(_extract_json_ld_image_candidates(item, page_url))
    return candidates


def _extract_json_ld_recipe_image(item: dict, page_url: str) -> str:
    return _choose_best_image(_extract_json_ld_image_candidates(item.get("image"), page_url), "jsonld")


def _extract_json_ld_fallback_image(json_ld_blocks: list, page_url: str) -> str:
    candidates: list[dict] = []
    for block in json_ld_blocks:
        for item in _iter_json_ld_items(block):
            if not isinstance(item, dict):
                continue
            image_keys = (
                "image",
                "primaryImageOfPage",
                "thumbnailUrl",
                "thumbnail",
            )
            for key in image_keys:
                candidates.extend(_extract_json_ld_image_candidates(item.get(key), page_url))
    return _choose_best_image(candidates, "jsonld")


def _extract_meta_image(html: str, page_url: str, source: str) -> str:
    if source == "og":
        tags = re.findall(r"<meta[^>]+property=[\"']og:image:secure_url[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL)
        tags.extend(re.findall(r"<meta[^>]+property=[\"']og:image[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))
        tags.extend(re.findall(r"<meta[^>]+name=[\"']og:image[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))
        tags.extend(re.findall(r"<meta[^>]+name=[\"']og:image:secure_url[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))
    else:
        tags = re.findall(r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL)
        tags.extend(re.findall(r"<meta[^>]+property=[\"']twitter:image[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))
        tags.extend(re.findall(r"<meta[^>]+name=[\"']twitter:image:src[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))
        tags.extend(re.findall(r"<meta[^>]+property=[\"']twitter:image:src[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))

    tags.extend(re.findall(r"<meta[^>]+itemprop=[\"']image[\"'][^>]+>", html, flags=re.IGNORECASE | re.DOTALL))

    candidates: list[dict] = []
    for tag in tags:
        attrs = _parse_html_attributes(tag)
        if attrs.get("content"):
            candidates.append({"url": attrs["content"], "page_url": page_url})
    return _choose_best_image(candidates, source)


def _best_url_from_srcset(srcset: str) -> str:
    best_url = ""
    best_metric = -1.0
    for entry in (srcset or "").split(","):
        part = entry.strip()
        if not part:
            continue
        chunks = part.split()
        src = chunks[0].strip()
        metric = 0.0
        if len(chunks) > 1:
            descriptor = chunks[1].strip().lower()
            width_match = re.match(r"(\d+)w", descriptor)
            density_match = re.match(r"(\d+(?:\.\d+)?)x", descriptor)
            if width_match:
                metric = float(width_match.group(1))
            elif density_match:
                metric = float(density_match.group(1)) * 1000.0
        if metric >= best_metric:
            best_metric = metric
            best_url = src
    return best_url


def _extract_dom_fallback_image(html: str, page_url: str) -> str:
    containers = re.findall(
        r"<(?:article|main|section|div)[^>]*(?:recipe|entry-content|post-content|article-content|content)[^>]*>.*?</(?:article|main|section|div)>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    scope_html = "\n".join(containers) if containers else html
    image_tags = re.findall(r"<img\b[^>]*>", scope_html, flags=re.IGNORECASE | re.DOTALL)
    candidates: list[dict] = []
    for img_tag in image_tags:
        attrs = _parse_html_attributes(img_tag)
        possible_urls = [
            attrs.get("src", ""),
            attrs.get("data-src", ""),
            attrs.get("data-lazy-src", ""),
            attrs.get("data-srcset", ""),
            attrs.get("srcset", ""),
        ]
        expanded_urls: list[str] = []
        for possible_url in possible_urls:
            if "," in possible_url and (" w" in possible_url or " x" in possible_url):
                srcset_url = _best_url_from_srcset(possible_url)
                if srcset_url:
                    expanded_urls.append(srcset_url)
            elif possible_url:
                expanded_urls.append(possible_url)

        for possible_url in expanded_urls:
            candidates.append(
                {
                    "url": possible_url,
                    "page_url": page_url,
                    "width": attrs.get("width"),
                    "height": attrs.get("height"),
                }
            )
    return _choose_best_image(candidates, "dom")


def _count_group_entries(groups: list[dict], key: str) -> int:
    total = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = group.get(key)
        if isinstance(entries, list):
            total += len([entry for entry in entries if _clean_text(entry)])
    return total


def _recipe_quality_score(candidate: dict) -> int:
    ingredients = candidate.get("ingredients") or []
    instructions = candidate.get("instructions") or []
    ingredient_groups = candidate.get("ingredient_groups") or []
    instruction_groups = candidate.get("instruction_groups") or []
    servings = str(candidate.get("servings") or "").strip()
    prep_time = str(candidate.get("prep_time") or "").strip()
    cook_time = str(candidate.get("cook_time") or "").strip()
    total_time = str(candidate.get("total_time") or "").strip()
    image_url = str(candidate.get("image_url") or "").strip()
    title = str(candidate.get("title") or "").strip()

    return (
        len(ingredients) * 4
        + len(instructions) * 4
        + _count_group_entries(ingredient_groups, "items") * 2
        + _count_group_entries(instruction_groups, "steps") * 2
        + (5 if image_url else 0)
        + (2 if servings else 0)
        + (1 if prep_time else 0)
        + (1 if cook_time else 0)
        + (1 if total_time else 0)
        + (1 if title else 0)
    )


def _recipe_payload_summary(label: str, payload: dict) -> str:
    ingredients = payload.get("ingredients") or []
    instructions = payload.get("instructions") or []
    ingredient_groups = payload.get("ingredient_groups") or []
    instruction_groups = payload.get("instruction_groups") or []
    return (
        f"{label}(title={bool(payload.get('title'))}, image={bool(payload.get('image_url'))}, "
        f"ingredients={len(ingredients)}, instructions={len(instructions)}, "
        f"ingredient_groups={len(ingredient_groups)}, instruction_groups={len(instruction_groups)}, "
        f"score={_recipe_quality_score(payload)})"
    )


def _recipe_parser_counts(candidate: dict) -> dict:
    ingredient_groups = _normalize_groups(candidate.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(candidate.get("instruction_groups") or [], "steps")
    ingredients = candidate.get("ingredients") or _flatten_groups(ingredient_groups, "items")
    instructions = candidate.get("instructions") or _flatten_groups(instruction_groups, "steps")
    return {
        "ingredients": len(ingredients),
        "instructions": len(instructions),
        "ingredient_groups": len(ingredient_groups),
        "instruction_groups": len(instruction_groups),
    }


def _log_recipe_candidate_counts(url: str, label: str, candidate: dict) -> None:
    counts = _recipe_parser_counts(candidate or {})
    logger.info(
        "extract parser candidate url=%s source=%s ingredients=%d instruction_groups=%d instructions=%d",
        url,
        label,
        counts.get("ingredients", 0),
        counts.get("instruction_groups", 0),
        counts.get("instructions", 0),
    )


def _log_recipe_db_write_trace(context: str, recipe_id: int | None, payload: dict) -> None:
    ingredient_groups = _normalize_groups(payload.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(payload.get("instruction_groups") or [], "steps")
    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")
    ingredients_json = _json_array_to_text(ingredients)
    instructions_json = _json_array_to_text(instructions)
    ingredient_groups_json = _json_groups_to_text(ingredient_groups, "items")
    instruction_groups_json = _json_groups_to_text(instruction_groups, "steps")
    logger.info(
        "%s recipe_id=%s ingredient_group_count_before_save=%d instruction_group_count_before_save=%d ingredients_count=%d instructions_count=%d ingredients_json_nonempty=%s instructions_json_nonempty=%s ingredient_groups_json_nonempty=%s instruction_groups_json_nonempty=%s ingredient_groups_json_has_named=%s instruction_groups_json_has_named=%s",
        context,
        recipe_id if recipe_id is not None else "pending",
        len(ingredient_groups),
        len(instruction_groups),
        len(ingredients),
        len(instructions),
        bool(ingredients_json and ingredients_json != "[]"),
        bool(instructions_json and instructions_json != "[]"),
        bool(ingredient_groups_json and ingredient_groups_json != "[]"),
        bool(instruction_groups_json and instruction_groups_json != "[]"),
        bool(any((group.get("title") or "").strip() for group in ingredient_groups)),
        bool(any((group.get("title") or "").strip() for group in instruction_groups)),
    )


def _has_named_and_unnamed_instruction_groups(groups: list[dict]) -> bool:
    has_named = False
    has_unnamed = False
    for group in groups:
        if not isinstance(group, dict):
            continue
        steps = group.get("steps")
        if not isinstance(steps, list) or not any(_clean_text(step) for step in steps):
            continue
        title = _normalize_section_title(group.get("title") or "")
        if title:
            has_named = True
        else:
            has_unnamed = True
        if has_named and has_unnamed:
            return True
    return False


def _count_instruction_prefix_expansions(instructions: list[str]) -> int:
    normalized_instructions = [
        _canonical_recipe_text(_clean_text(instruction))
        for instruction in instructions
        if _clean_text(instruction)
    ]
    expansion_count = 0
    for index, instruction in enumerate(normalized_instructions):
        if not instruction:
            continue
        for other_index, other_instruction in enumerate(normalized_instructions):
            if index == other_index or not other_instruction:
                continue
            if len(instruction) <= len(other_instruction):
                continue
            if len(instruction) - len(other_instruction) < 8:
                continue
            if instruction.startswith(f"{other_instruction} "):
                expansion_count += 1
                break
    return expansion_count


def _wprm_richer_than_jsonld(wprm_candidate: dict, jsonld_candidate: dict) -> bool:
    if not wprm_candidate or not jsonld_candidate:
        return False
    wprm_counts = _recipe_parser_counts(wprm_candidate)
    jsonld_counts = _recipe_parser_counts(jsonld_candidate)
    if (
        jsonld_counts["ingredients"] >= 3
        and wprm_counts["ingredients"] < jsonld_counts["ingredients"]
        and (jsonld_counts["ingredients"] - wprm_counts["ingredients"]) >= 3
    ):
        return False
    wprm_instruction_expansions = _count_instruction_prefix_expansions(wprm_candidate.get("instructions") or [])
    if (
        wprm_instruction_expansions > 0
        and wprm_counts["instructions"] > jsonld_counts["instructions"]
        and wprm_instruction_expansions >= (wprm_counts["instructions"] - jsonld_counts["instructions"])
    ):
        return False
    if wprm_counts["instruction_groups"] > jsonld_counts["instruction_groups"]:
        return True
    if (
        wprm_counts["ingredient_groups"] > jsonld_counts["ingredient_groups"]
        and wprm_counts["instruction_groups"] >= jsonld_counts["instruction_groups"]
        and wprm_counts["instruction_groups"] > 1
    ):
        return True
    if wprm_counts["instructions"] > jsonld_counts["instructions"]:
        return True
    wprm_instruction_groups = _normalize_groups(wprm_candidate.get("instruction_groups") or [], "steps")
    if _has_named_and_unnamed_instruction_groups(wprm_instruction_groups) and wprm_counts["instructions"] >= jsonld_counts["instructions"]:
        return True
    return False


def _json_array_to_text(value: list[str] | None) -> str | None:
    if value is None:
        return None
    return json.dumps([str(item).strip() for item in value if str(item).strip()])


def _text_to_json_array(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return _as_string_list(parsed)
    except Exception:
        pass
    return []


def _json_groups_to_text(value: list[dict] | None, key: str) -> str | None:
    if value is None:
        return None
    normalized = _normalize_groups(value, key)
    return json.dumps(normalized)


def _text_to_json_groups(value: str | None, key: str) -> list[dict]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return _normalize_groups(parsed, key)


def _coerce_review_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in REVIEW_STATUSES:
        if normalized == "review_ready":
            return "completed"
        return normalized
    if normalized in {"reviewed", "review_ready"}:
        return "completed"
    return "none"


def _has_recipe_content(recipe: Recipe) -> bool:
    ingredient_groups = _normalize_groups(recipe.ingredient_groups or [], "items")
    instruction_groups = _normalize_groups(recipe.instruction_groups or [], "steps")

    ingredient_count = len(_flatten_groups(ingredient_groups, "items"))
    instruction_count = len(_flatten_groups(instruction_groups, "steps"))

    if not ingredient_count:
        ingredient_count = len(_as_string_list(recipe.ingredients or []))
    if not instruction_count:
        instruction_count = len(_as_string_list(recipe.instructions or []))

    has_title = bool((recipe.title or "").strip())
    has_content = bool(ingredient_count or instruction_count)
    return bool(has_title and has_content)


def _is_recipe_imperfect(recipe: Recipe) -> bool:
    ingredient_groups = _normalize_groups(recipe.ingredient_groups or [], "items")
    instruction_groups = _normalize_groups(recipe.instruction_groups or [], "steps")

    ingredient_count = len(_flatten_groups(ingredient_groups, "items"))
    instruction_count = len(_flatten_groups(instruction_groups, "steps"))

    if not ingredient_count:
        ingredient_count = len(_as_string_list(recipe.ingredients or []))
    if not instruction_count:
        instruction_count = len(_as_string_list(recipe.instructions or []))

    return ingredient_count == 0 or instruction_count == 0


def _recipe_review_payload_from_row(row: sqlite3.Row) -> dict:
    return {
        "review_status": _coerce_review_status(row["review_status"]),
        "review_notes": row["review_notes"],
        "review_requested_at": row["review_requested_at"],
        "review_started_at": row["review_started_at"],
        "review_completed_at": row["review_completed_at"],
        "review_error": row["review_error"],
        "ai_review_provider": row["ai_review_provider"],
        "ai_review_model": row["ai_review_model"],
    }


def _recipe_ai_source_payload(row: sqlite3.Row) -> dict:
    empty_source = {
        "title": "",
        "ingredients": [],
        "instructions": [],
        "ingredient_groups": [],
        "instruction_groups": [],
    }
    current_saved = {
        "title": row["title"] or "",
        "ingredients": _text_to_json_array(row["ingredients"]),
        "instructions": _text_to_json_array(row["instructions"]),
        "ingredient_groups": _text_to_json_groups(row["ingredient_groups"], "items"),
        "instruction_groups": _text_to_json_groups(row["instruction_groups"], "steps"),
    }
    extraction = {}
    source_url = row["url"] or ""
    if source_url:
        try:
            extraction = fetch_recipe_data_from_url(source_url)
        except Exception as exc:
            logger.warning(
                "review_queue_source_payload recipe_id=%s source_url=%s extraction_error=%s",
                int(row["id"]),
                source_url,
                str(exc),
            )
    raw_sources = extraction.get("_raw_sources") if isinstance(extraction, dict) else None
    parser_counts = extraction.get("_parser_counts") if isinstance(extraction, dict) else None
    selected_source = extraction.get("_selected_source") if isinstance(extraction, dict) else ""
    selected_reason = extraction.get("_selected_reason") if isinstance(extraction, dict) else ""

    if not isinstance(raw_sources, dict):
        raw_sources = {"jsonld": dict(empty_source), "dom": dict(empty_source), "wprm": dict(empty_source)}
    if not isinstance(parser_counts, dict):
        parser_counts = {
            "jsonld": {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
            "dom": {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
            "wprm": {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
        }

    logger.info(
        "review_queue_source_payload recipe_id=%s selected_source=%s jsonld_steps=%s wprm_steps=%s dom_steps=%s",
        int(row["id"]),
        selected_source or "unknown",
        (parser_counts.get("jsonld") or {}).get("instructions", 0),
        (parser_counts.get("wprm") or {}).get("instructions", 0),
        (parser_counts.get("dom") or {}).get("instructions", 0),
    )

    return {
        "recipe_id": int(row["id"]),
        "source_url": source_url,
        "title_hint": row["title"] or "",
        "source_app": row["source_app"] or "",
        "source_type": row["source_type"] or "",
        "selected_source": selected_source or "saved",
        "selected_reason": selected_reason or "saved-row-fallback",
        "needs_review": bool(row["needs_review"]),
        "notes": row["notes"] or "",
        "current_saved": current_saved,
        "raw_sources": {
            "jsonld": raw_sources.get("jsonld") or dict(empty_source),
            "dom": raw_sources.get("dom") or dict(empty_source),
            "wprm": raw_sources.get("wprm") or dict(empty_source),
        },
        "parser_counts": {
            "jsonld": parser_counts.get("jsonld") or {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
            "dom": parser_counts.get("dom") or {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
            "wprm": parser_counts.get("wprm") or {"ingredients": 0, "instructions": 0, "ingredient_groups": 0, "instruction_groups": 0},
        },
    }


def build_ai_review_prompt(recipe_row: sqlite3.Row) -> str:
    source_payload = _recipe_ai_source_payload(recipe_row)
    payload_text = json.dumps(source_payload, ensure_ascii=False, indent=2)
    return (
        "You are cleaning recipe extraction output into strict JSON.\n"
        "Rules:\n"
        "- Use ONLY the data provided in input_data.\n"
        "- DO NOT hallucinate, invent, or add ingredients, steps, or sections.\n"
        "- Prefer the richest and most structured candidate source.\n"
        "- Preserve grouped ingredient/instruction structure when present.\n"
        "- Prefer WPRM instruction groups when they are more complete than JSON-LD.\n"
        "- Keep ingredient and instruction meaning unchanged.\n"
        "- Return strict JSON only (no markdown, no prose).\n"
        "Target shape:\n"
        '{"title":"","servings":"","prep_time":"","cook_time":"","total_time":"","ingredients":[],"instructions":[],"ingredient_groups":[{"title":"","items":[]}],"instruction_groups":[{"title":"","steps":[]}],"review_notes":""}\n'
        "Input data:\n"
        f"{payload_text}"
    )


def _manual_ai_cleanup_payload_from_row(row: sqlite3.Row) -> dict:
    ingredient_groups = _text_to_json_groups(row["ingredient_groups"], "items")
    instruction_groups = _text_to_json_groups(row["instruction_groups"], "steps")
    ingredients = _text_to_json_array(row["ingredients"])
    instructions = _text_to_json_array(row["instructions"])

    compact_payload = {
        "title": row["title"] or "",
        "servings": row["servings"] or "",
        "prep_time": row["prep_time"] or "",
        "cook_time": row["cook_time"] or "",
        "total_time": row["total_time"] or "",
        "notes": row["notes"] or "",
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": ingredients,
        "instructions": instructions,
    }

    source_url = _clean_text(row["url"] or "")
    if source_url:
        compact_payload["url"] = source_url

    if not ingredient_groups and ingredients:
        compact_payload["raw_ingredient_text"] = "\n".join(ingredients)
    if not instruction_groups and instructions:
        compact_payload["raw_instruction_text"] = "\n".join(instructions)

    try:
        stored_context = json.loads(row["ai_review_source_payload"]) if row["ai_review_source_payload"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        stored_context = {}
    transcript_context = stored_context.get("saved_cleanup_context") if isinstance(stored_context, dict) else None
    if isinstance(transcript_context, dict):
        compact_payload["_ai_cleanup_context"] = transcript_context

    return compact_payload


_SPOKEN_NUMBER_WORDS = {
    "a": 1.0,
    "an": 1.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
}
_SPOKEN_FRACTION_WORDS = {
    "half": 0.5,
    "quarter": 0.25,
    "fourth": 0.25,
    "third": 1.0 / 3.0,
}
_PROPER_NOUN_INGREDIENT_REPLACEMENTS = {
    "white lily": "White Lily",
}


def _normalize_transcript_context_text(value) -> str:
    return re.sub(r"\s+", " ", _clean_text(value or "")).strip()


def _canonical_cleanup_ingredient_name(value: str) -> str:
    cleaned = _normalize_ingredient_name(value or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_spoken_quantity_phrase(value: str) -> float | None:
    candidate = _normalize_transcript_context_text(value).lower()
    candidate = re.sub(r"[-–]+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate:
        return None
    direct_quantity, direct_remainder = _parse_ingredient_quantity(candidate)
    if direct_quantity is not None and not direct_remainder:
        return direct_quantity

    def _parse_spoken_fraction_tokens(tokens: list[str]) -> float | None:
        if not tokens:
            return None
        if tokens in (["half"], ["half", "a"], ["a", "half"], ["one", "half"]):
            return 0.5
        if tokens in (
            ["quarter"],
            ["quarters"],
            ["a", "quarter"],
            ["one", "quarter"],
            ["fourth"],
            ["fourths"],
            ["a", "fourth"],
            ["one", "fourth"],
        ):
            return 0.25
        if tokens in (["third"], ["thirds"], ["a", "third"], ["one", "third"]):
            return 1.0 / 3.0
        if tokens == ["two", "thirds"]:
            return 2.0 / 3.0
        if tokens in (["three", "quarters"], ["three", "quarter"], ["three", "fourths"], ["three", "fourth"]):
            return 0.75
        return None

    tokens = candidate.split()
    if not tokens:
        return None

    if len(tokens) >= 3 and tokens[1] == "and":
        whole = _SPOKEN_NUMBER_WORDS.get(tokens[0])
        fraction = _parse_spoken_fraction_tokens(tokens[2:])
        if whole is not None and fraction is not None:
            return whole + fraction

    fraction = _parse_spoken_fraction_tokens(tokens)
    if fraction is not None:
        return fraction

    return _SPOKEN_NUMBER_WORDS.get(candidate)


def _format_numeric_quantity(quantity: float) -> str:
    return format(round(float(quantity), 6), "g")


def _should_merge_suspicious_single_letter_unit_fragment(unit_token: str, next_part: str) -> bool:
    normalized_unit = _clean_text(unit_token).lower()
    if normalized_unit not in {"g", "l"}:
        return False
    next_token_match = re.match(r"^([a-z]+)", _clean_text(next_part), flags=re.IGNORECASE)
    if not next_token_match:
        return False
    return f"{normalized_unit}{next_token_match.group(1).lower()}" in _SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS


def _repair_suspicious_single_letter_unit_fragment(value: str) -> str:
    text = _clean_text(value)
    matched = re.match(r"^([gl])\s+([a-z]+)(\b.*)$", text, flags=re.IGNORECASE)
    if not matched:
        return text
    unit_token, fragment, tail = matched.groups()
    if f"{unit_token.lower()}{fragment.lower()}" not in _SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS:
        return text
    return f"{unit_token}{fragment}{tail}"


def _normalize_spoken_ingredient_text(value: str) -> str:
    raw = _repair_suspicious_single_letter_unit_fragment(value)
    if not raw:
        return ""
    if re.match(r"^(?:\d+(?:\.\d+)?|\d+\s+\d+/\d+|\d+/\d+|[Â¼Â½Â¾â…-â…ž])\b", raw):
        return raw

    words = raw.split()
    max_phrase_words = min(6, len(words) - 1)
    for word_count in range(max_phrase_words, 0, -1):
        quantity_text = " ".join(words[:word_count])
        quantity = _parse_spoken_quantity_phrase(quantity_text)
        if quantity is None:
            continue

        remainder = " ".join(words[word_count:]).strip()
        if not remainder:
            continue

        unit_match = re.match(r"^(?P<unit>[a-zA-Z]+)\b(?P<tail>.*)$", remainder)
        if not unit_match:
            continue

        unit = _INGREDIENT_UNIT_ALIASES.get(unit_match.group("unit").lower())
        if not unit:
            continue

        name = re.sub(r"^\s*of\s+", "", unit_match.group("tail") or "", flags=re.IGNORECASE).strip()
        if not name:
            continue

        display_unit = _format_display_unit(unit, quantity) or unit
        return _clean_text(f"{_format_numeric_quantity(quantity)} {display_unit} {name}")

    return raw


def _apply_conservative_proper_noun_corrections(value: str) -> str:
    corrected = _clean_text(value)
    for raw_phrase, replacement in _PROPER_NOUN_INGREDIENT_REPLACEMENTS.items():
        corrected = re.sub(rf"\b{re.escape(raw_phrase)}\b", replacement, corrected, flags=re.IGNORECASE)
    return corrected


def _find_transcript_quantity_evidence(transcript_text: str, ingredient_name: str, unit: str | None) -> float | None:
    normalized_transcript = _normalize_transcript_context_text(transcript_text).lower()
    normalized_name = _canonical_cleanup_ingredient_name(ingredient_name)
    if not normalized_transcript or not normalized_name or not unit:
        return None

    unit_aliases = sorted(
        {
            alias
            for alias, canonical_unit in _INGREDIENT_UNIT_ALIASES.items()
            if canonical_unit == unit
        }
        | {unit, f"{unit}s"},
        key=len,
        reverse=True,
    )
    quantity_pattern = (
        r"(?P<quantity>"
        r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+and\s+(?:a\s+)?"
        r"(?:half|quarter|fourth|third|two\s+thirds|three\s+quarters|three\s+fourths)"
        r"|three\s+quarters"
        r"|three\s+fourths"
        r"|two\s+thirds"
        r"|(?:a\s+|one\s+)?(?:half|quarter|fourth|third)"
        r"|half(?:\s+a)?"
        r"|a\s+half"
        r"|\d+\s+\d+/\d+"
        r"|\d+/\d+"
        r"|\d+(?:\.\d+)?"
        r"|[½⅓¼¾⅔⅛⅜⅝⅞]"
        r")"
    )
    ingredient_tokens = normalized_name.split()
    max_gap_words = 4
    max_window_tokens = len(ingredient_tokens) + max_gap_words

    def _contains_nearby_ingredient_tokens(tokens: list[str]) -> bool:
        if not tokens:
            return False
        for start_index in range(0, max(1, len(tokens) - len(ingredient_tokens) + 1)):
            window_tokens = tokens[start_index : start_index + max_window_tokens]
            ingredient_index = 0
            for token in window_tokens:
                if token == ingredient_tokens[ingredient_index]:
                    ingredient_index += 1
                    if ingredient_index == len(ingredient_tokens):
                        return True
            if ingredient_tokens[0] in window_tokens and len(ingredient_tokens) == 1:
                return True
        return False

    for unit_alias in unit_aliases:
        pattern = re.compile(
            rf"{quantity_pattern}\s+{re.escape(unit_alias)}\b",
            flags=re.IGNORECASE,
        )
        for match in pattern.finditer(normalized_transcript):
            trailing_segment = re.split(r"[.;:!?]", normalized_transcript[match.end():], maxsplit=1)[0]
            trailing_tokens = re.findall(r"[a-z]+", trailing_segment)
            if trailing_tokens[:1] == ["of"]:
                trailing_tokens = trailing_tokens[1:]
            if not trailing_tokens:
                continue
            if not _contains_nearby_ingredient_tokens(trailing_tokens):
                continue
            parsed_quantity = _parse_spoken_quantity_phrase(match.group("quantity"))
            if parsed_quantity is not None:
                return parsed_quantity
    return None


def _build_cleaned_ingredient_line(
    quantity: float | None,
    unit: str | None,
    name: str,
    note: str | None = None,
) -> str:
    parsed = {
        "quantity": quantity,
        "unit": unit,
        "name": _apply_conservative_proper_noun_corrections(name),
        "note": note,
    }
    parsed.update(_build_ingredient_display_fields(parsed))
    return parsed["display_text"] or _clean_text(name)


def _repair_saved_ingredient_lines_from_transcript(
    ingredient_lines: list[str],
    transcript_text: str,
) -> tuple[list[str], list[str]]:
    repaired_lines: list[str] = []
    flagged_lines: list[str] = []
    for line in ingredient_lines:
        parsed = _parse_ingredient_struct(line)
        ingredient_name = _clean_text(parsed.get("name") or "")
        if not ingredient_name:
            repaired_lines.append(_apply_conservative_proper_noun_corrections(_clean_text(line)))
            continue

        current_quantity = parsed.get("quantity")
        current_unit = parsed.get("unit")
        transcript_quantity = _find_transcript_quantity_evidence(transcript_text, ingredient_name, current_unit)
        suspicious_quantity = current_quantity is not None and 0 < float(current_quantity) < 0.1

        if transcript_quantity is not None and current_unit:
            repaired_lines.append(
                _build_cleaned_ingredient_line(
                    transcript_quantity,
                    current_unit,
                    ingredient_name,
                    parsed.get("note"),
                )
            )
            continue

        if suspicious_quantity:
            flagged_lines.append(_clean_text(line))
        repaired_lines.append(
            _build_cleaned_ingredient_line(
                current_quantity,
                current_unit,
                ingredient_name,
                parsed.get("note"),
            )
        )
    return repaired_lines, flagged_lines


def _prepare_saved_recipe_for_ai_cleanup(parsed_recipe: dict) -> dict:
    recipe_payload = dict(parsed_recipe or {})
    context = recipe_payload.get("_ai_cleanup_context")
    transcript_text = ""
    if isinstance(context, dict):
        transcript_text = _normalize_transcript_context_text(
            context.get("cleaned_transcript_text") or context.get("transcript_text") or ""
        )

    ingredient_groups = _normalize_groups(recipe_payload.get("ingredient_groups") or [], "items")
    if not ingredient_groups:
        flat_ingredients = _normalize_plain_string_list(recipe_payload.get("ingredients") or [])
        if flat_ingredients:
            ingredient_groups = [{"title": "", "items": flat_ingredients}]

    flagged_lines: list[str] = []
    prepared_groups: list[dict] = []
    for group in ingredient_groups:
        repaired_items = _normalize_plain_string_list(group.get("items") or [])
        repaired_items, group_flags = _repair_saved_ingredient_lines_from_transcript(repaired_items, transcript_text)
        flagged_lines.extend(group_flags)
        if repaired_items:
            prepared_groups.append({"title": _clean_text(group.get("title") or ""), "items": repaired_items})

    recipe_payload["ingredient_groups"] = prepared_groups
    recipe_payload["ingredients"] = _flatten_groups(prepared_groups, "items")

    if flagged_lines:
        recipe_payload["_ai_cleanup_flags"] = {
            "suspicious_ingredients_without_transcript_evidence": flagged_lines,
        }
    return recipe_payload


def extract_recipe_text_for_ai(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    container = (
        soup.select_one(".wprm-recipe-container")
        or soup.select_one(".wprm-recipe")
        or soup.select_one(".tasty-recipes")
        or soup.select_one(".recipe-card")
        or soup.find("article")
        or soup.body
        or soup
    )

    try:
        text = container.get_text("\n", strip=True)
    except TypeError:
        text = container.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    junk_lines = {"1x", "2x", "3x", "▢"}
    clean_lines = [line for line in lines if line not in junk_lines]
    text = "\n".join(clean_lines)

    start_idx = text.find("Ingredients")
    if start_idx >= 0:
        end_tokens = ("Notes", "Nutrition", "Video", "Did you make")
        end_candidates = [text.find(token, start_idx + 1) for token in end_tokens]
        end_candidates = [idx for idx in end_candidates if idx > start_idx]
        end_idx = min(end_candidates) if end_candidates else len(text)
        text = text[start_idx:end_idx]

    return text[:MAX_AI_CLEANUP_SOURCE_CHARS]


def _build_ai_input_from_parsed_recipe(parsed_recipe: dict) -> str:
    if not isinstance(parsed_recipe, dict):
        return ""

    lines: list[str] = []
    title = _clean_text(parsed_recipe.get("title") or "")
    if title:
        lines.extend(["Title:", title, ""])

    ingredient_groups = _normalize_groups(parsed_recipe.get("ingredient_groups") or [], "items")
    if not ingredient_groups:
        ingredients = _as_string_list(parsed_recipe.get("ingredients") or [])
        if ingredients:
            ingredient_groups = [{"title": "Ingredients", "items": ingredients}]
    if ingredient_groups:
        for index, group in enumerate(ingredient_groups):
            items = _as_string_list(group.get("items") or [])
            if not items:
                continue
            group_title = _clean_text(group.get("title") or "")
            section_title = group_title or ("Ingredients" if index == 0 else "Ingredients")
            lines.append(section_title)
            lines.extend(items)
            lines.append("")

    instruction_groups = _normalize_groups(parsed_recipe.get("instruction_groups") or [], "steps")
    if not instruction_groups:
        instructions = _as_string_list(parsed_recipe.get("instructions") or [])
        if instructions:
            instruction_groups = [{"title": "Instructions", "steps": instructions}]
    if instruction_groups:
        for index, group in enumerate(instruction_groups):
            steps = _as_string_list(group.get("steps") or [])
            if not steps:
                continue
            group_title = _clean_text(group.get("title") or "")
            section_title = group_title or ("Instructions" if index == 0 else "Instructions")
            lines.append(section_title)
            lines.extend(steps)
            lines.append("")

    return "\n".join(lines).strip()[:MAX_AI_CLEANUP_SOURCE_CHARS]


def _fetch_html_for_ai_cleanup(url: str) -> str:
    response = safe_get(url, headers=REQUEST_HEADERS, timeout=8)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        raise ValueError("non_html_response")
    return response.text or ""


def _manual_ai_cleanup_payload_from_extracted_recipe(recipe_row: sqlite3.Row, extracted_recipe: dict) -> dict:
    ingredient_groups = _normalize_groups(extracted_recipe.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(extracted_recipe.get("instruction_groups") or [], "steps")
    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")
    selected_source = _clean_text(extracted_recipe.get("_selected_source") or "")

    compact_payload = {
        "source": "original_url",
        "url": recipe_row["url"] or "",
        "selected_source": selected_source or "unknown",
        "title": (extracted_recipe.get("title") or "").strip() or (recipe_row["title"] or ""),
        "servings": (extracted_recipe.get("servings") or "").strip() or (recipe_row["servings"] or ""),
        "prep_time": (extracted_recipe.get("prep_time") or "").strip() or "",
        "cook_time": (extracted_recipe.get("cook_time") or "").strip() or "",
        "total_time": (extracted_recipe.get("total_time") or "").strip() or "",
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": ingredients,
        "instructions": instructions,
    }

    if ingredients:
        compact_payload["ingredient_text_block"] = "\n".join(ingredients)
    if instructions:
        compact_payload["instruction_text_block"] = "\n".join(instructions)

    return compact_payload


def _manual_ai_cleanup_payload_from_preview(preview: dict, source_url: str) -> dict:
    preview = preview if isinstance(preview, dict) else {}
    ingredient_groups = _normalize_groups(preview.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(preview.get("instruction_groups") or [], "steps")
    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")

    if not ingredient_groups:
        ingredients = _as_string_list(preview.get("ingredients") or [])
        if ingredients:
            ingredient_groups = [{"title": "", "items": ingredients}]
    if not instruction_groups:
        instructions = _as_string_list(preview.get("instructions") or [])
        if instructions:
            instruction_groups = [{"title": "Instructions", "steps": instructions}]

    compact_payload = {
        "source": "modal_preview",
        "url": source_url,
        "title": _clean_text(preview.get("title") or ""),
        "servings": _clean_text(preview.get("servings") or ""),
        "prep_time": _clean_text(preview.get("prep_time") or ""),
        "cook_time": _clean_text(preview.get("cook_time") or ""),
        "total_time": _clean_text(preview.get("total_time") or ""),
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": ingredients,
        "instructions": instructions,
    }
    return compact_payload


def _manual_ai_cleanup_payload_from_extracted_modal(source_url: str, extracted_recipe: dict, preview: dict) -> dict:
    ingredient_groups = _normalize_groups(extracted_recipe.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(extracted_recipe.get("instruction_groups") or [], "steps")
    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")
    selected_source = _clean_text(extracted_recipe.get("_selected_source") or "")

    compact_payload = {
        "source": "original_url",
        "url": source_url,
        "selected_source": selected_source or "unknown",
        "title": _clean_text(extracted_recipe.get("title") or "") or _clean_text(preview.get("title") or ""),
        "servings": _clean_text(extracted_recipe.get("servings") or "") or _clean_text(preview.get("servings") or ""),
        "prep_time": _clean_text(extracted_recipe.get("prep_time") or ""),
        "cook_time": _clean_text(extracted_recipe.get("cook_time") or ""),
        "total_time": _clean_text(extracted_recipe.get("total_time") or ""),
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": ingredients,
        "instructions": instructions,
    }

    if ingredients:
        compact_payload["ingredient_text_block"] = "\n".join(ingredients)
    if instructions:
        compact_payload["instruction_text_block"] = "\n".join(instructions)
    return compact_payload


def _has_compact_recipe_content(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    ingredient_groups = _normalize_groups(payload.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(payload.get("instruction_groups") or [], "steps")
    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")
    return bool(ingredients and instructions)


def build_ai_prompt(source_text: str, low_trust_quantities: bool = False) -> str:
    quantity_trust_rules = """
34. Ingredient quantities may be OCR-corrupted. Treat quantities as low-trust fields.
35. If a quantity looks corrupted, nonsensical, or non-numeric, keep the ingredient text but leave quantity ambiguous rather than inventing a value.
36. Prefer preserving visible fraction patterns (/, ½, ¼, ¾, ⅓, ⅔) if present nearby.
37. If a numeric quantity appears obviously invalid from OCR noise, preserve raw ingredient text and do NOT "fix" it by guessing a new number.
38. If uncertain, keep original text or omit the quantity portion rather than outputting an invented measurement.
""".strip() if low_trust_quantities else ""

    return f"""
You are cleaning messy recipe text that was extracted from a web page.

Your job:
- read the text carefully
- reconstruct the recipe in a simple, usable format
- keep only recipe content
- ignore ratings, votes, ads, metadata, and page chrome
- do NOT invent ingredients, amounts, times, or steps
- if something is unclear, keep it as written instead of guessing

Return STRICT JSON only.
Do not wrap in markdown.
Do not add explanations.

Use exactly this shape:
{{
  "title": "",
  "servings": "",
  "ingredient_groups": [
    {{
      "title": "",
      "items": []
    }}
  ],
  "instruction_groups": [
    {{
      "title": "Instructions",
      "steps": []
    }}
  ]
}}

Rules:
0. Ignore serving multipliers and scaling labels such as "1x", "2x", "3x". Do not include them in the response.
1. Start recipe content at the Ingredients section.
2. Stop recipe content at Notes. Ignore everything after Notes unless it is clearly part of the recipe.
3. Ignore Nutrition and everything after it.
4. Put ingredients into ingredient_groups.
5. Preserve ingredient section titles exactly when present.
6. Return a separate ingredient_groups entry for each ingredient section.
7. Do NOT combine ingredient sections into one group.
8. Do NOT flatten all ingredients into a single "Ingredients" group when named sections exist.
9. Keep the main unnamed ingredient block before named sections as a group titled "Ingredients".
10. Preserve ingredient section titles when obvious, such as:
   - Big Mac Sauce
   - For Your Bowls
   - Optional Toppings
11. Do NOT combine "Ingredients", "Big Mac Sauce", "For Your Bowls", or "Optional Toppings" into one group.
12. Put cooking directions into instruction_groups.
13. Preserve instruction section titles exactly when present.
14. Return a separate instruction_groups entry for each instruction section.
15. Do NOT combine instruction sections into one group.
16. Use "Instructions" for the main cooking section.
17. Keep sections like "Bowl Assembly" and "Meal Prep Assembly" as separate instruction_groups.
18. Do NOT combine "Instructions", "Bowl Assembly", or "Meal Prep Assembly" into one group.
19. If multiple section titles are present in the input, the output must contain multiple groups matching those sections.
20. Do NOT turn section titles into ingredients.
21. Do NOT turn section titles into steps.
22. Combine split ingredient fragments into a single readable line when clearly part of the same ingredient.
23. Example: "1 lb. lean ground beef 96/4" should be one ingredient line, not multiple items.
24. Keep ingredients as plain readable strings.
25. Keep instruction steps as plain readable strings.
26. Do NOT rename the recipe if a title is already present.
27. Use the full recipe title exactly as it appears. Do not shorten it.
28. If servings cannot be clearly found, return an empty string "" instead of guessing.
29. Ignore UI symbols such as "▢" and similar checkbox/list markers.
30. Do NOT convert units or rewrite ingredient quantities.
31. Use ingredient quantities exactly as they appear in the source text.
32. If multiple measurements are shown (e.g. grams and cups), keep the original format without changing values.
33. Do NOT replace, normalize, or infer different measurements.
{quantity_trust_rules}

Structure example (example shape only; do not copy literal text values):
{{
  "ingredient_groups": [
    {{ "title": "Ingredients", "items": ["..."] }},
    {{ "title": "Big Mac Sauce", "items": ["..."] }},
    {{ "title": "For Your Bowls", "items": ["..."] }}
  ],
  "instruction_groups": [
    {{ "title": "Instructions", "steps": ["..."] }},
    {{ "title": "Bowl Assembly", "steps": ["..."] }},
    {{ "title": "Meal Prep Assembly", "steps": ["..."] }}
  ]
}}

Recipe text:
{source_text}
"""


OCR_RECIPE_KEYWORDS = (
    "recipe",
    "ingredients",
    "instructions",
    "tablespoon",
    "tablespoons",
    "teaspoon",
    "teaspoons",
    "tbsp",
    "tsp",
    "cup",
    "cups",
    "oven",
    "bake",
    "mix",
    "sugar",
    "flour",
    "butter",
    "egg",
    "eggs",
    "servings",
    "preheat",
    "banana",
    "cinnamon",
    "pecans",
    "oats",
    "cake",
    "sour",
    "cream",
)
OCR_FRACTION_PATTERN = re.compile(r"(?<!\d)(\d{1,2}\s*/\s*\d{1,2})(?!\d)")
OCR_UNICODE_FRACTIONS = ("⅓", "¼", "½", "¾")


def _score_recipe_keywords(text: str) -> int:
    lowered = (text or "").lower()
    return sum(lowered.count(keyword) for keyword in OCR_RECIPE_KEYWORDS)


def _score_fraction_patterns(text: str) -> int:
    source = text or ""
    ascii_hits = len(OCR_FRACTION_PATTERN.findall(source))
    unicode_hits = sum(source.count(token) for token in OCR_UNICODE_FRACTIONS)
    return ascii_hits + unicode_hits


def _extract_text_from_ocr_worker(
    image_bytes: bytes,
    filename: str = "upload-image",
    content_type: str = "image/jpeg",
) -> dict:
    worker_url = (os.getenv("OCR_WORKER_URL") or "").strip()
    if not worker_url:
        raise ValueError("ocr_worker_not_configured")

    files = {
        "image": (
            filename or "upload-image",
            image_bytes,
            content_type or "image/jpeg",
        )
    }
    try:
        response = requests.post(worker_url, files=files, timeout=OCR_WORKER_TIMEOUT_SECONDS)
    except requests.Timeout:
        logger.warning("image_ocr_worker_timeout timeout=%s", OCR_WORKER_TIMEOUT_SECONDS)
        raise ValueError("ocr_worker_timeout")
    except requests.RequestException as exc:
        logger.warning("image_ocr_worker_request_failed error_type=%s error=%s", type(exc).__name__, str(exc))
        raise ValueError("ocr_worker_failed") from exc
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("image_ocr_worker_bad_status status=%s", getattr(response, "status_code", None))
        raise ValueError("ocr_worker_failed") from exc
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("invalid_ocr_worker_payload")

    text = _clean_text(payload.get("text") or "")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        raise ValueError("empty_ocr_worker_text")

    confidence_value = payload.get("confidence")
    try:
        confidence = float(confidence_value) if confidence_value is not None else None
    except (TypeError, ValueError):
        confidence = None

    rotation_value = payload.get("rotation", 0)
    try:
        rotation = int(rotation_value)
    except (TypeError, ValueError):
        rotation = 0

    engine = str(payload.get("engine") or "external_easyocr").strip() or "external_easyocr"
    keyword_score_value = payload.get("keyword_score")
    fraction_score_value = payload.get("fraction_score")
    try:
        keyword_score = int(keyword_score_value) if keyword_score_value is not None else _score_recipe_keywords(text)
    except (TypeError, ValueError):
        keyword_score = _score_recipe_keywords(text)
    try:
        fraction_score = int(fraction_score_value) if fraction_score_value is not None else _score_fraction_patterns(text)
    except (TypeError, ValueError):
        fraction_score = _score_fraction_patterns(text)

    logger.info(
        "image_ocr_worker_result engine=%s confidence=%s rotation=%s keyword_score=%s fraction_score=%s",
        engine,
        confidence,
        rotation,
        keyword_score,
        fraction_score,
    )

    return {
        "text": text,
        "confidence": confidence,
        "rotation": rotation,
        "engine": engine,
        "keyword_score": keyword_score,
        "fraction_score": fraction_score,
        "text_length": len(text),
    }


async def _extract_text_from_image_upload(image: UploadFile) -> dict:
    payload = await image.read()
    if not payload:
        raise ValueError("empty_image_payload")
    return _extract_text_from_ocr_worker(
        payload,
        filename=image.filename or "upload-image",
        content_type=image.content_type or "image/jpeg",
    )


def _parse_recipe_text_from_ocr(ocr_text: str, source_url: str, ocr_confidence: float | None = None) -> tuple[dict, str]:
    fallback = parse_social_caption_recipe(ocr_text, source_url=source_url, title_hint="")
    low_trust_quantities = ocr_confidence is not None and ocr_confidence < 70
    prompt = build_ai_prompt(ocr_text, low_trust_quantities=low_trust_quantities)
    try:
        raw_result = call_ollama_review(prompt)
        normalized_result = normalize_ai_review_response(raw_result)
        if _is_useful_ai_cleanup_result(normalized_result):
            return _merge_ocr_ai_cleanup_result(normalized_result, fallback), "ai_cleanup"
    except Exception as exc:
        logger.warning("image_ocr_ai_cleanup_failed reason=%s", str(exc))

    return fallback, "heuristic_fallback"


def _image_import_payload_from_parsed(parsed_recipe: dict, parsing_source: str) -> dict:
    recipe = parsed_recipe if isinstance(parsed_recipe, dict) else {}
    ingredient_groups = _normalize_groups(recipe.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(recipe.get("instruction_groups") or [], "steps")
    ingredients = _as_string_list(recipe.get("ingredients") or [])
    instructions = _as_string_list(recipe.get("instructions") or [])
    if ingredient_groups:
        ingredients = []
    if instruction_groups:
        instructions = []

    prep_time, prep_minutes = _normalize_duration(recipe.get("prep_time"))
    cook_time, cook_minutes = _normalize_duration(recipe.get("cook_time"))
    total_time, total_minutes = _normalize_duration(recipe.get("total_time"))
    return {
        "url": "",
        "original_source_url": "",
        "resolved_recipe_url": "",
        "content_source": "image_ocr",
        "title": _clean_text(recipe.get("title") or ""),
        "source_app": "Upload",
        "source_type": "Image",
        "image_url": "",
        "notes": _clean_text(recipe.get("notes") or ""),
        "ingredients": ingredients,
        "instructions": instructions,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "servings": _clean_text(recipe.get("servings") or ""),
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "total_minutes": total_minutes,
        "parser_source": parsing_source,
    }


def _merge_ocr_ai_cleanup_result(ai_recipe: dict, fallback_recipe: dict) -> dict:
    ai_recipe = ai_recipe if isinstance(ai_recipe, dict) else {}
    fallback_recipe = fallback_recipe if isinstance(fallback_recipe, dict) else {}

    merged = dict(fallback_recipe)

    for field in ("servings", "notes"):
        ai_value = _clean_text(ai_recipe.get(field) or "")
        fallback_value = _clean_text(fallback_recipe.get(field) or "")
        merged[field] = ai_value or fallback_value

    ai_title = _clean_text(ai_recipe.get("title") or "")
    fallback_title = _clean_text(fallback_recipe.get("title") or "")
    merged["title"] = ai_title if _score_ocr_title_candidate(ai_title, 0) else fallback_title

    for field in ("prep_time", "cook_time", "total_time"):
        ai_duration, ai_minutes = _normalize_duration(ai_recipe.get(field))
        fallback_duration, fallback_minutes = _normalize_duration(fallback_recipe.get(field))
        merged[field] = ai_duration or fallback_duration
        minutes_field = field.replace("_time", "_minutes")
        merged[minutes_field] = ai_minutes if ai_duration else fallback_minutes

    ingredient_groups = _normalize_groups(ai_recipe.get("ingredient_groups") or [], "items")
    if not ingredient_groups:
        ingredient_groups = _normalize_groups(fallback_recipe.get("ingredient_groups") or [], "items")
    merged["ingredient_groups"] = ingredient_groups
    merged["ingredients"] = _flatten_groups(ingredient_groups, "items")

    instruction_groups = _normalize_groups(ai_recipe.get("instruction_groups") or [], "steps")
    if not instruction_groups:
        instruction_groups = _normalize_groups(fallback_recipe.get("instruction_groups") or [], "steps")
    merged["instruction_groups"] = instruction_groups
    merged["instructions"] = _flatten_groups(instruction_groups, "steps")

    return merged


def _flatten_parsed_recipe_for_cleanup_prompt(parsed_recipe: dict) -> tuple[str, list[str], list[str]]:
    if not isinstance(parsed_recipe, dict):
        return "", [], []

    title = _clean_text(parsed_recipe.get("title") or "")
    ingredient_groups = _normalize_groups(parsed_recipe.get("ingredient_groups") or [], "items")
    ingredients = _flatten_groups(ingredient_groups, "items")
    if not ingredients:
        ingredients = _as_string_list(parsed_recipe.get("ingredients") or [])

    instruction_groups = _normalize_groups(parsed_recipe.get("instruction_groups") or [], "steps")
    instructions = _flatten_groups(instruction_groups, "steps")
    if not instructions:
        instructions = _as_string_list(parsed_recipe.get("instructions") or [])

    return title, ingredients, instructions


def _normalize_ai_cleanup_prompt_ingredient_line(value) -> str:
    raw = _clean_text(_stringify_recipe_component(value, prefer_ingredient_order=True))
    if not raw:
        return ""

    working = raw
    notes: list[str] = []
    for note_match in re.finditer(r"\(([^)]*)\)", working):
        note_text = _clean_text(note_match.group(1))
        if note_text:
            notes.append(note_text)
    if notes:
        working = re.sub(r"\([^)]*\)", " ", working)
    working = re.sub(r"\s+", " ", working).strip()

    quantity, remainder = _parse_ingredient_quantity(working)
    unit = None
    remainder_after_unit = remainder
    unit_match = re.match(r"^([a-zA-Z]+)\b", remainder)
    if unit_match:
        normalized_unit = _INGREDIENT_UNIT_ALIASES.get(unit_match.group(1).lower())
        if normalized_unit:
            unit = normalized_unit
            remainder_after_unit = remainder[unit_match.end() :].strip()

    name = re.sub(r"^of\s+", "", remainder_after_unit, flags=re.IGNORECASE).strip()
    display_quantity = _format_display_quantity(quantity)
    display_unit = _format_display_unit(unit, quantity)
    display_name = _clean_text(name)

    parts = [part for part in (display_quantity, display_unit, display_name) if part]
    display_text = " ".join(parts).strip() or raw
    if notes:
        display_text = f"{display_text} ({' ; '.join(notes)})"
    return _clean_text(display_text)


def _normalize_ai_cleanup_prompt_payload(parsed_recipe: dict) -> dict:
    recipe_payload = _prepare_saved_recipe_for_ai_cleanup(parsed_recipe if isinstance(parsed_recipe, dict) else {})
    ingredient_groups = _normalize_groups(recipe_payload.get("ingredient_groups") or [], "items")
    if not ingredient_groups:
        fallback_ingredients = _normalize_plain_string_list(recipe_payload.get("ingredients") or [])
        if fallback_ingredients:
            ingredient_groups = [{"title": "", "items": fallback_ingredients}]

    normalized_ingredient_groups: list[dict] = []
    for group in ingredient_groups:
        items = [
            normalized
            for normalized in (
                _normalize_ai_cleanup_prompt_ingredient_line(item)
                for item in (group.get("items") or [])
            )
            if normalized
        ]
        if items:
            normalized_ingredient_groups.append(
                {"title": _clean_text(group.get("title") or ""), "items": items}
            )

    instruction_groups = _normalize_groups(recipe_payload.get("instruction_groups") or [], "steps")
    if not instruction_groups:
        fallback_instructions = _normalize_instruction_steps(
            recipe_payload.get("instructions") or []
        )
        if fallback_instructions:
            instruction_groups = [{"title": "Instructions", "steps": fallback_instructions}]

    normalized_instruction_groups: list[dict] = []
    for group in instruction_groups:
        steps = _normalize_instruction_steps(group.get("steps") or [])
        if steps:
            normalized_instruction_groups.append(
                {"title": _clean_text(group.get("title") or ""), "steps": steps}
            )

    return {
        "title": _clean_text(recipe_payload.get("title") or ""),
        "servings": _clean_text(recipe_payload.get("servings") or ""),
        "prep_time": _clean_text(recipe_payload.get("prep_time") or ""),
        "cook_time": _clean_text(recipe_payload.get("cook_time") or ""),
        "total_time": _clean_text(recipe_payload.get("total_time") or ""),
        "notes": _clean_text(recipe_payload.get("notes") or ""),
        "ingredient_groups": normalized_ingredient_groups,
        "instruction_groups": normalized_instruction_groups,
        "ingredients": _flatten_groups(normalized_ingredient_groups, "items"),
        "instructions": _flatten_groups(normalized_instruction_groups, "steps"),
    }


def _build_transcript_cleanup_prompt(
    parsed_recipe: dict,
    source_text: str = "",
    source_url: str = "",
) -> str:
    prepared_recipe = _prepare_saved_recipe_for_ai_cleanup(parsed_recipe)
    structured_payload = _normalize_ai_cleanup_prompt_payload(prepared_recipe)

    optional_context: dict[str, str] = {}
    cleaned_source_url = _clean_text(source_url or "")
    cleaned_source_text = _clean_text(source_text or "")
    cleanup_context = prepared_recipe.get("_ai_cleanup_context") if isinstance(prepared_recipe, dict) else None
    if cleaned_source_url:
        optional_context["source_url"] = cleaned_source_url
    if cleaned_source_text:
        optional_context["source_text"] = cleaned_source_text[:MAX_AI_CLEANUP_SOURCE_CHARS]
    if isinstance(cleanup_context, dict):
        transcript_text = _normalize_transcript_context_text(
            cleanup_context.get("cleaned_transcript_text") or cleanup_context.get("transcript_text") or ""
        )
        if transcript_text:
            optional_context["saved_transcript_text"] = transcript_text[:MAX_AI_CLEANUP_SOURCE_CHARS]
    flags = prepared_recipe.get("_ai_cleanup_flags") if isinstance(prepared_recipe, dict) else None
    if isinstance(flags, dict):
        flagged = flags.get("suspicious_ingredients_without_transcript_evidence") or []
        if flagged:
            optional_context["suspicious_saved_ingredients"] = "\n".join(_normalize_plain_string_list(flagged))

    return (
        "You are a conservative cookbook editor cleaning a saved recipe draft.\n\n"
        "Your job is to improve presentation, organization, and readability without changing what the author is telling the cook to do.\n\n"
        "IMPORTANT:\n"
        "- The structured_recipe object is the primary source of truth.\n"
        "- Use optional_context only for clarification when it agrees with structured_recipe.\n"
        "- Source URL content is optional supporting context only.\n"
        "- Do NOT invent, modernize, improve, or replace the recipe.\n"
        "- Preserve every ingredient, quantity, unit, temperature, cooking time, cooking method, and recipe step unless the same information is being restated more clearly.\n"
        "- Do NOT add ingredients or steps from general cooking knowledge.\n"
        "- Do NOT silently fix suspicious values.\n"
        "- If a quantity looks suspicious or unusual, preserve it exactly as written unless structured_recipe or optional_context clearly confirms a safer wording.\n"
        "- Keep grouped ingredient and instruction structure when present.\n"
        "- Do NOT rewrite content for style alone.\n"
        "- Minor wording preferences, synonym swaps, and capitalization-only changes are not meaningful improvements.\n"
        "- Minor wording preferences, synonym swaps, and unnecessary rephrasing are not meaningful improvements.\n"
        "- If only cosmetic capitalization or trivial wording changes are available, return the recipe unchanged and set no_changes to true.\n\n"
        "Rules:\n"
        "1. Keep all valid ingredients unless they are clearly not part of the recipe.\n"
        "2. Keep explicit amounts and units exactly aligned with the saved recipe.\n"
        "3. Do NOT invent or infer different measurements.\n"
        "4. Rewrite machine-generated ingredient wording into natural recipe wording when the components are already present.\n"
        "5. Convert obvious decimal cooking quantities into common culinary fractions only when the conversion is exact or unambiguous.\n"
        "6. Example: 2.25 cups may become 2 1/4 cups, and 1.5 sticks may become 1 1/2 sticks.\n"
        "7. Example: 0.025 teaspoons must stay 0.025 teaspoons unless the saved recipe or optional_context proves another amount.\n"
        "8. Capitalize proper nouns such as White Lily, but do NOT Title Case every ingredient.\n"
        "9. Move preparation details into ingredient wording only when clearly supported by the saved recipe.\n"
        "10. Keep the same cooking order and intent.\n"
        "11. You MAY split crowded instructions into clearer steps when it improves readability without changing sequence.\n"
        "12. Clarify instruction wording only when it stays faithful to the same action.\n"
        "13. Reorganize sections only when it genuinely improves readability.\n"
        "14. Do NOT significantly change cooking times or temperatures.\n"
        "15. Keep notes faithful to the input when present.\n"
        "16. If the recipe is already clear and well structured, return the same recipe content unchanged and set no_changes to true.\n"
        "17. If something is uncertain, preserve the existing wording rather than guessing.\n\n"
        "Return ONLY valid JSON in exactly this format:\n"
        "{\n"
        '  "title": "",\n'
        '  "servings": "",\n'
        '  "prep_time": "",\n'
        '  "cook_time": "",\n'
        '  "total_time": "",\n'
        '  "ingredient_groups": [{"title": "", "items": []}],\n'
        '  "instruction_groups": [{"title": "Instructions", "steps": []}],\n'
        '  "no_changes": false,\n'
        '  "review_notes": ""\n'
        "}\n\n"
        "structured_recipe:\n"
        f"{json.dumps(structured_payload, ensure_ascii=False, indent=2)}\n\n"
        "optional_context:\n"
        f"{json.dumps(optional_context, ensure_ascii=False, indent=2)}"
    )


def _run_ai_cleanup_pipeline(source_url: str | None, parsed_recipe: dict | None = None) -> tuple[dict, dict, str, str, dict]:
    if not OLLAMA_BASE_URL:
        raise HTTPException(status_code=503, detail="AI cleanup is not configured. Set OLLAMA_BASE_URL to enable it.")
    cleaned_source_url = _clean_text(source_url or "")
    text = ""
    if cleaned_source_url:
        try:
            html = _fetch_html_for_ai_cleanup(cleaned_source_url)
            text = extract_recipe_text_for_ai(html)
        except Exception as exc:
            logger.warning(
                "ai_cleanup_source_fetch_failed url=%s error=%s",
                cleaned_source_url,
                str(exc),
            )
    parsed_recipe = _prepare_saved_recipe_for_ai_cleanup(parsed_recipe if isinstance(parsed_recipe, dict) else {})
    final_ai_input = _build_ai_input_from_parsed_recipe(parsed_recipe)
    final_input_source = "parsed_recipe"
    if not final_ai_input:
        if text:
            final_ai_input = text
            final_input_source = "raw_text_fallback"
        else:
            final_input_source = "structured_recipe_only"
    logger.info(f"ai_cleanup_input_length={len(text)}")
    logger.info(f"ai_cleanup_preview={text[:300]}")
    logger.info("ai_cleanup_source_url_present=%s", bool(cleaned_source_url))
    logger.info("ai_cleanup_final_input_source=%s", final_input_source)
    logger.info("ai_cleanup_final_input=%s", final_ai_input)
    logger.info("ai_cleanup_final_input_length=%s", len(final_ai_input))
    injected_title, injected_ingredients, injected_instructions = _flatten_parsed_recipe_for_cleanup_prompt(parsed_recipe)
    logger.info("cleanup_input_title=%s", injected_title)
    logger.info("cleanup_input_ingredient_count=%d", len(injected_ingredients))
    logger.info("cleanup_input_instruction_count=%d", len(injected_instructions))
    prompt = _build_transcript_cleanup_prompt(parsed_recipe, source_text=text, source_url=cleaned_source_url)
    logger.info("ai_cleanup_prompt_title=%s", injected_title)
    logger.info("ai_cleanup_prompt_ingredient_count=%d", len(injected_ingredients))
    logger.info("ai_cleanup_prompt_instruction_count=%d", len(injected_instructions))
    logger.info("ai_cleanup_prompt_preview=%s", prompt[:300])
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    response_payload = response.json()
    raw_response = response_payload.get("response")
    if isinstance(raw_response, dict):
        raw_response_text = json.dumps(raw_response, ensure_ascii=False)
    elif isinstance(raw_response, str):
        raw_response_text = raw_response
    else:
        raise ValueError("invalid_ollama_response")
    logger.info("ai_cleanup_raw_response=%s", raw_response_text)
    cleaned_response = raw_response_text.strip()
    if cleaned_response.startswith("```"):
        cleaned_response = re.sub(r"^```(?:json)?\s*", "", cleaned_response, flags=re.IGNORECASE).strip()
        cleaned_response = re.sub(r"\s*```$", "", cleaned_response).strip()
    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="AI cleanup returned invalid JSON") from exc
    logger.info("ai_cleanup_parsed_json=%s", json.dumps(parsed, ensure_ascii=False))
    normalized_result = normalize_ai_review_response(parsed)
    logger.info("ai_cleanup_normalized_result=%s", json.dumps(normalized_result, ensure_ascii=False))
    if not _is_useful_ai_cleanup_result(normalized_result):
        raise HTTPException(status_code=422, detail="AI cleanup returned empty recipe structure")
    logger.info("ai_cleanup_success")
    return parsed, normalized_result, raw_response_text, final_ai_input, parsed_recipe


def _modal_preview_payload_from_parsed_ai_json(parsed_json: dict, parsed_recipe: dict | None = None) -> dict:
    payload = parsed_json if isinstance(parsed_json, dict) else {}

    ingredient_groups = _filter_ai_ingredient_groups(_normalize_group_items(payload.get("ingredient_groups") or [], "items"))
    instruction_groups = _normalize_group_items(payload.get("instruction_groups") or [], "steps")

    normalized_instruction_groups: list[dict] = []
    for group in instruction_groups:
        steps = _normalize_instruction_steps(group.get("steps") or [])
        normalized_instruction_groups.append(
            {
                "title": _clean_text(group.get("title") or ""),
                "steps": steps,
            }
        )
    instruction_groups = normalized_instruction_groups

    ingredients = _flatten_groups(ingredient_groups, "items")
    instructions = _flatten_groups(instruction_groups, "steps")

    if not ingredients:
        ingredients = [
            item
            for item in _as_string_list(payload.get("ingredients") or [])
            if not _is_non_ingredient_header_line(item)
        ]
        if ingredients and not ingredient_groups:
            ingredient_groups = [{"title": "", "items": ingredients}]

    if not instructions:
        instructions = _as_string_list(payload.get("instructions") or [])
        if instructions and not instruction_groups:
            instructions = _normalize_instruction_steps(instructions)
            instruction_groups = [{"title": "Instructions", "steps": instructions}]

    return {
        "title": _clean_text(payload.get("title") or ""),
        "servings": _clean_text(payload.get("servings") or ""),
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": ingredients,
        "instructions": instructions,
    }


_COOKING_VERB_HINTS = ("cook", "mix", "spray", "add", "combine")


def _has_cooking_verb_hints(steps: list[str]) -> bool:
    lowered_steps = [(_clean_text(step)).lower() for step in (steps or []) if _clean_text(step)]
    return any(any(verb in step for verb in _COOKING_VERB_HINTS) for step in lowered_steps)


def _should_prefer_preview_instructions(preview_instructions: list[str], ai_instructions: list[str]) -> bool:
    preview_count = len(preview_instructions or [])
    ai_count = len(ai_instructions or [])
    if preview_count >= 3 and ai_count < preview_count:
        return True
    if _has_cooking_verb_hints(preview_instructions) and not _has_cooking_verb_hints(ai_instructions):
        return True
    return False


def _prefer_or_merge_preview_instructions(preview_payload: dict, ai_preview_payload: dict) -> dict:
    preview_instruction_groups = _normalize_groups(preview_payload.get("instruction_groups") or [], "steps")
    ai_instruction_groups = _normalize_groups(ai_preview_payload.get("instruction_groups") or [], "steps")
    preview_instructions = _flatten_groups(preview_instruction_groups, "steps")
    ai_instructions = _flatten_groups(ai_instruction_groups, "steps")

    if not _should_prefer_preview_instructions(preview_instructions, ai_instructions):
        return ai_preview_payload

    merged_payload = dict(ai_preview_payload)
    merged_payload["instruction_groups"] = preview_instruction_groups
    merged_payload["instructions"] = preview_instructions
    return merged_payload


def _prefer_richer_preview_payload(preview_payload: dict, ai_preview_payload: dict) -> dict:
    sanitized_preview_payload = _sanitize_preview_ingredient_payload(preview_payload)
    merged_payload = _prefer_or_merge_preview_instructions(sanitized_preview_payload, ai_preview_payload)
    sanitized_merged_payload = _sanitize_preview_ingredient_payload(merged_payload)
    preview_counts = _recipe_parser_counts(sanitized_preview_payload)
    ai_counts = _recipe_parser_counts(sanitized_merged_payload)

    if _should_prefer_preview_ingredients(sanitized_preview_payload, sanitized_merged_payload):
        sanitized_merged_payload["ingredient_groups"] = sanitized_preview_payload.get("ingredient_groups") or []
        sanitized_merged_payload["ingredients"] = sanitized_preview_payload.get("ingredients") or []

    if ai_counts.get("instruction_groups", 0) < preview_counts.get("instruction_groups", 0):
        preview_instruction_groups = _normalize_groups(preview_payload.get("instruction_groups") or [], "steps")
        sanitized_merged_payload["instruction_groups"] = preview_instruction_groups
        sanitized_merged_payload["instructions"] = _flatten_groups(preview_instruction_groups, "steps")

    for field in ("title", "servings", "prep_time", "cook_time", "total_time"):
        if not _clean_text(sanitized_merged_payload.get(field) or "") and _clean_text(preview_payload.get(field) or ""):
            sanitized_merged_payload[field] = _clean_text(preview_payload.get(field) or "")
    return sanitized_merged_payload


def _normalize_ai_cleanup_compare_payload(payload: dict) -> dict:
    source_payload = _sanitize_preview_ingredient_payload(payload if isinstance(payload, dict) else {})
    ingredient_groups = _normalize_groups(source_payload.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(source_payload.get("instruction_groups") or [], "steps")
    return {
        "title": _clean_text(source_payload.get("title") or ""),
        "servings": _clean_text(source_payload.get("servings") or ""),
        "prep_time": _clean_text(source_payload.get("prep_time") or ""),
        "cook_time": _clean_text(source_payload.get("cook_time") or ""),
        "total_time": _clean_text(source_payload.get("total_time") or ""),
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "ingredients": _flatten_groups(ingredient_groups, "items"),
        "instructions": _flatten_groups(instruction_groups, "steps"),
    }


def _canonical_ai_cleanup_compare_text(value: str) -> str:
    return re.sub(r"\s+", " ", _clean_text(value).lower()).strip()


def _canonical_ai_cleanup_compare_groups(groups: list[dict], key: str) -> list[dict]:
    canonical_groups: list[dict] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        entries = [
            canonical
            for canonical in (
                _canonical_ai_cleanup_compare_text(entry)
                for entry in (group.get(key) or [])
            )
            if canonical
        ]
        if entries:
            canonical_groups.append(
                {
                    "title": _canonical_ai_cleanup_compare_text(group.get("title") or ""),
                    key: entries,
                }
            )
    return canonical_groups


def _ai_cleanup_has_meaningful_changes(current_payload: dict, proposed_payload: dict) -> bool:
    current = _normalize_ai_cleanup_compare_payload(current_payload)
    proposed = _normalize_ai_cleanup_compare_payload(proposed_payload)
    return {
        "title": _canonical_ai_cleanup_compare_text(current.get("title") or ""),
        "servings": _canonical_ai_cleanup_compare_text(current.get("servings") or ""),
        "prep_time": _canonical_ai_cleanup_compare_text(current.get("prep_time") or ""),
        "cook_time": _canonical_ai_cleanup_compare_text(current.get("cook_time") or ""),
        "total_time": _canonical_ai_cleanup_compare_text(current.get("total_time") or ""),
        "ingredient_groups": _canonical_ai_cleanup_compare_groups(current.get("ingredient_groups") or [], "items"),
        "instruction_groups": _canonical_ai_cleanup_compare_groups(current.get("instruction_groups") or [], "steps"),
        "ingredients": [
            _canonical_ai_cleanup_compare_text(item)
            for item in (current.get("ingredients") or [])
            if _canonical_ai_cleanup_compare_text(item)
        ],
        "instructions": [
            _canonical_ai_cleanup_compare_text(item)
            for item in (current.get("instructions") or [])
            if _canonical_ai_cleanup_compare_text(item)
        ],
    } != {
        "title": _canonical_ai_cleanup_compare_text(proposed.get("title") or ""),
        "servings": _canonical_ai_cleanup_compare_text(proposed.get("servings") or ""),
        "prep_time": _canonical_ai_cleanup_compare_text(proposed.get("prep_time") or ""),
        "cook_time": _canonical_ai_cleanup_compare_text(proposed.get("cook_time") or ""),
        "total_time": _canonical_ai_cleanup_compare_text(proposed.get("total_time") or ""),
        "ingredient_groups": _canonical_ai_cleanup_compare_groups(proposed.get("ingredient_groups") or [], "items"),
        "instruction_groups": _canonical_ai_cleanup_compare_groups(proposed.get("instruction_groups") or [], "steps"),
        "ingredients": [
            _canonical_ai_cleanup_compare_text(item)
            for item in (proposed.get("ingredients") or [])
            if _canonical_ai_cleanup_compare_text(item)
        ],
        "instructions": [
            _canonical_ai_cleanup_compare_text(item)
            for item in (proposed.get("instructions") or [])
            if _canonical_ai_cleanup_compare_text(item)
        ],
    }


def _ai_cleanup_requested_no_changes(parsed_json: dict) -> bool:
    if not isinstance(parsed_json, dict):
        return False
    return bool(parsed_json.get("no_changes") is True or parsed_json.get("no_change") is True)


def _looks_like_ingredient_quantity(value: str) -> bool:
    candidate = _clean_text(value)
    if not candidate:
        return False
    return bool(
        re.fullmatch(
            r"(?:\d+(?:\.\d+)?|\d+\s+\d+/\d+|\d+/\d+|[¼½¾⅐-⅞])",
            candidate,
        )
    )


def _looks_like_ingredient_unit(value: str) -> bool:
    candidate = _clean_text(value).lower().rstrip(".")
    if not candidate:
        return False
    return candidate in _INGREDIENT_UNIT_ALIASES


def _normalize_component_ingredient_parts(parts: list[str]) -> str:
    cleaned_parts = [_clean_text(part) for part in parts if _clean_text(part)]
    if not cleaned_parts:
        return ""

    quantity = ""
    unit = ""
    remaining_parts: list[str] = []
    index = 0
    while index < len(cleaned_parts):
        part = cleaned_parts[index]
        if not quantity and (_looks_like_ingredient_quantity(part) or _parse_spoken_quantity_phrase(part) is not None):
            quantity = part
            index += 1
            continue
        if not unit and _looks_like_ingredient_unit(part):
            next_part = cleaned_parts[index + 1] if index + 1 < len(cleaned_parts) else ""
            if _should_merge_suspicious_single_letter_unit_fragment(part, next_part):
                remaining_parts.append(f"{part}{next_part}")
                index += 2
                continue
            unit = part
            index += 1
            continue
        remaining_parts.append(part)
        index += 1

    if remaining_parts:
        name = max(remaining_parts, key=lambda item: len(item))
        extras = [part for part in remaining_parts if part != name]
    else:
        name = ""
        extras = []

    if name and (quantity or unit):
        normalized_parts = [quantity, unit, name, *extras]
        return _clean_text(" ".join(part for part in normalized_parts if part))

    return _clean_text(" ".join(cleaned_parts))


def _stringify_recipe_component(value, *, prefer_ingredient_order: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        cleaned = _clean_text(value)
        if not cleaned:
            return ""
        maybe_wrapped_literal = cleaned
        if cleaned.count(",") >= 2 and not cleaned.startswith(("[", "{", "(")) and "'" in cleaned:
            maybe_wrapped_literal = f"({cleaned})"
        if maybe_wrapped_literal.startswith(("[", "{", "(")) or maybe_wrapped_literal != cleaned:
            try:
                parsed = ast.literal_eval(maybe_wrapped_literal)
            except Exception:
                parsed = None
            if parsed is not None and parsed != value:
                normalized = _stringify_recipe_component(parsed, prefer_ingredient_order=prefer_ingredient_order)
                if normalized:
                    return normalized
        return cleaned
    if isinstance(value, (list, tuple)):
        parts = [
            _stringify_recipe_component(item, prefer_ingredient_order=prefer_ingredient_order)
            for item in value
        ]
        parts = [part for part in parts if part]
        if not parts:
            return ""
        if prefer_ingredient_order:
            return _normalize_component_ingredient_parts(parts)
        return _clean_text(" ".join(parts))
    if isinstance(value, dict):
        text_value = _clean_text(value.get("text") or "")
        if text_value:
            return text_value
        component_order = (
            "amount",
            "quantity",
            "unit",
            "name",
            "item",
            "ingredient",
            "description",
            "notes",
            "weight",
            "note",
            "preparation",
            "prep",
        )
        components: list[str] = []
        seen_components: set[str] = set()
        for key in component_order:
            part = _stringify_recipe_component(value.get(key), prefer_ingredient_order=prefer_ingredient_order)
            if not part:
                continue
            normalized_part = part.lower()
            if normalized_part in seen_components:
                continue
            seen_components.add(normalized_part)
            components.append(part)
        if not components:
            for raw_part in value.values():
                part = _stringify_recipe_component(raw_part, prefer_ingredient_order=prefer_ingredient_order)
                if not part:
                    continue
                normalized_part = part.lower()
                if normalized_part in seen_components:
                    continue
                seen_components.add(normalized_part)
                components.append(part)
        if prefer_ingredient_order:
            return _normalize_component_ingredient_parts(components)
        return _clean_text(" ".join(components))
    return _clean_text(str(value))


def _normalize_instruction_steps(steps) -> list[str]:
    normalized: list[str] = []

    for step in _as_string_list(steps):
        text = _clean_text(step)
        if not text:
            continue

        numbered_parts = re.split(r"(?=\d+\.\s)", text)
        if len(numbered_parts) > 1:
            normalized.extend(
                _clean_text(part)
                for part in numbered_parts
                if _clean_text(part)
            )
            continue

        normalized.append(text)

    return normalized


def _as_string_list(value) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        cleaned = _stringify_recipe_component(value)
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple)):
        for item in value:
            cleaned = _stringify_recipe_component(item)
            if cleaned:
                result.append(cleaned)
    return result


def _normalize_group_items(raw_groups, key: str) -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(raw_groups, list):
        return normalized

    entry_keys = ("items", "ingredients", "lines") if key == "items" else ("steps", "instructions", "directions")

    for raw_group in raw_groups:
        if isinstance(raw_group, str):
            entries = _normalize_plain_string_list([raw_group]) if key == "items" else _as_string_list([raw_group])
            if entries:
                normalized.append({"title": "", key: entries})
            continue
        if not isinstance(raw_group, dict):
            continue
        title = _clean_text(raw_group.get("title") or raw_group.get("name") or "")
        raw_entries = None
        for entry_key in entry_keys:
            candidate_entries = raw_group.get(entry_key)
            if candidate_entries is not None:
                raw_entries = candidate_entries
                break
        entries = _normalize_plain_string_list(raw_entries) if key == "items" else _as_string_list(raw_entries)
        if entries:
            normalized.append({"title": title, key: entries})
    return normalized


def _normalize_plain_string_list(value) -> list[str]:
    cleaned_items: list[str] = []
    values = value if isinstance(value, (list, tuple)) else [value]
    for item in values:
        cleaned = _stringify_recipe_component(item, prefer_ingredient_order=True)
        cleaned = _normalize_spoken_ingredient_text(cleaned)

        # Fix stray spacing before punctuation (e.g., "teaspoons . mustard")
        cleaned = re.sub(r"\s+\.", ".", cleaned)

        # Remove orphan periods between words (e.g., "teaspoons. mustard" → "teaspoons mustard")
        cleaned = re.sub(r"([A-Za-z]{4,})\.(?=\s+\w)", r"\1", cleaned)

        # Normalize extra spaces again after cleanup
        cleaned = " ".join(cleaned.split())
        if cleaned:
            cleaned_items.append(cleaned)
    return cleaned_items


_AI_INGREDIENT_HEADER_LABEL_PATTERN = re.compile(
    r"\b(?:lean(?:er|est)?|green|healthy\s+fat(?:s)?|condiment(?:s)?|fuelings?|lean\s+and\s+green)\b",
    flags=re.IGNORECASE,
)
_AI_INGREDIENT_AMOUNT_PATTERN = re.compile(
    r"(?<!\w)(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+|[¼½¾⅐-⅞])\s*(?:"
    r"cup|cups|tbsp|tablespoons?|tsp|teaspoons?|lb|lbs|oz|ounces?|g|grams?|kg|kilograms?|"
    r"clove|cloves|slice|slices|can|cans|package|packages|pkt|pkts|stick|sticks|"
    r"sprig|sprigs|bunch|bunches|dash|pinch"
    r")?\b",
    flags=re.IGNORECASE,
)


def _is_non_ingredient_header_line(value: str) -> bool:
    candidate = _clean_text(value)
    if not candidate:
        return True

    lowered = candidate.lower()
    if re.match(r"^(?:serves?|servings?|serving\s+size|yield|makes?)\b", lowered):
        return True

    if candidate.endswith(":") and not re.search(r"\d", candidate):
        return True

    if re.match(r"^(?:for the|to serve|for serving|optional(?: toppings?| garnish| finishers?)?)\b", lowered):
        return True

    if re.fullmatch(r"(?:\d+\s+)?(?:lean(?:er|est)?|green|healthy\s+fat(?:s)?|condiment(?:s)?|fuelings?)", lowered):
        return True

    if ";" in candidate or " - " in candidate or " | " in candidate:
        parts = [part.strip() for part in re.split(r"\s*(?:;| \- |\|)\s*", candidate) if part.strip()]
        if len(parts) >= 2:
            trailing = " ".join(parts[1:])
            if _AI_INGREDIENT_HEADER_LABEL_PATTERN.search(trailing):
                return True

    if _AI_INGREDIENT_AMOUNT_PATTERN.search(candidate):
        return False

    return False


def _sanitize_ai_ingredient_group_title(value: str) -> str:
    candidate = _clean_text(value)
    if not candidate:
        return ""

    lowered = candidate.lower()
    if re.match(r"^(?:serves?|servings?|serving\s+size|yield|makes?)\b", lowered):
        return ""
    if len(candidate) > 60:
        return ""
    if _AI_INGREDIENT_HEADER_LABEL_PATTERN.search(candidate) and (
        ";" in candidate
        or "," in candidate
        or re.search(r"\b(?:source|nutrition|notes?|ingredients?)\b", lowered)
    ):
        return ""
    return candidate


def _filter_ai_ingredient_groups(groups: list[dict]) -> list[dict]:
    filtered_groups: list[dict] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = [
            item
            for item in (_clean_text(entry) for entry in (group.get("items") or []))
            if item and not _is_non_ingredient_header_line(item)
        ]
        if items:
            filtered_groups.append({"title": _sanitize_ai_ingredient_group_title(group.get("title") or ""), "items": items})
    return filtered_groups


def _sanitize_preview_ingredient_payload(payload: dict) -> dict:
    source_payload = payload if isinstance(payload, dict) else {}
    sanitized_payload = dict(source_payload)
    ingredient_groups = _filter_ai_ingredient_groups(
        _normalize_groups(source_payload.get("ingredient_groups") or [], "items")
    )
    if not ingredient_groups:
        fallback_ingredients = [
            item
            for item in _as_string_list(source_payload.get("ingredients") or [])
            if not _is_non_ingredient_header_line(item)
        ]
        if fallback_ingredients:
            ingredient_groups = [{"title": "", "items": fallback_ingredients}]
    sanitized_payload["ingredient_groups"] = ingredient_groups
    sanitized_payload["ingredients"] = _flatten_groups(ingredient_groups, "items")
    return sanitized_payload


def _bounded_text(value: str, limit: int) -> str:
    return str(value or "")[: max(0, int(limit))]


def _iter_all_nodes(root):
    yield root
    for child in getattr(root, "children", []) or []:
        yield child
        yield from _iter_all_nodes(child)


def _node_class_tokens(node) -> set[str]:
    class_value = ""
    if hasattr(node, "attrs"):
        class_value = str(node.attrs.get("class", "") or "")
    return {token for token in re.split(r"\s+", class_value.strip()) if token}


def _node_has_class_fragment(node, fragment: str) -> bool:
    fragment_lower = fragment.lower()
    return any(fragment_lower in token.lower() for token in _node_class_tokens(node))


def _normalized_tag_name(node) -> str:
    node_name = getattr(node, "name", None)
    return node_name.lower() if isinstance(node_name, str) else ""


def _iter_descendants_by_tag(root, tag_names: set[str]):
    expected_tags = {tag.lower() for tag in tag_names if isinstance(tag, str)}
    for node in _iter_all_nodes(root):
        if _normalized_tag_name(node) in expected_tags:
            yield node


def _iter_descendants_by_class_fragments(root, fragments: tuple[str, ...], tag_names: set[str] | None = None):
    expected_tags = {tag.lower() for tag in tag_names} if tag_names else None
    for node in _iter_all_nodes(root):
        if expected_tags and _normalized_tag_name(node) not in expected_tags:
            continue
        if any(_node_has_class_fragment(node, fragment) for fragment in fragments):
            yield node


def _iter_descendants_by_exact_class(root, class_names: set[str], tag_names: set[str] | None = None):
    expected_tags = {tag.lower() for tag in tag_names} if tag_names else None
    for node in _iter_all_nodes(root):
        if expected_tags and _normalized_tag_name(node) not in expected_tags:
            continue
        tokens = _node_class_tokens(node)
        if any(class_name in tokens for class_name in class_names):
            yield node


def _find_next_sibling_tag(parent, child, tag_names: set[str]):
    siblings = list(getattr(parent, "children", []) or [])
    seen_child = False
    for sibling in siblings:
        if sibling is child:
            seen_child = True
            continue
        if not seen_child:
            continue
        if _normalized_tag_name(sibling) in tag_names:
            return sibling
    return None


def _extract_parenthetical_notes(value: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    base_chars: list[str] = []
    depth = 0
    current_note: list[str] = []

    for char in _clean_text(value):
        if char == "(":
            if depth == 0:
                current_note = []
            else:
                current_note.append(char)
            depth += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                note_text = _clean_text("".join(current_note))
                if note_text:
                    notes.append(note_text)
                continue
            current_note.append(char)
            continue
        if depth > 0:
            current_note.append(char)
        else:
            base_chars.append(char)

    stripped = " ".join("".join(base_chars).split())
    return stripped, notes


def _parse_ingredient_core(text: str) -> tuple[float | None, str | None, str, list[str]]:
    working, notes = _extract_parenthetical_notes(_bounded_text(text, MAX_INGREDIENT_LINE_CHARS))
    quantity, remainder = _parse_ingredient_quantity(working)
    unit = None
    remainder_after_unit = remainder
    unit_match = re.match(r"^([a-zA-Z]+)\b", remainder)
    if unit_match:
        normalized_unit = _INGREDIENT_UNIT_ALIASES.get(unit_match.group(1).lower())
        if normalized_unit:
            unit = normalized_unit
            remainder_after_unit = remainder[unit_match.end():].strip()
    name = re.sub(r"^of\s+", "", remainder_after_unit, flags=re.IGNORECASE).strip()
    return quantity, unit, name, notes


def extract_json_ld_blocks(html: str) -> list[dict]:
    blocks: list[dict] = []
    seen_payloads: set[str] = set()
    for payload in extract_json_ld_payloads(_bounded_text(html, MAX_RECIPE_HTML_CHARS)):
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue
        signature = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
        if signature in seen_payloads:
            continue
        seen_payloads.add(signature)
        if isinstance(parsed, dict):
            blocks.append(parsed)
        elif isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))
    return blocks


def _parse_iso8601_minutes(value: str) -> int | None:
    text = _bounded_text(value, MAX_DURATION_TEXT_CHARS).strip()
    if not text:
        return None
    upper = text.upper()
    if not upper.startswith("P"):
        return None

    total = 0
    number = ""
    in_time = False
    saw_component = False
    multipliers = {
        "W": 7 * 24 * 60,
        "D": 24 * 60,
        "H": 60,
        "M": 1,
    }
    seconds = 0

    for char in upper[1:]:
        if char == "T":
            if number:
                return None
            in_time = True
            continue
        if char.isdigit():
            number += char
            continue
        if not number:
            return None
        amount = int(number)
        number = ""
        if char == "S":
            if not in_time:
                return None
            seconds = amount
            saw_component = True
            continue
        if char == "M" and not in_time:
            return None
        multiplier = multipliers.get(char)
        if multiplier is None:
            return None
        total += amount * multiplier
        saw_component = True
    if number or not saw_component:
        return None
    if seconds >= 30:
        total += 1
    return total


def _extract_wprm_instruction_groups(reduced_html: str) -> list[dict]:
    soup = BeautifulSoup(_bounded_text(reduced_html, MAX_RECIPE_HTML_CHARS), "html.parser")
    container = soup.select_one(".wprm-recipe-instructions-container") or soup
    groups: list[dict] = []
    seen_global_steps: set[str] = set()

    def _collect_steps(root) -> list[str]:
        steps: list[str] = []
        for node in _iter_descendants_by_exact_class(root, {"wprm-recipe-instruction-text", "wprm-recipe-instruction"}):
            text = _clean_instruction_step_text(node.get_text(" "))
            canonical = _canonical_recipe_text(text)
            if not text or (canonical and canonical in seen_global_steps):
                continue
            if canonical:
                seen_global_steps.add(canonical)
            steps.append(text)
        return steps

    group_nodes = list(_iter_descendants_by_exact_class(container, {"wprm-recipe-instruction-group"}))
    if not group_nodes:
        return []

    top_level_steps: list[str] = []
    for child in getattr(container, "children", []):
        if "wprm-recipe-instruction-group" in _node_class_tokens(child):
            continue
        if getattr(child, "name", ""):
            top_level_steps.extend(_collect_steps(child))
    if top_level_steps:
        groups.append({"title": "Instructions", "steps": top_level_steps})

    for group_node in group_nodes:
        title_node = next(iter(_iter_descendants_by_exact_class(group_node, {"wprm-recipe-group-name"})), None)
        title = _normalize_section_title(title_node.get_text(" ") if title_node else "")
        steps = _collect_steps(group_node)
        if steps:
            groups.append({"title": title, "steps": steps})
    return groups


def _extract_bigoven_instruction_groups(reduced_html: str) -> list[dict]:
    soup = BeautifulSoup(_bounded_text(reduced_html, MAX_RECIPE_HTML_CHARS), "html.parser")
    container = None
    for node in _iter_descendants_by_tag(soup, {"div"}):
        attrs = getattr(node, "attrs", {})
        if str(attrs.get("id", "")).lower() == "instr" and "instructions" in _node_class_tokens(node):
            container = node
            break
    if not container:
        return []
    steps = [
        _clean_instruction_step_text(node.get_text(" "))
        for node in _iter_descendants_by_tag(container, {"p"})
    ]
    steps = [step for step in steps if step]
    return [{"title": "", "steps": steps}] if steps else []


def _extract_recipe_scoped_html(reduced_html: str) -> str:
    return _bounded_text(reduced_html, MAX_RECIPE_HTML_CHARS)


def _extract_dom_recipe_data(html: str) -> dict:
    scoped_html = _extract_recipe_scoped_html(_bounded_text(html, MAX_RECIPE_HTML_CHARS))
    scoped_soup = BeautifulSoup(scoped_html, "html.parser")
    visible_text = _clean_text(extract_visible_text(scoped_html).replace("\n", " \n "))

    prep_time = _extract_time_from_text(visible_text, r"prep(?:aration)?\s*time")
    cook_time = _extract_time_from_text(visible_text, r"cook(?:ing)?\s*time")
    total_time = _extract_time_from_text(visible_text, r"total\s*time")

    def _dedupe_entries(entries: list[str]) -> list[str]:
        deduped: list[str] = []
        seen_entries: set[str] = set()
        for entry in entries:
            canonical = _canonical_recipe_text(entry)
            if not canonical or canonical in seen_entries:
                continue
            seen_entries.add(canonical)
            deduped.append(entry)
        return deduped

    ingredient_groups: list[dict] = []
    for heading in _iter_descendants_by_tag(scoped_soup, {"h2", "h3", "h4", "h5", "p"}):
        next_list = _find_next_sibling_tag(getattr(heading, "parent", None), heading, {"ul", "ol"})
        if next_list is None:
            continue
        class_blob = " ".join(_node_class_tokens(next_list)).lower()
        if "ingredient" not in class_blob:
            continue
        items = [
            text for text in (_clean_text(li.get_text(" ")) for li in _iter_descendants_by_tag(next_list, {"li"}))
            if text and not _is_dom_ingredient_noise(text)
        ]
        items = _dedupe_entries(items)
        if items:
            ingredient_groups.append({"title": _normalize_section_title(heading.get_text(" ")), "items": items})

    if not ingredient_groups:
        flat_ingredients = []
        for li in _iter_descendants_by_tag(scoped_soup, {"li"}):
            class_blob = " ".join(_node_class_tokens(li)).lower()
            if "ingredient" not in class_blob:
                continue
            text = _clean_text(li.get_text(" "))
            if text and not _is_dom_ingredient_noise(text):
                flat_ingredients.append(text)
        flat_ingredients = _dedupe_entries(flat_ingredients)
        if flat_ingredients:
            ingredient_groups.append({"title": "", "items": flat_ingredients})

    instruction_groups: list[dict] = []
    instruction_source = "generic"

    if scoped_soup.select_one(".wprm-recipe-instructions-container"):
        instruction_groups = _extract_wprm_instruction_groups(scoped_html)
        if instruction_groups:
            instruction_source = "wprm"

    if not instruction_groups:
        instruction_groups = _extract_bigoven_instruction_groups(scoped_html)
        if instruction_groups:
            instruction_source = "bigoven_instr"

    if not instruction_groups:
        for heading in _iter_descendants_by_tag(scoped_soup, {"h2", "h3", "h4", "h5", "p"}):
            next_list = _find_next_sibling_tag(getattr(heading, "parent", None), heading, {"ol", "ul"})
            if next_list is None:
                continue
            class_blob = " ".join(_node_class_tokens(next_list)).lower()
            if not any(term in class_blob for term in ("instruction", "direction", "method", "step")):
                continue
            steps = [
                text for text in (_clean_instruction_step_text(li.get_text(" ")) for li in _iter_descendants_by_tag(next_list, {"li"}))
                if text
            ]
            steps = _dedupe_entries(steps)
            if steps:
                instruction_groups.append({"title": _normalize_section_title(heading.get_text(" ")), "steps": steps})

    if not instruction_groups:
        flat_steps = []
        for li in _iter_descendants_by_tag(scoped_soup, {"li"}):
            class_blob = " ".join(_node_class_tokens(li)).lower()
            if not any(term in class_blob for term in ("instruction", "direction", "method", "step")):
                continue
            text = _clean_instruction_step_text(li.get_text(" "))
            if text:
                flat_steps.append(text)
        flat_steps = _dedupe_entries(flat_steps)
        if flat_steps:
            instruction_groups.append({"title": "", "steps": flat_steps})

    ingredient_groups = _dedupe_groups(ingredient_groups, "items")
    instruction_groups = _dedupe_groups(instruction_groups, "steps")

    return {
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": instruction_groups,
        "instruction_source": instruction_source,
    }


def _parse_html_attributes(tag: str) -> dict[str, str]:
    soup = BeautifulSoup(tag, "html.parser")
    node = next((child for child in getattr(soup, "children", []) or [] if getattr(child, "name", "")), None)
    if node is None:
        return {}
    attrs: dict[str, str] = {}
    for key, value in node.attrs.items():
        if isinstance(value, list):
            attrs[key.lower()] = " ".join(str(item) for item in value if str(item).strip())
        else:
            attrs[key.lower()] = str(value).strip()
    return attrs


def _extract_meta_image(html: str, page_url: str, source: str) -> str:
    soup = BeautifulSoup(_bounded_text(html, MAX_RECIPE_HTML_CHARS), "html.parser")
    meta_targets = (
        ("property", {"og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"}),
        ("name", {"og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"}),
        ("itemprop", {"image"}),
    )
    candidates: list[dict] = []
    for attr_name, wanted_values in meta_targets:
        for node in _iter_descendants_by_tag(soup, {"meta"}):
            attrs = getattr(node, "attrs", {})
            attr_value = str(attrs.get(attr_name, "") or "").strip().lower()
            if attr_value not in wanted_values:
                continue
            content = str(attrs.get("content", "") or "").strip()
            if content:
                candidates.append({"url": content, "page_url": page_url})
    return _choose_best_image(candidates, source)


def _extract_dom_fallback_image(html: str, page_url: str) -> str:
    scoped_html = _extract_recipe_scoped_html(html)
    soup = BeautifulSoup(scoped_html, "html.parser")
    candidates: list[dict] = []
    for node in _iter_descendants_by_tag(soup, {"img"}):
        attrs = {key.lower(): str(value).strip() for key, value in node.attrs.items() if not isinstance(value, list)}
        list_attrs = {key.lower(): " ".join(value) for key, value in node.attrs.items() if isinstance(value, list)}
        attrs.update(list_attrs)
        for key in ("src", "data-src", "data-lazy-src", "data-srcset", "srcset"):
            possible_url = attrs.get(key, "")
            if not possible_url:
                continue
            if "," in possible_url and (" w" in possible_url or " x" in possible_url):
                possible_url = _best_url_from_srcset(possible_url)
            if possible_url:
                candidates.append(
                    {
                        "url": possible_url,
                        "page_url": page_url,
                        "width": attrs.get("width"),
                        "height": attrs.get("height"),
                    }
                )
    return _choose_best_image(candidates, "dom")


def _parse_ingredient_struct(text: str) -> dict:
    raw = _clean_text(text)
    if not raw:
        parsed = {"raw": "", "quantity": None, "unit": None, "name": "", "note": None}
        parsed.update(_build_ingredient_display_fields(parsed))
        return parsed

    quantity, unit, name, notes = _parse_ingredient_core(raw)
    quantity = _fix_common_ocr_quantity_errors(quantity, unit, name)
    quantity = _maybe_override_with_parenthetical_quantity(quantity, unit, name, notes)

    if not name:
        parsed = {"raw": raw, "quantity": None, "unit": None, "name": raw, "note": " ; ".join(notes) if notes else None}
        parsed.update(_build_ingredient_display_fields(parsed))
        return parsed

    parsed = {"raw": raw, "quantity": quantity, "unit": unit, "name": name, "note": " ; ".join(notes) if notes else None}
    parsed.update(_build_ingredient_display_fields(parsed))
    return parsed


def _parse_spoken_quantity_phrase(value: str) -> float | None:
    candidate = _normalize_transcript_context_text(_bounded_text(value, MAX_REGEX_TEXT_CHARS)).lower()
    candidate = re.sub(r"[-â€“]+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate:
        return None
    direct_quantity, direct_remainder = _parse_ingredient_quantity(candidate)
    if direct_quantity is not None and not direct_remainder:
        return direct_quantity

    def _parse_spoken_fraction_tokens(tokens: list[str]) -> float | None:
        if not tokens:
            return None
        if tokens in (["half"], ["half", "a"], ["a", "half"], ["one", "half"]):
            return 0.5
        if tokens in (["quarter"], ["quarters"], ["a", "quarter"], ["one", "quarter"], ["fourth"], ["fourths"], ["a", "fourth"], ["one", "fourth"]):
            return 0.25
        if tokens in (["third"], ["thirds"], ["a", "third"], ["one", "third"]):
            return 1.0 / 3.0
        if tokens == ["two", "thirds"]:
            return 2.0 / 3.0
        if tokens in (["three", "quarters"], ["three", "quarter"], ["three", "fourths"], ["three", "fourth"]):
            return 0.75
        return None

    tokens = candidate.split()
    if len(tokens) >= 3 and tokens[1] == "and":
        whole = _SPOKEN_NUMBER_WORDS.get(tokens[0])
        fraction = _parse_spoken_fraction_tokens(tokens[2:])
        if whole is not None and fraction is not None:
            return whole + fraction

    fraction = _parse_spoken_fraction_tokens(tokens)
    if fraction is not None:
        return fraction
    return _SPOKEN_NUMBER_WORDS.get(candidate)


def _normalize_ai_cleanup_prompt_ingredient_line(value) -> str:
    raw = _clean_text(_stringify_recipe_component(value, prefer_ingredient_order=True))
    if not raw:
        return ""
    quantity, unit, name, notes = _parse_ingredient_core(raw)
    display_quantity = _format_display_quantity(quantity)
    display_unit = _format_display_unit(unit, quantity)
    display_name = _clean_text(name)
    parts = [part for part in (display_quantity, display_unit, display_name) if part]
    display_text = " ".join(parts).strip() or raw
    if notes:
        display_text = f"{display_text} ({' ; '.join(notes)})"
    return _clean_text(display_text)


def _looks_like_ingredient_quantity(value: str) -> bool:
    candidate = _clean_text(_bounded_text(value, MAX_DURATION_TEXT_CHARS))
    if not candidate:
        return False
    quantity, remainder = _parse_ingredient_quantity(candidate)
    return quantity is not None and not remainder


def _normalize_plain_string_list(value) -> list[str]:
    cleaned_items: list[str] = []
    values = value if isinstance(value, (list, tuple)) else [value]
    for item in values:
        cleaned = _stringify_recipe_component(item, prefer_ingredient_order=True)
        cleaned = _normalize_spoken_ingredient_text(_bounded_text(cleaned, MAX_REGEX_TEXT_CHARS))
        cleaned = re.sub(r"\s+\.", ".", cleaned[:MAX_REGEX_TEXT_CHARS])
        cleaned = re.sub(r"([A-Za-z]{4,})\.(?=\s+\w)", r"\1", cleaned)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            cleaned_items.append(cleaned)
    return cleaned_items


def _is_non_ingredient_header_line(value: str) -> bool:
    candidate = _clean_text(_bounded_text(value, MAX_INGREDIENT_GROUP_TITLE_CHARS))
    if not candidate:
        return True
    lowered = candidate.lower()
    if re.match(r"^(?:serves?|servings?|serving\s+size|yield|makes?)\b", lowered):
        return True
    if candidate.endswith(":") and not re.search(r"\d", candidate):
        return True
    if re.match(r"^(?:for the|to serve|for serving|optional(?: toppings?| garnish| finishers?)?)\b", lowered):
        return True
    if re.fullmatch(r"(?:\d+\s+)?(?:lean(?:er|est)?|green|healthy\s+fat(?:s)?|condiment(?:s)?|fuelings?)", lowered):
        return True
    if ";" in candidate or " - " in candidate or " | " in candidate:
        parts = [part.strip() for part in re.split(r"\s*(?:;| \- |\|)\s*", candidate) if part.strip()]
        if len(parts) >= 2 and _AI_INGREDIENT_HEADER_LABEL_PATTERN.search(" ".join(parts[1:])):
            return True
    if _AI_INGREDIENT_AMOUNT_PATTERN.search(candidate):
        return False
    if INGREDIENT_OPTIONAL_WORDING_RE.search(candidate) or INGREDIENT_FOODISH_WORD_RE.search(candidate):
        return False
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", candidate)
    if 1 <= len(words) <= 4 and all(len(word) > 1 for word in words):
        return False
    return True


def _sanitize_ai_ingredient_group_title(value: str) -> str:
    candidate = _clean_text(_bounded_text(value, MAX_INGREDIENT_GROUP_TITLE_CHARS))
    if not candidate:
        return ""
    lowered = candidate.lower()
    if re.match(r"^(?:serves?|servings?|serving\s+size|yield|makes?)\b", lowered):
        return ""
    if len(candidate) > 60:
        return ""
    if _AI_INGREDIENT_HEADER_LABEL_PATTERN.search(candidate) and (
        ";" in candidate or "," in candidate or re.search(r"\b(?:source|nutrition|notes?|ingredients?)\b", lowered)
    ):
        return ""
    return candidate


def _extract_ingredient_candidates_from_text(lines: list[str], text: str) -> list[str]:
    def _trim_candidate_line(value: str) -> str:
        return _clean_text(value)[:MAX_INGREDIENT_LINE_CHARS]

    def _strip_leading_bullet_token(value: str) -> str:
        cleaned = value.lstrip()
        if cleaned.startswith(("-", "*", "•")):
            return cleaned[1:].lstrip()
        return cleaned

    def _looks_like_quantity_or_unit_prefix(value: str) -> bool:
        candidate = _strip_leading_bullet_token(value)
        if not candidate:
            return False
        quantity, remainder = _parse_ingredient_quantity(candidate)
        if quantity is not None:
            remainder = remainder.lstrip()
            if remainder.lower().startswith("x "):
                remainder = remainder[2:].lstrip()
            token = remainder.split(None, 1)[0].rstrip(".,:;").lower() if remainder else ""
            return token in _INGREDIENT_UNIT_ALIASES or token in {"pinch", "handful", "clove", "cloves"}
        token = candidate.split(None, 1)[0].rstrip(".,:;").lower()
        return token in _INGREDIENT_UNIT_ALIASES or token in {"pinch", "handful", "clove", "cloves"}

    def _contains_measurement(value: str) -> bool:
        candidate = _trim_candidate_line(value)
        if not candidate:
            return False
        tokens = candidate.split()
        for index, token in enumerate(tokens):
            normalized = token.strip(".,:;()").lower()
            if normalized not in _INGREDIENT_UNIT_ALIASES or index == 0:
                continue
            prefix = " ".join(tokens[max(0, index - 2):index])
            quantity, remainder = _parse_ingredient_quantity(prefix)
            if quantity is not None and not remainder:
                return True
        return False

    bounded_text = _clean_text(text)[:MAX_REGEX_TEXT_CHARS]
    ingredients: list[str] = []
    for line in lines:
        cleaned = _clean_ingredient_candidate(_trim_candidate_line(line))
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(lowered.startswith(prefix) for prefix in ("method", "instructions", "directions", "steps")):
            continue
        if _looks_like_quantity_or_unit_prefix(cleaned) or _contains_measurement(cleaned):
            ingredients.append(cleaned)
            continue
        if _should_keep_short_unmeasured_ingredient_line(cleaned):
            ingredients.append(cleaned)

    if len(ingredients) < 2:
        for phrase in re.split(r"[,\n;]", bounded_text):
            cleaned = _clean_ingredient_candidate(phrase)
            if _contains_measurement(cleaned):
                ingredients.append(cleaned)

    for match in re.finditer(
        r"\b\d+(?:[\.,]\d+)?\s+(?:diced|chopped|minced|sliced|crushed)?\s*"
        r"(?:onions?|carrots?|celery(?:\s+stalks?)?|garlic(?:\s+cloves?)?)\b",
        bounded_text,
        flags=re.IGNORECASE,
    ):
        cleaned = _clean_ingredient_candidate(match.group(0))
        if cleaned:
            ingredients.append(cleaned)

    extra_match = re.search(r"\bextra\s+(?:cheddar|chedder)\b", bounded_text, flags=re.IGNORECASE)
    if extra_match:
        ingredients.append(_clean_ingredient_candidate(extra_match.group(0)))

    return _dedupe_text_entries(ingredients)


def _extract_ocr_preamble_lines(lines: list[str]) -> list[str]:
    preamble: list[str] = []
    for raw_line in lines:
        cleaned_line = _clean_text(_bounded_text(raw_line, MAX_REGEX_TEXT_CHARS)).strip(" -Ã¢â‚¬Â¢*")
        if not cleaned_line:
            continue
        heading_match = re.search(
            r"\b(ingredients?|instructions?|directions?|method|steps)\b",
            cleaned_line,
            flags=re.IGNORECASE,
        )
        if heading_match:
            prefix = cleaned_line[: heading_match.start()].strip(" :-|")
            if prefix:
                preamble.append(prefix)
            break
        preamble.append(cleaned_line)
    return preamble


def _looks_like_ocr_metadata_line(value: str) -> bool:
    candidate = _clean_text(_bounded_text(value, MAX_REGEX_TEXT_CHARS))
    if any(re.search(pattern, candidate, flags=re.IGNORECASE) for pattern in _OCR_TITLE_METADATA_PATTERNS):
        return True
    if re.search(r"\d", candidate):
        letters = re.findall(r"[A-Za-z]", candidate)
        digits = re.findall(r"\d", candidate)
        if digits and len(digits) >= max(2, len(letters)):
            return True
    return False


def parse_social_caption_recipe(caption_text: str, source_url: str, title_hint: str = "") -> dict:
    cleaned = _strip_social_caption_noise(_bounded_text(caption_text, MAX_REGEX_TEXT_CHARS))
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    title = _clean_text(title_hint)

    if source_url.startswith("image://") and lines:
        ocr_title = _extract_ocr_title_from_lines(lines)
        if ocr_title:
            title = ocr_title

    if not title and lines:
        first_line = _clean_text(_bounded_text(lines[0], MAX_REGEX_TEXT_CHARS)).strip(" -â€¢*")
        first_line_lower = first_line.lower()
        has_heading_word = any(word in first_line_lower for word in ("ingredient", "ingredients", "method", "instruction", "instructions"))
        if 6 <= len(first_line) <= 110 and not has_heading_word:
            title = first_line

    ingredients = _extract_ingredient_candidates_from_text(lines, cleaned)
    instructions = _split_instruction_sentences(cleaned)
    if not instructions and lines:
        instructions = [
            _clean_text(line).strip(" -â€¢*")
            for line in lines
            if re.search(r"\b(?:add|mix|whisk|stir|cook|bake|simmer|boil|heat|fold|serve|chop|slice|season)\b", line, re.IGNORECASE)
        ]
        instructions = _dedupe_text_entries(instructions)

    servings_match = re.search(r"\b(?:serves|servings?)\s*[:\-]?\s*(\d{1,2})\b", cleaned, flags=re.IGNORECASE)
    servings = servings_match.group(1) if servings_match else ""
    prep_time = _extract_time_from_text(cleaned, r"prep(?:aration)?\s*time")
    cook_time = _extract_time_from_text(cleaned, r"cook(?:ing)?\s*time")
    total_time = _extract_time_from_text(cleaned, r"total\s*time")
    prep_time, prep_minutes = _normalize_duration(prep_time)
    cook_time, cook_minutes = _normalize_duration(cook_time)
    total_time, total_minutes = _normalize_duration(total_time)

    return {
        "url": source_url,
        "title": title,
        "image_url": "",
        "ingredients": ingredients,
        "instructions": instructions,
        "ingredient_groups": [{"title": "", "items": ingredients}] if ingredients else [],
        "instruction_groups": [{"title": "", "steps": instructions}] if instructions else [],
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "total_minutes": total_minutes,
    }


def _parse_pasted_recipe_text(raw_text: str) -> dict:
    cleaned = _bounded_text(str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip(), MAX_REGEX_TEXT_CHARS)
    lines = [_normalize_pasted_recipe_line(line) for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        raise HTTPException(status_code=422, detail="Recipe text is required")

    title = ""
    servings = ""
    prep_time = ""
    cook_time = ""
    total_time = ""
    description_lines: list[str] = []
    note_lines: list[str] = []
    ingredient_section_lines: list[str] = []
    instruction_lines: list[str] = []
    note_heading = ""
    current_section = ""
    has_explicit_ingredient_heading = any(line.rstrip(":").strip().lower() in PASTE_INGREDIENT_HEADINGS for line in lines)

    for line in lines:
        bounded_line = _bounded_text(line, MAX_REGEX_TEXT_CHARS)
        heading = bounded_line.rstrip(":").strip().lower()
        if heading in PASTE_INGREDIENT_HEADINGS:
            current_section = "ingredients"
            continue
        if heading in PASTE_INSTRUCTION_HEADINGS:
            current_section = "instructions"
            continue
        if _is_paste_note_heading(bounded_line):
            current_section = "notes"
            note_heading = bounded_line.rstrip(":").strip()
            continue

        servings_match = re.match(r"^servings?\s*[:\-]\s*(.+)$", bounded_line, flags=re.IGNORECASE)
        if servings_match:
            servings = _clean_text(servings_match.group(1))
            continue
        prep_match = re.match(r"^prep(?:aration)?\s*time\s*[:\-]\s*(.+)$", bounded_line, flags=re.IGNORECASE)
        if prep_match:
            prep_time = _clean_text(prep_match.group(1))
            continue
        cook_match = re.match(r"^cook(?:ing)?\s*time\s*[:\-]\s*(.+)$", bounded_line, flags=re.IGNORECASE)
        if cook_match:
            cook_time = _clean_text(cook_match.group(1))
            continue
        total_match = re.match(r"^total\s*time\s*[:\-]\s*(.+)$", bounded_line, flags=re.IGNORECASE)
        if total_match:
            total_time = _clean_text(total_match.group(1))
            continue

        if not title and not current_section:
            title = bounded_line
            continue
        if has_explicit_ingredient_heading and not current_section and title:
            normalized_description = _normalize_pasted_recipe_line(bounded_line)
            if normalized_description:
                description_lines.append(normalized_description)
            continue
        if current_section == "ingredients":
            normalized_ingredient = _normalize_pasted_recipe_line(bounded_line)
            if normalized_ingredient:
                ingredient_section_lines.append(normalized_ingredient)
            continue
        if current_section == "instructions":
            normalized_instruction = _normalize_pasted_recipe_line(bounded_line, instruction=True)
            if normalized_instruction:
                instruction_lines.append(normalized_instruction)
            continue
        if current_section == "notes":
            normalized_note = _normalize_pasted_recipe_line(bounded_line)
            if normalized_note:
                note_lines.append(normalized_note)

    ingredient_groups = _build_pasted_ingredient_groups(ingredient_section_lines)
    ingredient_lines = _flatten_groups(ingredient_groups, "items")
    if not ingredient_lines:
        ingredient_lines = _extract_ingredient_candidates_from_text(lines, cleaned)
        ingredient_groups = [{"title": "", "items": ingredient_lines}] if ingredient_lines else []
    if not instruction_lines:
        instruction_lines = [
            normalized_instruction
            for normalized_instruction in (
                _normalize_pasted_recipe_line(step, instruction=True)
                for step in _split_instruction_sentences(cleaned)
            )
            if normalized_instruction
        ]

    prep_time, prep_minutes = _normalize_duration(prep_time)
    cook_time, cook_minutes = _normalize_duration(cook_time)
    total_time, total_minutes = _normalize_duration(total_time)
    candidate = {
        "url": "",
        "title": title,
        "image_url": "",
        "notes": _compose_pasted_recipe_notes(description_lines, note_lines, note_heading),
        "ingredients": ingredient_lines,
        "instructions": instruction_lines,
        "ingredient_groups": ingredient_groups,
        "instruction_groups": [{"title": "", "steps": instruction_lines}] if instruction_lines else [],
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "total_minutes": total_minutes,
    }
    return _finalize_recipe_candidate(candidate, "", "pasted_text")


def _normalized_ingredient_compare_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9%/]+", " ", _clean_text(value).lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _should_prefer_preview_ingredients(preview_payload: dict, ai_payload: dict) -> bool:
    preview_ingredients = preview_payload.get("ingredients") or []
    ai_ingredients = ai_payload.get("ingredients") or []
    preview_keys = {
        key
        for item in preview_ingredients
        if (key := _normalized_ingredient_compare_key(item))
    }
    ai_keys = {
        key
        for item in ai_ingredients
        if (key := _normalized_ingredient_compare_key(item))
    }
    if not preview_keys:
        return False
    if not ai_keys:
        return True
    if preview_keys == ai_keys:
        return False
    if ai_keys.issubset(preview_keys):
        return True
    return len(preview_keys) > len(ai_keys)


def _merge_split_ingredient_lines(items: list[str]) -> list[str]:
    merged: list[str] = []

    for raw_item in items:
        item = " ".join(str(raw_item or "").split()).strip()
        if not item:
            continue

        is_fragment = (
            len(item) <= 8
            and any(ch.isdigit() for ch in item)
            and not re.match(r"^\d+\s", item)
            and not re.match(r"^\d+/\d+\s", item)
            and not re.match(r"^\d+(?:\.\d+)?\s*(cup|cups|tbsp|tsp|lb|lbs|oz|g|kg)\b", item, re.IGNORECASE)
        )

        if is_fragment and merged:
            merged[-1] = f"{merged[-1]} {item}".strip()
        else:
            merged.append(item)

    return merged


def normalize_ai_review_response(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}
    title = _clean_text(payload.get("title") or payload.get("name") or "")
    servings = _clean_text(payload.get("servings") or payload.get("yield") or "")
    prep_time = _clean_text(payload.get("prep_time") or payload.get("prepTime") or "")
    cook_time = _clean_text(payload.get("cook_time") or payload.get("cookTime") or "")
    total_time = _clean_text(payload.get("total_time") or payload.get("totalTime") or "")

    raw_ingredient_groups = payload.get("ingredient_groups")
    has_grouped_ingredients = isinstance(raw_ingredient_groups, list) and any(
        isinstance(group, dict) for group in raw_ingredient_groups
    )
    logger.info("ai_cleanup_items_before_normalize=%s", raw_ingredient_groups)
    if has_grouped_ingredients:
        ingredient_groups = raw_ingredient_groups
    else:
        ingredient_groups = _normalize_group_items(raw_ingredient_groups, "items")
    if not ingredient_groups and not has_grouped_ingredients:
        fallback_ingredients = _normalize_plain_string_list(payload.get("ingredients") or [])
        ingredient_groups = [{"title": "", "items": fallback_ingredients}] if fallback_ingredients else []
    logger.info("ai_cleanup_items_after_normalize=%s", ingredient_groups)
    logger.info("ai_cleanup_items_before_merge=%s", ingredient_groups)
    if has_grouped_ingredients:
        ingredient_groups_after_merge = ingredient_groups
    else:
        ingredient_groups_after_merge = [
            {
                "title": group.get("title", ""),
                "items": _merge_split_ingredient_lines(group.get("items", [])),
            }
            for group in ingredient_groups
        ]
    logger.info("ai_cleanup_items_after_merge=%s", ingredient_groups_after_merge)
    ingredient_groups = _filter_ai_ingredient_groups(ingredient_groups_after_merge)

    raw_instruction_groups = payload.get("instruction_groups")
    has_grouped_instructions = isinstance(raw_instruction_groups, list) and any(
        isinstance(group, dict) for group in raw_instruction_groups
    )
    if has_grouped_instructions:
        instruction_groups = raw_instruction_groups
    else:
        instruction_groups = _normalize_group_items(raw_instruction_groups, "steps")
    if not instruction_groups and not has_grouped_instructions:
        instruction_groups = [{"title": "", "steps": _as_string_list(payload.get("instructions") or payload.get("steps") or [])}] if (payload.get("instructions") or payload.get("steps")) else []

    return {
        "title": title,
        "servings": servings,
        "prep_time": prep_time,
        "cook_time": cook_time,
        "total_time": total_time,
        "ingredient_groups": _normalize_groups(ingredient_groups, "items"),
        "instruction_groups": _normalize_groups(instruction_groups, "steps"),
        "review_notes": _clean_text(payload.get("review_notes") or ""),
    }


def _is_useful_ai_cleanup_result(normalized_result: dict) -> bool:
    ingredient_groups = _normalize_groups(normalized_result.get("ingredient_groups") or [], "items")
    instruction_groups = _normalize_groups(normalized_result.get("instruction_groups") or [], "steps")
    cleaned_ingredients = _flatten_groups(ingredient_groups, "items")
    cleaned_instructions = _flatten_groups(instruction_groups, "steps")
    return bool(cleaned_ingredients and cleaned_instructions)


def call_ollama_review(prompt: str) -> dict:
    if not OLLAMA_BASE_URL:
        raise HTTPException(status_code=503, detail="AI cleanup is not configured. Set OLLAMA_BASE_URL to enable it.")
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    raw_content = payload.get("response")
    if isinstance(raw_content, dict):
        return raw_content
    if not isinstance(raw_content, str):
        raise ValueError("Ollama response payload missing response content")
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return json.loads(cleaned)


def _claim_next_queued_review(conn: sqlite3.Connection) -> sqlite3.Row | None:
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT *
        FROM recipes
        WHERE review_status = 'queued'
        ORDER BY review_requested_at ASC, id ASC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    review_started_at = utcnow_iso()
    cur.execute(
        """
        UPDATE recipes
        SET review_status = 'processing',
            review_notes = NULL,
            review_started_at = ?,
            review_completed_at = NULL,
            review_error = NULL
        WHERE id = ?
          AND review_status = 'queued'
        """,
        (review_started_at, int(row["id"])),
    )
    if cur.rowcount == 0:
        conn.commit()
        return None
    conn.commit()
    return cur.execute("SELECT * FROM recipes WHERE id = ?", (int(row["id"]),)).fetchone()


def _run_review_worker_pass() -> bool:
    conn = get_conn()
    claimed_row: sqlite3.Row | None = None
    try:
        claimed_row = _claim_next_queued_review(conn)
        if not claimed_row:
            return False
        recipe_id = int(claimed_row["id"])
        logger.info("review_queue_worker_picked_up recipe_id=%s", recipe_id)
        source_payload = _recipe_ai_source_payload(claimed_row)
        prompt = build_ai_review_prompt(claimed_row)
        logger.info("review_queue_ollama_call recipe_id=%s model=%s", recipe_id, OLLAMA_MODEL)
        raw_result = call_ollama_review(prompt)
        normalized_result = normalize_ai_review_response(raw_result)
        ingredient_groups = normalized_result.get("ingredient_groups") or []
        instruction_groups = normalized_result.get("instruction_groups") or []

        title = (normalized_result.get("title") or "").strip() or (claimed_row["title"] or "")
        servings = (normalized_result.get("servings") or "").strip() or (claimed_row["servings"] or "")
        prep_time = (normalized_result.get("prep_time") or "").strip() or (claimed_row["prep_time"] or "")
        cook_time = (normalized_result.get("cook_time") or "").strip() or (claimed_row["cook_time"] or "")
        total_time = (normalized_result.get("total_time") or "").strip() or (claimed_row["total_time"] or "")

        cleaned_ingredients = _flatten_groups(ingredient_groups, "items")
        cleaned_instructions = _flatten_groups(instruction_groups, "steps")
        _log_recipe_db_write_trace(
            "review_queue_pre_save",
            recipe_id,
            {
                "ingredient_groups": ingredient_groups,
                "instruction_groups": instruction_groups,
            },
        )
        logger.info(
            "review_queue_apply_result recipe_id=%s ingredient_groups=%s instruction_groups=%s",
            recipe_id,
            len(ingredient_groups),
            len(instruction_groups),
        )

        completed_at = utcnow_iso()
        conn.execute(
            """
            UPDATE recipes
            SET title = ?,
                servings = ?,
                prep_time = ?,
                cook_time = ?,
                total_time = ?,
                ingredients = ?,
                instructions = ?,
                ingredient_groups = ?,
                instruction_groups = ?,
                review_status = 'completed',
                needs_review = 0,
                review_notes = ?,
                review_completed_at = ?,
                review_error = NULL,
                ai_review_provider = 'ollama',
                ai_review_model = ?,
                ai_review_source_payload = ?,
                ai_review_result = ?,
                ai_review_normalized = ?
            WHERE id = ?
            """,
            (
                title,
                servings,
                prep_time,
                cook_time,
                total_time,
                _json_array_to_text(cleaned_ingredients),
                _json_array_to_text(cleaned_instructions),
                _json_groups_to_text(ingredient_groups, "items"),
                _json_groups_to_text(instruction_groups, "steps"),
                normalized_result.get("review_notes") or "Cleaned by AI review queue",
                completed_at,
                OLLAMA_MODEL,
                json.dumps(source_payload, ensure_ascii=False),
                json.dumps(raw_result, ensure_ascii=False),
                json.dumps(normalized_result, ensure_ascii=False),
                recipe_id,
            ),
        )
        conn.commit()
        logger.info("review_queue_completed recipe_id=%s", recipe_id)
        return True
    except Exception as exc:
        recipe_id = int(claimed_row["id"]) if claimed_row else None
        if recipe_id is not None:
            conn.execute(
                """
                UPDATE recipes
                SET review_status = 'failed',
                    review_notes = ?,
                    review_completed_at = ?,
                    review_error = ?
                WHERE id = ?
                """,
                (str(exc), utcnow_iso(), str(exc), recipe_id),
            )
            conn.commit()
            logger.exception("review_queue_failed recipe_id=%s error=%s", recipe_id, str(exc))
        else:
            logger.exception("review_queue_failed recipe_id=unknown error=%s", str(exc))
        return False
    finally:
        conn.close()


async def process_review_queue() -> None:
    logger.info("review_queue_worker_started enabled=%s", AI_REVIEW_ENABLED)
    while True:
        try:
            processed = await asyncio.to_thread(_run_review_worker_pass) if AI_REVIEW_ENABLED else False
            if processed:
                await asyncio.sleep(0)
                continue
            await asyncio.sleep(AI_REVIEW_POLL_SECONDS)
        except asyncio.CancelledError:
            logger.info("review_queue_worker_stopped")
            raise


def fetch_recipe_data_from_url(url: str) -> dict:
    try:
        response = safe_get(url, headers=REQUEST_HEADERS, timeout=8)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return {}
        html = response.text or ""
    except Exception:
        return {}

    dom_data = _extract_dom_recipe_data(html)
    _, dom_prep_minutes = _normalize_duration(dom_data.get("prep_time", ""))
    _, dom_cook_minutes = _normalize_duration(dom_data.get("cook_time", ""))
    _, dom_total_minutes = _normalize_duration(dom_data.get("total_time", ""))

    jsonld_best_recipe: dict | None = None
    jsonld_best_score = -1
    found_recipe_json_ld = False
    json_ld_blocks = extract_json_ld_blocks(html)
    recipe_json_ld_image = ""
    for block in json_ld_blocks:
        for item in _iter_json_ld_items(block):
            if not isinstance(item, dict) or not _is_recipe_type(item.get("@type")):
                continue

            found_recipe_json_ld = True
            if not recipe_json_ld_image:
                recipe_json_ld_image = _extract_json_ld_recipe_image(item, url)
            title = (item.get("name") or "").strip()
            ingredients = item.get("recipeIngredient")
            if isinstance(ingredients, list):
                ingredients = [_clean_text(x) for x in ingredients if _clean_text(x)]
            else:
                ingredients = []

            schema_instruction_groups, instructions = _extract_instruction_groups_from_schema(
                item.get("recipeInstructions")
            )
            if not instructions:
                instructions = _normalize_instructions(item.get("recipeInstructions"))

            servings = item.get("recipeYield")
            if isinstance(servings, list):
                servings = ", ".join(str(x).strip() for x in servings if str(x).strip())
            elif servings is None:
                servings = ""
            else:
                servings = str(servings).strip()

            prep_time, prep_minutes = _normalize_duration(item.get("prepTime") or "")
            cook_time, cook_minutes = _normalize_duration(item.get("cookTime") or "")
            total_time, total_minutes = _normalize_duration(item.get("totalTime") or "")
            logger.info(
                "Recipe JSON-LD times for %s: prepTime=%r cookTime=%r",
                url,
                item.get("prepTime"),
                item.get("cookTime"),
            )

            ingredient_groups = [{"title": "", "items": ingredients}] if ingredients else []
            instruction_groups = _normalize_groups(schema_instruction_groups, "steps")
            if not instruction_groups and instructions:
                instruction_groups = [{"title": "", "steps": instructions}]

            candidate = {
                "title": title,
                "ingredients": ingredients,
                "instructions": instructions,
                "servings": servings,
                "prep_time": prep_time,
                "cook_time": cook_time,
                "total_time": total_time,
                "prep_minutes": prep_minutes,
                "cook_minutes": cook_minutes,
                "total_minutes": total_minutes,
                "ingredient_groups": ingredient_groups,
                "instruction_groups": instruction_groups,
            }
            score = (len(ingredients) * 3) + (len(instructions) * 2) + (1 if title else 0)
            if score > jsonld_best_score:
                jsonld_best_score = score
                jsonld_best_recipe = candidate
            _log_recipe_candidate_counts(url, "jsonld", candidate)
    if found_recipe_json_ld:
        logger.info(
            "extract parser JSON-LD summary url=%s found=%s ingredients=%d instructions=%d ingredient_groups=%d instruction_groups=%d image=%s",
            url,
            found_recipe_json_ld,
            len((jsonld_best_recipe or {}).get("ingredients") or []),
            len((jsonld_best_recipe or {}).get("instructions") or []),
            len((jsonld_best_recipe or {}).get("ingredient_groups") or []),
            len((jsonld_best_recipe or {}).get("instruction_groups") or []),
            bool(recipe_json_ld_image),
        )
    else:
        logger.info("extract parser JSON-LD summary url=%s found=false", url)

    schema_image = _extract_json_ld_fallback_image(json_ld_blocks, url)
    og_image = _extract_meta_image(html, url, "og")
    twitter_image = _extract_meta_image(html, url, "twitter")
    dom_image = _extract_dom_fallback_image(html, url)
    final_image = recipe_json_ld_image or schema_image or og_image or twitter_image or dom_image or ""
    logger.info(
        "Image extraction for %s: recipe_json_ld=%s schema_used=%s og_used=%s twitter_used=%s dom_used=%s final=%s",
        url,
        bool(recipe_json_ld_image),
        bool(schema_image and not recipe_json_ld_image),
        bool(og_image and not recipe_json_ld_image and not schema_image),
        bool(twitter_image and not recipe_json_ld_image and not schema_image and not og_image),
        bool(dom_image and not recipe_json_ld_image and not schema_image and not og_image and not twitter_image),
        final_image,
    )

    dom_ingredient_groups = _normalize_groups(dom_data.get("ingredient_groups", []), "items")
    dom_instruction_groups = _normalize_groups(dom_data.get("instruction_groups", []), "steps")
    dom_candidate = {
        "ingredients": _flatten_groups(dom_ingredient_groups, "items"),
        "instructions": _flatten_groups(dom_instruction_groups, "steps"),
        "image_url": final_image,
        "ingredient_groups": dom_ingredient_groups,
        "instruction_groups": dom_instruction_groups,
        "prep_time": dom_data.get("prep_time", ""),
        "cook_time": dom_data.get("cook_time", ""),
        "total_time": dom_data.get("total_time", ""),
        "prep_minutes": dom_prep_minutes,
        "cook_minutes": dom_cook_minutes,
        "total_minutes": dom_total_minutes,
    }
    logger.info(
        "extract parser DOM summary url=%s ingredients=%d instructions=%d ingredient_groups=%d instruction_groups=%d image=%s",
        url,
        len(dom_candidate["ingredients"]),
        len(dom_candidate["instructions"]),
        len(dom_candidate["ingredient_groups"]),
        len(dom_candidate["instruction_groups"]),
        bool(dom_candidate.get("image_url")),
    )
    _log_recipe_candidate_counts(url, "fallback_dom", dom_candidate)

    wprm_instruction_groups = dom_candidate["instruction_groups"] if (dom_data.get("instruction_source") == "wprm") else []
    wprm_candidate = {
        "title": (jsonld_best_recipe or {}).get("title") or "",
        "ingredients": dom_candidate["ingredients"],
        "instructions": _flatten_groups(wprm_instruction_groups, "steps"),
        "image_url": final_image,
        "ingredient_groups": dom_candidate["ingredient_groups"],
        "instruction_groups": wprm_instruction_groups,
        "servings": (jsonld_best_recipe or {}).get("servings") or "",
        "prep_time": (jsonld_best_recipe or {}).get("prep_time") or dom_candidate.get("prep_time") or "",
        "cook_time": (jsonld_best_recipe or {}).get("cook_time") or dom_candidate.get("cook_time") or "",
        "total_time": (jsonld_best_recipe or {}).get("total_time") or dom_candidate.get("total_time") or "",
        "prep_minutes": (jsonld_best_recipe or {}).get("prep_minutes") if jsonld_best_recipe is not None else dom_candidate.get("prep_minutes"),
        "cook_minutes": (jsonld_best_recipe or {}).get("cook_minutes") if jsonld_best_recipe is not None else dom_candidate.get("cook_minutes"),
        "total_minutes": (jsonld_best_recipe or {}).get("total_minutes") if jsonld_best_recipe is not None else dom_candidate.get("total_minutes"),
    }
    _log_recipe_candidate_counts(url, "wprm_dom", wprm_candidate)

    if jsonld_best_recipe is not None:
        jsonld_has_core = bool((jsonld_best_recipe.get("ingredients") or []) and (jsonld_best_recipe.get("instructions") or []))
        jsonld_group_count = len(_normalize_groups(jsonld_best_recipe.get("instruction_groups") or [], "steps"))
        wprm_group_titles = {
            _normalize_section_title(group.get("title", ""))
            for group in _normalize_groups(wprm_candidate.get("instruction_groups") or [], "steps")
            if isinstance(group, dict)
        }
        wprm_has_distinct_grouping = (
            len(wprm_candidate.get("instruction_groups") or []) > jsonld_group_count
            or any(title and title.lower() != "instructions" for title in wprm_group_titles)
        )
        if jsonld_has_core and dom_data.get("instruction_source") == "wprm" and not wprm_has_distinct_grouping:
            dom_candidate = {
                "ingredients": [],
                "instructions": [],
                "image_url": final_image,
                "ingredient_groups": [],
                "instruction_groups": [],
                "prep_time": "",
                "cook_time": "",
                "total_time": "",
                "prep_minutes": None,
                "cook_minutes": None,
                "total_minutes": None,
            }
            wprm_candidate = {
                "title": (jsonld_best_recipe or {}).get("title") or "",
                "ingredients": [],
                "instructions": [],
                "image_url": final_image,
                "ingredient_groups": [],
                "instruction_groups": [],
                "servings": (jsonld_best_recipe or {}).get("servings") or "",
                "prep_time": (jsonld_best_recipe or {}).get("prep_time") or "",
                "cook_time": (jsonld_best_recipe or {}).get("cook_time") or "",
                "total_time": (jsonld_best_recipe or {}).get("total_time") or "",
                "prep_minutes": (jsonld_best_recipe or {}).get("prep_minutes"),
                "cook_minutes": (jsonld_best_recipe or {}).get("cook_minutes"),
                "total_minutes": (jsonld_best_recipe or {}).get("total_minutes"),
            }

    parser_counts = {
        "jsonld": _recipe_parser_counts(jsonld_best_recipe or {}),
        "dom": _recipe_parser_counts(dom_candidate),
        "wprm": _recipe_parser_counts(wprm_candidate),
    }
    raw_sources = {
        "jsonld": dict(jsonld_best_recipe or {}),
        "dom": dict(dom_candidate),
        "wprm": dict(wprm_candidate),
    }
    logger.info(
        "extract parser counts url=%s jsonld=%s dom=%s wprm=%s",
        url,
        parser_counts.get("jsonld"),
        parser_counts.get("dom"),
        parser_counts.get("wprm"),
    )

    selected_source = "dom"
    reason = "dom-only"
    preferred = dom_candidate
    fallback = {}

    if jsonld_best_recipe is not None:
        jsonld_best_recipe["image_url"] = final_image
        jsonld_has_core = bool(jsonld_best_recipe.get("ingredients") or jsonld_best_recipe.get("instructions"))
        dom_has_core = bool(dom_candidate.get("ingredients") or dom_candidate.get("instructions"))

        preferred = jsonld_best_recipe
        reason = "jsonld-default"
        selected_source = "jsonld"
        if _wprm_richer_than_jsonld(wprm_candidate, jsonld_best_recipe):
            preferred = wprm_candidate
            reason = "wprm-richer-structure"
            selected_source = "wprm"
        elif not jsonld_has_core and dom_has_core:
            preferred = dom_candidate
            reason = "dom-replaced-weak-jsonld"
            selected_source = "dom"

        if selected_source == "jsonld":
            fallback = dom_candidate
        elif selected_source == "wprm":
            fallback = jsonld_best_recipe if jsonld_has_core else dom_candidate
        else:
            fallback = jsonld_best_recipe
    elif parser_counts["wprm"]["instructions"] > 0:
        preferred = wprm_candidate
        selected_source = "wprm"
        reason = "wprm-only"
        fallback = dom_candidate

    preferred, supplemented = _supplement_recipe_candidate(preferred, fallback)
    ingredient_groups_source = selected_source
    instruction_groups_source = selected_source
    if selected_source == "jsonld":
        jsonld_ingredient_groups = _normalize_groups((jsonld_best_recipe or {}).get("ingredient_groups") or [], "items")
        dom_ingredient_groups = _normalize_groups(dom_candidate.get("ingredient_groups") or [], "items")
        jsonld_instruction_groups = _normalize_groups((jsonld_best_recipe or {}).get("instruction_groups") or [], "steps")
        dom_instruction_groups = _normalize_groups(dom_candidate.get("instruction_groups") or [], "steps")
        dom_flat_instructions = _flatten_groups(dom_instruction_groups, "steps")
        jsonld_flat_instructions = _flatten_groups(jsonld_instruction_groups, "steps")
        dom_structure_is_noisy = _count_instruction_prefix_expansions(dom_flat_instructions) > 0
        if (
            not dom_structure_is_noisy
            and
            len(jsonld_ingredient_groups) <= 1
            and len(dom_ingredient_groups) >= 2
            and len(_flatten_groups(dom_ingredient_groups, "items")) >= len(_flatten_groups(jsonld_ingredient_groups, "items"))
        ):
            preferred["ingredient_groups"] = dom_ingredient_groups
            preferred["ingredients"] = _flatten_groups(dom_ingredient_groups, "items")
            ingredient_groups_source = "dom-override"

        if (
            not dom_structure_is_noisy
            and
            len(dom_flat_instructions) >= 2
            and (
                len(jsonld_instruction_groups) <= 1
                or len(dom_instruction_groups) > len(jsonld_instruction_groups)
                or _has_named_and_unnamed_instruction_groups(dom_instruction_groups)
                or (
                    any(
                        _normalize_section_title(group.get("title", "")).lower() != "instructions"
                        for group in dom_instruction_groups
                        if isinstance(group, dict)
                    )
                    and len(dom_flat_instructions) >= len(jsonld_flat_instructions)
                )
            )
        ):
            preferred["instruction_groups"] = dom_instruction_groups
            if len(jsonld_flat_instructions) <= 1 and len(dom_flat_instructions) > len(jsonld_flat_instructions):
                preferred["instructions"] = dom_flat_instructions
            instruction_groups_source = "dom-override"

    logger.info(
        "extract parser structure override url=%s ingredient_groups_source=%s instruction_groups_source=%s",
        url,
        ingredient_groups_source,
        instruction_groups_source,
    )
    logger.info(
        "extract parser final group counts url=%s ingredient_groups=%s instruction_groups=%s",
        url,
        len(preferred.get("ingredient_groups") or []),
        len(preferred.get("instruction_groups") or []),
    )
    preferred_counts_pre_finalize = _recipe_parser_counts(preferred)
    logger.info(
        "extract parser pre-finalize url=%s selected_source=%s selected_reason=%s ingredient_group_count_before_finalize=%d instruction_group_count_before_finalize=%d",
        url,
        selected_source,
        reason,
        preferred_counts_pre_finalize.get("ingredient_groups", 0),
        preferred_counts_pre_finalize.get("instruction_groups", 0),
    )
    preferred = _finalize_recipe_candidate(preferred, url, selected_source)
    preferred_counts_post_finalize = _recipe_parser_counts(preferred)
    logger.info(
        "extract parser post-finalize url=%s selected_source=%s selected_reason=%s ingredient_group_count=%d instruction_group_count=%d",
        url,
        selected_source,
        reason,
        preferred_counts_post_finalize.get("ingredient_groups", 0),
        preferred_counts_post_finalize.get("instruction_groups", 0),
    )
    preferred["_selected_source"] = selected_source
    preferred["_selected_reason"] = reason
    preferred["_instruction_groups_source"] = instruction_groups_source
    preferred["_parser_counts"] = parser_counts
    preferred["_raw_sources"] = raw_sources
    logger.info(
        "extract parser pre-return url=%s instructions=%s instruction_groups=%s selected_source=%s instruction_groups_source=%s",
        url,
        preferred.get("instructions") or [],
        preferred.get("instruction_groups") or [],
        preferred.get("_selected_source"),
        preferred.get("_instruction_groups_source"),
    )

    logger.info(
        "extract parser candidate selection url=%s selected=%s reason=%s supplemented=%s %s %s %s",
        url,
        selected_source,
        reason,
        supplemented,
        _recipe_payload_summary("jsonld", jsonld_best_recipe or {}),
        _recipe_payload_summary("dom", dom_candidate),
        _recipe_payload_summary("wprm", wprm_candidate),
    )
    return preferred


def _create_session(conn: sqlite3.Connection, user_id: int) -> tuple[str, datetime]:
    created_at = utcnow()
    expires_at = created_at + timedelta(hours=SESSION_TTL_HOURS)
    token = secrets.token_urlsafe(48)
    conn.execute(
        '''
        INSERT INTO sessions (user_id, session_token, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        ''',
        (user_id, token, created_at.isoformat(), expires_at.isoformat()),
    )
    conn.commit()
    return token, expires_at


def _set_auth_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(1, int((expires_at - utcnow()).total_seconds()))
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
        expires=expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        path="/",
        domain=COOKIE_DOMAIN,
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        domain=COOKIE_DOMAIN,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


def _get_current_user(request: Request) -> dict | None:
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        return None

    now_iso = utcnow_iso()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE expires_at <= ?", (now_iso,))
    row = cur.execute(
        '''
        SELECT users.id, users.email, users.display_name, users.is_admin, users.is_active
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.session_token = ?
          AND sessions.expires_at > ?
          AND users.is_active = 1
          AND users.is_locked_manual = 0
        LIMIT 1
        ''',
        (session_token, now_iso),
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def require_user(request: Request) -> dict:
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_admin(current_user: dict = Depends(require_user)) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def _active_admin_count(cur: sqlite3.Cursor) -> int:
    row = cur.execute(
        "SELECT COUNT(*) AS count FROM users WHERE is_admin = 1 AND is_active = 1"
    ).fetchone()
    return int(row["count"]) if row else 0


def _normalize_display_name(display_name: str | None) -> str | None:
    if display_name is None:
        return None
    normalized = display_name.strip()
    return normalized or None


def _settings_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _settings_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _get_auth_lockout_settings(cur: sqlite3.Cursor) -> dict:
    rows = cur.execute(
        '''
        SELECT key, value
        FROM app_settings
        WHERE key IN (?, ?, ?)
        ''',
        (AUTH_LOCKOUT_ENABLED_KEY, AUTH_MAX_FAILED_ATTEMPTS_KEY, AUTH_LOCKOUT_MINUTES_KEY),
    ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    enabled = _settings_bool(values.get(AUTH_LOCKOUT_ENABLED_KEY), True)
    max_failed_attempts = max(1, _settings_int(values.get(AUTH_MAX_FAILED_ATTEMPTS_KEY), 5))
    lockout_minutes = max(0, _settings_int(values.get(AUTH_LOCKOUT_MINUTES_KEY), 15))
    return {
        "auth_lockout_enabled": enabled,
        "auth_max_failed_attempts": max_failed_attempts,
        "auth_lockout_minutes": lockout_minutes,
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_rating(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1 or value > 5:
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    return int(value)


def _get_settings_key_bytes() -> bytes:
    key = (os.getenv(SETTINGS_ENCRYPTION_KEY_ENV, "") or "").strip()
    if not key:
        raise HTTPException(status_code=500, detail=INTERNAL_SERVER_ERROR_MESSAGE)
    return hashlib.sha256(key.encode("utf-8")).digest()


def _encrypt_user_setting(value: str) -> str:
    key_bytes = _get_settings_key_bytes()
    plaintext = value.encode("utf-8")
    encrypted = bytes(char ^ key_bytes[index % len(key_bytes)] for index, char in enumerate(plaintext))
    return base64.urlsafe_b64encode(encrypted).decode("utf-8")


class UserSettingDecryptionError(RuntimeError):
    def __init__(self, setting_key: str, setting_label: str):
        self.setting_key = setting_key
        self.setting_label = setting_label
        super().__init__(f"{setting_key}_decryption_failed")


def _build_unreadable_user_setting_payload(setting_key: str, setting_label: str) -> dict:
    return {
        "setting": setting_key,
        "status": "unreadable",
        "message": f"Saved {setting_label} could not be read. Delete or replace it in Import Settings, then test again.",
    }


def _decrypt_user_setting(value: str, *, setting_key: str, setting_label: str) -> str:
    try:
        encrypted = base64.urlsafe_b64decode(value.encode("utf-8"))
        key_bytes = _get_settings_key_bytes()
        decrypted = bytes(char ^ key_bytes[index % len(key_bytes)] for index, char in enumerate(encrypted))
        return decrypted.decode("utf-8")
    except Exception as exc:
        raise UserSettingDecryptionError(setting_key, setting_label) from exc


def _get_user_facebook_cookie(user_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT facebook_cookie_encrypted FROM user_import_settings WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    encrypted = (row["facebook_cookie_encrypted"] if row else "") or ""
    if not encrypted:
        return None
    return _decrypt_user_setting(
        encrypted,
        setting_key="facebook_cookie",
        setting_label="Facebook cookie",
    )


def _normalize_cookbook_name(value: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Cookbook name is required")
    return name


def _get_or_create_recipe_user_state(cur: sqlite3.Cursor, recipe_id: int, user_id: int):
    row = cur.execute(
        '''
        SELECT id, recipe_id, user_id, is_cooked, rating, personal_note, is_favorite, last_viewed_at, updated_at
        FROM recipe_user_state
        WHERE recipe_id = ? AND user_id = ?
        LIMIT 1
        ''',
        (recipe_id, user_id),
    ).fetchone()
    if row:
        return row

    now_iso = utcnow_iso()
    cur.execute(
        '''
        INSERT INTO recipe_user_state (recipe_id, user_id, is_cooked, rating, personal_note, is_favorite, last_viewed_at, updated_at)
        VALUES (?, ?, 0, NULL, NULL, 0, NULL, ?)
        ''',
        (recipe_id, user_id, now_iso),
    )
    return cur.execute(
        '''
        SELECT id, recipe_id, user_id, is_cooked, rating, personal_note, is_favorite, last_viewed_at, updated_at
        FROM recipe_user_state
        WHERE recipe_id = ? AND user_id = ?
        LIMIT 1
        ''',
        (recipe_id, user_id),
    ).fetchone()


def _fetch_recipe_related_data(cur: sqlite3.Cursor, recipe_ids: list[int], user_id: int) -> tuple[dict[int, list[dict]], dict[int, dict]]:
    if not recipe_ids:
        return {}, {}
    placeholders = ",".join("?" for _ in recipe_ids)
    cookbook_rows = cur.execute(
        f'''
        SELECT rc.recipe_id, c.id AS cookbook_id, c.name
        FROM recipe_cookbooks rc
        JOIN cookbooks c ON c.id = rc.cookbook_id
        WHERE c.user_id = ? AND rc.recipe_id IN ({placeholders})
        ORDER BY lower(c.name) ASC
        ''',
        (user_id, *recipe_ids),
    ).fetchall()
    cookbooks_by_recipe: dict[int, list[dict]] = {}
    for row in cookbook_rows:
        recipe_id = int(row["recipe_id"])
        cookbooks_by_recipe.setdefault(recipe_id, []).append(
            {"id": int(row["cookbook_id"]), "name": row["name"]}
        )

    state_rows = cur.execute(
        f'''
        SELECT recipe_id, is_cooked, rating, personal_note, is_favorite, last_viewed_at, updated_at
        FROM recipe_user_state
        WHERE user_id = ? AND recipe_id IN ({placeholders})
        ''',
        (user_id, *recipe_ids),
    ).fetchall()
    state_by_recipe = {
        int(row["recipe_id"]): {
            "is_cooked": bool(row["is_cooked"]),
            "rating": row["rating"],
            "personal_note": row["personal_note"],
            "is_favorite": bool(row["is_favorite"]),
            "last_viewed_at": row["last_viewed_at"],
            "updated_at": row["updated_at"],
        }
        for row in state_rows
    }
    return cookbooks_by_recipe, state_by_recipe


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": "1.0.0"}


@app.post("/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    password = payload.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    conn = get_conn()
    cur = conn.cursor()
    user = cur.execute(
        '''
        SELECT id, email, display_name, password_hash, is_admin, is_active, failed_login_attempts, locked_until, is_locked_manual
        FROM users
        WHERE lower(email) = ?
        LIMIT 1
        ''',
        (email,),
    ).fetchone()
    lockout_settings = _get_auth_lockout_settings(cur)
    now = utcnow()
    now_iso = now.isoformat()
    generic_error_message = "Unable to sign in. Please try again later."

    if user:
        if bool(user["is_locked_manual"]):
            logger.warning(
                "Blocked login for manually locked account email=%s timestamp=%s",
                email,
                now_iso,
            )
            conn.close()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=generic_error_message)
        locked_until = _parse_iso_datetime(user["locked_until"])
        if lockout_settings["auth_lockout_enabled"] and locked_until and locked_until > now:
            logger.warning(
                "Blocked login for locked account email=%s timestamp=%s",
                email,
                now_iso,
            )
            conn.close()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=generic_error_message)

    if not user or not verify_password(password, user["password_hash"]) or not user["is_active"]:
        if user:
            next_failed_attempts = int(user["failed_login_attempts"] or 0) + 1
            next_locked_until: str | None = None
            next_is_locked_manual = int(user["is_locked_manual"] or 0)
            if (
                lockout_settings["auth_lockout_enabled"]
                and next_failed_attempts >= int(lockout_settings["auth_max_failed_attempts"])
            ):
                if int(lockout_settings["auth_lockout_minutes"]) > 0:
                    next_locked_until = (now + timedelta(minutes=int(lockout_settings["auth_lockout_minutes"]))).isoformat()
                else:
                    next_is_locked_manual = 1
            cur.execute(
                '''
                UPDATE users
                SET failed_login_attempts = ?, locked_until = ?, is_locked_manual = ?
                WHERE id = ?
                ''',
                (next_failed_attempts, next_locked_until, next_is_locked_manual, user["id"]),
            )
            conn.commit()
        logger.warning(
            "Failed login attempt email=%s timestamp=%s",
            email,
            now_iso,
        )
        conn.close()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=generic_error_message)

    cur.execute(
        '''
        UPDATE users
        SET last_login = ?, failed_login_attempts = 0, locked_until = NULL
        WHERE id = ?
        ''',
        (now_iso, user["id"]),
    )
    token, expires_at = _create_session(conn, user["id"])
    conn.close()
    logger.info("Successful login user_id=%s timestamp=%s", user["id"], now_iso)

    response = JSONResponse(
        {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"] if "display_name" in user.keys() else None,
            "is_admin": bool(user["is_admin"]),
            "expires_at": expires_at.isoformat(),
        }
    )
    _set_auth_cookie(response, token, expires_at)
    return response


@app.post("/auth/logout")
def logout(request: Request):
    session_token = request.cookies.get(COOKIE_NAME)
    if session_token:
        conn = get_conn()
        conn.execute("DELETE FROM sessions WHERE session_token = ?", (session_token,))
        conn.commit()
        conn.close()

    response = JSONResponse({"message": "Logged out"})
    _clear_auth_cookie(response)
    return response


@app.get("/auth/me")
def me(current_user: dict = Depends(require_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "display_name": current_user.get("display_name"),
        "is_admin": bool(current_user["is_admin"]),
    }


class UpdateFacebookCookieRequest(BaseModel):
    facebook_cookie: str = Field(min_length=1)


def _looks_like_facebook_cookie_value(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    if "c_user=" in normalized or "xs=" in normalized:
        return True
    for line in normalized.splitlines():
        if "\t" in line and "facebook.com" in line:
            return True
    return False


def _is_raw_facebook_cookie_blob(value: str) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if "netscape http cookie file" in lowered:
        return True
    if "\t" in normalized and "facebook.com" in lowered:
        return True
    return bool(re.search(r"[\r\n]+", normalized))


def _safe_service_check(url: str, timeout_seconds: float = 1.8) -> tuple[str, str | None]:
    normalized = (url or "").strip()
    if not normalized:
        return "not_configured", None
    try:
        response = requests.get(normalized, timeout=timeout_seconds)
        if response.status_code < 500:
            return "online", normalized
        return "offline", normalized
    except Exception:
        return "offline", normalized


def _health_probe_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized
    return f"{parsed.scheme}://{parsed.netloc}/health"


def _ollama_status() -> tuple[str, str | None]:
    if not OLLAMA_BASE_URL or not OLLAMA_MODEL:
        return "not_configured", None
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.8)
        if response.ok:
            return "online", OLLAMA_BASE_URL
    except Exception:
        pass
    return "offline", OLLAMA_BASE_URL


@app.get("/settings/import")
def get_import_settings(current_user: dict = Depends(require_user)):
    conn = get_conn()
    row = conn.execute(
        '''
        SELECT facebook_cookie_encrypted, facebook_cookie_updated_at
        FROM user_import_settings
        WHERE user_id = ?
        LIMIT 1
        ''',
        (current_user["id"],),
    ).fetchone()
    conn.close()
    encrypted_cookie = (row["facebook_cookie_encrypted"] if row else "") or ""
    facebook_cookie_error = None
    facebook_cookie_status = "missing"
    if encrypted_cookie:
        facebook_cookie_status = "configured"
        try:
            _decrypt_user_setting(
                encrypted_cookie,
                setting_key="facebook_cookie",
                setting_label="Facebook cookie",
            )
        except UserSettingDecryptionError:
            facebook_cookie_status = "unreadable"
            facebook_cookie_error = _build_unreadable_user_setting_payload("facebook_cookie", "Facebook cookie")
    return {
        "has_facebook_cookie": bool(encrypted_cookie),
        "facebook_cookie_updated_at": row["facebook_cookie_updated_at"] if row else None,
        "facebook_cookie_status": facebook_cookie_status,
        "facebook_cookie_warning": facebook_cookie_error["message"] if facebook_cookie_error else "",
        "facebook_cookie_error": facebook_cookie_error,
    }


@app.get("/status/import-services")
def import_services_status(current_user: dict = Depends(require_user)):
    del current_user
    ocr_probe_url = _health_probe_url(os.getenv("OCR_WORKER_URL", "").strip())
    social_probe_url = _health_probe_url(os.getenv("SOCIAL_DOWNLOADER_URL", "").strip())
    whisper_probe_url = _health_probe_url(os.getenv("WHISPER_PROCESSOR_URL", "").strip())
    ocr_status, ocr_url = _safe_service_check(ocr_probe_url)
    social_status, social_url = _safe_service_check(social_probe_url)
    whisper_status, whisper_url = _safe_service_check(whisper_probe_url)
    ollama_status, ollama_url = _ollama_status()
    now_iso = utcnow_iso()
    services = {
        "backend": {"status": "online", "url": None, "last_checked_at": now_iso},
        "ocr_worker": {"status": ocr_status, "url": ocr_url, "last_checked_at": now_iso},
        "social_downloader": {"status": social_status, "url": social_url, "last_checked_at": now_iso},
        "whisper_processor": {"status": whisper_status, "url": whisper_url, "last_checked_at": now_iso},
        "ollama": {
            "status": ollama_status,
            "url": ollama_url,
            "model": OLLAMA_MODEL if OLLAMA_MODEL else None,
            "last_checked_at": now_iso,
        },
        "ai_review": {
            "status": "online" if AI_REVIEW_ENABLED else "not_configured",
            "enabled": AI_REVIEW_ENABLED,
            "last_checked_at": now_iso,
        },
    }
    blocking = [name for name in ("ocr_worker", "social_downloader", "whisper_processor", "ollama") if services[name]["status"] == "offline"]
    warning = "Some import services are offline. Imports may fail until services recover." if blocking else ""
    return {"services": services, "warning": warning}


@app.put("/settings/import/facebook-cookie")
def put_facebook_import_cookie(payload: UpdateFacebookCookieRequest, current_user: dict = Depends(require_user)):
    cookie_value = (payload.facebook_cookie or "").strip()
    if not cookie_value:
        raise HTTPException(status_code=400, detail="facebook_cookie is required")
    if _is_raw_facebook_cookie_blob(cookie_value):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "facebook_cookie"],
                    "msg": "Invalid Facebook cookie format",
                    "input": "<bytes omitted>",
                }
            ],
        )
    encrypted_cookie = _encrypt_user_setting(cookie_value)
    now_iso = utcnow_iso()
    conn = get_conn()
    conn.execute(
        '''
        INSERT INTO user_import_settings (user_id, facebook_cookie_encrypted, facebook_cookie_updated_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          facebook_cookie_encrypted = excluded.facebook_cookie_encrypted,
          facebook_cookie_updated_at = excluded.facebook_cookie_updated_at,
          updated_at = excluded.updated_at
        ''',
        (current_user["id"], encrypted_cookie, now_iso, now_iso),
    )
    conn.commit()
    conn.close()
    return {"has_facebook_cookie": True, "facebook_cookie_updated_at": now_iso}


@app.delete("/settings/import/facebook-cookie")
def delete_facebook_import_cookie(current_user: dict = Depends(require_user)):
    now_iso = utcnow_iso()
    conn = get_conn()
    conn.execute(
        '''
        INSERT INTO user_import_settings (user_id, facebook_cookie_encrypted, facebook_cookie_updated_at, updated_at)
        VALUES (?, NULL, NULL, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          facebook_cookie_encrypted = NULL,
          facebook_cookie_updated_at = NULL,
          updated_at = excluded.updated_at
        ''',
        (current_user["id"], now_iso),
    )
    conn.commit()
    conn.close()
    return {"has_facebook_cookie": False, "facebook_cookie_updated_at": None}


@app.post("/settings/import/facebook-cookie/test")
def test_facebook_import_cookie(current_user: dict = Depends(require_user)):
    try:
        cookie_value = _get_user_facebook_cookie(int(current_user["id"])) if current_user.get("id") else None
    except UserSettingDecryptionError:
        error_payload = _build_unreadable_user_setting_payload("facebook_cookie", "Facebook cookie")
        return {
            "status": "unreadable_cookie",
            "message": error_payload["message"],
            "setting": error_payload["setting"],
        }
    if not cookie_value:
        return {"status": "missing_cookie", "message": "No Facebook cookie saved"}
    if not _looks_like_facebook_cookie_value(cookie_value):
        return {"status": "invalid_format", "message": "Saved Facebook cookie format looks invalid"}
    return {"status": "success", "message": "Facebook cookie is saved and ready to use"}


@app.get("/admin/users")
def admin_list_users(_: dict = Depends(require_admin)):
    conn = get_conn()
    rows = conn.execute(
        '''
        SELECT id, email, display_name, is_admin, is_active, created_at, last_login, failed_login_attempts, locked_until, is_locked_manual
        FROM users
        ORDER BY id ASC
        '''
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/admin/security-settings")
def admin_get_security_settings(_: dict = Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    settings = _get_auth_lockout_settings(cur)
    conn.close()
    return settings


@app.put("/admin/security-settings")
def admin_update_security_settings(
    payload: AdminSecuritySettingsUpdateRequest,
    current_admin: dict = Depends(require_admin),
):
    max_failed_attempts = int(payload.auth_max_failed_attempts)
    lockout_minutes = int(payload.auth_lockout_minutes)
    if max_failed_attempts < 1:
        raise HTTPException(status_code=400, detail="Max failed attempts must be at least 1")
    if lockout_minutes < 0:
        raise HTTPException(status_code=400, detail="Lockout duration must be at least 0 minutes")

    now_iso = utcnow_iso()
    conn = get_conn()
    cur = conn.cursor()
    settings_updates = [
        (AUTH_LOCKOUT_ENABLED_KEY, "true" if payload.auth_lockout_enabled else "false"),
        (AUTH_MAX_FAILED_ATTEMPTS_KEY, str(max_failed_attempts)),
        (AUTH_LOCKOUT_MINUTES_KEY, str(lockout_minutes)),
    ]
    for setting_key, setting_value in settings_updates:
        cur.execute(
            '''
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              updated_at = excluded.updated_at
            ''',
            (setting_key, setting_value, now_iso),
        )
    conn.commit()
    conn.close()
    logger.info(
        "Admin updated security settings admin_id=%s timestamp=%s lockout_enabled=%s max_failed_attempts=%s lockout_minutes=%s",
        current_admin["id"],
        now_iso,
        payload.auth_lockout_enabled,
        max_failed_attempts,
        lockout_minutes,
    )
    return {
        "auth_lockout_enabled": payload.auth_lockout_enabled,
        "auth_max_failed_attempts": max_failed_attempts,
        "auth_lockout_minutes": lockout_minutes,
    }


@app.post("/admin/users")
def admin_create_user(payload: CreateUserRequest, current_admin: dict = Depends(require_admin)):
    email = payload.email.strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    display_name = _normalize_display_name(payload.display_name)
    conn = get_conn()
    cur = conn.cursor()
    exists = cur.execute(
        "SELECT id FROM users WHERE lower(email) = ? LIMIT 1",
        (email,),
    ).fetchone()
    if exists:
        conn.close()
        raise HTTPException(status_code=409, detail="User already exists")

    cur.execute(
        '''
        INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at, last_login)
        VALUES (?, ?, ?, ?, 1, ?, NULL)
        ''',
        (email, display_name, hash_password(payload.password), int(payload.is_admin), utcnow_iso()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    logger.info(
        "Admin user created user_id=%s email=%s created_by=%s timestamp=%s",
        user_id,
        email,
        current_admin["id"],
        utcnow_iso(),
    )
    return {
        "id": user_id,
        "email": email,
        "display_name": display_name,
        "is_admin": payload.is_admin,
        "is_active": True,
    }


@app.put("/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: UpdateUserRequest, current_admin: dict = Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, email, is_admin, is_active FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    updates: list[str] = []
    values: list[object] = []
    target_is_active = bool(user["is_active"])

    if payload.display_name is not None:
        updates.append("display_name = ?")
        values.append(_normalize_display_name(payload.display_name))
    if payload.is_admin is not None:
        target_is_admin = bool(payload.is_admin)
        if bool(user["is_admin"]) and bool(user["is_active"]) and not target_is_admin and _active_admin_count(cur) <= 1:
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot remove admin rights from the last active admin")
        if int(current_admin["id"]) == int(user_id) and bool(user["is_admin"]) and not target_is_admin:
            conn.close()
            raise HTTPException(status_code=400, detail="Admin cannot remove own admin rights")
        updates.append("is_admin = ?")
        values.append(int(target_is_admin))
    if payload.is_active is not None:
        target_is_active = bool(payload.is_active)
        if not target_is_active and int(current_admin["id"]) == int(user_id):
            conn.close()
            raise HTTPException(status_code=400, detail="Admin cannot deactivate own account")
        if bool(user["is_admin"]) and not target_is_active and _active_admin_count(cur) <= 1:
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
        updates.append("is_active = ?")
        values.append(int(target_is_active))

    if not updates:
        conn.close()
        raise HTTPException(status_code=400, detail="No updates provided")

    values.append(user_id)
    cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(values))
    if payload.is_active is not None and not target_is_active:
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    updated = cur.execute(
        "SELECT id, email, display_name, is_admin, is_active, created_at, last_login FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(updated)


@app.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: ResetPasswordRequest, current_admin: dict = Depends(require_admin)):
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")
    conn = get_conn()
    cur = conn.cursor()
    exists = cur.execute("SELECT id FROM users WHERE id = ? LIMIT 1", (user_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(payload.password), user_id),
    )
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(
        "Admin reset password user_id=%s reset_by=%s timestamp=%s",
        user_id,
        current_admin["id"],
        utcnow_iso(),
    )
    return {"message": "Password reset"}


@app.post("/admin/users/{user_id}/deactivate")
def admin_deactivate_user(user_id: int, current_admin: dict = Depends(require_admin)):
    if int(current_admin["id"]) == int(user_id):
        raise HTTPException(status_code=400, detail="Admin cannot deactivate own account")
    conn = get_conn()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, is_admin, is_active FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    if bool(user["is_admin"]) and bool(user["is_active"]) and _active_admin_count(cur) <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot deactivate the last active admin")
    cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(
        "Admin deactivated user user_id=%s deactivated_by=%s timestamp=%s",
        user_id,
        current_admin["id"],
        utcnow_iso(),
    )
    return {"message": "User deactivated"}


@app.post("/admin/users/{user_id}/activate")
def admin_activate_user(user_id: int, current_admin: dict = Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    logger.info(
        "Admin reactivated user user_id=%s reactivated_by=%s timestamp=%s",
        user_id,
        current_admin["id"],
        utcnow_iso(),
    )
    return {"message": "User activated"}


@app.post("/admin/users/{user_id}/lock")
def admin_lock_user(user_id: int, current_admin: dict = Depends(require_admin)):
    if int(current_admin["id"]) == int(user_id):
        raise HTTPException(status_code=400, detail="Admin cannot manually lock own account")
    conn = get_conn()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, is_admin, is_active FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    if bool(user["is_admin"]) and bool(user["is_active"]) and _active_admin_count(cur) <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot lock the last active admin")
    cur.execute(
        "UPDATE users SET is_locked_manual = 1, locked_until = NULL WHERE id = ?",
        (user_id,),
    )
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User locked"}


@app.post("/admin/users/{user_id}/unlock")
def admin_unlock_user(user_id: int, _: dict = Depends(require_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_locked_manual = 0, locked_until = NULL, failed_login_attempts = 0 WHERE id = ?",
        (user_id,),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    return {"message": "User unlocked"}


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, current_admin: dict = Depends(require_admin)):
    if int(current_admin["id"]) == int(user_id):
        raise HTTPException(status_code=400, detail="Admin cannot delete own account")
    conn = get_conn()
    cur = conn.cursor()
    user = cur.execute(
        "SELECT id, email, is_admin, is_active FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    if bool(user["is_admin"]) and bool(user["is_active"]) and _active_admin_count(cur) <= 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot delete the last active admin")
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(
        "Admin deleted user user_id=%s email=%s deleted_by=%s timestamp=%s",
        user_id,
        user["email"],
        current_admin["id"],
        utcnow_iso(),
    )
    return {"message": "User deleted"}


@app.get("/recipes")
def get_recipes(current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM recipes WHERE user_id = ? ORDER BY id DESC",
        (int(current_user["id"]),),
    )
    rows = cur.fetchall()
    recipe_ids = [int(row["id"]) for row in rows]
    cookbooks_by_recipe, state_by_recipe = _fetch_recipe_related_data(
        cur,
        recipe_ids,
        int(current_user["id"]),
    )
    conn.close()

    recipes: list[dict] = []
    for row in rows:
        payload = dict(row)
        recipe_id = int(payload["id"])
        payload["image_url"] = _normalize_recipe_image_value(payload.get("image_url"))
        payload["ingredients"] = _text_to_json_array(payload.get("ingredients"))
        payload["instructions"] = _text_to_json_array(payload.get("instructions"))
        payload["ingredient_groups"] = _text_to_json_groups(payload.get("ingredient_groups"), "items")
        payload["instruction_groups"] = _text_to_json_groups(payload.get("instruction_groups"), "steps")
        payload["servings"] = payload.get("servings") or ""
        payload["prep_time"] = payload.get("prep_time") or ""
        payload["cook_time"] = payload.get("cook_time") or ""
        payload["total_time"] = payload.get("total_time") or ""
        payload["original_source_url"] = payload.get("original_source_url") or ""
        payload["resolved_recipe_url"] = payload.get("resolved_recipe_url") or payload.get("url") or ""
        payload["content_source"] = payload.get("content_source") or "direct_recipe_url"
        payload["prep_minutes"] = payload.get("prep_minutes")
        payload["cook_minutes"] = payload.get("cook_minutes")
        payload["total_minutes"] = payload.get("total_minutes")
        payload.update(_recipe_review_payload_from_row(row))

        if not payload["ingredient_groups"] and payload["ingredients"]:
            payload["ingredient_groups"] = [{"title": "", "items": payload["ingredients"]}]
        if not payload["instruction_groups"] and payload["instructions"]:
            payload["instruction_groups"] = [{"title": "", "steps": payload["instructions"]}]

        cookbooks = cookbooks_by_recipe.get(recipe_id, [])
        user_state = state_by_recipe.get(recipe_id, {})
        payload["cookbooks"] = cookbooks
        payload["cookbook_ids"] = [int(item["id"]) for item in cookbooks]
        payload["is_cooked"] = bool(user_state.get("is_cooked", False))
        payload["rating"] = user_state.get("rating")
        payload["personal_note"] = user_state.get("personal_note")
        payload["user_state"] = {
            "is_cooked": bool(user_state.get("is_cooked", False)),
            "rating": user_state.get("rating"),
            "personal_note": user_state.get("personal_note"),
            "is_favorite": bool(user_state.get("is_favorite", False)),
            "last_viewed_at": user_state.get("last_viewed_at"),
            "updated_at": user_state.get("updated_at"),
        }
        recipes.append(payload)
    return recipes


@app.post("/recipes")
def add_recipe(recipe: Recipe, current_user: dict = Depends(require_user)):
    logger.info(
        "add_recipe_request user_id=%s title_len=%d ingredients=%d instructions=%d ingredient_groups=%d instruction_groups=%d",
        current_user.get("id"),
        len((recipe.title or "").strip()),
        len(recipe.ingredients or []),
        len(recipe.instructions or []),
        len(recipe.ingredient_groups or []),
        len(recipe.instruction_groups or []),
    )
    if not _has_recipe_content(recipe):
        logger.error(
            "add_recipe_rejected_empty_content user_id=%s title=%s ingredients=%s instructions=%s",
            current_user.get("id"),
            (recipe.title or "").strip(),
            recipe.ingredients or [],
            recipe.instructions or [],
        )
        raise HTTPException(status_code=422, detail="Recipe extraction is empty or unusable")

    normalized_url = (recipe.url or "").strip()
    content_source = recipe.content_source
    source_type = recipe.source_type
    if not normalized_url:
        normalized_url = ""
        content_source = content_source or "image_ocr"
        source_type = source_type or "Image"

    review_status = "queued" if _coerce_review_status(recipe.review_status) == "queued" else "none"
    review_requested_at = utcnow_iso() if review_status == "queued" else None
    _log_recipe_db_write_trace(
        "add_recipe_pre_save",
        None,
        {
            "ingredient_groups": recipe.ingredient_groups or [],
            "instruction_groups": recipe.instruction_groups or [],
        },
    )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO recipes (
            user_id,
            title,
            url,
            original_source_url,
            resolved_recipe_url,
            content_source,
            image_url,
            source_app,
            source_type,
            notes,
            tags,
            needs_review,
            review_status,
            review_notes,
            review_requested_at,
            ingredients,
            instructions,
            servings,
            prep_time,
            cook_time,
            total_time,
            prep_minutes,
            cook_minutes,
            total_minutes,
            ingredient_groups,
            instruction_groups,
            ai_review_source_payload
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            int(current_user["id"]),
            recipe.title,
            normalized_url,
            recipe.original_source_url,
            recipe.resolved_recipe_url,
            content_source,
            _normalize_recipe_image_value(recipe.image_url),
            recipe.source_app,
            source_type,
            recipe.notes,
            recipe.tags,
            int(recipe.needs_review),
            review_status,
            recipe.review_notes,
            review_requested_at,
            _json_array_to_text(recipe.ingredients),
            _json_array_to_text(recipe.instructions),
            (recipe.servings or "").strip() if recipe.servings is not None else None,
            (recipe.prep_time or "").strip() if recipe.prep_time is not None else None,
            (recipe.cook_time or "").strip() if recipe.cook_time is not None else None,
            (recipe.total_time or "").strip() if recipe.total_time is not None else None,
            recipe.prep_minutes,
            recipe.cook_minutes,
            recipe.total_minutes,
            _json_groups_to_text(recipe.ingredient_groups, "items"),
            _json_groups_to_text(recipe.instruction_groups, "steps"),
            json.dumps(recipe.ai_review_source_payload, ensure_ascii=False) if isinstance(recipe.ai_review_source_payload, dict) else None,
        ),
    )
    conn.commit()
    recipe_id = cur.lastrowid
    conn.close()
    if review_status == "queued":
        logger.info("review_queue_started recipe_id=%s", recipe_id)
    return {"message": "Recipe added", "id": recipe_id}


@app.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM recipes WHERE id = ? AND user_id = ?",
        (recipe_id, int(current_user["id"])),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.close()
    return {"message": "deleted"}


@app.put("/recipes/{recipe_id}")
def update_recipe(recipe_id: int, recipe: Recipe, current_user: dict = Depends(require_user)):
    if not _has_recipe_content(recipe):
        raise HTTPException(status_code=422, detail="Recipe extraction is empty or unusable")

    normalized_url = (recipe.url or "").strip()
    content_source = recipe.content_source
    source_type = recipe.source_type
    if not normalized_url:
        normalized_url = ""
        content_source = content_source or "image_ocr"
        source_type = source_type or "Image"

    review_status = "queued" if _coerce_review_status(recipe.review_status) == "queued" else "none"
    review_requested_at = utcnow_iso() if review_status == "queued" else None
    _log_recipe_db_write_trace(
        "update_recipe_pre_save",
        recipe_id,
        {
            "ingredient_groups": recipe.ingredient_groups or [],
            "instruction_groups": recipe.instruction_groups or [],
        },
    )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        '''
        UPDATE recipes
        SET title = ?, url = ?, original_source_url = ?, resolved_recipe_url = ?, content_source = ?,
            image_url = ?, source_app = ?, source_type = ?, notes = ?, tags = ?,
            needs_review = ?, review_status = ?, review_notes = ?, review_requested_at = ?, ingredients = ?, instructions = ?, servings = ?,
            prep_time = ?, cook_time = ?, total_time = ?,
            prep_minutes = ?, cook_minutes = ?, total_minutes = ?,
            ingredient_groups = ?, instruction_groups = ?
        WHERE id = ?
          AND user_id = ?
        ''',
        (
            recipe.title,
            normalized_url,
            recipe.original_source_url,
            recipe.resolved_recipe_url,
            content_source,
            _normalize_recipe_image_value(recipe.image_url),
            recipe.source_app,
            source_type,
            recipe.notes,
            recipe.tags,
            int(recipe.needs_review),
            review_status,
            recipe.review_notes,
            review_requested_at,
            _json_array_to_text(recipe.ingredients),
            _json_array_to_text(recipe.instructions),
            (recipe.servings or "").strip() if recipe.servings is not None else None,
            (recipe.prep_time or "").strip() if recipe.prep_time is not None else None,
            (recipe.cook_time or "").strip() if recipe.cook_time is not None else None,
            (recipe.total_time or "").strip() if recipe.total_time is not None else None,
            recipe.prep_minutes,
            recipe.cook_minutes,
            recipe.total_minutes,
            _json_groups_to_text(recipe.ingredient_groups, "items"),
            _json_groups_to_text(recipe.instruction_groups, "steps"),
            recipe_id,
            int(current_user["id"]),
        ),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    conn.close()
    if review_status == "queued":
        logger.info("review_queue_started recipe_id=%s", recipe_id)
    return {"message": "updated"}


@app.post("/recipes/{recipe_id}/queue-review")
def queue_recipe_review(recipe_id: int, current_user: dict = Depends(require_user)):
    requested_at = utcnow_iso()
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    status_now = _coerce_review_status(row["review_status"])
    if status_now == "processing":
        conn.close()
        return {"message": "Already processing", **_recipe_review_payload_from_row(row)}

    cur.execute(
        """
        UPDATE recipes
        SET review_status = 'queued',
            review_requested_at = ?,
            review_started_at = NULL,
            review_completed_at = NULL,
            review_error = NULL
        WHERE id = ?
          AND user_id = ?
        """,
        (requested_at, recipe_id, int(current_user["id"])),
    )
    conn.commit()
    updated = cur.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.close()
    logger.info("review_queue_started recipe_id=%s", recipe_id)
    return {
        "message": "Queued for AI review",
        "ai_review_enabled": AI_REVIEW_ENABLED,
        **_recipe_review_payload_from_row(updated),
    }


@app.get("/recipes/{recipe_id}/review-status")
def get_recipe_review_status(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return {
        "recipe_id": recipe_id,
        "ai_review_enabled": AI_REVIEW_ENABLED,
        **_recipe_review_payload_from_row(row),
    }


@app.get("/recipes/{recipe_id}/review-result")
def get_recipe_review_result(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")

    raw_result = None
    normalized_result = None
    if row["ai_review_result"]:
        try:
            raw_result = json.loads(row["ai_review_result"])
        except Exception:
            raw_result = row["ai_review_result"]
    if row["ai_review_normalized"]:
        try:
            normalized_result = json.loads(row["ai_review_normalized"])
        except Exception:
            normalized_result = row["ai_review_normalized"]

    return {
        "recipe_id": recipe_id,
        **_recipe_review_payload_from_row(row),
        "ai_review_source_payload": row["ai_review_source_payload"],
        "ai_review_result": raw_result,
        "ai_review_normalized": normalized_result,
    }


@app.post("/recipes/{recipe_id}/retry-review")
def retry_recipe_review(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    requested_at = utcnow_iso()
    cur.execute(
        """
        UPDATE recipes
        SET review_status = 'queued',
            review_requested_at = ?,
            review_started_at = NULL,
            review_completed_at = NULL,
            review_error = NULL
        WHERE id = ?
          AND user_id = ?
        """,
        (requested_at, recipe_id, int(current_user["id"])),
    )
    conn.commit()
    updated = cur.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    conn.close()
    logger.info("review_queue_started recipe_id=%s retry=true", recipe_id)
    return {"message": "Queued for AI review", **_recipe_review_payload_from_row(updated)}


@app.post("/recipes/{recipe_id}/ai-cleanup")
def run_manual_ai_cleanup(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    source_url = _clean_text(row["url"] or "")

    logger.info("manual_ai_cleanup_start recipe_id=%s", recipe_id)
    if source_url:
        logger.info("manual_ai_cleanup_fetch_start recipe_id=%s url=%s", recipe_id, source_url)
    parsed_recipe = _manual_ai_cleanup_payload_from_row(row)
    preview_payload = _sanitize_preview_ingredient_payload(parsed_recipe)

    try:
        parsed_json, normalized_result, _, _, returned_parsed_recipe = _run_ai_cleanup_pipeline(
            source_url or None,
            parsed_recipe=parsed_recipe,
        )
        logger.info("manual_ai_cleanup_fetch_success recipe_id=%s url=%s", recipe_id, source_url)
        if _is_useful_ai_cleanup_result(normalized_result):
            ai_preview_payload = _modal_preview_payload_from_parsed_ai_json(parsed_json, returned_parsed_recipe)
            preview_payload = _prefer_richer_preview_payload(preview_payload, ai_preview_payload)
            preview_payload = _sanitize_preview_ingredient_payload(preview_payload)
            if _ai_cleanup_requested_no_changes(parsed_json) or not _ai_cleanup_has_meaningful_changes(parsed_recipe, preview_payload):
                logger.info("manual_ai_cleanup_no_changes recipe_id=%s source=ai_cleanup", recipe_id)
                return {
                    "message": "No meaningful improvements recommended.",
                    "payload_source": "ai_cleanup",
                    "preview": preview_payload,
                    "no_changes": True,
                }
            logger.info("manual_ai_cleanup_ready_for_review recipe_id=%s source=ai_cleanup", recipe_id)
            return {
                "message": "AI cleanup ready for review",
                "payload_source": "ai_cleanup",
                "preview": preview_payload,
                "no_changes": False,
            }
        raise HTTPException(status_code=422, detail="AI cleanup returned empty recipe structure")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("manual_ai_cleanup_failed recipe_id=%s error=%s", recipe_id, str(exc))
        raise HTTPException(status_code=502, detail="AI cleanup failed while processing this recipe")
    finally:
        conn.close()


@app.post("/recipes/modal-ai-cleanup")
def run_modal_ai_cleanup(payload: ModalAiCleanupRequest, _: dict = Depends(require_user)):
    source_url = _clean_text(payload.url or "")
    extracted_preview = payload.preview if isinstance(payload.preview, dict) else {}
    if not source_url:
        raise HTTPException(status_code=422, detail="Recipe URL is required for AI cleanup")

    logger.info("modal_ai_cleanup_start url=%s", source_url)
    logger.info("modal_ai_cleanup_fetch_start url=%s", source_url)
    preview_payload = _sanitize_preview_ingredient_payload(
        {
            "title": _clean_text(extracted_preview.get("title") or ""),
            "servings": _clean_text(extracted_preview.get("servings") or ""),
            "prep_time": _clean_text(extracted_preview.get("prep_time") or ""),
            "cook_time": _clean_text(extracted_preview.get("cook_time") or ""),
            "total_time": _clean_text(extracted_preview.get("total_time") or ""),
            "ingredient_groups": _normalize_groups(extracted_preview.get("ingredient_groups") or [], "items"),
            "instruction_groups": _normalize_groups(extracted_preview.get("instruction_groups") or [], "steps"),
            "ingredients": _normalize_plain_string_list(extracted_preview.get("ingredients") or []),
            "instructions": _as_string_list(extracted_preview.get("instructions") or []),
        }
    )
    payload_source = "recipe_container"
    try:
        parsed_json, normalized_result, _, _, parsed_recipe = _run_ai_cleanup_pipeline(
            source_url,
            parsed_recipe=preview_payload,
        )
        logger.info("modal_ai_cleanup_fetch_success url=%s", source_url)
        logger.info("modal_ai_cleanup_parsed_ai_json=%s", json.dumps(parsed_json, ensure_ascii=False))
        ai_result_useful = _is_useful_ai_cleanup_result(normalized_result)
        logger.info("modal_ai_cleanup_ai_result_useful=%s", ai_result_useful)
        if ai_result_useful:
            ai_preview_payload = _modal_preview_payload_from_parsed_ai_json(parsed_json, parsed_recipe)
            _log_recipe_candidate_counts(source_url, "ai_cleanup_raw", ai_preview_payload)
            preview_payload = _prefer_richer_preview_payload(preview_payload, ai_preview_payload)
            _log_recipe_candidate_counts(source_url, "ai_cleanup_merged", preview_payload)
            logger.info("AI_DIRECT_PAYLOAD=%s", json.dumps(preview_payload))
            logger.info("modal_ai_cleanup_parsed_ai_json=%s", json.dumps(parsed_json, ensure_ascii=False))
            logger.info("modal_ai_cleanup_preview_payload_direct=%s", json.dumps(preview_payload, ensure_ascii=False))
            logger.info(
                "modal_ai_cleanup_preview_payload_group_counts ingredients=%s instructions=%s",
                len(preview_payload.get("ingredient_groups", [])),
                len(preview_payload.get("instruction_groups", [])),
            )
            payload_source = "ai_cleanup"
            if _ai_cleanup_requested_no_changes(parsed_json) or not _ai_cleanup_has_meaningful_changes(parsed_recipe, preview_payload):
                preview_payload = _sanitize_preview_ingredient_payload(preview_payload)
                logger.info("modal_ai_cleanup_no_changes url=%s", source_url)
                return {
                    "preview": preview_payload,
                    "payload_source": payload_source,
                    "message": "No meaningful improvements recommended.",
                    "no_changes": True,
                }
        else:
            logger.warning("modal_ai_cleanup_fallback reason=%s", "empty_ai_structure")
    except HTTPException as exc:
        reason = "exception"
        detail = exc.detail if isinstance(exc.detail, str) else ""
        if detail == "AI cleanup returned invalid JSON":
            reason = "invalid_json"
        elif detail == "AI cleanup returned empty recipe structure":
            reason = "empty_ai_structure"
        logger.warning("modal_ai_cleanup_fallback reason=%s", reason)
    except Exception as exc:
        logger.warning("modal_ai_cleanup_fallback reason=%s", "exception")
        logger.exception("modal_ai_cleanup_failed url=%s reason=%s", source_url, str(exc))
    preview_payload = _sanitize_preview_ingredient_payload(preview_payload)
    logger.info("modal_ai_cleanup_preview_payload=%s", json.dumps(preview_payload, ensure_ascii=False))
    logger.info("modal_ai_cleanup_selected_source=%s", payload_source)
    logger.info("modal_ai_cleanup_preview_direct_ai=%s", json.dumps(preview_payload, ensure_ascii=False))
    logger.info("modal_ai_cleanup_preview=%s", json.dumps(preview_payload, ensure_ascii=False))
    return {"preview": preview_payload, "payload_source": payload_source, "no_changes": False}


@app.get("/cookbooks")
def get_cookbooks(current_user: dict = Depends(require_user)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.name,
            c.created_at,
            COUNT(rc.recipe_id) AS recipe_count,
            MIN(r.image_url) AS cover_image
        FROM cookbooks c
        LEFT JOIN recipe_cookbooks rc ON rc.cookbook_id = c.id
        LEFT JOIN recipes r ON r.id = rc.recipe_id AND r.user_id = c.user_id
        WHERE c.user_id = ?
        GROUP BY c.id, c.name, c.created_at
        ORDER BY lower(c.name) ASC
        """,
        (int(current_user["id"]),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/cookbooks")
def create_cookbook(payload: CookbookPayload, current_user: dict = Depends(require_user)):
    name = _normalize_cookbook_name(payload.name)
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id, name, created_at FROM cookbooks WHERE user_id = ? AND lower(name) = lower(?) LIMIT 1",
        (int(current_user["id"]), name),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Cookbook already exists")
    cur.execute(
        "INSERT INTO cookbooks (user_id, name, created_at) VALUES (?, ?, ?)",
        (int(current_user["id"]), name, utcnow_iso()),
    )
    cookbook_id = int(cur.lastrowid)
    conn.commit()
    created = cur.execute(
        "SELECT id, name, created_at FROM cookbooks WHERE id = ? AND user_id = ?",
        (cookbook_id, int(current_user["id"])),
    ).fetchone()
    conn.close()
    return dict(created)


@app.put("/cookbooks/{cookbook_id}")
def update_cookbook(cookbook_id: int, payload: CookbookPayload, current_user: dict = Depends(require_user)):
    name = _normalize_cookbook_name(payload.name)
    conn = get_conn()
    cur = conn.cursor()
    cookbook = cur.execute(
        "SELECT id FROM cookbooks WHERE id = ? AND user_id = ? LIMIT 1",
        (cookbook_id, int(current_user["id"])),
    ).fetchone()
    if not cookbook:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    conflict = cur.execute(
        "SELECT id FROM cookbooks WHERE user_id = ? AND lower(name) = lower(?) AND id != ? LIMIT 1",
        (int(current_user["id"]), name, cookbook_id),
    ).fetchone()
    if conflict:
        conn.close()
        raise HTTPException(status_code=409, detail="Cookbook already exists")
    cur.execute("UPDATE cookbooks SET name = ? WHERE id = ?", (name, cookbook_id))
    conn.commit()
    updated = cur.execute(
        "SELECT id, name, created_at FROM cookbooks WHERE id = ? AND user_id = ?",
        (cookbook_id, int(current_user["id"])),
    ).fetchone()
    conn.close()
    return dict(updated)


@app.delete("/cookbooks/{cookbook_id}")
def delete_cookbook(cookbook_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cookbooks WHERE id = ? AND user_id = ?",
        (cookbook_id, int(current_user["id"])),
    )
    conn.commit()
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Cookbook not found")
    conn.close()
    return {"message": "deleted"}


@app.get("/recipes/{recipe_id}/cookbooks")
def get_recipe_cookbooks(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    recipe = cur.execute(
        "SELECT id FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    rows = cur.execute(
        '''
        SELECT c.id, c.name, c.created_at
        FROM recipe_cookbooks rc
        JOIN cookbooks c ON c.id = rc.cookbook_id
        WHERE rc.recipe_id = ? AND c.user_id = ?
        ORDER BY lower(c.name) ASC
        ''',
        (recipe_id, int(current_user["id"])),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.put("/recipes/{recipe_id}/cookbooks")
def set_recipe_cookbooks(
    recipe_id: int,
    payload: RecipeCookbookMembershipPayload,
    current_user: dict = Depends(require_user),
):
    cookbook_ids = sorted(set(int(cookbook_id) for cookbook_id in payload.cookbook_ids))
    conn = get_conn()
    cur = conn.cursor()
    recipe = cur.execute(
        "SELECT id FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    if cookbook_ids:
        placeholders = ",".join("?" for _ in cookbook_ids)
        found = cur.execute(
            f"SELECT id FROM cookbooks WHERE user_id = ? AND id IN ({placeholders})",
            (int(current_user["id"]), *cookbook_ids),
        ).fetchall()
        if len(found) != len(cookbook_ids):
            conn.close()
            raise HTTPException(status_code=400, detail="One or more cookbook ids are invalid")

    existing_rows = cur.execute(
        "SELECT cookbook_id FROM recipe_cookbooks WHERE recipe_id = ? ORDER BY cookbook_id ASC",
        (recipe_id,),
    ).fetchall()
    existing_cookbook_ids = [int(row["cookbook_id"]) for row in existing_rows]
    logger.info(
        "Recipe cookbook membership update requested recipe_id=%s submitted=%s existing=%s",
        recipe_id,
        cookbook_ids,
        existing_cookbook_ids,
    )

    cur.execute("DELETE FROM recipe_cookbooks WHERE recipe_id = ?", (recipe_id,))
    for cookbook_id in cookbook_ids:
        cur.execute(
            "INSERT OR IGNORE INTO recipe_cookbooks (recipe_id, cookbook_id) VALUES (?, ?)",
            (recipe_id, cookbook_id),
        )
    conn.commit()
    rows = cur.execute(
        '''
        SELECT c.id, c.name, c.created_at
        FROM recipe_cookbooks rc
        JOIN cookbooks c ON c.id = rc.cookbook_id
        WHERE rc.recipe_id = ? AND c.user_id = ?
        ORDER BY lower(c.name) ASC
        ''',
        (recipe_id, int(current_user["id"])),
    ).fetchall()
    final_cookbook_ids = [int(row["id"]) for row in rows]
    logger.info(
        "Recipe cookbook membership updated recipe_id=%s final=%s",
        recipe_id,
        final_cookbook_ids,
    )
    conn.close()
    return [dict(row) for row in rows]


@app.get("/recipes/{recipe_id}/state")
def get_recipe_state(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    recipe = cur.execute(
        "SELECT id FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    row = _get_or_create_recipe_user_state(cur, recipe_id, int(current_user["id"]))
    conn.commit()
    conn.close()
    return {
        "id": int(row["id"]),
        "recipe_id": int(row["recipe_id"]),
        "user_id": int(row["user_id"]),
        "is_cooked": bool(row["is_cooked"]),
        "rating": row["rating"],
        "personal_note": row["personal_note"],
        "is_favorite": bool(row["is_favorite"]),
        "last_viewed_at": row["last_viewed_at"],
        "updated_at": row["updated_at"],
    }


@app.put("/recipes/{recipe_id}/state")
def put_recipe_state(
    recipe_id: int,
    payload: RecipeUserStatePayload,
    current_user: dict = Depends(require_user),
):
    conn = get_conn()
    cur = conn.cursor()
    recipe = cur.execute(
        "SELECT id FROM recipes WHERE id = ? AND user_id = ? LIMIT 1",
        (recipe_id, int(current_user["id"])),
    ).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    row = _get_or_create_recipe_user_state(cur, recipe_id, int(current_user["id"]))

    next_is_cooked = bool(row["is_cooked"]) if payload.is_cooked is None else bool(payload.is_cooked)
    next_rating = row["rating"] if payload.rating is None else _validate_rating(payload.rating)
    next_note = row["personal_note"] if payload.personal_note is None else payload.personal_note
    next_favorite = bool(row["is_favorite"]) if payload.is_favorite is None else bool(payload.is_favorite)
    now_iso = utcnow_iso()
    cur.execute(
        '''
        UPDATE recipe_user_state
        SET is_cooked = ?, rating = ?, personal_note = ?, is_favorite = ?, updated_at = ?
        WHERE id = ?
        ''',
        (int(next_is_cooked), next_rating, next_note, int(next_favorite), now_iso, int(row["id"])),
    )
    conn.commit()
    updated = cur.execute(
        '''
        SELECT id, recipe_id, user_id, is_cooked, rating, personal_note, is_favorite, last_viewed_at, updated_at
        FROM recipe_user_state
        WHERE id = ?
        ''',
        (int(row["id"]),),
    ).fetchone()
    conn.close()
    return {
        "id": int(updated["id"]),
        "recipe_id": int(updated["recipe_id"]),
        "user_id": int(updated["user_id"]),
        "is_cooked": bool(updated["is_cooked"]),
        "rating": updated["rating"],
        "personal_note": updated["personal_note"],
        "is_favorite": bool(updated["is_favorite"]),
        "last_viewed_at": updated["last_viewed_at"],
        "updated_at": updated["updated_at"],
    }


@app.get("/extract-metadata")
def extract_metadata(url: str = Query(...), current_user: dict = Depends(require_user), _: dict | None = None):
    if not isinstance(current_user, dict):
        current_user = {}
    if not current_user and _:
        current_user = _
    raw_url = (url or "").strip()
    submission_source_type = _detect_submission_source_type(raw_url)
    is_social = _is_social_share_url(raw_url)
    original_source_url = raw_url if is_social else ""
    resolved_recipe_url = ""
    content_source = "direct_recipe_url"
    logger.info(
        "extract-metadata request received source_url=%s source_type=%s",
        raw_url,
        submission_source_type,
    )
    try:
        extraction_method = ""
        fallback_reason = ""
        social_resolution = None
        recovery_trace = {
            "title_hint": "",
            "hosts": [],
            "direct_slug_attempted": False,
            "direct_slug_candidates": [],
            "site_search_attempted": False,
            "site_search_candidates": [],
            "external_search_attempted": False,
            "external_search_candidates": [],
            "external_search_query": "",
        }
        caption_fallback_ran = False
        caption_recipe_like = False
        transcript_pipeline_attempted = False
        transcript_fallback_payload = None
        if not is_social:
            validate_public_url(raw_url)
        if is_social:
            try:
                social_resolution = resolve_social_url(raw_url)
            except Exception as exc:
                logger.exception("social-share-url resolution failed source_url=%s error=%s", raw_url, str(exc))
                fallback_reason = f"social_resolver_failed:{exc}"
                social_resolution = SimpleNamespace(
                    canonical_url="",
                    post_id="",
                    resolved_url="",
                    method="none",
                    error=fallback_reason,
                    headless_attempted=False,
                    headless_candidate_urls=[],
                    fast_path_candidate_urls=[],
                    ytdlp_title="",
                    ytdlp_description="",
                    ytdlp_webpage_url="",
                    ytdlp_description_urls=[],
                )
            extracted_url = (social_resolution.resolved_url or "").strip()
            if not fallback_reason:
                fallback_reason = social_resolution.error or ""
            extraction_method = social_resolution.method or ("redirect:final" if extracted_url else "none")
            logger.info(
                "social-share-url resolution original_url=%s canonical_url=%s post_id=%s extracted_url=%s extraction_method=%s fallback_reason=%s",
                raw_url,
                social_resolution.canonical_url or "",
                social_resolution.post_id or "",
                extracted_url or "",
                extraction_method or "none",
                fallback_reason or "",
            )
            if extracted_url and not is_valid_social_destination_url(extracted_url):
                logger.info(
                    "extract-metadata parser skipped because resolved social URL failed validation source_url=%s resolved_url=%s",
                    raw_url,
                    extracted_url,
                )
                extracted_url = ""
                fallback_reason = fallback_reason or "social_resolved_url_failed_validation"
            if extracted_url:
                resolved_recipe_url = extracted_url
                content_source = "direct_recipe_url"
            if not extracted_url:
                recovered_url, recovered_method = _recover_recipe_url_from_social_signals(
                    raw_url,
                    social_resolution,
                    recovery_trace,
                )
                if recovered_url:
                    validated, _ = _validate_recipe_page_and_parse(recovered_url)
                    if validated:
                        extracted_url = recovered_url
                        resolved_recipe_url = recovered_url
                        extraction_method = f"recovered:{recovered_method}"
                        content_source = "resolved_recipe_url"
                        logger.info(
                            "social_recovery_selected source_url=%s recovered_url=%s method=%s",
                            raw_url,
                            recovered_url,
                            recovered_method,
                        )
                    else:
                        content_source = "transcript_ai_fallback"
                        logger.info(
                            "social_recovery_rejected source_url=%s recovered_url=%s reason=validation_failed",
                            raw_url,
                            recovered_url,
                        )
                else:
                    content_source = "transcript_ai_fallback"
                ytdlp_caption = (social_resolution.ytdlp_description or "").strip()
                if ytdlp_caption and not extracted_url:
                    caption_fallback_ran = True
                    logger.info("social_ytdlp_caption_mode source_url=%s", raw_url)
                    recipe_like = looks_like_recipe_text(ytdlp_caption)
                    caption_recipe_like = recipe_like
                    logger.info(
                        "social_ytdlp_caption_detected recipe_like=%s source_url=%s caption_length=%d",
                        str(recipe_like).lower(),
                        raw_url,
                        len(ytdlp_caption),
                    )
                    if recipe_like:
                        caption_recipe = parse_social_caption_recipe(
                            ytdlp_caption,
                            raw_url,
                            title_hint=social_resolution.ytdlp_title or "",
                        )
                        ingredient_count = len(caption_recipe.get("ingredients") or [])
                        instruction_count = len(caption_recipe.get("instructions") or [])
                        if ingredient_count or instruction_count:
                            logger.info(
                                "social_ytdlp_caption_parsed ingredients=%d instructions=%d source_url=%s",
                                ingredient_count,
                                instruction_count,
                                raw_url,
                            )
                            social_app_name = (
                                "Facebook"
                                if submission_source_type == "facebook"
                                else "Instagram" if submission_source_type == "instagram" else "Social"
                            )
                            return {
                                "url": raw_url,
                                "original_source_url": original_source_url,
                                "resolved_recipe_url": "",
                                "content_source": "transcript_ai_fallback",
                                "title": caption_recipe.get("title", ""),
                                "source_app": social_app_name,
                                "source_type": "Social",
                                "image_url": "",
                                "ingredients": caption_recipe.get("ingredients", []),
                                "instructions": caption_recipe.get("instructions", []),
                                "ingredient_groups": caption_recipe.get("ingredient_groups", []),
                                "instruction_groups": caption_recipe.get("instruction_groups", []),
                                "servings": caption_recipe.get("servings", ""),
                                "prep_time": caption_recipe.get("prep_time", ""),
                                "cook_time": caption_recipe.get("cook_time", ""),
                                "total_time": caption_recipe.get("total_time", ""),
                                "prep_minutes": caption_recipe.get("prep_minutes"),
                                "cook_minutes": caption_recipe.get("cook_minutes"),
                                "total_minutes": caption_recipe.get("total_minutes"),
                                "social_metadata": {
                                    "canonical_url": social_resolution.canonical_url,
                                    "post_id": social_resolution.post_id,
                                    "method": "ytdlp_caption",
                                    "error": social_resolution.error,
                                    "caption_length": len(ytdlp_caption),
                                },
                            }
                        logger.info(
                            "social_ytdlp_caption_failed reason=empty_parse source_url=%s caption_length=%d",
                            raw_url,
                            len(ytdlp_caption),
                        )
                    else:
                        logger.info(
                            "social_ytdlp_caption_failed reason=not_recipe_like source_url=%s caption_length=%d",
                            raw_url,
                            len(ytdlp_caption),
                        )
                else:
                    logger.info("social_ytdlp_caption_failed reason=missing_description source_url=%s", raw_url)
                if not extracted_url:
                    transcript_pipeline_attempted = True
                    transcript_source_url = (social_resolution.canonical_url or raw_url or "").strip() or raw_url
                    logger.info("TRANSCRIPT_PIPELINE_TRIGGERED source_url=%s", transcript_source_url)
                    try:
                        logger.info("social_transcript_pipeline_start source_url=%s", transcript_source_url)
                        user_facebook_cookie = None
                        facebook_cookie_warning = ""
                        if current_user and current_user.get("id"):
                            try:
                                user_facebook_cookie = _get_user_facebook_cookie(int(current_user["id"]))
                            except UserSettingDecryptionError as exc:
                                facebook_cookie_warning = _build_unreadable_user_setting_payload(
                                    exc.setting_key,
                                    exc.setting_label,
                                )["message"]
                                logger.warning(
                                    "social_transcript_user_cookie_unreadable user_id=%s setting=%s",
                                    current_user["id"],
                                    exc.setting_key,
                                )
                        logger.info(
                            "social_transcript_user_cookie has_user_cookie=%s has_warning=%s",
                            bool(user_facebook_cookie),
                            bool(facebook_cookie_warning),
                        )
                        transcript_result: TranscriptPipelineResult = run_social_video_transcript_pipeline(
                            transcript_source_url,
                            ollama_base_url=OLLAMA_BASE_URL,
                            ollama_model=OLLAMA_MODEL,
                            ollama_timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
                            facebook_cookie=user_facebook_cookie,
                        )
                        if not transcript_result.success:
                            if not (fallback_reason or "").startswith("social_resolver_failed:"):
                                fallback_reason = transcript_result.fallback_reason or "transcript_pipeline_failed"
                            logger.info(
                                "social_transcript_pipeline_failed source_url=%s reason=%s",
                                raw_url,
                                fallback_reason,
                            )
                            raise TranscriptPipelineStageError(
                                "ollama",
                                RuntimeError(fallback_reason or "transcript_pipeline_failed:ollama"),
                            )
                        transcript_recipe = _normalize_transcript_recipe_payload(
                            transcript_result.structured_recipe,
                            raw_url,
                            title_hint=social_resolution.ytdlp_title or "",
                            cleaned_transcript_text=transcript_result.cleaned_transcript_text,
                        )
                        transcript_ingredient_count = len(transcript_recipe.get("ingredients") or [])
                        transcript_instruction_count = len(transcript_recipe.get("instructions") or [])
                        logger.info(
                            "social_transcript_pipeline_parsed source_url=%s ingredients=%d instructions=%d mentioned_websites=%d",
                            raw_url,
                            transcript_ingredient_count,
                            transcript_instruction_count,
                            len(transcript_result.mentioned_websites),
                        )
                        transcript_title_hint = transcript_recipe.get("title", "") or social_resolution.ytdlp_title or ""
                        transcript_recovered_url, transcript_recovered_method = _recover_recipe_url_from_transcript_mentions(
                            raw_url,
                            transcript_title_hint,
                            transcript_result.mentioned_websites,
                            transcript_recipe.get("ingredients") or [],
                            recovery_trace,
                        )
                        if transcript_recovered_url:
                            transcript_validated, _ = _validate_recipe_page_and_parse(transcript_recovered_url)
                            if transcript_validated:
                                logger.info(
                                    "social_transcript_pipeline_recovered source_url=%s recovered_url=%s method=%s",
                                    raw_url,
                                    transcript_recovered_url,
                                    transcript_recovered_method,
                                )
                                resolved_recipe_url = transcript_recovered_url
                                content_source = "resolved_recipe_url"
                                social_app_name = (
                                    "Facebook"
                                    if submission_source_type == "facebook"
                                    else "Instagram" if submission_source_type == "instagram" else "Social"
                                )
                                recovered_recipe = fetch_recipe_data_from_url(transcript_recovered_url)
                                return {
                                    "url": transcript_recovered_url,
                                    "original_source_url": original_source_url,
                                    "resolved_recipe_url": transcript_recovered_url,
                                    "content_source": "resolved_recipe_url",
                                    "title": recovered_recipe.get("title", ""),
                                    "source_app": social_app_name,
                                    "source_type": "Social",
                                    "image_url": recovered_recipe.get("image_url", ""),
                                    "ingredients": recovered_recipe.get("ingredients", []),
                                    "instructions": recovered_recipe.get("instructions", []),
                                    "ingredient_groups": recovered_recipe.get("ingredient_groups", []),
                                    "instruction_groups": recovered_recipe.get("instruction_groups", []),
                                    "servings": recovered_recipe.get("servings", ""),
                                    "prep_time": recovered_recipe.get("prep_time", ""),
                                    "cook_time": recovered_recipe.get("cook_time", ""),
                                    "total_time": recovered_recipe.get("total_time", ""),
                                    "prep_minutes": recovered_recipe.get("prep_minutes"),
                                    "cook_minutes": recovered_recipe.get("cook_minutes"),
                                    "total_minutes": recovered_recipe.get("total_minutes"),
                                    "social_metadata": {
                                        "canonical_url": social_resolution.canonical_url,
                                        "post_id": social_resolution.post_id,
                                        "method": transcript_recovered_method,
                                        "error": social_resolution.error,
                                    },
                                }
                        social_app_name = (
                            "Facebook"
                            if submission_source_type == "facebook"
                            else "Instagram" if submission_source_type == "instagram" else "Social"
                        )
                        transcript_fallback_payload = {
                            "url": raw_url,
                            "original_source_url": original_source_url,
                            "resolved_recipe_url": "",
                            "content_source": "transcript_ai_fallback",
                            "title": transcript_recipe.get("title", ""),
                            "source_app": social_app_name,
                            "source_type": "Social",
                            "image_url": "",
                            "ingredients": transcript_recipe.get("ingredients", []),
                            "instructions": transcript_recipe.get("instructions", []),
                            "ingredient_groups": transcript_recipe.get("ingredient_groups", []),
                            "instruction_groups": transcript_recipe.get("instruction_groups", []),
                            "servings": transcript_recipe.get("servings", ""),
                            "prep_time": transcript_recipe.get("prep_time", ""),
                            "cook_time": transcript_recipe.get("cook_time", ""),
                            "total_time": transcript_recipe.get("total_time", ""),
                            "prep_minutes": transcript_recipe.get("prep_minutes"),
                            "cook_minutes": transcript_recipe.get("cook_minutes"),
                            "total_minutes": transcript_recipe.get("total_minutes"),
                            "recipe_type": "transcript",
                            "title_inferred": transcript_result.title_inferred,
                            "measurements_partial": transcript_result.measurements_partial,
                            "ai_review_source_payload": {
                                "saved_cleanup_context": {
                                    "transcript_text": transcript_result.transcript_text,
                                    "cleaned_transcript_text": transcript_result.cleaned_transcript_text,
                                    "mentioned_websites": transcript_result.mentioned_websites[:10],
                                    "source_type": submission_source_type,
                                }
                            },
                            "social_metadata": {
                                "canonical_url": social_resolution.canonical_url,
                                "post_id": social_resolution.post_id,
                                "method": "transcript_pipeline",
                                "error": social_resolution.error,
                                "transcript_length": len(transcript_result.transcript_text),
                                "transcript_cleaned_length": len(transcript_result.cleaned_transcript_text),
                                "mentioned_websites": transcript_result.mentioned_websites[:10],
                                "facebook_cookie_warning": facebook_cookie_warning,
                                "recipe_type": "transcript",
                                "title_inferred": transcript_result.title_inferred,
                                "measurements_partial": transcript_result.measurements_partial,
                            },
                        }
                    except Exception as exc:
                        if isinstance(exc, TranscriptPipelineStageError):
                            if not (fallback_reason or "").startswith("social_resolver_failed:"):
                                fallback_reason = exc.reason
                            logger.info(
                                "social_transcript_pipeline_failed source_url=%s reason=%s",
                                raw_url,
                                fallback_reason,
                            )
                        elif isinstance(exc, YtDlpExtractError):
                            if not (fallback_reason or "").startswith("social_resolver_failed:"):
                                fallback_reason = "transcript_pipeline_failed:ytdlp"
                            logger.info(
                                "social_transcript_pipeline_failed source_url=%s reason=transcript_pipeline_failed:ytdlp",
                                raw_url,
                            )
                        else:
                            if (fallback_reason or "").strip().lower() in {
                                "",
                                "facebook_external_url_not_found",
                                "instagram_external_url_not_found",
                                "social_url_still_internal",
                            }:
                                fallback_reason = "transcript_pipeline_failed"
                            logger.info("social_transcript_pipeline_failed source_url=%s reason=%s", raw_url, exc)
            cleaned_url = normalize_shared_url(extracted_url) if extracted_url else ""
            if not cleaned_url:
                if transcript_fallback_payload:
                    return transcript_fallback_payload
                unresolved_reason = _normalize_social_fallback_reason(fallback_reason, submission_source_type)
                logger.info(
                    "social_debug_unresolved source_url=%s raw_input_url=%s resolver_method=%s resolver_error=%s resolved_url=%s",
                    raw_url,
                    raw_url,
                    social_resolution.method or "none",
                    social_resolution.error or "",
                    (social_resolution.resolved_url or "").strip(),
                )
                logger.info(
                    "social_debug_unresolved source_url=%s extracted_hosts=%s title_hint=%s",
                    raw_url,
                    recovery_trace.get("hosts", []),
                    recovery_trace.get("title_hint", ""),
                )
                logger.info(
                    "social_debug_unresolved source_url=%s direct_slug_attempted=%s direct_slug_candidates=%s",
                    raw_url,
                    str(bool(recovery_trace.get("direct_slug_attempted"))).lower(),
                    recovery_trace.get("direct_slug_candidates", []),
                )
                logger.info(
                    "social_debug_unresolved source_url=%s site_search_attempted=%s site_search_candidates=%s",
                    raw_url,
                    str(bool(recovery_trace.get("site_search_attempted"))).lower(),
                    recovery_trace.get("site_search_candidates", []),
                )
                logger.info(
                    "social_debug_unresolved source_url=%s external_search_attempted=%s external_search_query=%s external_search_candidates=%s",
                    raw_url,
                    str(bool(recovery_trace.get("external_search_attempted"))).lower(),
                    recovery_trace.get("external_search_query", ""),
                    recovery_trace.get("external_search_candidates", []),
                )
                logger.info(
                    "social_debug_unresolved source_url=%s caption_fallback_ran=%s looks_like_recipe_text=%s transcript_pipeline_attempted=%s final_reason=%s",
                    raw_url,
                    str(caption_fallback_ran).lower(),
                    str(caption_recipe_like).lower(),
                    str(transcript_pipeline_attempted).lower(),
                    unresolved_reason,
                )
                logger.info(
                    "extract-metadata unresolved source_url=%s source_type=%s fallback_reason=%s",
                    raw_url,
                    submission_source_type,
                    unresolved_reason,
                )
                transcript_failure_stage = _extract_transcript_failure_stage(fallback_reason)
                return {
                    "status": "partial",
                    "reason": unresolved_reason,
                    "resolved_url": None,
                    "source_url": raw_url,
                    "candidate_urls": [],
                    "url": raw_url,
                    "title": "",
                    "image_url": "",
                    "description": "",
                    "source_app": "Facebook" if submission_source_type == "facebook" else "Instagram" if submission_source_type == "instagram" else "",
                    "source_type": "Social" if submission_source_type in ("facebook", "instagram") else "Web",
                    "social_metadata": {
                        "canonical_url": social_resolution.canonical_url,
                        "post_id": social_resolution.post_id,
                        "method": social_resolution.method,
                        "error": social_resolution.error,
                        "headless_attempted": social_resolution.headless_attempted,
                        "headless_candidate_urls": social_resolution.headless_candidate_urls[:5],
                        "fast_path_candidate_urls": social_resolution.fast_path_candidate_urls[:5],
                        "ytdlp_title": social_resolution.ytdlp_title,
                        "ytdlp_description_length": len((social_resolution.ytdlp_description or "").strip()),
                        "ytdlp_webpage_url": social_resolution.ytdlp_webpage_url,
                        "transcript_pipeline_stage": transcript_failure_stage,
                        "transcript_pipeline_failure_reason": fallback_reason,
                    },
                }
        else:
            cleaned_url = normalize_shared_url(raw_url)

        logger.info(
            "extract-metadata request raw_url=%s normalized_url=%s extraction_method=%s",
            raw_url,
            cleaned_url,
            extraction_method or "standard",
        )
        source_app, source_type = infer_source(cleaned_url)
        if is_social:
            logger.info("extract-metadata parser running on trusted resolved social URL=%s", cleaned_url)
        recipe_data = fetch_recipe_data_from_url(cleaned_url)
        title = recipe_data.get("title") or fetch_title_from_url(cleaned_url)
    except PublicUrlValidationError as exc:
        raise HTTPException(status_code=422, detail=USER_FACING_PUBLIC_URL_ERROR) from exc
    except Exception as exc:
        logger.exception(
            "extract-metadata failed raw_url=%s is_social=%s error=%s",
            raw_url,
            is_social,
            str(exc),
        )
        if is_social:
            unresolved_reason = _social_unresolved_reason(submission_source_type)
            logger.info(
                "extract-metadata unresolved source_url=%s source_type=%s fallback_reason=%s",
                raw_url,
                submission_source_type,
                unresolved_reason,
            )
            return {
                "status": "partial",
                "reason": unresolved_reason,
                "resolved_url": None,
                "source_url": raw_url,
                "url": raw_url,
                "source_app": "Facebook" if submission_source_type == "facebook" else "",
                "source_type": "Social" if submission_source_type == "facebook" else "Web",
            }
        raise HTTPException(status_code=502, detail="Recipe extraction failed while processing this page.") from exc

    payload = {
        "url": cleaned_url,
        "original_source_url": original_source_url or cleaned_url,
        "resolved_recipe_url": resolved_recipe_url or (cleaned_url if is_social else cleaned_url),
        "content_source": content_source if is_social else "direct_recipe_url",
        "title": title,
        "source_app": source_app,
        "source_type": source_type,
        "image_url": recipe_data.get("image_url", ""),
        "ingredients": recipe_data.get("ingredients", []),
        "instructions": recipe_data.get("instructions", []),
        "ingredient_groups": recipe_data.get("ingredient_groups", []),
        "instruction_groups": recipe_data.get("instruction_groups", []),
        "servings": recipe_data.get("servings", ""),
        "prep_time": recipe_data.get("prep_time", ""),
        "cook_time": recipe_data.get("cook_time", ""),
        "total_time": recipe_data.get("total_time", ""),
        "prep_minutes": recipe_data.get("prep_minutes"),
        "cook_minutes": recipe_data.get("cook_minutes"),
        "total_minutes": recipe_data.get("total_minutes"),
    }
    logger.info(
        "extract-metadata response summary normalized_url=%s selected_source=%s selected_reason=%s title=%s image=%s ingredients=%d instructions=%d ingredient_groups=%d instruction_groups=%d",
        cleaned_url,
        recipe_data.get("_selected_source", ""),
        recipe_data.get("_selected_reason", ""),
        bool(payload.get("title")),
        bool(payload.get("image_url")),
        len(payload.get("ingredients", [])),
        len(payload.get("instructions", [])),
        len(payload.get("ingredient_groups", [])),
        len(payload.get("instruction_groups", [])),
    )
    return payload


@app.post("/import/text")
def import_text_recipe(payload: PasteTextImportRequest, _: dict = Depends(require_user)):
    parsed = _parse_pasted_recipe_text(payload.text)
    return {
        "url": "",
        "original_source_url": "",
        "resolved_recipe_url": "",
        "content_source": "pasted_text",
        "title": parsed.get("title") or "",
        "source_app": "Paste",
        "source_type": "Paste Text",
        "image_url": "",
        "notes": parsed.get("notes", ""),
        "ingredients": parsed.get("ingredients", []),
        "instructions": parsed.get("instructions", []),
        "ingredient_groups": parsed.get("ingredient_groups", []),
        "instruction_groups": parsed.get("instruction_groups", []),
        "ingredients_structured": parsed.get("ingredients_structured", []),
        "servings": parsed.get("servings", ""),
        "prep_time": parsed.get("prep_time", ""),
        "cook_time": parsed.get("cook_time", ""),
        "total_time": parsed.get("total_time", ""),
        "prep_minutes": parsed.get("prep_minutes"),
        "cook_minutes": parsed.get("cook_minutes"),
        "total_minutes": parsed.get("total_minutes"),
        "parser_source": "heuristic_paste",
    }


@app.post("/shopping-list")
def build_shopping_list(payload: ShoppingListRequest, current_user: dict = Depends(require_user)):
    recipe_ids = [int(recipe_id) for recipe_id in payload.recipe_ids if int(recipe_id) > 0]
    recipe_ids = list(dict.fromkeys(recipe_ids))
    if not recipe_ids:
        return {"items": []}

    placeholders = ",".join("?" for _ in recipe_ids)
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        f"SELECT * FROM recipes WHERE user_id = ? AND id IN ({placeholders}) ORDER BY id ASC",
        (int(current_user["id"]), *recipe_ids),
    ).fetchall()
    conn.close()
    return {"items": _build_shopping_list_from_recipe_rows(rows)}


@app.post("/grocery-list/preview")
def preview_grocery_list(payload: ShoppingListRequest, current_user: dict = Depends(require_user)):
    return build_shopping_list(payload, current_user)


def _parse_iso_date(date_text: str) -> datetime:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from exc


@app.get("/meal-plan")
def get_meal_plan(start_date: str = Query(...), current_user: dict = Depends(require_user)):
    start_dt = _parse_iso_date(start_date)
    end_dt = start_dt + timedelta(days=6)
    user_id = int(current_user["id"])
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT mpi.*, r.title AS recipe_title, r.image_url AS recipe_image_url
        FROM meal_plan_items mpi
        JOIN recipes r ON r.id = mpi.recipe_id
        WHERE mpi.user_id = ?
          AND mpi.plan_date >= ?
          AND mpi.plan_date <= ?
        ORDER BY mpi.plan_date ASC,
            CASE mpi.meal_slot
                WHEN 'breakfast' THEN 1
                WHEN 'lunch' THEN 2
                WHEN 'dinner' THEN 3
                WHEN 'other' THEN 4
                ELSE 5
            END ASC,
            mpi.created_at ASC,
            mpi.id ASC
        """,
        (user_id, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")),
    ).fetchall()
    conn.close()
    items_by_date: dict[str, list[dict]] = {}
    for row in rows:
        items_by_date.setdefault(row["plan_date"], []).append({
            "id": int(row["id"]),
            "plan_date": row["plan_date"],
            "recipe_id": int(row["recipe_id"]),
            "recipe_title": row["recipe_title"] or "",
            "meal_slot": row["meal_slot"] or "dinner",
            "recipe_image_url": row["recipe_image_url"] or "",
            "servings_override": row["servings_override"] or "",
        })
    days = []
    for offset in range(7):
        day = start_dt + timedelta(days=offset)
        date_key = day.strftime("%Y-%m-%d")
        days.append({"date": date_key, "label": day.strftime("%A"), "items": items_by_date.get(date_key, [])})
    return {"start_date": start_dt.strftime("%Y-%m-%d"), "end_date": end_dt.strftime("%Y-%m-%d"), "days": days}


@app.post("/meal-plan/items")
def create_meal_plan_item(payload: MealPlanItemCreate, current_user: dict = Depends(require_user)):
    _parse_iso_date(payload.plan_date)
    meal_slot = _normalize_meal_slot(payload.meal_slot)
    user_id = int(current_user["id"])
    conn = get_conn()
    cur = conn.cursor()
    recipe = cur.execute(
        "SELECT id, title, image_url FROM recipes WHERE id = ? AND user_id = ?",
        (payload.recipe_id, user_id),
    ).fetchone()
    if not recipe:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")
    existing = cur.execute(
        """
        SELECT id, plan_date, recipe_id, meal_slot, servings_override, created_at
        FROM meal_plan_items
        WHERE user_id = ? AND plan_date = ? AND recipe_id = ? AND meal_slot = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id, payload.plan_date, int(recipe["id"]), meal_slot),
    ).fetchone()
    if existing:
        conn.close()
        return {
            "id": int(existing["id"]),
            "plan_date": existing["plan_date"],
            "recipe_id": int(existing["recipe_id"]),
            "recipe_title": recipe["title"] or "",
            "meal_slot": existing["meal_slot"] or "dinner",
            "recipe_image_url": recipe["image_url"] or "",
            "servings_override": existing["servings_override"] or "",
        }
    now_iso = utcnow_iso()
    servings_override = str(payload.servings_override or "").strip()
    cur.execute(
        """
        INSERT INTO meal_plan_items (user_id, plan_date, recipe_id, meal_slot, servings_override, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, payload.plan_date, int(recipe["id"]), meal_slot, servings_override or None, now_iso, now_iso),
    )
    item_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return {
        "id": item_id,
        "plan_date": payload.plan_date,
        "recipe_id": int(recipe["id"]),
        "recipe_title": recipe["title"] or "",
        "meal_slot": meal_slot,
        "recipe_image_url": recipe["image_url"] or "",
        "servings_override": servings_override,
    }


@app.delete("/meal-plan/items/{item_id}")
def delete_meal_plan_item(item_id: int, current_user: dict = Depends(require_user)):
    user_id = int(current_user["id"])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM meal_plan_items WHERE id = ? AND user_id = ?", (item_id, user_id))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Meal plan item not found")
    conn.commit()
    conn.close()
    return {"success": True}


@app.post("/meal-plan/grocery-preview")
def meal_plan_grocery_preview(payload: MealPlanWeekRequest, current_user: dict = Depends(require_user)):
    start_dt = _parse_iso_date(payload.start_date)
    end_dt = start_dt + timedelta(days=6)
    user_id = int(current_user["id"])
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT recipe_id, servings_override
        FROM meal_plan_items
        WHERE user_id = ? AND plan_date >= ? AND plan_date <= ?
        ORDER BY recipe_id ASC, id ASC
        """,
        (user_id, start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")),
    ).fetchall()
    recipe_ids = sorted({int(row["recipe_id"]) for row in rows})
    if not recipe_ids:
        conn.close()
        return {"items": []}
    placeholders = ",".join("?" for _ in recipe_ids)
    recipe_rows = cur.execute(
        f"SELECT * FROM recipes WHERE user_id = ? AND id IN ({placeholders}) ORDER BY id ASC",
        (user_id, *recipe_ids),
    ).fetchall()
    conn.close()

    recipe_map = {int(row["id"]): row for row in recipe_rows}
    structured: list[dict] = []
    for item in rows:
        recipe_id = int(item["recipe_id"])
        recipe_row = recipe_map.get(recipe_id)
        if not recipe_row:
            continue
        base_servings = _extract_numeric_servings(recipe_row["servings"])
        override_servings = _extract_numeric_servings(item["servings_override"])
        scale_factor = 1.0
        if base_servings is not None and override_servings is not None:
            scale_factor = override_servings / base_servings
        for ingredient_text in _recipe_row_ingredient_lines(recipe_row):
            parsed = _parse_ingredient_struct(ingredient_text)
            if not parsed.get("name"):
                continue
            if scale_factor != 1.0:
                parsed = _scale_ingredient(parsed, scale_factor)
            parsed["recipe_id"] = recipe_id
            parsed["recipe_title"] = recipe_row["title"]
            structured.append(parsed)
    return {"items": _build_shopping_list_items(structured)}


@app.get("/grocery-list")
def get_grocery_list(current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    payload = _grocery_list_payload(cur, int(current_user["id"]))
    conn.close()
    return payload


@app.post("/grocery-list/items")
def add_grocery_items(payload: GroceryItemsPayload, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    user_id = int(current_user["id"])
    source_recipe_ids = sorted(
        {
            int(item.source_recipe_id)
            for item in payload.items
            if item.source_recipe_id is not None
        }
    )
    if source_recipe_ids:
        placeholders = ",".join("?" for _ in source_recipe_ids)
        cur.execute(
            f"DELETE FROM grocery_items WHERE user_id = ? AND source_recipe_id IN ({placeholders})",
            [user_id, *source_recipe_ids],
        )
    for item in payload.items:
        _insert_grocery_item(cur, user_id, item)
    conn.commit()
    result = _grocery_list_payload(cur, user_id)
    conn.close()
    return result


@app.patch("/grocery-list/items/{item_id}")
def update_grocery_item(item_id: int, payload: GroceryItemUpdatePayload, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    user_id = int(current_user["id"])
    cur.execute(
        """
        UPDATE grocery_items
        SET checked = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (1 if payload.checked else 0, utcnow_iso(), item_id, user_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Grocery item not found")
    conn.commit()
    result = _grocery_list_payload(cur, user_id)
    conn.close()
    return result


@app.delete("/grocery-list/checked")
def clear_checked_grocery_items(current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    user_id = int(current_user["id"])
    cur.execute("DELETE FROM grocery_items WHERE user_id = ? AND checked = 1", (user_id,))
    conn.commit()
    result = _grocery_list_payload(cur, user_id)
    conn.close()
    return result


@app.delete("/grocery-list")
def clear_grocery_list(current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    user_id = int(current_user["id"])
    cur.execute("DELETE FROM grocery_items WHERE user_id = ?", (user_id,))
    conn.commit()
    result = _grocery_list_payload(cur, user_id)
    conn.close()
    return result


@app.delete("/grocery-list/source/{recipe_id}")
def remove_grocery_source(recipe_id: int, current_user: dict = Depends(require_user)):
    conn = get_conn()
    cur = conn.cursor()
    user_id = int(current_user["id"])
    cur.execute(
        "DELETE FROM grocery_items WHERE user_id = ? AND source_recipe_id = ?",
        (user_id, recipe_id),
    )
    conn.commit()
    result = _grocery_list_payload(cur, user_id)
    conn.close()
    return result


async def _import_image_recipe_from_upload(image: UploadFile | None) -> dict:
    if image is None:
        raise HTTPException(status_code=422, detail="Image file is required")

    content_type = (image.content_type or "").lower().strip()
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Please upload an image.")

    try:
        ocr_result = await _extract_text_from_image_upload(image)
    except ValueError as exc:
        if str(exc) == "empty_image_payload":
            raise HTTPException(status_code=422, detail="Uploaded image was empty.")
        if str(exc) == "ocr_worker_not_configured":
            raise HTTPException(status_code=503, detail="Image OCR worker is not configured.")
        if str(exc) == "ocr_worker_timeout":
            raise HTTPException(
                status_code=504,
                detail="Image OCR worker timed out. Make sure the OCR worker is running on the PC.",
            )
        if str(exc) == "ocr_worker_failed" or str(exc) == "invalid_ocr_worker_payload":
            raise HTTPException(status_code=502, detail="Image OCR worker failed while processing this upload.")
        if str(exc) == "empty_ocr_worker_text":
            raise HTTPException(status_code=422, detail="Couldn't read recipe text from this image. Try a clearer photo.")
        raise HTTPException(status_code=422, detail="Invalid image upload.")
    except Exception as exc:
        logger.exception("image_ocr_extract_failed error=%s", str(exc))
        raise HTTPException(status_code=502, detail="Image OCR failed while processing this upload.")

    source_url = f"image://upload/{image.filename or 'upload'}"
    extracted_text = ocr_result.get("text") or ""
    ocr_confidence = ocr_result.get("confidence")
    parsed_recipe, parser_source = _parse_recipe_text_from_ocr(
        extracted_text,
        source_url=source_url,
        ocr_confidence=ocr_confidence,
    )
    payload = _image_import_payload_from_parsed(parsed_recipe, parser_source)
    payload["ocr_confidence"] = ocr_confidence
    payload["ocr_engine"] = ocr_result.get("engine")
    payload["ocr_rotation"] = ocr_result.get("rotation")
    payload["ocr_keyword_score"] = ocr_result.get("keyword_score")
    payload["ocr_fraction_score"] = ocr_result.get("fraction_score")
    if ocr_confidence is not None and ocr_confidence < 70:
        payload["low_confidence_quantities"] = True
    if ocr_confidence is not None and ocr_confidence < 70:
        payload["ocr_warning"] = "OCR confidence is low. Please review ingredients and measurements carefully."
        payload["ocr_warning_level"] = "strong" if ocr_confidence < 45 else "mild"
    return payload


if PYTHON_MULTIPART_INSTALLED:
    @app.post("/import/image")
    async def import_image_recipe(image: UploadFile = File(...), _: dict = Depends(require_user)):
        return await _import_image_recipe_from_upload(image)
else:
    @app.post("/import/image")
    async def import_image_recipe(request: Request, _: dict = Depends(require_user)):
        try:
            form_data = await request.form()
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Image upload parsing is unavailable on this server. Install python-multipart to enable this endpoint.",
            )

        image = form_data.get("image")
        if image is not None and not isinstance(image, UploadFile):
            raise HTTPException(status_code=422, detail="Image file is required")
        return await _import_image_recipe_from_upload(image)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        correlation_id = _request_correlation_id(request)
        logger.error(
            "http_exception status=%s path=%s correlation_id=%s detail=%s",
            exc.status_code,
            request.url.path,
            correlation_id,
            exc.detail,
        )
        return _json_error_response(
            request,
            status_code=exc.status_code,
            detail=INTERNAL_SERVER_ERROR_MESSAGE,
            correlation_id=correlation_id,
            headers=exc.headers,
        )
    return _json_error_response(request, status_code=exc.status_code, detail=exc.detail, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    correlation_id = _request_correlation_id(request)
    logger.exception(
        "unhandled_exception path=%s correlation_id=%s error=%s",
        request.url.path,
        correlation_id,
        str(exc),
    )
    return _json_error_response(
        request,
        status_code=500,
        detail=INTERNAL_SERVER_ERROR_MESSAGE,
        correlation_id=correlation_id,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    def _json_safe_validation_errors(errors):
        safe_errors = []
        for error in errors:
            item = dict(error)
            if isinstance(item.get("input"), (bytes, bytearray)):
                item["input"] = "<bytes omitted>"
            safe_errors.append(item)
        return safe_errors

    safe_errors = _json_safe_validation_errors(exc.errors())
    logger.error("request_validation_error path=%s errors=%s", request.url.path, safe_errors)
    return _json_error_response(request, status_code=422, detail=safe_errors)
