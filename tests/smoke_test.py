"""
smoke_test.py — Prueba rápida del sistema Medida 83 sin Ollama ni PostgreSQL.

Verifica que la lógica interna funciona correctamente usando datos de prueba:
  - JudgeResult: parsing de JSON y display
  - LLMJudge._parse_response(): casos normales y de error
  - AgentResult / RunContext: estado del pipeline
  - RunTracker: escritura en JSONL
  - RunStats: cálculo de métricas

Ejecutar:
    python tests/smoke_test.py
"""

import json
import sys
import tempfile
import logging
from pathlib import Path

# ── Setup: agregar raíz del proyecto al path ───────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Mock db.postgres_client antes de importar agentes ─────────────────────
from unittest.mock import MagicMock
_db_mock = MagicMock()
_db_mock.get_sql_database = MagicMock(return_value=MagicMock())
sys.modules.setdefault("db", MagicMock())
sys.modules.setdefault("db.postgres_client", _db_mock)

# ── Logging con formato visual ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke")

# Colores ANSI para terminal
OK   = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SEP  = "-" * 60


def check(nombre: str, condicion: bool, detalle: str = "") -> bool:
    simbolo = OK if condicion else FAIL
    sufijo = f"  ({detalle})" if detalle else ""
    log.info(f"  {simbolo}  {nombre}{sufijo}")
    return condicion


def seccion(titulo: str) -> None:
    log.info(f"\n{SEP}")
    log.info(f"  {titulo}")
    log.info(SEP)


# ═══════════════════════════════════════════════════════════════════════════
def test_judge_result():
    seccion("1. JudgeResult — display y atributos")
    from judge.llm_judge import JudgeResult

    jr = JudgeResult(
        scores={
            "completitud": 9, "precision_datos": 8,
            "precision_regulatoria": 9, "coherencia": 8, "calidad_redaccion": 8,
        },
        score_total=8.4,
        aprobado=True,
        fortalezas=["Datos precisos y coherentes", "Buena cobertura normativa"],
        sugerencias=["Agregar más citas textuales de la Medida 83"],
        resumen="El informe demuestra un análisis riguroso con integración correcta de los datos.",
    )

    texto = jr.to_display_text()
    log.info(f"\n{texto}\n")

    ok = True
    ok &= check("score_total correcto",    jr.score_total == 8.4,   f"valor={jr.score_total}")
    ok &= check("aprobado=True",           jr.aprobado is True)
    ok &= check("display contiene APROBADO", "APROBADO" in texto)
    ok &= check("display contiene 8.4/10",   "8.4/10" in texto)
    ok &= check("muestra fortalezas",        "Datos precisos" in texto)
    ok &= check("muestra sugerencias",       "citas textuales" in texto)
    ok &= check("parse_error=False por defecto", JudgeResult().parse_error is False)
    return ok


# ═══════════════════════════════════════════════════════════════════════════
def test_llm_judge_parsing():
    seccion("2. LLMJudge._parse_response() — sin Ollama")
    from judge.llm_judge import LLMJudge

    # Instanciar sin __init__ (evita crear ChatOllama)
    judge = object.__new__(LLMJudge)

    json_valido = json.dumps({
        "scores": {
            "completitud": 9, "precision_datos": 8,
            "precision_regulatoria": 9, "coherencia": 8, "calidad_redaccion": 8,
        },
        "score_total": 8.4,
        "aprobado": True,
        "fortalezas": ["Preciso", "Coherente"],
        "sugerencias": ["Más citas normativas"],
        "resumen": "Buen informe regulatorio.",
    })

    ok = True

    # Caso 1: JSON limpio
    r = judge._parse_response(json_valido)
    log.info(f"  → Caso 1 (JSON limpio): score={r.score_total}, aprobado={r.aprobado}")
    ok &= check("JSON limpio — parse_error=False", r.parse_error is False)
    ok &= check("JSON limpio — score_total=8.4",   r.score_total == 8.4)

    # Caso 2: JSON envuelto en texto (comportamiento real de LLMs locales)
    json_con_texto = (
        "Aquí está mi evaluación del informe:\n\n"
        + json_valido
        + "\n\nEspero que sea útil."
    )
    r2 = judge._parse_response(json_con_texto)
    log.info(f"  → Caso 2 (JSON + texto): score={r2.score_total}, parse_error={r2.parse_error}")
    ok &= check("JSON con texto — extrae correctamente", r2.parse_error is False)
    ok &= check("JSON con texto — score_total=8.4",      r2.score_total == 8.4)

    # Caso 3: Sin JSON → fallback
    r3 = judge._parse_response("El informe es bueno pero necesita mejoras en la redacción.")
    log.info(f"  → Caso 3 (sin JSON): parse_error={r3.parse_error}, score={r3.score_total}")
    ok &= check("Sin JSON — parse_error=True",   r3.parse_error is True)
    ok &= check("Sin JSON — score_total=0.0",    r3.score_total == 0.0)
    ok &= check("Sin JSON — sugerencias no vacías", len(r3.sugerencias) > 0)

    # Caso 4: JSON inválido → fallback
    r4 = judge._parse_response("{esto: no es json valido}")
    log.info(f"  → Caso 4 (JSON inválido): parse_error={r4.parse_error}")
    ok &= check("JSON inválido — parse_error=True", r4.parse_error is True)

    return ok


# ═══════════════════════════════════════════════════════════════════════════
def test_agent_result_y_run_context():
    seccion("3. AgentResult + RunContext — estado del pipeline")
    from agents.base_agent import AgentResult
    from agents.orquestador import RunContext

    ok = True

    # AgentResult
    r_ok  = AgentResult("AgenteDatos", "Portaciones: 45,320. Incumplimientos: 1,247.")
    r_err = AgentResult("AgenteRegulatorio", "[error]", error="DB timeout")

    log.info(f"  → {r_ok}")
    log.info(f"  → {r_err}")

    ok &= check("AgentResult OK — succeeded=True",  r_ok.succeeded is True)
    ok &= check("AgentResult ERR — succeeded=False", r_err.succeeded is False)

    # RunContext pipeline completo
    ctx = RunContext(question="¿Cuántos incumplimientos de Medida 83 en Q4 2024?")
    ctx.datos_result       = AgentResult("AgenteDatos",       "datos ok")
    ctx.regulatorio_result = AgentResult("AgenteRegulatorio", "reg ok")
    ctx.redactor_result    = AgentResult("AgenteRedactor",    "red ok")
    ctx.agent_timings      = {"AgenteDatos": 12.5, "AgenteRegulatorio": 8.3, "AgenteRedactor": 6.1}
    ctx.judge_result       = {"score_total": 8.4, "aprobado": True}

    log.info(f"\n  Resumen del contexto:\n{ctx.summary()}\n")

    ok &= check("RunContext — all_agents_succeeded=True", ctx.all_agents_succeeded is True)
    ok &= check("RunContext — agents_with_errors=[]",     ctx.agents_with_errors == [])
    ok &= check("RunContext — agent_timings registrados", "AgenteDatos" in ctx.agent_timings)

    # RunContext con error
    ctx2 = RunContext(question="Prueba con error")
    ctx2.datos_result       = AgentResult("AgenteDatos",       "[e]", error="DB timeout")
    ctx2.regulatorio_result = AgentResult("AgenteRegulatorio", "ok")
    ctx2.redactor_result    = AgentResult("AgenteRedactor",    "ok")

    ok &= check("RunContext con error — all_agents_succeeded=False", not ctx2.all_agents_succeeded)
    ok &= check("RunContext con error — agente en errors list",
                "AgenteDatos" in ctx2.agents_with_errors)

    return ok


# ═══════════════════════════════════════════════════════════════════════════
def test_run_tracker_y_stats():
    seccion("4. RunTracker + RunStats — LLMOps")
    from agents.base_agent import AgentResult
    from agents.orquestador import RunContext
    from judge.llm_judge import JudgeResult
    from llmops.tracker import RunTracker, RunStats

    ok = True

    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "runs.jsonl"
        tracker  = RunTracker(log_file=log_file)

        # Simular 3 runs: 2 aprobados (scores 9.0 y 7.5), 1 con error sin judge
        runs_data = [
            (9.0, True,  {"AgenteDatos": 10.1, "AgenteRegulatorio": 7.8, "AgenteRedactor": 5.5}),
            (7.5, True,  {"AgenteDatos": 13.2, "AgenteRegulatorio": 9.1, "AgenteRedactor": 6.8}),
            (None, None, {}),   # pipeline con error, sin judge
        ]

        for i, (score, aprobado, timings) in enumerate(runs_data):
            ctx = RunContext(question=f"Pregunta de prueba #{i+1}")
            ctx.datos_result       = AgentResult("AgenteDatos",       "ok" if score else "[e]",
                                                  error=None if score else "DB timeout")
            ctx.regulatorio_result = AgentResult("AgenteRegulatorio", "ok")
            ctx.redactor_result    = AgentResult("AgenteRedactor",    "ok")
            ctx.agent_timings      = timings

            jr = None
            if score is not None:
                jr = JudgeResult(
                    scores={k: int(score) for k in [
                        "completitud","precision_datos","precision_regulatoria",
                        "coherencia","calidad_redaccion"
                    ]},
                    score_total=score, aprobado=aprobado,
                )

            run_id = tracker.record_run(ctx, jr)
            log.info(f"  → Run {i+1} guardado: id={run_id}, score={score or 'N/A'}")

        # Verificar que el archivo JSONL es válido
        lineas = log_file.read_text().strip().split("\n")
        ok &= check("JSONL: 3 líneas escritas", len(lineas) == 3, f"líneas={len(lineas)}")
        for linea in lineas:
            json.loads(linea)  # lanzaría excepción si no es JSON válido
        ok &= check("JSONL: todas las líneas son JSON válido", True)

        # Verificar RunStats
        stats = RunStats(log_file=log_file)
        ok &= check("RunStats: total_runs=3",     stats.total_runs == 3,
                    f"total={stats.total_runs}")
        ok &= check("RunStats: success_rate≈66.7%", abs(stats.success_rate - 66.7) < 0.2,
                    f"rate={stats.success_rate:.1f}%")
        ok &= check("RunStats: avg_judge_score=8.25",
                    stats.avg_judge_score == 8.25,
                    f"avg={stats.avg_judge_score}")
        ok &= check("RunStats: judge_approval_rate=100%",
                    stats.judge_approval_rate == 100.0,
                    f"approval={stats.judge_approval_rate}%")

        timings = stats.avg_agent_timing()
        ok &= check("RunStats: latencia AgenteDatos≈11.65s",
                    abs(timings.get("AgenteDatos", 0) - 11.65) < 0.1,
                    f"avg={timings.get('AgenteDatos')}s")

        log.info("")
        stats.print_report()

    return ok


# ═══════════════════════════════════════════════════════════════════════════
def main():
    log.info(f"\n{'='*60}")
    log.info("  SMOKE TEST — Sistema Multi-Agente Medida 83")
    log.info(f"{'='*60}")

    resultados = {
        "JudgeResult":            test_judge_result(),
        "LLMJudge._parse_response": test_llm_judge_parsing(),
        "AgentResult + RunContext": test_agent_result_y_run_context(),
        "RunTracker + RunStats":   test_run_tracker_y_stats(),
    }

    # ── Resumen final ──────────────────────────────────────────────────────
    log.info(f"\n{SEP}")
    log.info("  RESUMEN")
    log.info(SEP)

    total_ok = sum(resultados.values())
    total    = len(resultados)

    for nombre, paso in resultados.items():
        log.info(f"  {OK if paso else FAIL}  {nombre}")

    log.info(f"\n  {total_ok}/{total} módulos OK")

    if total_ok == total:
        log.info("  \033[92mTodo en orden. El sistema está listo.\033[0m")
        sys.exit(0)
    else:
        log.info("  \033[91mAlgunos módulos fallaron. Revisar los detalles arriba.\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
