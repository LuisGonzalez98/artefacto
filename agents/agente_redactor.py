"""
agente_redactor.py — Narrativa institucional Secciones 3-9 del informe DG-VRA/CRT.

Usa formato de marcadores de sección (===S3===, ===S8===, etc.) en lugar de JSON
para evitar problemas de escape con modelos pequeños. word_generator lo parsea con regex.
"""

import logging
import re

import config
from utils import llm_client
from utils.context import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el sistema SGIRA (Sistema Generador de Informes de Análisis Regulatorio) de la
Dirección General de Vigilancia de Regulación Asimétrica (DG-VRA) de la Comisión Reguladora de
Telecomunicaciones (CRT) de México.

IDENTIDAD INSTITUCIONAL:
- Institución: COMISIÓN REGULADORA DE TELECOMUNICACIONES (CRT)
- Dependencia: Dirección General de Vigilancia de Regulación Asimétrica (DG-VRA)
- Tono: impersonal institucional — "esta Dirección General", "el análisis revela", "se observa"
- Condicional epistémico OBLIGATORIO: "podría indicar", "sugiere", "es consistente con"

REGLAS ABSOLUTAS:
1. Prosa técnico-jurídica institucional continua. CERO viñetas, CERO listas, CERO guiones.
2. Sin markdown: sin #, sin *, sin **, sin _, sin corchetes.
3. NO menciones tablas, gráficas, inteligencia artificial ni modelo de lenguaje.
4. Separación estricta: los datos son INDICADORES POTENCIALES; la infracción requiere investigación.
5. Responde ÚNICAMENTE con los marcadores de sección y el texto indicado. NADA más."""


def _parse_sections(raw: str) -> dict:
    """Extrae secciones del formato ===KEY=== seguido de texto plano."""
    result = {}
    parts = re.split(r'===([A-Z0-9_]+)===', raw)
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            key = parts[i].lower()
            result[key] = parts[i + 1].strip()
    return result


def run(question: str, datos_content: str = "", regulatorio_content: str = "",
        metadata: dict | None = None) -> AgentResult:
    logger.info("AgenteRedactor: generando secciones 3-9...")
    meta = metadata or {}
    print(f"  Inputs: datos={len(datos_content):,} chars | regulatorio={len(regulatorio_content):,} chars")
    modelo = config.GROQ_MODEL if config.LLM_PROVIDER == "groq" else config.HF_MODEL
    print(f"  Enviando al LLM ({modelo})...")
    try:
        content = _write_sections(question, datos_content, regulatorio_content, meta)
        return AgentResult(agent_name="AgenteRedactor", content=content, succeeded=True)
    except Exception as e:
        logger.error(f"AgenteRedactor error: {e}", exc_info=True)
        print(f"  [ERROR] {e}")
        return AgentResult(agent_name="AgenteRedactor",
                           content=f"ERROR:{e}", succeeded=False, error=str(e))


def _fmt(meta: dict) -> str:
    ret60   = meta.get("retornos_60", 0)
    tasa    = meta.get("tasa", 0.0)
    hhi     = meta.get("hhi", 0.0)
    hhi_cat = meta.get("hhi_categoria", "")
    periodo = meta.get("periodo", "2023-2024")
    reg     = meta.get("regresion", {})
    tend    = reg.get("tendencia", "estable")
    slope   = reg.get("pendiente", 0)
    r2      = reg.get("r_cuadrado", 0)
    pval    = reg.get("p_valor", 1.0)
    proy    = meta.get("proyeccion", [])
    proy_str = "; ".join(
        f"{p['mes']}: {p['proyeccion']:,} indicadores (IC {p['ic_inf']}-{p['ic_sup']})"
        for p in proy
    )
    top_op = meta.get("ind_por_op", [])
    top_str = "; ".join(
        f"{r.get('operador','?')}: {r.get('indicadores',0):,} casos ({r.get('pct_total',0):.1f}%)"
        for r in top_op[:3]
    )
    return (
        f"Periodo: {periodo}. Indicadores potenciales (retornos AEP en <=60 dias): {ret60:,}. "
        f"Tasa sobre salidas del AEP: {tasa:.2f}%. HHI: {hhi:.0f} ({hhi_cat}). "
        f"Principales operadores intermedios: {top_str}. "
        f"Tendencia estadistica: {tend} (pendiente={slope}, R2={r2}, p-valor={pval}). "
        f"Proyeccion 3 meses: {proy_str}."
    )


def _call(prompt: str, max_tokens: int) -> str:
    return llm_client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
    )


def _write_sections(question: str, datos_content: str,
                    regulatorio_content: str, meta: dict) -> str:
    datos = _fmt(meta)

    # ── Llamada 1 / 2: Secciones 3-7 ────────────────────────────────
    prompt_a = f"""Redacta las secciones 3, 4, 5, 6 y 7 del informe DG-VRA/CRT sobre la Medida 83.
Cada seccion: 80-100 palabras de prosa institucional continua.

DATOS CLAVE: {datos}
CONTEXTO: {datos_content[:400] if datos_content else ''}

Responde EXACTAMENTE con este formato (escribe el texto de cada seccion despues del marcador):

===S3===
[Objeto y Metodologia: que se mide, por que son indicadores indirectos, limitaciones metodologicas, necesidad de validacion humana antes de producir efectos regulatorios]

===S4===
[Calidad de Datos: completitud de la base de datos, niveles de nulos, implicaciones para la robustez del analisis]

===S5===
[Concentracion de Mercado: interpretacion del HHI calculado, clasificacion del mercado, relevancia de la Medida 83 dado el nivel de concentracion]

===S5_HHI===
[Parrafo adicional HHI: distribucion de portaciones por operador receptor, justificacion de la medida asimetrica]

===S6===
[Parrafo introductorio de la seccion de Portabilidad: alcance del analisis cuantitativo de indicadores potenciales]

===S6_1===
[Universo Regulatorio: total TIPO_6, portaciones con AEP como donador, pares ida-vuelta identificados, retornos en 60 dias o menos]

===S6_2===
[Indicadores por Operador Receptor: distribucion por operador intermedio, dias promedio de retorno, implicaciones regulatorias del patron observado]

===S6_3===
[Distribucion por Rango de Dias: patron de retornos en los distintos rangos temporales, que sugiere la concentracion en rangos cortos]

===S6_4===
[Tendencia Mensual: evolucion mensual de indicadores, periodos de mayor concentracion, tendencia general del fenomeno]

===S6_5===
[Muestra de Casos con Mayor Inmediatez: interpretacion de los retornos mas rapidos y su relevancia regulatoria]

===S7===
[Analisis Estadistico: interpretacion de la regresion lineal, pendiente, R2, p-valor, significado sobre la evolucion del fenomeno]

===S7_1===
[Proyeccion 3 Meses: implicaciones para la planificacion regulatoria, incertidumbre del modelo proyectivo]
"""

    print("  [Llamada 1/2] Secciones 3-7...")
    raw_a = _call(prompt_a, max_tokens=1400)
    secs_a = _parse_sections(raw_a)
    print(f"  Llamada 1: {len(secs_a)} secciones — {list(secs_a.keys())}")

    # ── Llamada 2 / 2: Secciones 8-9 ────────────────────────────────
    prompt_b = f"""Redacta las secciones 8 y 9 del informe DG-VRA/CRT sobre la Medida 83.

DATOS CLAVE: {datos}
MARCO REGULATORIO: {regulatorio_content[:350] if regulatorio_content else ''}

Responde EXACTAMENTE con este formato (escribe el texto de cada seccion despues del marcador):

===S8===
[Analisis de Impacto Regulatorio AIR segun metodologia OCDE: problema regulatorio identificado, objetivos de politica publica de la Medida 83, evaluacion de impactos con los datos del analisis, balance costo-beneficio de la medida vigente, indicadores de efectividad observados, conclusion del AIR. 150-200 palabras.]

===S9===
[Parrafo introductorio de Conclusiones y Propuesta de Resolucion: sintesis del analisis completo y advertencia expresa de caracter preliminar. 80-100 palabras.]

===S9_1===
[Escenario A MODIFICAR LA MEDIDA: argumentos a favor y en contra de modificar el periodo de proteccion o el alcance. Que modificaciones serian procedentes dado el patron observado. 100-130 palabras.]

===S9_2===
[Escenario B MANTENER LA MEDIDA: argumentos para mantener la Medida 83 sin cambios. Que elementos del analisis estadistico y regulatorio sustentan la continuidad del regimen vigente. 100-130 palabras.]

===S9_3===
[Escenario C ELIMINAR LA MEDIDA: argumentos hipoteticos y riesgos concretos de eliminar la proteccion. Por que los indicadores potenciales observados no sustentan esta opcion en la etapa actual del mercado. 100-130 palabras.]

===S9_4===
[Recomendacion Institucional DG-VRA: recomendacion con advertencia expresa de que los hallazgos son preliminares, necesidad de validacion humana por personal tecnico-juridico antes de producir efectos regulatorios, y propuesta concreta de siguiente paso procesal ante el Pleno. 100-130 palabras.]
"""

    print("  [Llamada 2/2] Secciones 8-9 (AIR + conclusiones)...")
    raw_b = _call(prompt_b, max_tokens=1400)
    secs_b = _parse_sections(raw_b)
    print(f"  Llamada 2: {len(secs_b)} secciones — {list(secs_b.keys())}")

    merged = {**secs_a, **secs_b}
    print(f"  Total secciones generadas: {len(merged)} — {list(merged.keys())}")
    # Serializar como texto de marcadores para word_generator
    parts = []
    for key, val in merged.items():
        parts.append(f"==={key.upper()}===\n{val}")
    return "\n\n".join(parts)
