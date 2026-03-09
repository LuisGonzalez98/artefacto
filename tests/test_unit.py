"""
test_unit.py — Tests unitarios del sistema multi-agente Medida 83.

Prueba la lógica pura de los componentes sin llamadas a Ollama, PostgreSQL
ni ChromaDB:

1. JudgeResult.to_display_text()         — formateo del resultado del juez
2. LLMJudge._parse_response()            — parsing robusto del JSON del LLM
3. AgentResult                           — dataclass de salida de agentes
4. RunContext                            — estado compartido del pipeline
5. RunTracker.record_run()              — escritura JSONL de runs
6. RunStats                             — cálculo de métricas históricas

Para evitar instanciar LLMJudge (que crearía ChatOllama), se usa
object.__new__(LLMJudge) que saltea __init__() por completo.

Ejecutar:
    pytest tests/test_unit.py -v
"""

import json
import pytest
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# 1. JudgeResult — display y atributos
# ═══════════════════════════════════════════════════════════════════════════════

class TestJudgeResult:

    def _make_result(self, score=8.4, aprobado=True):
        from judge.llm_judge import JudgeResult
        return JudgeResult(
            scores={
                "completitud": 9,
                "precision_datos": 8,
                "precision_regulatoria": 8,
                "coherencia": 9,
                "calidad_redaccion": 8,
            },
            score_total=score,
            aprobado=aprobado,
            fortalezas=["Datos precisos", "Buena estructura"],
            sugerencias=["Agregar más citas normativas"],
            resumen="Informe de buena calidad regulatoria.",
        )

    def test_display_text_aprobado(self):
        result = self._make_result(score=8.4, aprobado=True)
        text = result.to_display_text()
        assert "APROBADO" in text
        assert "8.4/10" in text
        assert "Completitud" in text
        assert "Precisión de datos" in text
        assert "Datos precisos" in text
        assert "Agregar más citas normativas" in text

    def test_display_text_rechazado(self):
        from judge.llm_judge import JudgeResult
        result = JudgeResult(score_total=5.0, aprobado=False, resumen="Calidad insuficiente.")
        text = result.to_display_text()
        assert "REQUIERE REVISIÓN" in text
        assert "5.0/10" in text

    def test_display_text_sin_fortalezas(self):
        from judge.llm_judge import JudgeResult
        result = JudgeResult(score_total=7.0, aprobado=True, fortalezas=[], sugerencias=[])
        text = result.to_display_text()
        # No debe incluir secciones vacías
        assert "Fortalezas:" not in text
        assert "Sugerencias de mejora:" not in text

    def test_parse_error_flag_false_por_defecto(self):
        from judge.llm_judge import JudgeResult
        result = JudgeResult()
        assert result.parse_error is False
        assert result.score_total == 0.0
        assert result.aprobado is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LLMJudge._parse_response() — sin instanciar Ollama
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def judge():
    """LLMJudge sin __init__: evita crear ChatOllama (no necesita Ollama)."""
    from judge.llm_judge import LLMJudge
    return object.__new__(LLMJudge)


class TestLLMJudgeParsing:

    def _valid_json(self, score_total=8.0, aprobado=True):
        return json.dumps({
            "scores": {
                "completitud": 8,
                "precision_datos": 8,
                "precision_regulatoria": 8,
                "coherencia": 8,
                "calidad_redaccion": 8,
            },
            "score_total": score_total,
            "aprobado": aprobado,
            "fortalezas": ["Coherente", "Preciso"],
            "sugerencias": ["Más detalles"],
            "resumen": "Buen informe regulatorio.",
        })

    def test_json_valido(self, judge):
        result = judge._parse_response(self._valid_json(8.0, True))
        assert result.parse_error is False
        assert result.score_total == 8.0
        assert result.aprobado is True
        assert result.scores["completitud"] == 8
        assert result.fortalezas == ["Coherente", "Preciso"]

    def test_json_con_texto_antes_y_despues(self, judge):
        """LLMs locales frecuentemente envuelven el JSON en texto explicativo."""
        raw = (
            "Aquí está mi evaluación del informe:\n\n"
            + self._valid_json(6.8, False)
            + "\n\nEspero que esta evaluación sea útil para mejorar el informe."
        )
        result = judge._parse_response(raw)
        assert result.parse_error is False
        assert result.score_total == 6.8
        assert result.aprobado is False

    def test_sin_json_retorna_fallback(self, judge):
        result = judge._parse_response("El informe es bueno pero necesita mejoras.")
        assert result.parse_error is True
        assert result.score_total == 0.0
        assert result.aprobado is False
        assert len(result.sugerencias) > 0

    def test_json_invalido_retorna_fallback(self, judge):
        result = judge._parse_response("{esto: no es JSON válido}")
        assert result.parse_error is True

    def test_score_total_se_recalcula_si_falta(self, judge):
        """Si el LLM omite score_total, se calcula del promedio de scores."""
        data = {
            "scores": {
                "completitud": 10,
                "precision_datos": 10,
                "precision_regulatoria": 10,
                "coherencia": 10,
                "calidad_redaccion": 10,
            },
            "aprobado": True,
            "fortalezas": [],
            "sugerencias": [],
            "resumen": "Perfecto.",
        }
        # Omitimos score_total intencionalmente
        result = judge._parse_response(json.dumps(data))
        assert result.parse_error is False
        assert result.score_total == 10.0

    def test_score_se_redondea_a_2_decimales(self, judge):
        raw = self._valid_json(score_total=7.333333)
        result = judge._parse_response(raw)
        # El resultado debe tener máximo 2 decimales
        assert result.score_total == round(result.score_total, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AgentResult — dataclass de salida de agentes
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentResult:

    def test_succeeded_cuando_no_hay_error(self):
        from agents.base_agent import AgentResult
        r = AgentResult(agent_name="AgenteDatos", content="Análisis completado.")
        assert r.succeeded is True

    def test_failed_cuando_hay_error(self):
        from agents.base_agent import AgentResult
        r = AgentResult(agent_name="AgenteDatos", content="[error]", error="DB timeout")
        assert r.succeeded is False

    def test_str_exitoso(self):
        from agents.base_agent import AgentResult
        r = AgentResult(agent_name="AgenteDatos", content="Texto de prueba.")
        assert "AgenteDatos" in str(r)
        assert "OK" in str(r)

    def test_str_fallido(self):
        from agents.base_agent import AgentResult
        r = AgentResult(agent_name="AgenteRedactor", content="[e]", error="Timeout")
        assert "AgenteRedactor" in str(r)
        assert "ERROR" in str(r)

    def test_metadata_default_vacio(self):
        from agents.base_agent import AgentResult
        r = AgentResult(agent_name="Test", content="x")
        assert r.metadata == {}

    def test_metadata_personalizado(self):
        from agents.base_agent import AgentResult
        r = AgentResult(
            agent_name="AgenteRegulatorio",
            content="ok",
            metadata={"sources": ["medida83.pdf"], "docs_retrieved": 3},
        )
        assert r.metadata["docs_retrieved"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RunContext — estado del pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunContext:

    def _make_result(self, name, ok=True):
        from agents.base_agent import AgentResult
        if ok:
            return AgentResult(name, f"output de {name}")
        return AgentResult(name, "[error]", error="fallo simulado")

    def test_all_succeeded_cuando_todos_ok(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        ctx.datos_result = self._make_result("AgenteDatos")
        ctx.regulatorio_result = self._make_result("AgenteRegulatorio")
        ctx.redactor_result = self._make_result("AgenteRedactor")
        assert ctx.all_agents_succeeded is True
        assert ctx.agents_with_errors == []

    def test_not_succeeded_cuando_uno_falla(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        ctx.datos_result = self._make_result("AgenteDatos")
        ctx.regulatorio_result = self._make_result("AgenteRegulatorio", ok=False)
        ctx.redactor_result = self._make_result("AgenteRedactor")
        assert ctx.all_agents_succeeded is False
        assert "AgenteRegulatorio" in ctx.agents_with_errors

    def test_agents_with_errors_multiples(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        ctx.datos_result = self._make_result("AgenteDatos", ok=False)
        ctx.regulatorio_result = self._make_result("AgenteRegulatorio", ok=False)
        ctx.redactor_result = self._make_result("AgenteRedactor")
        errors = ctx.agents_with_errors
        assert len(errors) == 2
        assert "AgenteDatos" in errors
        assert "AgenteRegulatorio" in errors

    def test_not_succeeded_cuando_resultado_es_none(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        # Sin asignar resultados → all_agents_succeeded debe ser False
        assert ctx.all_agents_succeeded is False

    def test_agent_timings_inicia_vacio(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        assert ctx.agent_timings == {}

    def test_summary_incluye_pregunta(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="¿Cuántas portaciones hubo?")
        texto = ctx.summary()
        assert "portaciones" in texto

    def test_summary_incluye_resultado_judge(self):
        from agents.orquestador import RunContext
        ctx = RunContext(question="Prueba")
        ctx.judge_result = {"score_total": 8.5, "aprobado": True}
        texto = ctx.summary()
        assert "8.5" in texto
        assert "APROBADO" in texto


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RunTracker — escritura JSONL
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunTracker:

    def _make_ctx(self, question="Prueba", timings=None):
        from agents.orquestador import RunContext
        from agents.base_agent import AgentResult
        ctx = RunContext(question=question)
        ctx.datos_result = AgentResult("AgenteDatos", "datos ok")
        ctx.regulatorio_result = AgentResult("AgenteRegulatorio", "reg ok")
        ctx.redactor_result = AgentResult("AgenteRedactor", "red ok")
        ctx.agent_timings = timings or {
            "AgenteDatos": 12.5,
            "AgenteRegulatorio": 8.3,
            "AgenteRedactor": 6.1,
        }
        return ctx

    def test_crea_archivo_jsonl(self, tmp_path):
        from llmops.tracker import RunTracker
        tracker = RunTracker(log_file=tmp_path / "runs.jsonl")
        ctx = self._make_ctx()
        tracker.record_run(ctx, judge_result=None)
        assert (tmp_path / "runs.jsonl").exists()

    def test_run_id_tiene_8_chars(self, tmp_path):
        from llmops.tracker import RunTracker
        tracker = RunTracker(log_file=tmp_path / "runs.jsonl")
        run_id = tracker.record_run(self._make_ctx())
        assert len(run_id) == 8

    def test_entrada_es_json_valido(self, tmp_path):
        from llmops.tracker import RunTracker
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        tracker.record_run(self._make_ctx("¿Test?"))
        entry = json.loads(log.read_text())
        assert "run_id" in entry
        assert "timestamp" in entry
        assert "pipeline_ok" in entry
        assert "agent_timings_sec" in entry

    def test_pipeline_ok_true_cuando_todos_ok(self, tmp_path):
        from llmops.tracker import RunTracker
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        tracker.record_run(self._make_ctx())
        entry = json.loads(log.read_text())
        assert entry["pipeline_ok"] is True

    def test_pipeline_ok_false_cuando_hay_error(self, tmp_path):
        from llmops.tracker import RunTracker
        from agents.orquestador import RunContext
        from agents.base_agent import AgentResult
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        ctx = RunContext(question="Error test")
        ctx.datos_result = AgentResult("AgenteDatos", "[e]", error="DB timeout")
        ctx.regulatorio_result = AgentResult("AgenteRegulatorio", "ok")
        ctx.redactor_result = AgentResult("AgenteRedactor", "ok")
        tracker.record_run(ctx)
        entry = json.loads(log.read_text())
        assert entry["pipeline_ok"] is False
        assert "AgenteDatos" in entry["agents_with_errors"]

    def test_timings_se_guardan(self, tmp_path):
        from llmops.tracker import RunTracker
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        tracker.record_run(self._make_ctx(timings={"AgenteDatos": 15.7}))
        entry = json.loads(log.read_text())
        assert entry["agent_timings_sec"]["AgenteDatos"] == 15.7

    def test_judge_disabled_cuando_none(self, tmp_path):
        from llmops.tracker import RunTracker
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        tracker.record_run(self._make_ctx(), judge_result=None)
        entry = json.loads(log.read_text())
        assert entry["judge"]["enabled"] is False

    def test_judge_enabled_con_resultado(self, tmp_path):
        from llmops.tracker import RunTracker
        from judge.llm_judge import JudgeResult
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        jr = JudgeResult(score_total=8.5, aprobado=True, scores={"completitud": 9})
        tracker.record_run(self._make_ctx(), judge_result=jr)
        entry = json.loads(log.read_text())
        assert entry["judge"]["enabled"] is True
        assert entry["judge"]["score_total"] == 8.5
        assert entry["judge"]["aprobado"] is True

    def test_acumula_multiples_runs(self, tmp_path):
        from llmops.tracker import RunTracker
        log = tmp_path / "runs.jsonl"
        tracker = RunTracker(log_file=log)
        for i in range(4):
            tracker.record_run(self._make_ctx(f"Pregunta {i}"))
        lines = log.read_text().strip().split("\n")
        assert len(lines) == 4
        # Verificar que cada línea es JSON válido
        for line in lines:
            json.loads(line)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RunStats — métricas históricas
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunStats:

    def _write_runs(self, tmp_path, runs: list[dict]) -> Path:
        """Helper: escribe una lista de entries JSONL en un archivo temporal."""
        log = tmp_path / "runs.jsonl"
        with open(log, "w") as f:
            for entry in runs:
                f.write(json.dumps(entry) + "\n")
        return log

    def test_sin_archivo_todo_vacio(self, tmp_path):
        from llmops.tracker import RunStats
        stats = RunStats(log_file=tmp_path / "nonexistent.jsonl")
        assert stats.total_runs == 0
        assert stats.success_rate == 0.0
        assert stats.avg_judge_score is None
        assert stats.judge_approval_rate is None

    def test_total_runs(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "judge": {"enabled": False}, "agent_timings_sec": {}},
            {"pipeline_ok": True, "judge": {"enabled": False}, "agent_timings_sec": {}},
            {"pipeline_ok": False, "judge": {"enabled": False}, "agent_timings_sec": {}},
        ])
        stats = RunStats(log_file=log)
        assert stats.total_runs == 3

    def test_success_rate(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "judge": {"enabled": False}, "agent_timings_sec": {}},
            {"pipeline_ok": True, "judge": {"enabled": False}, "agent_timings_sec": {}},
            {"pipeline_ok": False, "judge": {"enabled": False}, "agent_timings_sec": {}},
        ])
        stats = RunStats(log_file=log)
        assert abs(stats.success_rate - 66.7) < 0.1

    def test_avg_judge_score(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 8.0, "aprobado": True, "scores": {}, "parse_error": False}},
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 6.0, "aprobado": False, "scores": {}, "parse_error": False}},
            {"pipeline_ok": False, "agent_timings_sec": {},
             "judge": {"enabled": False}},
        ])
        stats = RunStats(log_file=log)
        assert stats.avg_judge_score == 7.0

    def test_judge_approval_rate(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 8.0, "aprobado": True, "scores": {}, "parse_error": False}},
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 6.0, "aprobado": False, "scores": {}, "parse_error": False}},
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 7.5, "aprobado": True, "scores": {}, "parse_error": False}},
        ])
        stats = RunStats(log_file=log)
        assert abs(stats.judge_approval_rate - 66.7) < 0.1

    def test_avg_agent_timing(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "judge": {"enabled": False},
             "agent_timings_sec": {"AgenteDatos": 10.0, "AgenteRegulatorio": 8.0}},
            {"pipeline_ok": True, "judge": {"enabled": False},
             "agent_timings_sec": {"AgenteDatos": 12.0, "AgenteRegulatorio": 6.0}},
        ])
        stats = RunStats(log_file=log)
        timings = stats.avg_agent_timing()
        assert timings["AgenteDatos"] == 11.0
        assert timings["AgenteRegulatorio"] == 7.0

    def test_dimension_averages(self, tmp_path):
        from llmops.tracker import RunStats
        scores1 = {"completitud": 8, "precision_datos": 6, "precision_regulatoria": 9,
                   "coherencia": 7, "calidad_redaccion": 8}
        scores2 = {"completitud": 6, "precision_datos": 8, "precision_regulatoria": 7,
                   "coherencia": 9, "calidad_redaccion": 6}
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 7.6, "aprobado": True,
                       "scores": scores1, "parse_error": False}},
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 7.2, "aprobado": True,
                       "scores": scores2, "parse_error": False}},
        ])
        stats = RunStats(log_file=log)
        dims = stats.dimension_averages()
        assert dims["completitud"] == 7.0   # (8 + 6) / 2
        assert dims["precision_datos"] == 7.0   # (6 + 8) / 2

    def test_recent_runs_orden_mas_reciente(self, tmp_path):
        from llmops.tracker import RunStats
        entries = [
            {"run_id": f"run{i}", "pipeline_ok": True,
             "judge": {"enabled": False}, "agent_timings_sec": {}}
            for i in range(5)
        ]
        log = self._write_runs(tmp_path, entries)
        stats = RunStats(log_file=log)
        recent = stats.recent_runs(3)
        # El más reciente debe ser el último escrito (run4)
        assert recent[0]["run_id"] == "run4"
        assert len(recent) == 3

    def test_parse_error_excluye_del_avg(self, tmp_path):
        from llmops.tracker import RunStats
        log = self._write_runs(tmp_path, [
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 9.0, "aprobado": True,
                       "scores": {}, "parse_error": False}},
            {"pipeline_ok": True, "agent_timings_sec": {},
             "judge": {"enabled": True, "score_total": 0.0, "aprobado": False,
                       "scores": {}, "parse_error": True}},  # parse error → excluir
        ])
        stats = RunStats(log_file=log)
        # Solo el primer run (score=9.0) debe contribuir al promedio
        assert stats.avg_judge_score == 9.0
