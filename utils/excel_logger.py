"""
utils/excel_logger.py — Registro acumulativo de ejecuciones del LLM-as-a-Judge.

Escribe en CSV (nunca se bloquea aunque esté abierto en Excel) y genera
un xlsx formateado cada vez que se llama. Si el xlsx está bloqueado por Excel,
el registro queda igualmente en el CSV.
"""

import csv
from datetime import datetime
from pathlib import Path

import config

_HEADERS = [
    "Timestamp",
    "Documento Word",
    "Score Total",
    "Veredicto",
    "Completitud",
    "Precisión Datos",
    "Precisión Regulatoria",
    "Coherencia",
    "Calidad Redacción",
    "Fortalezas",
    "Sugerencias",
    "Resumen Evaluador",
    "Comentario",
]

_COL_WIDTHS = [20, 42, 12, 18, 13, 16, 21, 12, 18, 45, 45, 60, 35]


def _build_row(docx_path: Path, judge_result, run_ts: datetime) -> list:
    if judge_result is None or judge_result.parse_error:
        return [
            run_ts.strftime("%Y-%m-%d %H:%M:%S"),
            docx_path.name,
            "", "Sin evaluación", "", "", "", "", "", "", "", "", "",
        ]
    s = judge_result.scores
    return [
        run_ts.strftime("%Y-%m-%d %H:%M:%S"),
        docx_path.name,
        judge_result.score_total,
        "APROBADO" if judge_result.aprobado else "REQUIERE REVISIÓN",
        s.get("completitud", ""),
        s.get("precision_datos", ""),
        s.get("precision_regulatoria", ""),
        s.get("coherencia", ""),
        s.get("calidad_redaccion", ""),
        "; ".join(judge_result.fortalezas),
        "; ".join(judge_result.sugerencias),
        judge_result.resumen,
        "",  # Comentario — columna libre
    ]


def _append_csv(csv_path: Path, row: list) -> None:
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(_HEADERS)
        w.writerow(row)


def _build_xlsx(csv_path: Path, xlsx_path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            rows.append(r)

    wb = Workbook()
    ws = wb.active
    ws.title = "Evaluaciones"

    hdr_font  = Font(bold=True, color="FFFFFF", size=11)
    hdr_fill  = PatternFill("solid", fgColor="003366")
    thin      = Side(style="thin", color="CCCCCC")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)
    c_align   = Alignment(horizontal="center", vertical="center", wrap_text=True)
    l_align   = Alignment(horizontal="left",   vertical="center", wrap_text=True)

    for ci, (h, w) in enumerate(zip(_HEADERS, _COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = c_align if ci <= 4 else l_align
        cell.border = border
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    for ri, row in enumerate(rows[1:], start=2):
        try:
            aprobado = row[3] == "APROBADO"
            sin_eval = row[3] == "Sin evaluación"
            if sin_eval:
                fill = PatternFill("solid", fgColor="F2F2F2")
            else:
                fill = PatternFill("solid", fgColor="E8F5E9" if aprobado else "FFF3CD")
            score_font = Font(
                color="666666" if sin_eval else ("1B5E20" if aprobado else "7B3F00"),
                bold=not sin_eval,
            )
        except Exception:
            fill = PatternFill("solid", fgColor="F2F2F2")
            score_font = Font()

        for ci, val in enumerate(row, start=1):
            cell = ws.cell(row=ri, column=ci)
            cell.border = border
            cell.fill   = fill
            cell.alignment = c_align if ci <= 4 else l_align
            if ci in (3, 5, 6, 7, 8, 9):
                try:
                    cell.value = float(val) if val else None
                    cell.number_format = "0.0" if ci == 3 else "0"
                except ValueError:
                    cell.value = val
            else:
                cell.value = val
            if ci == 3:
                cell.font = score_font
        ws.row_dimensions[ri].height = 40

    wb.save(xlsx_path)


def log_judge(docx_path: Path, judge_result, run_ts: datetime) -> Path:
    output_dir = config.DOCS_DIR.parent
    csv_path   = output_dir / "LLM_as_a_judge.csv"
    xlsx_path  = output_dir / "LLM_as_a_judge.xlsx"

    row = _build_row(docx_path, judge_result, run_ts)
    _append_csv(csv_path, row)      # siempre funciona, nunca se bloquea

    try:
        _build_xlsx(csv_path, xlsx_path)   # regenera el xlsx completo desde el csv
    except PermissionError:
        pass   # xlsx abierto en Excel — los datos ya están en el csv

    return xlsx_path
