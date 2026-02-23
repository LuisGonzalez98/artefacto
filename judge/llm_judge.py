"""
llm_judge.py — Evaluador LLM-as-a-Judge del pipeline.

Evalúa la calidad del output combinado de los tres agentes usando
el mismo modelo LLM (llama3.1 via Ollama), sin herramientas ni RAG.

El juez evalúa cinco dimensiones:
1. Completitud: ¿Se respondió la pregunta original de manera completa?
2. Precisión de datos: ¿Las cifras son coherentes internamente?
3. Precisión regulatoria: ¿Las referencias a la Medida 83 son correctas?
4. Coherencia: ¿Los tres agentes producen una narrativa sin contradicciones?
5. Calidad de redacción: ¿El texto es apropiado para un informe regulatorio?

Estrategia de extracción JSON robusta:
- Los LLMs locales frecuentemente agregan texto antes/después del JSON
- Se usa re.search(r'\{.*\}', raw, re.DOTALL) para extraer solo el bloque JSON
- Si el parsing falla, se retorna un JudgeResult de fallback (nunca crashea)

Temperatura 0.0: el scoring debe ser determinista y reproducible.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

import config

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """Eres un evaluador experto en análisis regulatorio de telecomunicaciones en México, con especialización en portabilidad numérica móvil y normativa del IFT.

Tu tarea es evaluar la calidad de un informe generado por un sistema multi-agente sobre el cumplimiento de la Medida 83.

=== ANÁLISIS DE DATOS (Agente Datos) ===
{datos_content}

=== CONTEXTO REGULATORIO (Agente Regulatorio) ===
{regulatorio_content}

=== REDACCIÓN FINAL (Agente Redactor) ===
{redactor_content}

=== PREGUNTA ORIGINAL ===
{question}

Evalúa el informe completo en las siguientes dimensiones, asignando un puntaje del 1 al 10:

- COMPLETITUD (1-10): ¿La respuesta aborda todos los aspectos de la pregunta original?
- PRECISION_DATOS (1-10): ¿Las cifras y datos son coherentes internamente y sin contradicciones?
- PRECISION_REGULATORIA (1-10): ¿Las referencias a la Medida 83 y el marco normativo son correctas y suficientes?
- COHERENCIA (1-10): ¿Los tres agentes producen una narrativa integrada y sin contradicciones entre sí?
- CALIDAD_REDACCION (1-10): ¿El texto es claro, formal y apropiado para un informe regulatorio oficial?

Puntaje mínimo para aprobar: {min_score}/10 (promedio de las 5 dimensiones)

Responde ÚNICAMENTE con el siguiente JSON válido, sin texto antes ni después:
{{
  "scores": {{
    "completitud": <entero 1-10>,
    "precision_datos": <entero 1-10>,
    "precision_regulatoria": <entero 1-10>,
    "coherencia": <entero 1-10>,
    "calidad_redaccion": <entero 1-10>
  }},
  "score_total": <float, promedio exacto de los 5 puntajes>,
  "aprobado": <true si score_total >= {min_score}, false en caso contrario>,
  "fortalezas": ["<fortaleza principal 1>", "<fortaleza principal 2>"],
  "sugerencias": ["<sugerencia de mejora 1>", "<sugerencia de mejora 2>"],
  "resumen": "<2-3 oraciones de evaluación general del informe>"
}}
"""


@dataclass
class JudgeResult:
    """
    Resultado estructurado de la evaluación LLM-as-a-Judge.

    Attributes:
        scores: Dict con puntajes 1-10 por dimensión.
        score_total: Promedio de los puntajes (0.0 a 10.0).
        aprobado: True si score_total >= JUDGE_MIN_SCORE.
        fortalezas: Lista de puntos fuertes del informe.
        sugerencias: Lista de sugerencias de mejora.
        resumen: Texto de evaluación general.
        raw_response: Respuesta cruda del LLM (para debugging).
        parse_error: True si hubo error al parsear el JSON del LLM.
    """
    scores: dict = field(default_factory=dict)
    score_total: float = 0.0
    aprobado: bool = False
    fortalezas: list = field(default_factory=list)
    sugerencias: list = field(default_factory=list)
    resumen: str = ""
    raw_response: str = ""
    parse_error: bool = False

    def to_display_text(self) -> str:
        """Texto formateado para mostrar en el documento Word o logs."""
        status = "APROBADO" if self.aprobado else "REQUIERE REVISIÓN"
        lines = [
            f"Puntuación Total: {self.score_total:.1f}/10 — {status}",
            "",
            f"Evaluación: {self.resumen}",
            "",
            "Puntajes por dimensión:",
        ]
        dimension_labels = {
            "completitud": "Completitud",
            "precision_datos": "Precisión de datos",
            "precision_regulatoria": "Precisión regulatoria",
            "coherencia": "Coherencia entre agentes",
            "calidad_redaccion": "Calidad de redacción",
        }
        for key, label in dimension_labels.items():
            score = self.scores.get(key, "N/A")
            lines.append(f"  • {label}: {score}/10")
        if self.fortalezas:
            lines.append("")
            lines.append("Fortalezas:")
            for f in self.fortalezas:
                lines.append(f"  + {f}")
        if self.sugerencias:
            lines.append("")
            lines.append("Sugerencias de mejora:")
            for s in self.sugerencias:
                lines.append(f"  → {s}")
        return "\n".join(lines)


class LLMJudge:
    """
    Evaluador LLM-as-a-Judge usando el mismo modelo llama3.1.

    Evalúa la salida completa del pipeline y retorna un JudgeResult.
    Nunca lanza excepciones al caller; errores de parsing se capturan
    en JudgeResult.parse_error.
    """

    def __init__(self):
        # temperature=0.0 para evaluación determinista y reproducible
        self.llm = ChatOllama(
            base_url=config.OLLAMA_BASE_URL,
            model=config.OLLAMA_MODEL,
            temperature=0.0,
        )

    def evaluate(self, ctx) -> JudgeResult:
        """
        Evalúa el RunContext completo del pipeline.

        Args:
            ctx: RunContext con los resultados de los tres agentes.

        Returns:
            JudgeResult con puntajes y evaluación. Nunca lanza excepción.
        """
        logger.info("LLMJudge iniciando evaluación del pipeline...")

        datos_content = (
            ctx.datos_result.content
            if ctx.datos_result else "[Agente Datos no ejecutado]"
        )
        regulatorio_content = (
            ctx.regulatorio_result.content
            if ctx.regulatorio_result else "[Agente Regulatorio no ejecutado]"
        )
        redactor_content = (
            ctx.redactor_result.content
            if ctx.redactor_result else "[Agente Redactor no ejecutado]"
        )

        prompt = ChatPromptTemplate.from_template(JUDGE_PROMPT)
        chain = prompt | self.llm | StrOutputParser()

        try:
            raw = chain.invoke({
                "question": ctx.question,
                "datos_content": datos_content,
                "regulatorio_content": regulatorio_content,
                "redactor_content": redactor_content,
                "min_score": config.JUDGE_MIN_SCORE,
            })
        except Exception as e:
            logger.error(f"LLMJudge falló al invocar el LLM: {e}")
            return JudgeResult(
                resumen=f"Error al ejecutar el evaluador: {e}",
                sugerencias=["Verificar que Ollama esté corriendo y el modelo esté disponible"],
                raw_response=str(e),
                parse_error=True,
            )

        logger.debug(f"LLMJudge respuesta cruda:\n{raw[:500]}...")
        result = self._parse_response(raw)

        logger.info(
            f"LLMJudge completado. Score: {result.score_total:.1f}/10 — "
            f"{'APROBADO' if result.aprobado else 'REQUIERE REVISION'}"
        )
        return result

    def _parse_response(self, raw: str) -> JudgeResult:
        """
        Extrae y parsea el JSON de la respuesta del LLM.

        Estrategia robusta: busca el bloque JSON con regex aunque el LLM
        haya agregado texto antes o después (comportamiento común en LLMs locales).
        """
        # Intentar extraer JSON con regex (maneja prose before/after)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            logger.warning(
                "LLMJudge no retornó JSON parseable. "
                f"Respuesta cruda (primeros 300 chars): {raw[:300]}"
            )
            return self._fallback_result(raw, "No se encontró JSON en la respuesta")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"Error al parsear JSON del juez: {e}")
            return self._fallback_result(raw, f"JSON inválido: {e}")

        # Extraer scores con valores por defecto seguros
        scores = data.get("scores", {})

        # Calcular score_total si el LLM no lo calculó correctamente
        if scores:
            calculated_total = sum(scores.values()) / len(scores)
        else:
            calculated_total = 0.0

        score_total = float(data.get("score_total", calculated_total))
        # Redondear a 2 decimales para presentación limpia
        score_total = round(score_total, 2)

        aprobado = data.get("aprobado", score_total >= config.JUDGE_MIN_SCORE)

        return JudgeResult(
            scores=scores,
            score_total=score_total,
            aprobado=bool(aprobado),
            fortalezas=data.get("fortalezas", []),
            sugerencias=data.get("sugerencias", []),
            resumen=data.get("resumen", ""),
            raw_response=raw,
            parse_error=False,
        )

    def _fallback_result(self, raw: str, reason: str) -> JudgeResult:
        """Resultado de fallback cuando el parsing falla. Nunca crashea."""
        return JudgeResult(
            scores={},
            score_total=0.0,
            aprobado=False,
            fortalezas=[],
            sugerencias=[
                f"No se pudo parsear la evaluación automática: {reason}",
                "Revisar manualmente el informe generado",
            ],
            resumen=f"Error en evaluación automática: {reason}",
            raw_response=raw,
            parse_error=True,
        )
