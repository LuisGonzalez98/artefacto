"""
main.py — Punto de entrada del sistema multi-agente Medida 83.

Uso:
    python main.py                     # Ejecuta el pipeline completo
    python main.py --discover-schema   # Solo muestra el esquema de la BD y sale
    python main.py --no-judge          # Omite la evaluación del LLM Judge
    python main.py --reingest          # Re-ingesta todos los documentos RAG
    python main.py --stats             # Muestra estadísticas LLMOps históricas

El pipeline completo:
    1. Verifica conexión a PostgreSQL
    2. Ejecuta Orquestador (AgenteDatos → AgenteRegulatorio → AgenteRedactor)
    3. Ejecuta LLM Judge para evaluar la calidad
    4. Genera documento Word con texto coloreado por agente
    5. Guarda el informe en output/medida83_informe_YYYYMMDD_HHMMSS.docx
"""

import argparse
import logging
import sys
from pathlib import Path


def setup_logging(output_dir: Path) -> None:
    """Configura logging a consola y archivo. Debe llamarse antes de importar módulos."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "run.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema multi-agente para análisis de cumplimiento de la Medida 83 del IFT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                         # Ejecutar pipeline completo
  python main.py --discover-schema       # Ver esquema de la BD y salir
  python main.py --no-judge              # Sin evaluación automática
  python main.py --reingest              # Re-ingestar documentos RAG
  python main.py --question "¿Cuántas portaciones hubo en Q4 2024?"
  python main.py --stats                 # Ver métricas LLMOps históricas
        """,
    )
    parser.add_argument(
        "--discover-schema",
        action="store_true",
        help="Muestra el esquema de la BD de portabilidad y sale sin ejecutar el pipeline",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Omite la evaluación LLM-as-a-Judge (útil para pruebas rápidas)",
    )
    parser.add_argument(
        "--reingest",
        action="store_true",
        help="Re-ingesta todos los documentos RAG (útil al agregar nuevos PDFs o schema docs)",
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Pregunta de análisis personalizada (usa la pregunta por defecto si no se especifica)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Muestra estadísticas LLMOps de todas las ejecuciones previas y sale",
    )
    return parser.parse_args()


# Pregunta de análisis por defecto sobre Medida 83
DEFAULT_QUESTION = (
    "Analiza el cumplimiento de la Medida 83 del IFT (CTOGÉSIMA TERCERA) para el período "
    "más reciente disponible en la base de datos. Calcula: "
    "(1) total de portaciones ejecutadas, "
    "(2) número y porcentaje de casos donde el Agente Económico Preponderante "
    "contactó al usuario portado dentro de los 60 días naturales prohibidos, "
    "(3) desglose por concesionario/operador de los casos de incumplimiento, "
    "(4) evolución mensual del nivel de incumplimiento. "
    "Identifica los periodos y operadores con mayor incumplimiento."
)


def cmd_discover_schema() -> None:
    """Modo --discover-schema: muestra el esquema de la BD y sale."""
    from db.postgres_client import test_connection, get_table_names, get_schema_info

    print("\n=== Descubrimiento de Esquema PostgreSQL ===\n")

    if not test_connection():
        print("ERROR: No se pudo conectar a PostgreSQL. Verifica tu archivo .env")
        sys.exit(1)

    tables = get_table_names()
    if not tables:
        print("No se encontraron tablas. Verifica las credenciales y el nombre de la BD.")
        sys.exit(1)

    print(f"Tablas encontradas ({len(tables)}):\n")
    for t in tables:
        print(f"  - {t}")

    print("\n=== DDL de las tablas ===\n")
    schema_info = get_schema_info(tables)
    print(schema_info)

    print(
        "\n=== Siguiente paso ===\n"
        "Copia el DDL anterior y créa un archivo en data/docs/schema_docs/esquema.txt\n"
        "Agrega descripciones de negocio a cada columna para mejorar el análisis.\n"
        "Ejecuta 'python main.py --reingest' después de agregar los archivos."
    )


def cmd_reingest() -> None:
    """Modo --reingest: re-ingesta todos los vectorstores."""
    from rag.rag_datos import get_schema_retriever
    from rag.rag_regulatorio import get_regulatorio_retriever
    from rag.rag_redactor import get_plantillas_retriever

    logger = logging.getLogger(__name__)
    logger.info("Re-ingestando todos los documentos RAG...")

    logger.info("  1/3 Schema docs (AgenteDatos)...")
    get_schema_retriever(force_reingest=True)

    logger.info("  2/3 Documentos regulatorios (AgenteRegulatorio)...")
    get_regulatorio_retriever(force_reingest=True)

    logger.info("  3/3 Plantillas de redacción (AgenteRedactor)...")
    get_plantillas_retriever(force_reingest=True)

    logger.info("Re-ingestación completada.")


def cmd_stats() -> None:
    """Modo --stats: muestra estadísticas LLMOps históricas y sale."""
    from llmops.tracker import RunStats
    stats = RunStats()
    stats.print_report()


def cmd_run_pipeline(question: str, include_judge: bool) -> None:
    """Modo normal: ejecuta el pipeline completo."""
    from db.postgres_client import test_connection
    from agents.orquestador import Orquestador
    from judge.llm_judge import LLMJudge
    from output.word_generator import build_word_document
    from llmops.tracker import RunTracker
    import config

    logger = logging.getLogger(__name__)

    logger.info("=== Sistema Multi-Agente Medida 83 ===")
    logger.info(f"Modelo LLM:         {config.OLLAMA_MODEL}")
    logger.info(f"Modelo embeddings:  {config.OLLAMA_EMBED_MODEL}")
    logger.info(f"Ollama URL:         {config.OLLAMA_BASE_URL}")
    logger.info(f"PostgreSQL:         {config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}")

    # Pre-flight: verificar conexión a PostgreSQL
    print("\nVerificando conexión a PostgreSQL...")
    if not test_connection():
        logger.error(
            "No se pudo conectar a PostgreSQL. "
            "Verifica los valores en .env (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, etc.)"
        )
        sys.exit(1)

    # Ejecutar pipeline
    print(f"\nPregunta de análisis:\n  {question}\n")
    print("Iniciando pipeline de agentes...\n")

    orchestrator = Orquestador()
    ctx = orchestrator.run(question=question)

    if not ctx.all_agents_succeeded:
        logger.warning(
            f"Pipeline completado con errores en: {ctx.agents_with_errors}. "
            "El documento Word reflejará los errores."
        )

    # Evaluación del juez
    judge_result = None
    if include_judge:
        print("\nEjecutando evaluación LLM-as-a-Judge...")
        judge = LLMJudge()
        judge_result = judge.evaluate(ctx)
        ctx.judge_result = {
            "score_total": judge_result.score_total,
            "aprobado": judge_result.aprobado,
        }

        print(f"\n── Resultado del Juez ──")
        print(judge_result.to_display_text())
    else:
        logger.info("Evaluación de juez omitida (--no-judge)")

    # Registrar run en el log LLMOps
    tracker = RunTracker()
    run_id = tracker.record_run(ctx, judge_result)
    logger.info(f"[LLMOps] Run ID: {run_id}")

    # Generar documento Word
    print("\nGenerando documento Word...")
    output_path = build_word_document(ctx, judge_result)

    print(f"\n{'='*60}")
    print(f"Informe generado exitosamente:")
    print(f"  {output_path}")
    print(f"{'='*60}")
    print(f"\nEstado del pipeline: {'OK' if ctx.all_agents_succeeded else 'Con errores'}")

    if judge_result:
        status = "APROBADO" if judge_result.aprobado else "REQUIERE REVISIÓN"
        print(f"Evaluación automática: {judge_result.score_total:.1f}/10 — {status}")

    print(f"\nLog completo en: {config.OUTPUT_DIR / 'run.log'}")


def main() -> None:
    # Importar config solo para obtener OUTPUT_DIR antes de inicializar logging
    import config
    setup_logging(config.OUTPUT_DIR)

    args = parse_args()
    logger = logging.getLogger(__name__)

    if args.discover_schema:
        cmd_discover_schema()
        return

    if args.stats:
        cmd_stats()
        return

    if args.reingest:
        cmd_reingest()
        # Continuar con el pipeline si se especificó --reingest sin --discover-schema
        if len(sys.argv) == 2:
            # Solo se pasó --reingest; salir después de re-ingestar
            print("\nRe-ingestación completada. Ejecuta 'python main.py' para correr el pipeline.")
            return

    question = args.question or DEFAULT_QUESTION
    include_judge = not args.no_judge

    try:
        cmd_run_pipeline(question=question, include_judge=include_judge)
    except KeyboardInterrupt:
        logger.info("Pipeline interrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error no controlado en el pipeline: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
