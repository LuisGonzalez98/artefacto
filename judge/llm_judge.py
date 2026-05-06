"""
judge/llm_judge.py — Evaluador LLM-as-a-Judge del pipeline (texto MORADO).

Evalúa la calidad del informe completo en 5 dimensiones (1-10 cada una):
  1. Completitud — ¿Se respondió la pregunta de forma íntegra?
  2. Precisión de datos — ¿Las cifras son coherentes y sin contradicciones?
  3. Precisión regulatoria — ¿Las referencias a la Medida 83 son correctas?
  4. Coherencia — ¿Los tres agentes producen una narrativa integrada?
  5. Calidad de redacción — ¿El texto es apropiado para un informe regulatorio?

Temperatura 0: scoring determinista y reproducible.
Parsing robusto con regex para manejar texto que el LLM añada antes/después del JSON.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import config
from utils import llm_client

logger = logging.getLogger(__name__)

_JUDGE_TEMPLATE = """Eres un evaluador experto en análisis regulatorio de telecomunicaciones en México.

Evalúa la calidad del siguiente informe sobre cumplimiento de la Medida 83 del IFT.

=== ANÁLISIS DE DATOS (AgenteDatos) ===
{datos}

=== MARCO REGULATORIO (AgenteRegulatorio) ===
{regulatorio}

=== INFORME EJECUTIVO (AgenteRedactor) ===
{redactor}

=== PREGUNTA ORIGINAL ===
{question}

Evalúa en 5 dimensiones (puntaje entero 1-10 cada una):
  completitud          — ¿Se respondió la pregunta de forma completa?
  precision_datos      — ¿Las cifras son coherentes y sin contradicciones?
  precision_regulatoria — ¿Las referencias a la Medida 83 son correctas?
  coherencia           — ¿Los tres agentes producen una narrativa integrada?
  calidad_redaccion    — ¿El texto es apropiado para un informe regulatorio oficial?

Puntaje mínimo para aprobar: {min_score}/10 (promedio de las 5 dimensiones)

Responde ÚNICAMENTE con este JSON exacto (sin ningún texto antes ni después):
{{
  "scores": {{
    "completitud": <entero 1-10>,
    "precision_datos": <entero 1-10>,
    "precision_regulatoria": <entero 1-10>,
    "coherencia": <entero 1-10>,
    "calidad_redaccion": <entero 1-10>
  }},
  "score_total": <float, promedio de los 5 puntajes>,
  "aprobado": <true si score_total >= {min_score}, false en caso contrario>,
  "fortalezas": ["<fortaleza 1>", "<fortaleza 2>"],
  "sugerencias": ["<sugerencia de mejora 1>", "<sugerencia de mejora 2>"],
  "resumen": "<2-3 oraciones de evaluación general del informe>"
}}"""


@dataclass
class JudgeResult:
    scores: dict = field(default_factory=dict)
    score_total: float = 0.0
    aprobado: bool = False
    fortalezas: list = field(default_factory=list)
    sugerencias: list = field(default_factory=list)
    resumen: str = ""
    parse_error: bool = False

    def to_display_text(self) -> str:
        status = "APROBADO" if self.aprobado else "REQUIERE REVISIÓN"
        labels = {
            "completitud": "Completitud",
            "precision_datos": "Precisión de datos",
            "precision_regulatoria": "Precisión regulatoria",
            "coherencia": "Coherencia entre agentes",
            "calidad_redaccion": "Calidad de redacción",
        }
        lines = [
            f"Puntuación Total: {self.score_total:.1f}/10 — {status}",
            "",
            f"Evaluación: {self.resumen}",
            "",
            "Puntajes por dimensión:",
        ]
        for key, label in labels.items():
            lines.append(f"  • {label}: {self.scores.get(key, 'N/A')}/10")
        if self.fortalezas:
            lines += ["", "Fortalezas:"] + [f"  + {f}" for f in self.fortalezas]
        if self.sugerencias:
            lines += ["", "Sugerencias de mejora:"] + [f"  → {s}" for s in self.sugerencias]
        return "\n".join(lines)


def evaluate(ctx) -> JudgeResult:
    """
    Evalúa el RunContext completo. Nunca lanza excepción al caller.

    Args:
        ctx: RunContext con resultados de los tres agentes.

    Returns:
        JudgeResult con puntajes y evaluación narrativa.
    """
    logger.info("LLMJudge: evaluando calidad del informe...")

    datos = ctx.datos_result.content if ctx.datos_result else "[No ejecutado]"
    regulatorio = ctx.regulatorio_result.content if ctx.regulatorio_result else "[No ejecutado]"
    redactor = ctx.redactor_result.content if ctx.redactor_result else "[No ejecutado]"

    dimensiones = ["completitud", "precision_datos", "precision_regulatoria", "coherencia", "calidad_redaccion"]
    print(f"  Dimensiones a evaluar ({len(dimensiones)}):")
    for d in dimensiones:
        print(f"    - {d}")

    total_chars = len(datos) + len(regulatorio) + len(redactor)
    print(f"  Texto total del pipeline a evaluar: {total_chars:,} caracteres (truncado a 2,800 para el judge)")
    modelo = config.GROQ_MODEL if config.LLM_PROVIDER == "groq" else config.HF_MODEL
    print(f"  Enviando al LLM ({modelo}) con temperatura 0 (scoring deterministico)...")

    prompt = _JUDGE_TEMPLATE.format(
        datos=datos[:1000],
        regulatorio=regulatorio[:800],
        redactor=redactor[:1000],
        question=ctx.question,
        min_score=config.JUDGE_MIN_SCORE,
    )

    try:
        raw = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
        )
    except Exception as e:
        logger.error(f"LLMJudge error al invocar LLM: {e}")
        print(f"  [ERROR] {e}")
        return JudgeResult(
            resumen=f"Error al ejecutar el evaluador: {e}",
            sugerencias=["Verificar configuración del proveedor LLM en .env"],
            parse_error=True,
        )

    print(f"  Respuesta recibida — parseando JSON de evaluacion...")
    result = _parse(raw)
    if result.parse_error:
        print(f"  [WARN] No se pudo parsear el JSON — evaluacion parcial")
    else:
        print(f"  Puntaje total calculado: {result.score_total:.1f}/10")
        print(f"  Umbral minimo de aprobacion: {config.JUDGE_MIN_SCORE}/10")
    return result


def _parse(raw: str) -> JudgeResult:
    """Extrae el JSON de la respuesta del LLM con regex (maneja texto antes/después)."""
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        logger.warning("LLMJudge: no se encontró JSON en la respuesta del LLM.")
        return JudgeResult(
            resumen="No se pudo parsear la evaluación automática.",
            sugerencias=["Revisar el informe manualmente."],
            parse_error=True,
        )
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"LLMJudge: JSON inválido — {e}")
        return JudgeResult(
            resumen="JSON inválido en la respuesta del evaluador.",
            sugerencias=["Revisar el informe manualmente."],
            parse_error=True,
        )

    scores = data.get("scores", {})
    calculated = sum(scores.values()) / len(scores) if scores else 0.0
    total = round(float(data.get("score_total", calculated)), 2)

    return JudgeResult(
        scores=scores,
        score_total=total,
        aprobado=bool(data.get("aprobado", total >= config.JUDGE_MIN_SCORE)),
        fortalezas=data.get("fortalezas", []),
        sugerencias=data.get("sugerencias", []),
        resumen=data.get("resumen", ""),
        parse_error=False,
    )
