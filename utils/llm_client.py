"""
llm_client.py — Thin wrapper over Groq or HuggingFace Inference API.

Incluye reintento automático con backoff exponencial para errores de rate limit
(tanto requests-per-minute como tokens-per-minute).

Usage:
    from llm_client import chat
    response = chat([{"role": "user", "content": "Hola"}])
"""

import re
import time
import logging

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_BACKOFF_BASE = 15  # segundos mínimos de espera en rate limit


def chat(messages: list, max_tokens: int = 1500) -> str:
    """Envía una solicitud al LLM configurado y devuelve el texto de respuesta."""
    if config.LLM_PROVIDER == "groq":
        return _groq_chat(messages, max_tokens)
    return _hf_chat(messages, max_tokens)


def _groq_chat(messages: list, max_tokens: int) -> str:
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Instala groq: pip install groq")

    if not config.GROQ_API_KEY or config.GROQ_API_KEY == "gsk_tu_api_key_aqui":
        raise ValueError(
            "GROQ_API_KEY no configurada.\n"
            "  1. Regístrate gratis en https://console.groq.com\n"
            "  2. Crea una API Key\n"
            "  3. Cópiala en tu archivo .env"
        )

    client = Groq(api_key=config.GROQ_API_KEY)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
            )
            return response.choices[0].message.content

        except Exception as e:
            err_str = str(e)
            # Detectar rate limit por código 429 o texto del mensaje
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower()
            if is_rate_limit and attempt < _MAX_RETRIES:
                wait = _parse_retry_after(err_str, default=_BACKOFF_BASE * attempt)
                print(f"  [Rate limit] Esperando {wait:.0f}s antes de reintentar (intento {attempt}/{_MAX_RETRIES})...")
                logger.warning(f"Groq rate limit — esperando {wait}s (intento {attempt})")
                time.sleep(wait)
            else:
                raise


def _parse_retry_after(error_msg: str, default: float) -> float:
    """Extrae el tiempo de espera sugerido del mensaje de error de Groq."""
    match = re.search(r"try again in ([\d.]+)s", error_msg, re.IGNORECASE)
    if match:
        # Añadir 3s de margen al tiempo sugerido
        return float(match.group(1)) + 3.0
    return default


def _hf_chat(messages: list, max_tokens: int) -> str:
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        raise ImportError("Instala huggingface_hub: pip install huggingface_hub")

    if not config.HF_TOKEN or config.HF_TOKEN == "hf_tu_token_aqui":
        raise ValueError(
            "HF_TOKEN no configurada.\n"
            "  1. Regístrate gratis en https://huggingface.co/join\n"
            "  2. Ve a https://huggingface.co/settings/tokens\n"
            "  3. Crea un token y cópialo en tu archivo .env"
        )

    client = InferenceClient(token=config.HF_TOKEN)
    response = client.chat_completion(
        model=config.HF_MODEL,
        messages=messages,
        max_new_tokens=max_tokens,
    )
    return response.choices[0].message.content
