"""
config.py — Fuente única de configuración para proyecto_83.

Diseñado para ser portable entre macOS y Windows:
- Usa pathlib.Path para todas las rutas (nunca strings con barras hardcodeadas)
- Carga variables de entorno desde .env en la raíz del proyecto
- Provee valores por defecto razonables para desarrollo local

Todos los demás módulos importan de aquí; nunca usen os.environ directamente.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Raíz del proyecto: directorio que contiene este archivo.
# Path(__file__).resolve().parent funciona igual en Mac y Windows,
# independientemente del directorio de trabajo actual (cwd).
BASE_DIR: Path = Path(__file__).resolve().parent

# Cargar .env desde la raíz del proyecto
load_dotenv(BASE_DIR / ".env")


# ── Ollama ───────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


# ── PostgreSQL ───────────────────────────────────────────────
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "portabilidad")
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_SCHEMA: str = os.getenv("POSTGRES_SCHEMA", "public")


def get_postgres_uri() -> str:
    """URI de conexión SQLAlchemy para PostgreSQL + psycopg2."""
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )


# ── Rutas ────────────────────────────────────────────────────
def _resolve_dir(env_key: str, default: Path) -> Path:
    """
    Devuelve la ruta configurada en la variable de entorno env_key,
    o el valor por defecto si la variable está vacía o no existe.
    Siempre retorna un objeto Path.
    """
    raw = os.getenv(env_key, "").strip()
    return Path(raw) if raw else default


CHROMA_BASE_DIR: Path = _resolve_dir("CHROMA_BASE_DIR", BASE_DIR / "data" / "chroma_db")
DATA_DOCS_DIR: Path = _resolve_dir("DATA_DOCS_DIR", BASE_DIR / "data" / "docs")
OUTPUT_DIR: Path = _resolve_dir("OUTPUT_DIR", BASE_DIR / "output")

# Sub-directorios de ChromaDB (uno por agente para evitar colisiones de colección)
CHROMA_DATOS_DIR: Path = CHROMA_BASE_DIR / "datos"
CHROMA_REGULATORIO_DIR: Path = CHROMA_BASE_DIR / "regulatorio"
CHROMA_REDACTOR_DIR: Path = CHROMA_BASE_DIR / "redactor"

# Sub-directorios de documentos fuente para RAG
DOCS_SCHEMA_DIR: Path = DATA_DOCS_DIR / "schema_docs"
DOCS_REGULATORIO_DIR: Path = DATA_DOCS_DIR / "regulatorio"
DOCS_PLANTILLAS_DIR: Path = DATA_DOCS_DIR / "plantillas"


# ── Parámetros de RAG ────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))


# ── LLM-as-a-Judge ──────────────────────────────────────────
JUDGE_MIN_SCORE: int = int(os.getenv("JUDGE_MIN_SCORE", "7"))


# ── Colores para documento Word (RGB como tuplas) ────────────
# Se usan como RGBColor(*COLOR_X) en python-docx
COLOR_DATOS: tuple[int, int, int] = (0, 70, 127)       # Azul  — Agente Datos
COLOR_REGULATORIO: tuple[int, int, int] = (0, 112, 0)  # Verde — Agente Regulatorio
COLOR_REDACTOR: tuple[int, int, int] = (192, 0, 0)     # Rojo  — Agente Redactor
COLOR_JUDGE: tuple[int, int, int] = (128, 0, 128)      # Morado — LLM Judge
COLOR_GRAY: tuple[int, int, int] = (128, 128, 128)     # Gris  — Metadatos / errores
