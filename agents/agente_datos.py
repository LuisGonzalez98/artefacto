"""
agente_datos.py — Consultas SQL + estadísticos para el informe DG-VRA/CRT.

Ejecuta 12 consultas sobre la tabla 'portaciones' y calcula:
  - Indicadores potenciales (pares ida-vuelta AEP <= 60 días)
  - Concentración de mercado (HHI)
  - Distribución por operador, rango de días y mes
  - Regresión lineal sobre la tendencia mensual
  - Proyección a 3 meses
"""

import logging
import math
import sqlite3
from datetime import datetime, timedelta

import config
from utils import llm_client
from utils.context import AgentResult

logger = logging.getLogger(__name__)

# Códigos de operador (espejo de init_db)
CODIGOS = {
    "Telcel":        "AMX-001",
    "AT&T México":   "ATT-002",
    "Movistar":      "MOV-003",
    "Altan Redes":   "ALT-004",
    "Virgin Mobile": "VGN-005",
    "Bait":          "BAI-006",
}

_PAR_IDA_VUELTA = """
    SELECT p1.numero_telefono,
           p1.fecha_portacion           AS fecha_ida,
           p2.fecha_portacion           AS fecha_vuelta,
           p1.operador_destino          AS operador_intermedio,
           p1.codigo_destino            AS codigo_intermedio,
           CAST(julianday(p2.fecha_portacion) - julianday(p1.fecha_portacion) AS INTEGER) AS dias
    FROM   portaciones p1
    JOIN   portaciones p2 ON p1.numero_telefono = p2.numero_telefono
    WHERE  p1.operador_origen  = 'Telcel'
      AND  p2.operador_destino = 'Telcel'
      AND  p2.fecha_portacion  > p1.fecha_portacion
      AND  p1.tipo_portacion   = 'TIPO_6'
      AND  p2.tipo_portacion   = 'TIPO_6'
"""

_RETORNOS_60 = _PAR_IDA_VUELTA + " AND julianday(p2.fecha_portacion) - julianday(p1.fecha_portacion) <= 60"

SYSTEM_PROMPT = """Eres analista de datos de la Dirección General de Vigilancia de Regulación Asimétrica (DG-VRA)
de la Comisión Reguladora de Telecomunicaciones (CRT) de México.

Redactas la narrativa cuantitativa interna (borrador) para informes de fiscalización de la Medida 83.

REGLAS:
- Prosa técnica institucional. Cero listas, cero viñetas, cero markdown.
- Tono: "el análisis muestra", "se observa", "esta Dirección General identificó".
- Condicional epistémico: "podría indicar", "sugiere", "es consistente con".
- NUNCA afirmar infracción probada; los datos son indicadores indirectos.
- Integra cifras exactas al texto corrido."""


def run(question: str) -> AgentResult:
    logger.info("AgenteDatos: ejecutando consultas SQL...")
    try:
        data = _query_db()
        metadata = _build_metadata(data)
        narrative = _analyze_with_llm(data, question)
        return AgentResult(agent_name="AgenteDatos", content=narrative,
                           succeeded=True, metadata=metadata)
    except Exception as e:
        logger.error(f"AgenteDatos error: {e}", exc_info=True)
        print(f"  [ERROR] {e}")
        return AgentResult(agent_name="AgenteDatos",
                           content=f"Error en análisis de datos: {e}",
                           succeeded=False, error=str(e))


def _query_db() -> dict:
    db = str(config.SQLITE_DB_PATH)
    print(f"  Conectando a: {config.SQLITE_DB_PATH.name}")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    def q(sql):   return [dict(r) for r in conn.execute(sql).fetchall()]
    def s(sql):   return conn.execute(sql).fetchone()[0]

    N = 12
    print(f"  Ejecutando {N} consultas SQL...")

    print(f"    [ 1/{N}] Total portaciones TIPO_6")
    total_tipo6 = s("SELECT COUNT(*) FROM portaciones WHERE tipo_portacion='TIPO_6'")

    print(f"    [ 2/{N}] Portaciones donde AEP fue donador")
    aep_donador = s("SELECT COUNT(*) FROM portaciones WHERE operador_origen='Telcel' AND tipo_portacion='TIPO_6'")

    print(f"    [ 3/{N}] Pares ida-vuelta (cualquier plazo)")
    pares_total = s(f"SELECT COUNT(DISTINCT p1.numero_telefono) FROM ({_PAR_IDA_VUELTA}) p1")

    print(f"    [ 4/{N}] Retornos <= 60 días (indicadores potenciales)")
    retornos_60 = s(f"SELECT COUNT(*) FROM ({_RETORNOS_60}) r")

    print(f"    [ 5/{N}] Calidad de datos (nulos por campo clave)")
    nulos_tel  = s("SELECT COUNT(*) FROM portaciones WHERE numero_telefono IS NULL OR numero_telefono=''")
    nulos_fec  = s("SELECT COUNT(*) FROM portaciones WHERE fecha_portacion IS NULL OR fecha_portacion=''")
    nulos_ori  = s("SELECT COUNT(*) FROM portaciones WHERE operador_origen IS NULL OR operador_origen=''")
    nulos_dest = s("SELECT COUNT(*) FROM portaciones WHERE operador_destino IS NULL OR operador_destino=''")

    print(f"    [ 6/{N}] Participación por operador receptor (HHI)")
    participacion = q(
        "SELECT operador_destino, codigo_destino, COUNT(*) AS total "
        "FROM portaciones WHERE tipo_portacion='TIPO_6' "
        "GROUP BY operador_destino ORDER BY total DESC"
    )

    print(f"    [ 7/{N}] Indicadores por operador receptor intermedio")
    ind_por_op = q(f"""
        SELECT operador_intermedio, codigo_intermedio,
               COUNT(*) AS indicadores,
               ROUND(AVG(dias), 1) AS dias_prom,
               MIN(dias) AS dias_min, MAX(dias) AS dias_max
        FROM ({_RETORNOS_60}) r
        GROUP BY operador_intermedio ORDER BY indicadores DESC
    """)

    print(f"    [ 8/{N}] Distribución por rango de días")
    dist_dias = q(f"""
        SELECT CASE
                 WHEN dias BETWEEN 1  AND  7 THEN '01-07'
                 WHEN dias BETWEEN 8  AND 14 THEN '08-14'
                 WHEN dias BETWEEN 15 AND 21 THEN '15-21'
                 WHEN dias BETWEEN 22 AND 30 THEN '22-30'
                 WHEN dias BETWEEN 31 AND 45 THEN '31-45'
                 ELSE '46-60'
               END AS rango,
               COUNT(*) AS total
        FROM ({_RETORNOS_60}) r
        GROUP BY rango ORDER BY rango
    """)

    print(f"    [ 9/{N}] Tendencia mensual de indicadores")
    tendencia = q(f"""
        SELECT strftime('%Y-%m', fecha_ida) AS mes, COUNT(*) AS indicadores
        FROM ({_RETORNOS_60}) r
        GROUP BY mes ORDER BY mes
    """)

    print(f"    [10/{N}] Tendencia mensual de portaciones totales")
    tend_total = q(
        "SELECT strftime('%Y-%m', fecha_portacion) AS mes, COUNT(*) AS total "
        "FROM portaciones WHERE tipo_portacion='TIPO_6' GROUP BY mes ORDER BY mes"
    )

    print(f"    [11/{N}] Muestra de casos con mayor inmediatez de retorno")
    muestra = q(f"""
        SELECT numero_telefono, fecha_ida, fecha_vuelta, operador_intermedio, dias
        FROM ({_RETORNOS_60}) r
        ORDER BY dias ASC LIMIT 10
    """)

    print(f"    [12/{N}] Período cubierto")
    periodo_inicio = s("SELECT MIN(fecha_portacion) FROM portaciones") or "2023-01"
    periodo_fin    = s("SELECT MAX(fecha_portacion) FROM portaciones") or "2024-12"

    conn.close()

    tasa = (retornos_60 / aep_donador * 100) if aep_donador > 0 else 0.0
    print(f"\n  Hallazgos clave:")
    print(f"    Total TIPO_6             : {total_tipo6:,}")
    print(f"    AEP como donador         : {aep_donador:,}")
    print(f"    Pares ida-vuelta (total) : {pares_total:,}")
    print(f"    Retornos <= 60 dias      : {retornos_60:,}")
    print(f"    Tasa de indicadores      : {tasa:.2f}%")

    return {
        "total_tipo6": total_tipo6,
        "aep_donador": aep_donador,
        "pares_total": pares_total,
        "retornos_60": retornos_60,
        "tasa": tasa,
        "nulos_telefono": nulos_tel,
        "nulos_fecha": nulos_fec,
        "nulos_origen": nulos_ori,
        "nulos_destino": nulos_dest,
        "participacion": participacion,
        "ind_por_op": ind_por_op,
        "dist_dias": dist_dias,
        "tendencia": tendencia,
        "tend_total": tend_total,
        "muestra": muestra,
        "periodo_inicio": periodo_inicio,
        "periodo_fin": periodo_fin,
    }


def _build_metadata(data: dict) -> dict:
    total = data["total_tipo6"]

    # HHI
    total_port = sum(r["total"] for r in data["participacion"])
    hhi = 0.0
    part_enriquecida = []
    for r in data["participacion"]:
        pct = (r["total"] / total_port * 100) if total_port > 0 else 0
        hhi += pct ** 2
        part_enriquecida.append({
            "operador": r["operador_destino"],
            "codigo":   r.get("codigo_destino", CODIGOS.get(r["operador_destino"], "---")),
            "total":    r["total"],
            "pct":      round(pct, 2),
        })
    hhi = round(hhi, 1)
    if hhi >= 2500:
        hhi_cat = "Altamente concentrado (HHI >= 2,500)"
    elif hhi >= 1500:
        hhi_cat = "Moderadamente concentrado (1,500 <= HHI < 2,500)"
    else:
        hhi_cat = "Competitivo (HHI < 1,500)"

    # Indicadores por operador con %
    ret60 = data["retornos_60"]
    ind_op = []
    for r in data["ind_por_op"]:
        ind_op.append({
            "codigo":    r.get("codigo_intermedio", CODIGOS.get(r["operador_intermedio"], "---")),
            "operador":  r["operador_intermedio"],
            "indicadores": r["indicadores"],
            "pct_total": round(r["indicadores"] / ret60 * 100, 2) if ret60 > 0 else 0.0,
            "dias_prom": r["dias_prom"],
            "dias_min":  r["dias_min"],
            "dias_max":  r["dias_max"],
        })

    # Distribución días con %
    dist = []
    for r in data["dist_dias"]:
        dist.append({
            "rango": r["rango"],
            "total": r["total"],
            "pct":   round(r["total"] / ret60 * 100, 2) if ret60 > 0 else 0.0,
        })

    # Regresión lineal sobre tendencia mensual
    tend = data["tendencia"]
    regresion = _linreg(tend)

    # Proyección 3 meses
    proyeccion = _proyectar(tend, regresion)

    # Período
    periodo = f"{data['periodo_inicio'][:7]} — {data['periodo_fin'][:7]}"

    return {
        "total_tipo6":         data["total_tipo6"],
        "aep_donador":         data["aep_donador"],
        "pares_total":         data["pares_total"],
        "retornos_60":         ret60,
        "tasa":                round(data["tasa"], 2),
        "periodo":             periodo,
        # Calidad
        "registros_totales":   data["total_tipo6"],
        "nulos_telefono":      data["nulos_telefono"],
        "nulos_fecha":         data["nulos_fecha"],
        "nulos_origen":        data["nulos_origen"],
        "nulos_destino":       data["nulos_destino"],
        # Mercado
        "participacion":       part_enriquecida,
        "hhi":                 hhi,
        "hhi_categoria":       hhi_cat,
        # Sección 6
        "ind_por_op":          ind_op,
        "dist_dias":           dist,
        "tendencia":           [{"mes": r["mes"], "indicadores": r["indicadores"]} for r in tend],
        "muestra":             [dict(r) for r in data["muestra"]],
        # Estadísticos
        "regresion":           regresion,
        "proyeccion":          proyeccion,
    }


def _linreg(tend: list) -> dict:
    """Regresión lineal mínimos cuadrados sobre la serie mensual de indicadores."""
    if len(tend) < 3:
        return {"pendiente": 0, "intercepto": 0, "r_cuadrado": 0,
                "p_valor": 1.0, "error_estandar": 0, "tendencia": "estable"}

    xs = list(range(1, len(tend) + 1))
    ys = [r["indicadores"] for r in tend]
    n  = len(xs)
    xm = sum(xs) / n
    ym = sum(ys) / n

    ss_xy = sum((xi - xm) * (yi - ym) for xi, yi in zip(xs, ys))
    ss_xx = sum((xi - xm) ** 2 for xi in xs)
    ss_yy = sum((yi - ym) ** 2 for yi in ys)

    if ss_xx == 0:
        return {"pendiente": 0, "intercepto": ym, "r_cuadrado": 0,
                "p_valor": 1.0, "error_estandar": 0, "tendencia": "estable"}

    slope = ss_xy / ss_xx
    intercept = ym - slope * xm
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(xs, ys))
    r2  = max(0.0, 1 - ss_res / ss_yy) if ss_yy > 0 else 0.0
    mse = ss_res / (n - 2) if n > 2 else 0.0
    se  = (mse / ss_xx) ** 0.5 if ss_xx > 0 else 0.0
    t   = slope / se if se > 0 else 0.0
    # Aproximación p-valor con distribución normal (válida para n > 10)
    p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))

    if slope > 1.0:
        tendencia = "creciente"
    elif slope < -1.0:
        tendencia = "decreciente"
    else:
        tendencia = "estable"

    return {
        "pendiente":      round(slope, 4),
        "intercepto":     round(intercept, 4),
        "r_cuadrado":     round(r2, 4),
        "p_valor":        round(p_val, 4),
        "error_estandar": round(se, 4),
        "tendencia":      tendencia,
    }


def _proyectar(tend: list, reg: dict) -> list:
    """Proyecta 3 meses hacia adelante con intervalo de confianza (±15%)."""
    if not tend:
        return []
    n     = len(tend)
    slope = reg["pendiente"]
    intcp = reg["intercepto"]
    # Último mes del dataset
    try:
        last_mes = datetime.strptime(tend[-1]["mes"], "%Y-%m")
    except Exception:
        return []

    proyeccion = []
    for i in range(1, 4):
        x  = n + i
        y  = max(0, slope * x + intcp)
        me = (last_mes.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        margen = round(y * 0.15)
        proyeccion.append({
            "mes":      me.strftime("%Y-%m"),
            "proyeccion": round(y),
            "ic_inf":   max(0, round(y) - margen),
            "ic_sup":   round(y) + margen,
        })
    return proyeccion


def _analyze_with_llm(data: dict, question: str) -> str:
    total   = data["total_tipo6"]
    aep     = data["aep_donador"]
    ret60   = data["retornos_60"]
    pares   = data["pares_total"]
    tasa    = data["tasa"]
    modelo  = config.GROQ_MODEL if config.LLM_PROVIDER == "groq" else config.HF_MODEL
    print(f"\n  Enviando datos al LLM ({modelo}) para narrativa cuantitativa...")

    tipos_str = "; ".join(
        f"{r['operador_intermedio']}: {r['indicadores']:,} casos"
        for r in data["ind_por_op"]
    )
    dist_str = "; ".join(
        f"días {r['rango']}: {r['total']:,} casos"
        for r in data["dist_dias"]
    )

    prompt = f"""Redacta la narrativa cuantitativa interna para el informe de la DG-VRA/CRT sobre la Medida 83.

PREGUNTA: {question}

DATOS VERIFICADOS:
- Total portaciones TIPO_6 analizadas: {total:,}
- Portaciones donde el AEP (Telcel) fue donador: {aep:,}
- Pares ida-vuelta identificados (cualquier plazo): {pares:,}
- Indicadores potenciales (retornos <= 60 días): {ret60:,}
- Tasa de indicadores sobre salidas del AEP: {tasa:.2f}%
- Distribución por operador receptor intermedio: {tipos_str}
- Distribución por rango de días: {dist_str}
- Período: {data['periodo_inicio'][:7]} a {data['periodo_fin'][:7]}

Redacta EXACTAMENTE tres párrafos:

Párrafo 1 (70-90 palabras): Universo total de portaciones TIPO_6 analizadas, cuántas tuvieron al AEP como donador y su peso relativo.

Párrafo 2 (90-110 palabras): Indicadores potenciales: número exacto de retornos en <= 60 días, tasa sobre salidas del AEP, distribución por operador intermedio y por rangos temporales.

Párrafo 3 (70-90 palabras): Valoración del patrón observado y su relevancia regulatoria como indicador indirecto. Usa condicional epistémico.

Sin títulos. Sin listas. Sin markdown. Prosa institucional DG-VRA/CRT."""

    response = llm_client.chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=800,
    )
    print(f"  Narrativa generada ({len(response):,} caracteres)")
    return response
