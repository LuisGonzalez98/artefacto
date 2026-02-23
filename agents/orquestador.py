"""
orquestador.py — Orquestador del pipeline multi-agente.

Responsabilidades:
- Definir RunContext: el estado compartido de una ejecución completa
- Coordinar la ejecución secuencial de los tres agentes
- Pasar el contexto acumulado de un agente al siguiente
- NO tiene LLM propio ni RAG propio

Flujo del pipeline:
    AgenteDatos.run(question)
        → datos_result.content
            AgenteRegulatorio.run(question, datos_result.content)
                → regulatorio_result.content
                    AgenteRedactor.run(question, datos_result.content, regulatorio_result.content)
                        → redactor_result

Cada agente recibe los outputs de todos los agentes anteriores.
El Orquestador NO llama al juez ni al generador de Word;
eso lo hace main.py para mantener las responsabilidades separadas.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.agente_datos import AgenteDatos
from agents.agente_regulatorio import AgenteRegulatorio
from agents.agente_redactor import AgenteRedactor
from agents.base_agent import AgentResult

logger = logging.getLogger(__name__)


@dataclass
class RunContext:
    """
    Estado completo de una ejecución del pipeline.

    Creado por el Orquestador y consumido por LLMJudge y WordGenerator.
    Actúa como el "registro histórico" de la ejecución: qué se preguntó,
    qué produjo cada agente, y dónde se guardó el resultado.

    Attributes:
        question: La pregunta de análisis que originó la ejecución.
        run_timestamp: Marca de tiempo del inicio de la ejecución.
        datos_result: Output del Agente Datos (cuantitativo).
        regulatorio_result: Output del Agente Regulatorio (normativo).
        redactor_result: Output del Agente Redactor (narrativo).
        judge_result: Dict con el resultado resumido del LLM Judge.
        output_path: Ruta al archivo .docx generado (se asigna al final).
    """
    question: str
    run_timestamp: datetime = field(default_factory=datetime.now)
    datos_result: Optional[AgentResult] = None
    regulatorio_result: Optional[AgentResult] = None
    redactor_result: Optional[AgentResult] = None
    judge_result: Optional[dict] = None
    output_path: Optional[Path] = None

    @property
    def all_agents_succeeded(self) -> bool:
        """True si los tres agentes completaron sin errores."""
        return all(
            r is not None and r.succeeded
            for r in [self.datos_result, self.regulatorio_result, self.redactor_result]
        )

    @property
    def agents_with_errors(self) -> list[str]:
        """Lista de nombres de agentes que tuvieron errores."""
        errors = []
        for result in [self.datos_result, self.regulatorio_result, self.redactor_result]:
            if result is not None and not result.succeeded:
                errors.append(result.agent_name)
        return errors

    def summary(self) -> str:
        """Resumen legible del estado del contexto."""
        lines = [
            f"RunContext | {self.run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Pregunta: {self.question[:80]}{'...' if len(self.question) > 80 else ''}",
            f"Agentes OK: {self.all_agents_succeeded}",
        ]
        if self.agents_with_errors:
            lines.append(f"Agentes con error: {', '.join(self.agents_with_errors)}")
        if self.judge_result:
            score = self.judge_result.get("score_total", "N/A")
            aprobado = self.judge_result.get("aprobado", False)
            lines.append(f"Judge: {score}/10 — {'APROBADO' if aprobado else 'REQUIERE REVISION'}")
        if self.output_path:
            lines.append(f"Documento: {self.output_path}")
        return "\n".join(lines)


class Orquestador:
    """
    Coordina la ejecución secuencial del pipeline de tres agentes.

    No tiene estado mutable entre ejecuciones (cada llamada a run()
    es independiente). Instancia los agentes una vez en __init__
    para reutilizar las conexiones al LLM y los vectorstores.
    """

    def __init__(self):
        logger.info("Inicializando agentes del pipeline...")
        self.agente_datos = AgenteDatos()
        self.agente_regulatorio = AgenteRegulatorio()
        self.agente_redactor = AgenteRedactor()
        logger.info("Todos los agentes inicializados.")

    def run(self, question: str) -> RunContext:
        """
        Ejecuta el pipeline completo para una pregunta de análisis.

        Los agentes se ejecutan secuencialmente. Si un agente falla,
        el pipeline continúa con el siguiente usando el contenido de error
        como contexto (via _safe_run). Esto asegura que siempre se
        produzca un RunContext completo, aunque algunos agentes hayan fallado.

        Args:
            question: Pregunta de análisis sobre cumplimiento de Medida 83.

        Returns:
            RunContext con los resultados de todos los agentes.
        """
        ctx = RunContext(question=question)
        logger.info(f"=== Pipeline iniciado | Pregunta: {question[:60]}... ===")

        # ── Etapa 1: Análisis de datos ────────────────────────────
        logger.info("── Etapa 1/3: AgenteDatos ──")
        ctx.datos_result = self.agente_datos._safe_run(question=question)
        self._log_stage_result("AgenteDatos", ctx.datos_result)

        # ── Etapa 2: Contexto regulatorio ─────────────────────────
        logger.info("── Etapa 2/3: AgenteRegulatorio ──")
        ctx.regulatorio_result = self.agente_regulatorio._safe_run(
            question=question,
            datos_result=ctx.datos_result.content,
        )
        self._log_stage_result("AgenteRegulatorio", ctx.regulatorio_result)

        # ── Etapa 3: Redacción del informe ────────────────────────
        logger.info("── Etapa 3/3: AgenteRedactor ──")
        ctx.redactor_result = self.agente_redactor._safe_run(
            question=question,
            datos_result=ctx.datos_result.content,
            regulatorio_result=ctx.regulatorio_result.content,
        )
        self._log_stage_result("AgenteRedactor", ctx.redactor_result)

        logger.info(f"=== Pipeline completado ===\n{ctx.summary()}")
        return ctx

    def _log_stage_result(self, stage_name: str, result: AgentResult) -> None:
        """Registra el resultado de cada etapa del pipeline."""
        if result.succeeded:
            logger.info(
                f"  {stage_name}: OK | {len(result.content)} chars | "
                f"metadata: {result.metadata}"
            )
        else:
            logger.error(
                f"  {stage_name}: ERROR | {result.error} | "
                f"Contenido parcial: {result.content[:100]}..."
            )
