import os
from urllib.parse import quote_plus
from . import logger
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# env = os.getenv("ENV", 'llamacpp-remote')  # Default to 'llamacpp-remote' if ENV is not set
env = os.getenv("ENV", 'azure')  # Default to 'llamacpp-remote' if ENV is not set

env_file = f".env.{env}"

env_path = os.path.join(BASE_DIR, env_file)

logger.info("Configuration loaded for environment: %r", env)
logger.info("Loading configuration from %r", env_path)

# Load a base .env first (shared, provider-independent secrets such as the database
# credentials and SerpAPI key live here once). The provider-specific .env.<env> file
# is loaded afterwards and overrides any overlapping keys. Both files are gitignored,
# so secrets stay local and are never pushed or overwritten on pull.
base_env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(base_env_path):
    logger.info("Base environment file found: %r", base_env_path)
    load_dotenv(base_env_path, override=False)

if os.path.exists(env_path):
    logger.info("Environment file found: %r", env_path)
    load_dotenv(env_path, override=True)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
BASE_URL  = os.getenv("BASE_URL", "http://localhost:11434")
MODEL = os.getenv("MODEL", "llama3.2:3b")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama")  # Options: 'localai', 'ollama'

logger.info("Configuration - MODEL: %r, EMBEDDING_MODEL: %r, BASE_URL: %r, MODEL_PROVIDER: %r", 
            MODEL, EMBEDDING_MODEL, BASE_URL, MODEL_PROVIDER)

QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "device_kb"


TEMPERATURE = 0
TOP_P = 0

MEMORY_TOP_K = 5
RAG_TOP_K = 5

RAG_INDEX_PATH = "data/rag_index"
MEMORY_BASE_PATH = "data/session_memory"

MYSQL_URI = os.getenv("MYSQL_URI")
if not MYSQL_URI:
    _mysql_user = os.getenv("MYSQL_USER", "root")
    _mysql_password = os.getenv("MYSQL_PASSWORD", "")
    _mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    _mysql_port = os.getenv("MYSQL_PORT", "3306")
    _mysql_db = os.getenv("MYSQL_DB", "inventory")
    MYSQL_URI = (
        f"mysql+pymysql://{_mysql_user}:{quote_plus(_mysql_password)}"
        f"@{_mysql_host}:{_mysql_port}/{_mysql_db}"
    )

# ---------- CONFIG intent ----------
# Mandatory approval gate before any delivery/execution (CONFIG_INTENT_PLAN.md §7).
CONFIG_REQUIRE_APPROVAL = os.getenv("CONFIG_REQUIRE_APPROVAL", "true").strip().lower() in {"1", "true", "yes"}
# Polish follow-up questions (COLLECT_FIELDS / DISAMBIGUATE) through the LLM so they
# read naturally. Falls back to the deterministic wording on any failure. §6, decision C.
CONFIG_LLM_PHRASING = os.getenv("CONFIG_LLM_PHRASING", "true").strip().lower() in {"1", "true", "yes"}
# LLM pre-flight: once all mandatory fields are collected, validate them against the
# target playbook (presence, plausibility, safety) before the approval gate. Fail-open.
CONFIG_LLM_PREFLIGHT = os.getenv("CONFIG_LLM_PREFLIGHT", "true").strip().lower() in {"1", "true", "yes"}
# Collect fields via a dynamic, LLM-built form (structured submit = no per-turn LLM).
# When off, falls back to conversational text questions. The `answer` text fallback is
# always present, so non-form clients keep working either way.
CONFIG_USE_FORMS = os.getenv("CONFIG_USE_FORMS", "true").strip().lower() in {"1", "true", "yes"}

CONVERSTIONAL_MEMORY_PROMPT = """
You are an enterprise network device migration assistant.

Use ONLY the information provided.

Conversation Memory:
{memory_context}

Internal Knowledge Base:
{rag_context}

User Question:
{query}

If information is missing, clearly state it.
Do not hallucinate.
"""
