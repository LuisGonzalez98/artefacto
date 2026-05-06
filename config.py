import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# LLM provider: "groq" (recommended) or "huggingface"
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")

# Groq
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL:   str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# HuggingFace
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_MODEL: str = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

# Database
SQLITE_DB_PATH: Path = Path(os.getenv("SQLITE_DB_PATH", "data/portabilidad.db"))
if not SQLITE_DB_PATH.is_absolute():
    SQLITE_DB_PATH = BASE_DIR / SQLITE_DB_PATH

# Output
_out_raw = os.getenv("OUTPUT_DIR", "output").strip()
OUTPUT_DIR: Path = Path(_out_raw) if _out_raw else BASE_DIR / "output"
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = BASE_DIR / OUTPUT_DIR

DOCS_DIR: Path = OUTPUT_DIR / "documentos"
LOGS_DIR: Path = OUTPUT_DIR / "logs"

# Word template (opcional)
_tpl_raw = os.getenv("WORD_TEMPLATE", "").strip()
WORD_TEMPLATE: Path | None = None
if _tpl_raw:
    _tpl_path = Path(_tpl_raw) if Path(_tpl_raw).is_absolute() else BASE_DIR / _tpl_raw
    WORD_TEMPLATE = _tpl_path if _tpl_path.exists() else None
if WORD_TEMPLATE is None:
    _default_tpl = BASE_DIR / "data" / "templates" / "plantilla.docx"
    if _default_tpl.exists():
        WORD_TEMPLATE = _default_tpl

# Judge threshold (1-10)
JUDGE_MIN_SCORE: float = float(os.getenv("JUDGE_MIN_SCORE", "7"))

# Institución (DG-VRA / CRT)
INSTITUCION   = "COMISIÓN REGULADORA DE TELECOMUNICACIONES"
DEPENDENCIA   = "Dirección General de Vigilancia de Regulación Asimétrica (DG-VRA)"
DOMICILIO     = "Insurgentes Sur 1143, Col. Nochebuena, Benito Juárez, CDMX, C.P. 03720"
URL_INST      = "www.gob.mx/crt"
MEDIDA_NOMBRE = "Medida Octogésima Tercera (Medida 83)"

# Colores para Word
COLOR_PRIMARIO    = (0,  51, 102)   # azul oscuro institucional
COLOR_SECUNDARIO  = (102, 102, 102) # gris
COLOR_ACENTO      = (192, 0, 0)     # rojo para advertencias
COLOR_VERDE       = (0, 112, 0)
COLOR_MORADO      = (128, 0, 128)
COLOR_GRAY        = (128, 128, 128)
COLOR_DATOS       = COLOR_PRIMARIO
COLOR_REGULATORIO = COLOR_VERDE
COLOR_REDACTOR    = COLOR_ACENTO
COLOR_JUDGE       = COLOR_MORADO

# Hex para matplotlib
COLOR_PRIMARIO_HEX   = "#003366"
COLOR_SECUNDARIO_HEX = "#666666"
