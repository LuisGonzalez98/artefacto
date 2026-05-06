"""
db/init_db.py — Base SQLite con registros de portabilidad numérica (Medida 83 / CRT-DG-VRA).

Modelo de datos:
  portaciones — Todos los eventos de portación (TIPO_6).
                Los "indicadores potenciales" son pares ida-vuelta donde el mismo número
                portó DESDE Telcel y regresó A Telcel en <= 60 días naturales.
"""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

AEP = "Telcel"
OPERADORES = {
    "Telcel":          "AMX-001",
    "AT&T México":     "ATT-002",
    "Movistar":        "MOV-003",
    "Altan Redes":     "ALT-004",
    "Virgin Mobile":   "VGN-005",
    "Bait":            "BAI-006",
}
OP_NAMES = list(OPERADORES.keys())
AREA_CODES = ["55", "33", "81", "222", "664", "442", "477", "614", "667", "999"]

# Perfiles por semilla — varían tasa de retorno, distribución temporal y concentración de operadores
# seed=1: Escenario moderado (baseline)
# seed=2: Alta concentración — tasa alta, retornos muy rápidos, un operador domina
# seed=3: Baja concentración — tasa baja, retornos tardíos, mercado distribuido
_PERFILES = {
    1: {
        "random_seed":   1,
        "retorno_rate":  0.28,
        "pesos_dias":    [15, 20, 18, 22, 15, 10],   # días 22-30 con mayor peso
        "op_weights":    [0, 30, 28, 18, 14, 10],    # AT&T y Movistar lideran
        "desc":          "Escenario 1 — Moderado (baseline ~28% indicadores)",
    },
    2: {
        "random_seed":   7,
        "retorno_rate":  0.42,
        "pesos_dias":    [30, 28, 18, 12, 8, 4],     # retornos muy rápidos (1-14 días)
        "op_weights":    [0, 60, 18, 10, 8, 4],      # AT&T concentra 60% → HHI alto
        "desc":          "Escenario 2 — Alta concentración (~42% indicadores, retornos tempranos)",
    },
    3: {
        "random_seed":   13,
        "retorno_rate":  0.14,
        "pesos_dias":    [5, 10, 15, 22, 25, 23],    # retornos tardíos (31-60 días)
        "op_weights":    [0, 22, 22, 20, 18, 18],    # mercado distribuido → HHI bajo
        "desc":          "Escenario 3 — Baja concentración (~14% indicadores, retornos tardíos)",
    },
}


def _phone() -> str:
    ac = random.choice(AREA_CODES)
    return ac + "".join(str(random.randint(0, 9)) for _ in range(10 - len(ac)))


def init_db(db_path: Path, num_portaciones: int = 50_000, seed: int = 1) -> dict:
    perfil = _PERFILES.get(seed, _PERFILES[1])
    random.seed(perfil["random_seed"])
    print(f"  Perfil: {perfil['desc']}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS portaciones;

        CREATE TABLE portaciones (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            folio_portacion     TEXT    NOT NULL,
            numero_telefono     TEXT    NOT NULL,
            fecha_portacion     TEXT    NOT NULL,
            operador_origen     TEXT    NOT NULL,
            codigo_origen       TEXT    NOT NULL,
            operador_destino    TEXT    NOT NULL,
            codigo_destino      TEXT    NOT NULL,
            tipo_portacion      TEXT    NOT NULL DEFAULT 'TIPO_6'
        );

        CREATE INDEX idx_port_phone   ON portaciones(numero_telefono);
        CREATE INDEX idx_port_origen  ON portaciones(operador_origen);
        CREATE INDEX idx_port_destino ON portaciones(operador_destino);
        CREATE INDEX idx_port_fecha   ON portaciones(fecha_portacion);
    """)

    start_dt = datetime(2023, 1, 1)
    end_dt   = datetime(2024, 12, 31)
    total_days = (end_dt - start_dt).days
    folio_n = 1

    rows: list[tuple] = []
    aep_departures: list[tuple] = []  # (phone, fecha_str, destino)

    # — Portaciones iniciales ─────────────────────────────────────────────────
    for _ in range(num_portaciones):
        phone = _phone()
        fecha = (start_dt + timedelta(days=random.randint(0, total_days))).strftime("%Y-%m-%d")
        folio = f"NMP-{folio_n:06d}"
        folio_n += 1

        if random.random() < 0.40:
            origen  = AEP
            non_aep = [op for op in OP_NAMES if op != AEP]
            destino = random.choices(non_aep, weights=perfil["op_weights"][1:])[0]
            aep_departures.append((phone, fecha, destino))
        else:
            origen  = random.choice([op for op in OP_NAMES if op != AEP])
            destino = random.choice([op for op in OP_NAMES if op != origen])

        rows.append((folio, phone, fecha,
                     origen,  OPERADORES[origen],
                     destino, OPERADORES[destino], "TIPO_6"))

    # — Retornos al AEP en <= 60 días (indicadores potenciales) ──────────────
    # Pesos de distribución por rango de días (simula concentración temprana)
    RANGOS = [(1, 7), (8, 14), (15, 21), (22, 30), (31, 45), (46, 60)]
    PESOS  = perfil["pesos_dias"]

    n_retornos_objetivo = int(len(aep_departures) * perfil["retorno_rate"])
    muestra = random.sample(aep_departures, n_retornos_objetivo)

    retornos_generados = 0
    for phone, fecha_ida, operador_intermedio in muestra:
        ida_dt = datetime.strptime(fecha_ida, "%Y-%m-%d")
        lo, hi = random.choices(RANGOS, weights=PESOS)[0]
        dias   = random.randint(lo, hi)
        vuelta_dt = ida_dt + timedelta(days=dias)
        if vuelta_dt > end_dt:
            continue
        folio = f"NMP-{folio_n:06d}"
        folio_n += 1
        rows.append((folio, phone, vuelta_dt.strftime("%Y-%m-%d"),
                     operador_intermedio, OPERADORES[operador_intermedio],
                     AEP,                OPERADORES[AEP], "TIPO_6"))
        retornos_generados += 1

    cur.executemany(
        "INSERT INTO portaciones "
        "(folio_portacion, numero_telefono, fecha_portacion, "
        "operador_origen, codigo_origen, operador_destino, codigo_destino, tipo_portacion) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    return {
        "portaciones": len(rows),
        "portaciones_base": num_portaciones,
        "aep_departures": len(aep_departures),
        "retornos": retornos_generados,
    }
