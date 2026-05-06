"""
main.py — Sistema Multi-Agente DG-VRA/CRT — Análisis Medida 83.

SETUP (3 pasos):
  1. pip install -r requirements.txt
  2. Copia .env.example como .env y agrega tu API key
  3. python main.py

MODOS:
  python main.py                   # Pipeline completo
  python main.py --no-judge        # Sin evaluación LLM-as-a-Judge
  python main.py --reset-db        # Regenera la base SQLite
  python main.py --question "..."  # Pregunta personalizada
"""

import argparse
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config
from utils.context import RunContext

DEFAULT_QUESTION = (
    "Analiza el cumplimiento de la Medida Octogésima Tercera (Medida 83) del IFT para el período "
    "2023-2024. Calcula: (1) total de portaciones tipo 6 y cuántas tuvieron al AEP como donador, "
    "(2) pares ida-vuelta donde el usuario retornó al AEP en 60 días o menos (indicadores potenciales), "
    "(3) distribución de indicadores por operador receptor intermedio, por rango de días y por mes, "
    "(4) concentración de mercado (HHI) y participación por operador receptor, "
    "(5) tendencia estadística mensual de indicadores potenciales y proyección a 3 meses. "
    "Identifica los períodos y operadores con mayor concentración de indicadores y evalúa "
    "la gravedad del patrón observado."
)


def setup_logging(run_ts: datetime) -> Path:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOGS_DIR / f"run_{run_ts.strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
    )
    return log_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sistema Multi-Agente DG-VRA/CRT — Medida 83",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--no-judge",  action="store_true", help="Omite evaluación LLM-as-a-Judge")
    parser.add_argument("--reset-db",  type=int, nargs="?", const=1, default=None, metavar="SEED",
                        help="Regenera la BD. SEED: 1=moderado (default), 2=alta concentración, 3=baja concentración")
    parser.add_argument("--question",  type=str, default=None, help="Pregunta personalizada")
    return parser.parse_args()


def ensure_db() -> None:
    db_path = config.SQLITE_DB_PATH
    print(f"  Ruta: {db_path}")
    if db_path.exists():
        try:
            conn  = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM portaciones").fetchone()[0]
            conn.close()
            if count > 0:
                print(f"  Estado: OK — {count:,} registros existentes")
                return
        except Exception:
            pass
    print("  Estado: no encontrada — generando registros sinteticos...")
    from db.init_db import init_db
    stats = init_db(db_path)
    print(f"  Creada: {stats['portaciones']:,} portaciones | {stats['retornos']:,} indicadores potenciales")


def _sep(char="─", width=60):
    print(char * width)


def run_pipeline(question: str, include_judge: bool, run_ts: datetime, log_path: Path) -> None:
    from agents import agente_datos, agente_regulatorio, agente_redactor
    from judge import llm_judge
    from utils.word_generator import build_word_document

    ctx = RunContext(question=question, run_timestamp=run_ts)
    modelo   = config.GROQ_MODEL if config.LLM_PROVIDER == "groq" else config.HF_MODEL
    plantilla = config.WORD_TEMPLATE.name if config.WORD_TEMPLATE else "ninguna"

    _sep("=")
    print(f"  {config.INSTITUCION}")
    print(f"  {config.DEPENDENCIA}")
    print("  ANÁLISIS DE CUMPLIMIENTO — MEDIDA 83")
    _sep("=")
    print(f"  Proveedor LLM  : {config.LLM_PROVIDER.upper()}")
    print(f"  Modelo         : {modelo}")
    print(f"  Base de datos  : {config.SQLITE_DB_PATH.name}")
    print(f"  Plantilla Word : {plantilla}")
    print(f"  Timestamp      : {ctx.run_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    _sep()
    print(f"  Pregunta:")
    print(f"  {question[:110]}{'...' if len(question) > 110 else ''}")
    _sep()

    # ── Agente 1: Datos ──────────────────────────────────────────────
    print("\n[1/3] AGENTE DATOS — Consultas SQL + estadísticos")
    _sep()
    t0 = time.time()
    ctx.datos_result = agente_datos.run(question)
    ctx.agent_timings["AgenteDatos"] = round(time.time() - t0, 1)
    if ctx.datos_result.succeeded:
        print(f"  >> OK en {ctx.agent_timings['AgenteDatos']}s | {len(ctx.datos_result.content):,} chars")
    else:
        print(f"  >> ERROR: {ctx.datos_result.error}")

    # ── Agente 2: Regulatorio ─────────────────────────────────────────
    print("\n[2/3] AGENTE REGULATORIO — Marco jurídico (Secciones 1-2)")
    _sep()
    t0 = time.time()
    datos_text = ctx.datos_result.content if ctx.datos_result.succeeded else ""
    ctx.regulatorio_result = agente_regulatorio.run(question, datos_content=datos_text)
    ctx.agent_timings["AgenteRegulatorio"] = round(time.time() - t0, 1)
    if ctx.regulatorio_result.succeeded:
        print(f"  >> OK en {ctx.agent_timings['AgenteRegulatorio']}s | {len(ctx.regulatorio_result.content):,} chars")
    else:
        print(f"  >> ERROR: {ctx.regulatorio_result.error}")

    # ── Agente 3: Redactor ────────────────────────────────────────────
    print("\n[3/3] AGENTE REDACTOR — Secciones 3-9 (narrativa institucional)")
    _sep()
    t0 = time.time()
    reg_text = ctx.regulatorio_result.content if ctx.regulatorio_result.succeeded else ""
    ctx.redactor_result = agente_redactor.run(
        question, datos_content=datos_text, regulatorio_content=reg_text,
        metadata=ctx.datos_result.metadata if ctx.datos_result else {},
    )
    ctx.agent_timings["AgenteRedactor"] = round(time.time() - t0, 1)
    if ctx.redactor_result.succeeded:
        print(f"  >> OK en {ctx.agent_timings['AgenteRedactor']}s | {len(ctx.redactor_result.content):,} chars")
    else:
        print(f"  >> ERROR: {ctx.redactor_result.error}")

    # ── LLM Judge ─────────────────────────────────────────────────────
    judge_result = None
    if include_judge:
        print("\n[JUDGE] LLM-AS-A-JUDGE — Evaluación de calidad")
        _sep()
        t0 = time.time()
        judge_result = llm_judge.evaluate(ctx)
        elapsed = round(time.time() - t0, 1)
        ctx.judge_result = {"score_total": judge_result.score_total, "aprobado": judge_result.aprobado}
        print(f"  >> Evaluación completada en {elapsed}s")
        _sep()
        print(judge_result.to_display_text())
    else:
        print("\n[JUDGE] Omitido (--no-judge)")

    # ── Documento Word ────────────────────────────────────────────────
    print("\n[OUTPUT] Generando documento Word...")
    output_path = build_word_document(ctx, judge_result)
    print(f"  >> Guardado: {output_path.name}")

    # ── Registro Excel LLM Judge ──────────────────────────────────────
    try:
        from utils.excel_logger import log_judge
        excel_path = log_judge(output_path, judge_result, run_ts)
        print(f"  >> Registro Judge: {excel_path.name}")
    except Exception as _exc:
        excel_path = None
        print(f"  >> Registro Judge: omitido ({_exc})")

    # ── Resumen ───────────────────────────────────────────────────────
    total_time = sum(ctx.agent_timings.values())
    estado = "OK" if ctx.all_agents_succeeded else f"Con errores ({', '.join(ctx.agents_with_errors)})"
    _sep("=")
    print("  RESULTADO FINAL")
    _sep("=")
    print(f"  Informe   : {output_path}")
    if excel_path:
        print(f"  Registro  : {excel_path}")
    print(f"  Pipeline  : {estado}")
    print(f"  Tiempo    : {total_time}s  "
          f"(datos={ctx.agent_timings.get('AgenteDatos')}s | "
          f"reg={ctx.agent_timings.get('AgenteRegulatorio')}s | "
          f"red={ctx.agent_timings.get('AgenteRedactor')}s)")
    if judge_result:
        verdict = "APROBADO" if judge_result.aprobado else "REQUIERE REVISIÓN"
        print(f"  Calidad   : {judge_result.score_total:.1f}/10 — {verdict}")
    print(f"  Log       : {log_path}")
    _sep("=")


def main() -> None:
    run_ts   = datetime.now()
    log_path = setup_logging(run_ts)
    args     = parse_args()
    logger   = logging.getLogger(__name__)

    if args.reset_db is not None:
        from db.init_db import init_db
        seed = args.reset_db
        print(f"Regenerando base de datos (semilla {seed})...")
        stats = init_db(config.SQLITE_DB_PATH, seed=seed)
        print(f"  Listo: {stats['portaciones']:,} portaciones, {stats['retornos']:,} indicadores potenciales")
        if len(sys.argv) <= 3:
            return

    print("\nVerificando base de datos...")
    ensure_db()

    question = args.question or DEFAULT_QUESTION
    try:
        run_pipeline(question=question, include_judge=not args.no_judge,
                     run_ts=run_ts, log_path=log_path)
    except KeyboardInterrupt:
        logger.info("Pipeline interrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error en el pipeline: {e}", exc_info=True)
        print(f"\n[ERROR] {e}")
        print("Revisa tu archivo .env y verifica que la API key esté configurada correctamente.")
        sys.exit(1)


if __name__ == "__main__":
    main()
