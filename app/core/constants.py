"""Application-wide constants."""

from enum import StrEnum


class Role(StrEnum):
    """User role hierarchy for RBAC."""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Permission(StrEnum):
    """Granular permissions for RBAC."""

    # User management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Document management
    DOCUMENT_READ = "document:read"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DELETE = "document:delete"

    # Knowledge base management
    KB_READ = "knowledge_base:read"
    KB_CREATE = "knowledge_base:create"
    KB_UPDATE = "knowledge_base:update"
    KB_DELETE = "knowledge_base:delete"

    # RAG operations
    RAG_QUERY = "rag:query"
    RAG_EMBED = "rag:embed"
    RAG_REINDEX = "rag:reindex"

    # Agent management
    AGENT_EXECUTE = "agent:execute"
    AGENT_CONFIGURE = "agent:configure"

    # System administration
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_AUDIT = "system:audit"

    # Evaluation
    EVAL_RUN = "evaluation:run"
    EVAL_VIEW = "evaluation:view"


# Role ↔ Permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.USER_READ,
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_DELETE,
        Permission.KB_READ,
        Permission.KB_CREATE,
        Permission.KB_UPDATE,
        Permission.KB_DELETE,
        Permission.RAG_QUERY,
        Permission.RAG_EMBED,
        Permission.RAG_REINDEX,
        Permission.AGENT_EXECUTE,
        Permission.AGENT_CONFIGURE,
        Permission.SYSTEM_MONITOR,
        Permission.SYSTEM_CONFIG,
        Permission.SYSTEM_AUDIT,
        Permission.EVAL_RUN,
        Permission.EVAL_VIEW,
    },
    Role.USER: {
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_UPLOAD,
        Permission.KB_READ,
        Permission.KB_CREATE,
        Permission.RAG_QUERY,
        Permission.AGENT_EXECUTE,
        Permission.EVAL_VIEW,
    },
    Role.VIEWER: {
        Permission.DOCUMENT_READ,
        Permission.KB_READ,
        Permission.RAG_QUERY,
        Permission.EVAL_VIEW,
    },
    Role.AUDITOR: {
        Permission.SYSTEM_AUDIT,
        Permission.SYSTEM_MONITOR,
        Permission.EVAL_VIEW,
    },
}


# ── Pagination ──────────────────────────────
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# ── Rate Limiting ───────────────────────────
RATE_LIMIT_WINDOW_SECONDS: int = 60

# ── File Uploads ─────────────────────────────
ALLOWED_DOCUMENT_TYPES: set[str] = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# ── Redis Key Prefixes ──────────────────────
REDIS_KEY_PREFIX = "rag:"
REDIS_RATE_LIMIT_PREFIX = f"{REDIS_KEY_PREFIX}ratelimit:"
REDIS_SESSION_PREFIX = f"{REDIS_KEY_PREFIX}session:"
REDIS_CACHE_PREFIX = f"{REDIS_KEY_PREFIX}cache:"
REDIS_QUEUE_PREFIX = f"{REDIS_KEY_PREFIX}queue:"
