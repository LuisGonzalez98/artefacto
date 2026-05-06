"""
word_generator.py — Ensambla el informe DG-VRA/CRT en formato Word.

Estructura:
  Portada → HITL → Sección 1-2 (reg) → Sección 3 (red) →
  Sección 4 (calidad, tabla) → Sección 5 (HHI, tablas, gráfica) →
  Sección 6 (6.1-6.5, tablas, gráficas) → Sección 7 (regresión, gráfica) →
  Sección 8 (AIR) → Sección 9 (escenarios) → Cierre
"""

import logging
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

import config

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False
    logger.warning("matplotlib/numpy no disponibles — gráficas omitidas")

_BLACK    = RGBColor(0, 0, 0)
_BLUE     = RGBColor(*config.COLOR_PRIMARIO)
_GRAY     = RGBColor(*config.COLOR_SECUNDARIO)
_RED      = RGBColor(*config.COLOR_ACENTO)
_AMBER_BG = "FFF3CD"
_HDR_BG   = "D9E1F2"
_SUB_BG   = "F2F2F2"
_CHART_W  = Inches(5.8)


# ─── Section-marker parser ───────────────────────────────────────────────────

def _parse(result) -> dict:
    """Parsea el formato ===KEY===\\ntext producido por los agentes."""
    if result is None or not result.succeeded:
        return {}
    content = result.content or ""
    if content.startswith("ERROR:"):
        return {}
    out = {}
    parts = re.split(r'===([A-Z0-9_]+)===', content)
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            key = parts[i].lower()
            out[key] = parts[i + 1].strip()
    return out


def _sec(sections: dict, key: str, fallback: str = "") -> str:
    val = sections.get(key, fallback)
    return val if isinstance(val, str) and val.strip() else fallback


# ─── Document helpers ─────────────────────────────────────────────────────────

def _open_document() -> Document:
    if config.WORD_TEMPLATE and config.WORD_TEMPLATE.exists():
        print(f"  Plantilla: {config.WORD_TEMPLATE.name}")
        doc = Document(str(config.WORD_TEMPLATE))
        body = doc.element.body
        for child in list(body):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "sectPr":
                body.remove(child)
        return doc
    print("  Formato: documento por defecto")
    return Document()


def _shade_para(p, fill: str):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def _shade_cell(cell, fill: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _style_table(table):
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "AAAAAA")
        borders.append(b)
    existing = tblPr.find(qn("w:tblBorders"))
    if existing is not None:
        tblPr.remove(existing)
    tblPr.append(borders)


def _add_table(doc: Document, headers: list[str], rows: list[list],
               col_widths: list[float] | None = None) -> None:
    n_cols = len(headers)
    table  = doc.add_table(rows=1, cols=n_cols)
    _style_table(table)
    if col_widths:
        for i, w in enumerate(col_widths):
            table.columns[i].width = Inches(w)

    hdr = table.rows[0].cells
    for i, (cell, text) in enumerate(zip(hdr, headers)):
        cell.text = text
        run = cell.paragraphs[0].runs[0]
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = _BLACK
        _shade_cell(cell, _HDR_BG)

    for row_data in rows:
        cells = table.add_row().cells
        for cell, val in zip(cells, row_data):
            cell.text = str(val)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)

    doc.add_paragraph("")


def _src_note(doc: Document):
    p = doc.add_paragraph()
    r = p.add_run("Fuente: Base de datos de portabilidad numérica — DG-VRA/CRT")
    r.italic = True
    r.font.size = Pt(8)
    r.font.color.rgb = _GRAY
    doc.add_paragraph("")


def _add_narrative(doc: Document, text: str):
    if not text or not text.strip():
        return
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run(para.replace("\n", " "))
        r.font.size = Pt(11)
        r.font.color.rgb = _BLACK


def _section_heading(doc: Document, num: str, title: str):
    h = doc.add_heading("", level=1)
    h.clear()
    run = h.add_run(f"{num} {title}")
    run.font.color.rgb = _BLUE
    run.font.bold = True
    run.font.size = Pt(13)


def _subsection_heading(doc: Document, num: str, title: str):
    h = doc.add_heading("", level=2)
    h.clear()
    run = h.add_run(f"{num} {title}")
    run.font.color.rgb = _GRAY
    run.font.bold = True
    run.font.size = Pt(11)


# ─── Portada ─────────────────────────────────────────────────────────────────

def _add_portada(doc: Document, ctx, meta: dict):
    doc.add_paragraph("")
    doc.add_paragraph("")

    def _center_run(text, size, bold=False, color=_BLACK, italic=False):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.font.bold  = bold
        r.font.color.rgb = color
        r.font.italic = italic

    _center_run(config.INSTITUCION, 14, bold=True)
    _center_run(config.DEPENDENCIA, 11, bold=True)
    doc.add_paragraph("")
    _center_run("INFORME DE ANÁLISIS DE CUMPLIMIENTO REGULATORIO", 16, bold=True)
    _center_run(config.MEDIDA_NOMBRE, 13, bold=True)
    doc.add_paragraph("")
    doc.add_paragraph("")

    ret60  = meta.get("retornos_60", 0)
    periodo = meta.get("periodo", "2023-2024")
    folio  = f"DG-VRA-{ctx.run_timestamp.strftime('%Y%m%d-%H%M')}"
    fecha  = ctx.run_timestamp.strftime("%d de %B de %Y")

    metadatos = [
        ("Elaborado por",         "Sistema SGIRA — Agentes DG-VRA/CRT"),
        ("Clasificación",         "USO INTERNO — PRELIMINAR"),
        ("Fecha",                 fecha),
        ("Período analizado",     periodo),
        ("Indicadores potenciales", f"{ret60:,} retornos al AEP en <= 60 días naturales"),
        ("Folio",                 folio),
    ]
    for label, value in metadatos:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f"{label}: ")
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = _BLACK
        r2 = p.add_run(value)
        r2.font.size = Pt(10)
        r2.font.color.rgb = _BLACK

    doc.add_paragraph("")
    doc.add_paragraph("")

    aviso = doc.add_paragraph()
    aviso.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = aviso.add_run(
        "CONFIDENCIAL — USO INTERNO. Este documento contiene información preliminar de análisis "
        "regulatorio de la DG-VRA/CRT. Su distribución está restringida al personal autorizado. "
        "No puede ser divulgado, reproducido ni citado sin autorización expresa de la Dirección General."
    )
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = _GRAY


# ─── HITL Disclaimer ─────────────────────────────────────────────────────────

def _add_hitl(doc: Document):
    h = doc.add_paragraph()
    r = h.add_run("AVISO IMPORTANTE — REVISIÓN HUMANA REQUERIDA (Human-in-the-Loop)")
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(0x7B, 0x61, 0x00)
    _shade_para(h, _AMBER_BG)

    body = doc.add_paragraph()
    r = body.add_run(
        "El presente documento ha sido elaborado mediante un sistema multiagente de inteligencia "
        "artificial. Los hallazgos, cifras e interpretaciones aquí contenidos constituyen un análisis "
        "automatizado de carácter estrictamente preliminar. Conforme al principio de supervisión humana "
        "en el uso de tecnologías de inteligencia artificial en procesos regulatorios, los resultados "
        "de este informe requieren revisión, validación y aprobación expresa por parte del personal "
        "técnico y jurídico competente de la Dirección General antes de ser utilizados con fines "
        "regulatorios, sancionatorios o de cualquier naturaleza oficial. Ninguna conclusión de este "
        "documento produce efectos jurídicos por sí misma."
    )
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(0x4A, 0x3C, 0x00)
    _shade_para(body, _AMBER_BG)
    doc.add_paragraph("")


# ─── Tablas temáticas ─────────────────────────────────────────────────────────

def _add_table_calidad(doc: Document, meta: dict):
    total = meta.get("registros_totales", 0)
    def pct(n): return f"{n:,}  ({n/total*100:.2f}%)" if total else str(n)
    rows = [
        ["Registros totales analizados",    f"{total:,}"],
        ["Nulos en número_telefono",         pct(meta.get("nulos_telefono", 0))],
        ["Nulos en fecha_portacion",         pct(meta.get("nulos_fecha", 0))],
        ["Nulos en operador_origen",         pct(meta.get("nulos_origen", 0))],
        ["Nulos en operador_destino",        pct(meta.get("nulos_destino", 0))],
        ["Completitud general estimada",     f"{100 - (meta.get('nulos_telefono',0)/total*100 if total else 0):.2f}%"],
    ]
    _add_table(doc, ["Campo / Métrica", "Resultado"], rows)
    _src_note(doc)


def _add_table_participacion(doc: Document, meta: dict):
    rows = [
        [r["operador"], r["codigo"], f"{r['total']:,}", f"{r['pct']:.2f}%"]
        for r in meta.get("participacion", [])
    ]
    _add_table(doc,
               ["Operador Receptor", "Código", "Portaciones Recibidas", "% del Total"],
               rows)
    _src_note(doc)


def _add_table_hhi(doc: Document, meta: dict):
    rows = [
        ["Índice HHI calculado",       f"{meta.get('hhi', 0):,.1f}"],
        ["Clasificación del mercado",   meta.get("hhi_categoria", "")],
        ["Umbral mercado competitivo",  "HHI < 1,500"],
        ["Umbral mercado concentrado",  "1,500 <= HHI < 2,500"],
        ["Umbral altamente concentrado","HHI >= 2,500"],
    ]
    _add_table(doc, ["Parámetro", "Valor"], rows)
    _src_note(doc)


def _add_table_universo(doc: Document, meta: dict):
    rows = [
        ["Total portaciones TIPO_6 analizadas",          f"{meta.get('total_tipo6', 0):,}"],
        ["Portaciones donde AEP fue donador",             f"{meta.get('aep_donador', 0):,}"],
        ["Pares ida-vuelta identificados (cualquier plazo)", f"{meta.get('pares_total', 0):,}"],
        ["Indicadores potenciales (retorno <= 60 días)", f"{meta.get('retornos_60', 0):,}"],
        ["Tasa de indicadores / salidas AEP",            f"{meta.get('tasa', 0.0):.2f}%"],
        ["Período analizado",                            meta.get("periodo", "")],
    ]
    _add_table(doc, ["Métrica", "Valor"], rows)
    _src_note(doc)


def _add_table_ind_por_op(doc: Document, meta: dict):
    rows = [
        [r["codigo"], r["operador"], f"{r['indicadores']:,}",
         f"{r['pct_total']:.2f}%", f"{r['dias_prom']:.1f}",
         str(r["dias_min"]), str(r["dias_max"])]
        for r in meta.get("ind_por_op", [])
    ]
    _add_table(doc,
               ["Código", "Operador Receptor", "Indicadores", "% Total",
                "Días Prom.", "Días Mín.", "Días Máx."],
               rows)
    _src_note(doc)


def _add_table_dist_dias(doc: Document, meta: dict):
    rows = [
        [r["rango"], f"{r['total']:,}", f"{r['pct']:.2f}%"]
        for r in meta.get("dist_dias", [])
    ]
    _add_table(doc, ["Rango de Días", "Total Indicadores", "% del Total"], rows)
    _src_note(doc)


def _add_table_tendencia(doc: Document, meta: dict):
    rows = [[r["mes"], f"{r['indicadores']:,}"] for r in meta.get("tendencia", [])]
    _add_table(doc, ["Mes", "Indicadores Potenciales"], rows)
    _src_note(doc)


def _add_table_muestra(doc: Document, meta: dict):
    rows = [
        [r["numero_telefono"][-4:].rjust(10, "*"),
         r["fecha_ida"], r["fecha_vuelta"], r["operador_intermedio"], str(r["dias"])]
        for r in meta.get("muestra", [])
    ]
    _add_table(doc,
               ["N.º (parcial)", "Fecha Ida", "Fecha Vuelta", "Operador Intermedio", "Días"],
               rows)
    _src_note(doc)


def _add_table_regresion(doc: Document, meta: dict):
    reg = meta.get("regresion", {})
    rows = [
        ["Pendiente (β₁)",           str(reg.get("pendiente", 0))],
        ["Intercepto (β₀)",          str(reg.get("intercepto", 0))],
        ["Coeficiente R²",           str(reg.get("r_cuadrado", 0))],
        ["P-valor (significancia)",  str(reg.get("p_valor", 1.0))],
        ["Error estándar",           str(reg.get("error_estandar", 0))],
        ["Tendencia observada",      reg.get("tendencia", "estable").capitalize()],
    ]
    _add_table(doc, ["Parámetro Estadístico", "Valor"], rows)
    _src_note(doc)


def _add_table_proyeccion(doc: Document, meta: dict):
    rows = [
        [r["mes"], f"{r['proyeccion']:,}", f"{r['ic_inf']:,}", f"{r['ic_sup']:,}"]
        for r in meta.get("proyeccion", [])
    ]
    _add_table(doc,
               ["Mes Proyectado", "Proyección Central", "IC Inferior (95%)", "IC Superior (95%)"],
               rows)
    _src_note(doc)


# ─── Gráficas matplotlib ──────────────────────────────────────────────────────

def _embed_chart(doc: Document, fig, caption: str):
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    doc.add_picture(buf, width=_CHART_W)
    note = doc.add_paragraph()
    r = note.add_run(f"Fuente: Base de datos de portabilidad numérica — DG-VRA/CRT. {caption}")
    r.italic = True
    r.font.size = Pt(8)
    r.font.color.rgb = _GRAY
    doc.add_paragraph("")


def _chart_tendencia(doc: Document, meta: dict):
    if not _HAS_MPL:
        return
    tend = meta.get("tendencia", [])
    if not tend:
        return
    meses = [r["mes"] for r in tend]
    vals  = [r["indicadores"] for r in tend]
    reg   = meta.get("regresion", {})
    slope = reg.get("pendiente", 0)
    intcp = reg.get("intercepto", 0)
    xs    = list(range(1, len(meses) + 1))
    trend_line = [slope * x + intcp for x in xs]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(meses, vals, color=config.COLOR_PRIMARIO_HEX, linewidth=2,
            marker="o", markersize=4, label="Indicadores mensuales")
    ax.plot(meses, trend_line, color=config.COLOR_SECUNDARIO_HEX,
            linewidth=1.5, linestyle="--", label=f"Tendencia lineal (β={slope:.2f})")
    ax.set_title("Gráfica 1 — Distribución Temporal de Indicadores Potenciales",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Mes")
    ax.set_ylabel("Indicadores potenciales")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    _embed_chart(doc, fig, "Gráfica 1 — Tendencia mensual con regresión lineal.")


def _chart_dist_dias(doc: Document, meta: dict):
    if not _HAS_MPL:
        return
    dist = meta.get("dist_dias", [])
    if not dist:
        return
    rangos = [r["rango"] for r in dist]
    totals = [r["total"] for r in dist]
    pcts   = [r["pct"] for r in dist]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(rangos, totals, color=config.COLOR_PRIMARIO_HEX, alpha=0.85)
    for bar, pct in zip(bars, pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f"{pct:.1f}%", ha="center", va="bottom", fontsize=8,
                color=config.COLOR_SECUNDARIO_HEX)
    ax.set_title("Gráfica 2 — Indicadores Potenciales por Rango de Días",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Rango de días entre portación de ida y retorno al AEP")
    ax.set_ylabel("Total de indicadores")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    _embed_chart(doc, fig, "Gráfica 2 — Distribución de indicadores por rango de días.")


def _chart_operadores(doc: Document, meta: dict):
    if not _HAS_MPL:
        return
    ops = meta.get("ind_por_op", [])
    if not ops:
        return
    nombres = [r["operador"] for r in ops]
    counts  = [r["indicadores"] for r in ops]

    fig, ax = plt.subplots(figsize=(8, max(3, len(nombres) * 0.6)))
    y_pos = range(len(nombres))
    bars  = ax.barh(list(y_pos), counts, color=config.COLOR_PRIMARIO_HEX, alpha=0.85)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(nombres)
    for bar, val in zip(bars, counts):
        ax.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=9)
    ax.set_title("Gráfica 3 — Participación por Operador Receptor Intermedio",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Total de indicadores potenciales")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    _embed_chart(doc, fig, "Gráfica 3 — Indicadores por operador receptor.")


def _chart_proyeccion(doc: Document, meta: dict):
    if not _HAS_MPL:
        return
    tend = meta.get("tendencia", [])
    proy = meta.get("proyeccion", [])
    if not tend or not proy:
        return

    meses_hist = [r["mes"] for r in tend]
    vals_hist  = [r["indicadores"] for r in tend]
    meses_proy = [r["mes"] for r in proy]
    vals_proy  = [r["proyeccion"] for r in proy]
    ic_inf     = [r["ic_inf"] for r in proy]
    ic_sup     = [r["ic_sup"] for r in proy]

    all_meses = meses_hist + meses_proy
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(len(meses_hist)), vals_hist,
            color=config.COLOR_PRIMARIO_HEX, linewidth=2,
            marker="o", markersize=3, label="Histórico")
    offset = len(meses_hist)
    xs_proy = list(range(offset - 1, offset + len(meses_proy)))
    proy_line = [vals_hist[-1]] + vals_proy
    ax.plot(xs_proy, proy_line, color=config.COLOR_SECUNDARIO_HEX,
            linewidth=2, linestyle="--", marker="s", markersize=4, label="Proyección")
    ax.fill_between(range(offset, offset + len(meses_proy)),
                    ic_inf, ic_sup, alpha=0.2, color=config.COLOR_SECUNDARIO_HEX,
                    label="IC 95%")
    tick_labels = meses_hist + meses_proy
    ax.set_xticks(range(len(tick_labels)))
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=7)
    ax.set_title("Gráfica 4 — Proyección de Tendencia a 3 Meses",
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("Indicadores potenciales")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    _embed_chart(doc, fig, "Gráfica 4 — Proyección con intervalo de confianza al 95%.")


# ─── Cierre ───────────────────────────────────────────────────────────────────

def _add_cierre(doc: Document):
    doc.add_page_break()
    for _ in range(4):
        doc.add_paragraph("")

    def _c(text, size=10, bold=False, color=_GRAY):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.font.bold  = bold
        r.font.color.rgb = color

    _c(config.INSTITUCION, 11, bold=True, color=_BLUE)
    _c(config.DEPENDENCIA, 10)
    _c(config.DOMICILIO)
    _c(config.URL_INST)


# ─── Punto de entrada ─────────────────────────────────────────────────────────

def build_word_document(ctx, judge_result=None) -> Path:
    doc  = _open_document()
    meta = ctx.datos_result.metadata if ctx.datos_result else {}
    reg  = _parse(ctx.regulatorio_result)
    red  = _parse(ctx.redactor_result)

    # Portada
    _add_portada(doc, ctx, meta)
    doc.add_page_break()

    # HITL
    _add_hitl(doc)

    # ── 1. Antecedentes ──────────────────────────────────────────────
    _section_heading(doc, "1.", "ANTECEDENTES Y MARCO JURÍDICO")
    _add_narrative(doc, _sec(reg, "s1",
        "La Medida Octogésima Tercera del Instituto Federal de Telecomunicaciones establece "
        "restricciones al Agente Económico Preponderante en materia de contacto comercial "
        "con usuarios portados."))

    # ── 2. Facultades ────────────────────────────────────────────────
    _section_heading(doc, "2.", "FACULTADES DE LA DIRECCIÓN GENERAL")
    _add_narrative(doc, _sec(reg, "s2",
        "La Dirección General de Vigilancia de Regulación Asimétrica tiene atribuciones "
        "para analizar el cumplimiento de medidas asimétricas impuestas al Agente Económico Preponderante."))

    # ── 3. Objeto y Metodología ──────────────────────────────────────
    _section_heading(doc, "3.", "OBJETO Y METODOLOGÍA DEL ANÁLISIS")
    _add_narrative(doc, _sec(red, "s3",
        "El presente análisis tiene por objeto identificar indicadores potenciales de "
        "incumplimiento a la Medida 83 mediante el estudio de pares ida-vuelta en la base "
        "de datos de portabilidad numérica."))

    # ── 4. Calidad de datos ──────────────────────────────────────────
    _section_heading(doc, "4.", "CALIDAD DE LOS DATOS ANALIZADOS")
    _add_narrative(doc, _sec(red, "s4",
        "La base de datos analizada presenta niveles de completitud adecuados para los "
        "propósitos del presente estudio, con nulos marginales en los campos clave."))
    _add_table_calidad(doc, meta)

    # ── 5. Concentración de mercado ──────────────────────────────────
    _section_heading(doc, "5.", "ANÁLISIS DE CONCENTRACIÓN DE MERCADO")
    _add_narrative(doc, _sec(red, "s5",
        "El mercado de portabilidad numérica presenta una estructura altamente concentrada, "
        "lo que confiere especial relevancia a la fiscalización del comportamiento del AEP."))

    _subsection_heading(doc, "5.1", "Participación por Operador Receptor")
    _add_table_participacion(doc, meta)
    _chart_operadores(doc, meta)

    _subsection_heading(doc, "5.2", "Índice de Concentración de Mercado (HHI)")
    _add_narrative(doc, _sec(red, "s5_hhi", ""))
    _add_table_hhi(doc, meta)

    # ── 6. Portabilidad — Indicadores Medida 83 ──────────────────────
    _section_heading(doc, "6.", "ANÁLISIS DE PORTABILIDAD — INDICADORES MEDIDA 83")
    _add_narrative(doc, _sec(red, "s6", ""))

    _subsection_heading(doc, "6.1", "Universo Regulatorio")
    _add_narrative(doc, _sec(red, "s6_1", ""))
    _add_table_universo(doc, meta)

    _subsection_heading(doc, "6.2", "Indicadores Potenciales por Operador Receptor")
    _add_narrative(doc, _sec(red, "s6_2", ""))
    _add_table_ind_por_op(doc, meta)

    _subsection_heading(doc, "6.3", "Distribución por Rango de Días")
    _add_narrative(doc, _sec(red, "s6_3", ""))
    _add_table_dist_dias(doc, meta)
    _chart_dist_dias(doc, meta)

    _subsection_heading(doc, "6.4", "Distribución Temporal de Indicadores")
    _add_narrative(doc, _sec(red, "s6_4", ""))
    _add_table_tendencia(doc, meta)
    _chart_tendencia(doc, meta)

    _subsection_heading(doc, "6.5", "Muestra de Casos con Mayor Inmediatez de Retorno")
    _add_narrative(doc, _sec(red, "s6_5", ""))
    _add_table_muestra(doc, meta)

    # ── 7. Análisis estadístico ───────────────────────────────────────
    _section_heading(doc, "7.", "ANÁLISIS ESTADÍSTICO DE TENDENCIA TEMPORAL")
    _add_narrative(doc, _sec(red, "s7", ""))
    _add_table_regresion(doc, meta)

    _subsection_heading(doc, "7.1", "Proyección a 3 Meses")
    _add_narrative(doc, _sec(red, "s7_1", ""))
    _add_table_proyeccion(doc, meta)
    _chart_proyeccion(doc, meta)

    # ── 8. AIR ───────────────────────────────────────────────────────
    _section_heading(doc, "8.", "ANÁLISIS DE IMPACTO REGULATORIO (AIR)")
    _add_narrative(doc, _sec(red, "s8",
        "El Análisis de Impacto Regulatorio de la Medida 83 indica que la medida asimétrica "
        "cumple con los objetivos de política pública para los que fue diseñada."))

    # ── 9. Conclusiones ───────────────────────────────────────────────
    _section_heading(doc, "9.", "CONCLUSIONES Y PROPUESTA DE RESOLUCIÓN")
    _add_narrative(doc, _sec(red, "s9", ""))

    _subsection_heading(doc, "9.1", "Escenario A — Modificar la Medida")
    _add_narrative(doc, _sec(red, "s9_1", ""))

    _subsection_heading(doc, "9.2", "Escenario B — Mantener la Medida")
    _add_narrative(doc, _sec(red, "s9_2", ""))

    _subsection_heading(doc, "9.3", "Escenario C — Eliminar la Medida")
    _add_narrative(doc, _sec(red, "s9_3", ""))

    _subsection_heading(doc, "9.4", "Recomendación Institucional de la DG-VRA")
    _add_narrative(doc, _sec(red, "s9_4", ""))

    # Cierre
    _add_cierre(doc)

    # Guardar
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ts = ctx.run_timestamp.strftime("%Y%m%d_%H%M%S")
    output_path = config.DOCS_DIR / f"DG-VRA_Medida83_{ts}.docx"
    doc.save(str(output_path))
    logger.info(f"Documento guardado: {output_path}")
    return output_path
