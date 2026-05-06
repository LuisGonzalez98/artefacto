"""
agente_regulatorio.py — Secciones 1 y 2 del informe DG-VRA/CRT.

Usa formato de marcadores ===S1=== / ===S2=== (texto plano, sin JSON).
"""

import logging
import re

import config
from utils import llm_client
from utils.context import AgentResult
from rag.retriever import SimpleRetriever

logger = logging.getLogger(__name__)

_retriever = SimpleRetriever(config.BASE_DIR / "data" / "docs" / "regulatorio")

_MARCO = """
MEDIDA OCTOGÉSIMA TERCERA (MEDIDA 83) — MARCO REGULATORIO

DISPOSICIÓN CENTRAL
El Agente Económico Preponderante (Telcel/América Móvil) tiene prohibido contactar con fines
comerciales o de retención a los suscriptores que hayan portado su número fuera de sus redes
durante los primeros 60 días naturales posteriores a la portabilidad. Los indicadores potenciales
se identifican mediante pares ida-vuelta: el mismo número porta DESDE el AEP y regresa AL AEP
en 60 días o menos, patrón consistente con posible reactivación comercial durante el período de
protección.

FUNDAMENTO LEGAL
- Ley Federal de Telecomunicaciones y Radiodifusión (LFTR), artículos de portabilidad numérica
- Resoluciones del IFT sobre medidas asimétricas al Agente Económico Preponderante
- Reglas de Portabilidad Numérica vigentes

RÉGIMEN SANCIONATORIO
- Multas de hasta el 10% de los ingresos anuales del AEP (arts. 302-304 LFTR)
- Medidas correctivas del Pleno del IFT
- Escalamiento a COFECE si se acredita afectación a la competencia
"""

SYSTEM_PROMPT = f"""Eres el area juridica de la Direccion General de Vigilancia de Regulacion Asimetrica
(DG-VRA) de la Comision Reguladora de Telecomunicaciones (CRT) de Mexico.

MARCO NORMATIVO:
{_MARCO}

REGLAS:
- Prosa juridica formal continua. Cero vinietas, cero listas, cero markdown.
- Tono: "esta Direccion General", "el presente analisis", "la normativa establece".
- Condicional epistemico: "podria indicar", "sugiere", "es consistente con".
- NUNCA afirmar infraccion probada.
- Responde UNICAMENTE con los marcadores de seccion y el texto. NADA mas."""


def _parse_sections(raw: str) -> dict:
    result = {}
    parts = re.split(r'===([A-Z0-9_]+)===', raw)
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            key = parts[i].lower()
            result[key] = parts[i + 1].strip()
    return result


def run(question: str, datos_content: str = "") -> AgentResult:
    logger.info("AgenteRegulatorio: generando secciones 1 y 2...")
    if datos_content:
        print(f"  Contexto del AgenteDatos: {len(datos_content):,} caracteres")
    try:
        content = _analyze_with_llm(question, datos_content)
        return AgentResult(agent_name="AgenteRegulatorio", content=content, succeeded=True)
    except Exception as e:
        logger.error(f"AgenteRegulatorio error: {e}", exc_info=True)
        print(f"  [ERROR] {e}")
        return AgentResult(agent_name="AgenteRegulatorio",
                           content=f"ERROR:{e}", succeeded=False, error=str(e))


def _analyze_with_llm(question: str, datos_content: str) -> str:
    print(f"  Buscando documentos en RAG...")
    rag_context = _retriever.retrieve(question, k=4)
    rag_section = ""
    if rag_context:
        n = rag_context.count("---") + 1
        print(f"  RAG: {n} fragmentos recuperados")
        rag_section = f"\nFUENTES RAG:\n{rag_context[:1200]}\n"
    else:
        print(f"  RAG: sin documentos — usando marco normativo embebido")

    datos_ref = f"\nCIFRAS CLAVE:\n{datos_content[:300]}\n" if datos_content else ""
    modelo = config.GROQ_MODEL if config.LLM_PROVIDER == "groq" else config.HF_MODEL
    print(f"  Enviando al LLM ({modelo})...")

    prompt = f"""Redacta las Secciones 1 y 2 del informe de analisis DG-VRA/CRT sobre la Medida 83.
Cada seccion: 130-180 palabras de prosa juridica institucional continua.

PREGUNTA: {question}
{datos_ref}{rag_section}

Responde EXACTAMENTE con este formato (escribe el texto despues de cada marcador):

===S1===
[Seccion 1 ANTECEDENTES Y MARCO JURIDICO: origen normativo de la Medida 83, su finalidad, contexto de preponderancia del AEP en el mercado de telecomunicaciones de Mexico, y limitaciones de la informacion disponible para el analisis. Primera persona institucional del IFT/CRT.]

===S2===
[Seccion 2 FACULTADES DE LA DIRECCION GENERAL: fundamento reglamentario que habilita a la DG-VRA para analizar y fiscalizar el cumplimiento de medidas asimetricas. Referencia al marco legal aplicable y competencias de la Direccion General.]
"""

    raw = llm_client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=600,
    )
    print(f"  Respuesta recibida ({len(raw):,} chars)")
    parsed = _parse_sections(raw)
    print(f"  Secciones parseadas: {list(parsed.keys())}")

    parts = []
    for key, val in parsed.items():
        parts.append(f"==={key.upper()}===\n{val}")
    return "\n\n".join(parts)
