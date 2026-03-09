"""
llmops/tracker.py — Registro y métricas de ejecuciones del pipeline.

LLMOps para el sistema Medida 83. Persiste cada run en un archivo JSONL
(output/runs_log.jsonl), donde cada línea es un objeto JSON independiente.

Este módulo registra:
- Timestamps y latencias por agente (en segundos)
- Scores del LLM Judge por dimensión y total
- Estado del pipeline (aprobado / con errores)
- Pregunta analizada (truncada para no inflar el log)

El módulo también provee RunStats, que lee el historial y calcula:
- Número total de runs y tasa de éxito
- Promedio y tendencia de scores del juez
- Latencias medias por agente
- Últimos N runs para revisión rápida

Formato JSONL (una línea = un run):
  {"run_id": "...", "timestamp": "...", "question_excerpt": "...", ...}

No requiere dependencias externas más allá de la stdlib.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

RUNS_LOG_FILE: Path = config.OUTPUT_DIR / "runs_log.jsonl"


class RunTracker:
    """
    Registra cada ejecución del pipeline en un archivo JSONL persistente.

    Uso típico en main.py:
        tracker = RunTracker()
        tracker.record_run(ctx, judge_result)
    """

    def __init__(self, log_file: Path = RUNS_LOG_FILE):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def record_run(self, ctx, judge_result=None) -> str:
        """
        Registra el run completo del pipeline en el archivo JSONL.

        Args:
            ctx: RunContext con resultados de agentes y timings.
            judge_result: JudgeResult opcional (None si se usó --no-judge).

        Returns:
            run_id: UUID único del run registrado.
        """
        run_id = str(uuid.uuid4())[:8]

        entry = {
            "run_id": run_id,
            "timestamp": ctx.run_timestamp.isoformat(),
            "model": config.OLLAMA_MODEL,
            "question_excerpt": ctx.question[:120] + ("..." if len(ctx.question) > 120 else ""),
            "pipeline_ok": ctx.all_agents_succeeded,
            "agents_with_errors": ctx.agents_with_errors,
            "agent_timings_sec": ctx.agent_timings if hasattr(ctx, "agent_timings") else {},
            "judge": self._extract_judge_data(judge_result),
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(f"[LLMOps] Run {run_id} registrado en {self.log_file.name}")
        except OSError as e:
            logger.warning(f"[LLMOps] No se pudo escribir el log de run: {e}")

        return run_id

    def _extract_judge_data(self, judge_result) -> dict:
        """Extrae los datos relevantes del JudgeResult para el log."""
        if judge_result is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "score_total": judge_result.score_total,
            "aprobado": judge_result.aprobado,
            "scores": judge_result.scores,
            "parse_error": judge_result.parse_error,
        }


class RunStats:
    """
    Lee el historial de runs y calcula estadísticas agregadas.

    Uso:
        stats = RunStats()
        stats.print_report()
    """

    def __init__(self, log_file: Path = RUNS_LOG_FILE):
        self.log_file = log_file
        self._runs: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Carga todos los runs del archivo JSONL."""
        if not self.log_file.exists():
            return
        with open(self.log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        self._runs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    @property
    def total_runs(self) -> int:
        return len(self._runs)

    @property
    def runs_with_judge(self) -> list[dict]:
        return [r for r in self._runs if r.get("judge", {}).get("enabled")]

    @property
    def success_rate(self) -> float:
        """Porcentaje de runs donde el pipeline completó sin errores."""
        if not self._runs:
            return 0.0
        ok = sum(1 for r in self._runs if r.get("pipeline_ok"))
        return ok / len(self._runs) * 100

    @property
    def avg_judge_score(self) -> Optional[float]:
        """Promedio del score total del juez sobre todos los runs evaluados."""
        scores = [
            r["judge"]["score_total"]
            for r in self.runs_with_judge
            if not r["judge"].get("parse_error")
        ]
        return round(sum(scores) / len(scores), 2) if scores else None

    @property
    def judge_approval_rate(self) -> Optional[float]:
        """Porcentaje de runs aprobados por el juez."""
        evaluated = [
            r for r in self.runs_with_judge
            if not r["judge"].get("parse_error")
        ]
        if not evaluated:
            return None
        approved = sum(1 for r in evaluated if r["judge"].get("aprobado"))
        return round(approved / len(evaluated) * 100, 1)

    def avg_agent_timing(self) -> dict[str, float]:
        """Latencia promedio por agente en segundos."""
        totals: dict[str, list[float]] = {}
        for run in self._runs:
            for agent, secs in run.get("agent_timings_sec", {}).items():
                totals.setdefault(agent, []).append(secs)
        return {
            agent: round(sum(vals) / len(vals), 2)
            for agent, vals in totals.items()
        }

    def dimension_averages(self) -> dict[str, float]:
        """Promedio por dimensión del juez sobre todos los runs evaluados."""
        dim_totals: dict[str, list[float]] = {}
        for run in self.runs_with_judge:
            scores = run.get("judge", {}).get("scores", {})
            for dim, val in scores.items():
                dim_totals.setdefault(dim, []).append(val)
        return {
            dim: round(sum(vals) / len(vals), 2)
            for dim, vals in dim_totals.items()
        }

    def recent_runs(self, n: int = 5) -> list[dict]:
        """Retorna los últimos N runs (más reciente primero)."""
        return list(reversed(self._runs[-n:]))

    def print_report(self) -> None:
        """Imprime el reporte de estadísticas en consola."""
        sep = "=" * 60
        sub = "-" * 60
        print(f"\n{sep}")
        print("  LLMOps - Estadisticas del pipeline Medida 83")
        print(f"{sep}")

        if self.total_runs == 0:
            print("\n  Sin runs registrados. Ejecuta el pipeline al menos una vez.")
            print(f"{sep}\n")
            return

        print(f"\n  Total de runs registrados : {self.total_runs}")
        print(f"  Tasa de exito del pipeline: {self.success_rate:.1f}%")

        # LLM Judge
        n_judge = len(self.runs_with_judge)
        if n_judge > 0:
            print(f"\n  -- LLM Judge ({n_judge} runs evaluados) --")
            avg = self.avg_judge_score
            approval = self.judge_approval_rate
            print(f"  Score promedio  : {avg}/10" if avg is not None else "  Score promedio  : N/A")
            print(f"  Tasa aprobacion : {approval}%" if approval is not None else "  Tasa aprobacion : N/A")

            dims = self.dimension_averages()
            if dims:
                print("\n  Promedios por dimension:")
                labels = {
                    "completitud": "Completitud",
                    "precision_datos": "Precision de datos",
                    "precision_regulatoria": "Precision regulatoria",
                    "coherencia": "Coherencia",
                    "calidad_redaccion": "Calidad de redaccion",
                }
                for key, label in labels.items():
                    val = dims.get(key, "N/A")
                    bar = "#" * int(val) if isinstance(val, float) else ""
                    print(f"    {label:<28}: {val:>4}/10  {bar}")

        # Latencias
        timings = self.avg_agent_timing()
        if timings:
            print("\n  -- Latencias promedio por agente --")
            for agent, secs in timings.items():
                print(f"    {agent:<25}: {secs:>6.1f} s")

        # Ultimos runs
        print("\n  -- Ultimos 5 runs --")
        header = f"  {'ID':>8}  {'Fecha':<19}  {'OK':>3}  {'Score':>6}  {'Aprobado'}"
        print(header)
        print("  " + "-" * 58)
        for run in self.recent_runs(5):
            ts = run.get("timestamp", "")[:19]
            ok = "OK" if run.get("pipeline_ok") else "ERR"
            judge = run.get("judge", {})
            if judge.get("enabled") and not judge.get("parse_error"):
                score = f"{judge['score_total']:.1f}"
                aprobado = "SI" if judge.get("aprobado") else "NO"
            else:
                score = " N/A"
                aprobado = "-"
            print(f"  {run.get('run_id', '?'):>8}  {ts:<19}  {ok:>3}  {score:>6}  {aprobado}")

        print(f"\n{sep}\n")
