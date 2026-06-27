"""
report_generator.py — Generatore PDF OSINT per face_recognition-ng

Produce un report PDF con design dark-tech dato il risultato di /osint/full.
Uso standalone:
    python report_generator.py --data result.json --out report.pdf
Uso da API:
    from report_generator import build_pdf
    pdf_bytes = build_pdf(osint_data, target_image_bytes)
"""

import io
import json
import argparse
import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

W, H = A4

# ── Palette ─────────────────────────────────────────────────────────────────
BG      = HexColor("#0d1117")
SURFACE = HexColor("#161b22")
CARD    = HexColor("#1f2937")
CYAN    = HexColor("#00e5ff")
VIOLET  = HexColor("#7c3aed")
GREEN   = HexColor("#00ff9f")
ORANGE  = HexColor("#ff6b35")
YELLOW  = HexColor("#ffd166")
RED     = HexColor("#ef233c")
WHITE   = HexColor("#f0f6fc")
MUTED   = HexColor("#8b949e")


def _S(name: str, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)


# ── Stili testo ──────────────────────────────────────────────────────────────
sTitle   = _S("Title",   fontSize=26, fontName="Helvetica-Bold", textColor=WHITE,   alignment=TA_CENTER, spaceAfter=4, leading=32)
sSubtitle= _S("Sub",     fontSize=12, fontName="Helvetica",      textColor=CYAN,    alignment=TA_CENTER, spaceAfter=3, leading=16)
sMeta    = _S("Meta",    fontSize=8,  fontName="Helvetica",      textColor=MUTED,   alignment=TA_CENTER, spaceAfter=2)
sH1      = _S("H1",      fontSize=18, fontName="Helvetica-Bold", textColor=CYAN,    spaceBefore=12, spaceAfter=5, leading=22)
sH2      = _S("H2",      fontSize=13, fontName="Helvetica-Bold", textColor=YELLOW,  spaceBefore=8,  spaceAfter=4, leading=16)
sH3      = _S("H3",      fontSize=10, fontName="Helvetica-Bold", textColor=GREEN,   spaceBefore=5,  spaceAfter=3, leading=13)
sBody    = _S("Body",    fontSize=9,  fontName="Helvetica",      textColor=WHITE,   spaceAfter=4, leading=13, alignment=TA_JUSTIFY)
sBullet  = _S("Bullet",  fontSize=9,  fontName="Helvetica",      textColor=WHITE,   leftIndent=14, spaceAfter=3, leading=12, bulletIndent=4, bulletText=">")
sCaption = _S("Caption", fontSize=7.5,fontName="Helvetica-Oblique",textColor=MUTED, alignment=TA_CENTER, spaceAfter=4)
sCode    = _S("Code",    fontSize=8,  fontName="Courier",        textColor=GREEN,   backColor=SURFACE, leftIndent=10, rightIndent=10, spaceAfter=5, leading=12, borderPad=6)
sWarn    = _S("Warn",    fontSize=8,  fontName="Helvetica-Oblique",textColor=ORANGE, leftIndent=10, spaceAfter=3, leading=11)
sLabel   = _S("Label",   fontSize=8,  fontName="Helvetica-Bold", textColor=MUTED,   alignment=TA_CENTER)


def _dark_table(header_col=VIOLET):
    return TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  header_col),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0),  9),
        ("ALIGN",         (0,0), (-1,-1), "LEFT"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [SURFACE, CARD]),
        ("TEXTCOLOR",     (0,1), (-1,-1), WHITE),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 8.5),
        ("GRID",          (0,0), (-1,-1), 0.4, HexColor("#2e3350")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ])


class _PageDeco:
    """Callback per header/footer dark su ogni pagina."""
    def __call__(self, canv, doc):
        canv.saveState()
        canv.setFillColor(BG)
        canv.rect(0, 0, W, H, fill=1, stroke=0)
        canv.setFillColor(VIOLET)
        canv.rect(0, H-8*mm, W, 8*mm, fill=1, stroke=0)
        canv.setFillColor(CYAN)
        canv.rect(0, H-10*mm, 55*mm, 2*mm, fill=1, stroke=0)
        canv.setFillColor(SURFACE)
        canv.rect(0, 0, W, 10*mm, fill=1, stroke=0)
        canv.setFillColor(CYAN)
        canv.rect(0, 9.5*mm, W, 0.5*mm, fill=1, stroke=0)
        canv.setFont("Helvetica", 7)
        canv.setFillColor(MUTED)
        canv.drawString(15*mm, 3.5*mm, "face_recognition-ng  |  OSINT Report")
        canv.setFillColor(CYAN)
        canv.drawRightString(W-15*mm, 3.5*mm, f"Pagina {doc.page}")
        canv.setFillColor(VIOLET)
        canv.rect(0, 10*mm, 3*mm, H-18*mm, fill=1, stroke=0)
        canv.restoreState()


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _make_radar_chart(sources: dict) -> io.BytesIO:
    labels = list(sources.keys())
    vals   = list(sources.values())
    N = len(labels)
    vals_plot = vals + vals[:1]
    angles = [n/N*2*np.pi for n in range(N)] + [0]
    fig, ax = plt.subplots(figsize=(5,5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    ax.plot(angles, vals_plot, color="#00e5ff", linewidth=2)
    ax.fill(angles, vals_plot, color="#00e5ff", alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color="#f0f6fc", size=8)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25","50","75","100"], color="#8b949e", size=6)
    ax.grid(color="#8b949e", alpha=0.3)
    ax.spines["polar"].set_color("#8b949e")
    ax.set_title("Efficacia fonti OSINT", color="#f0f6fc", size=11, pad=14)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_social_bar(platforms: list) -> io.BytesIO:
    names  = [p["platform"] for p in platforms]
    found  = [1 if p.get("found") else 0 for p in platforms]
    colors = ["#00ff9f" if f else "#ef233c" for f in found]
    fig, ax = plt.subplots(figsize=(8, max(2.5, len(names)*0.45)))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    bars = ax.barh(names, [1]*len(names), color=colors, edgecolor="#2e3350", height=0.5)
    ax.set_xlim(0, 1.3)
    ax.set_xticks([])
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, color="#f0f6fc", size=9)
    ax.spines[:].set_visible(False)
    for i, (bar, f) in enumerate(zip(bars, found)):
        label = "TROVATO" if f else "NON TROVATO"
        color = "#00ff9f" if f else "#ef233c"
        ax.text(0.05, i, label, va="center", ha="left", color=color, fontsize=8, fontweight="bold")
    ax.set_title("Stato profili social", color="#f0f6fc", size=11, pad=10)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_pipeline_chart() -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(11, 3))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.set_xlim(0, 11); ax.set_ylim(0, 3); ax.axis("off")
    steps = [
        (0.9,  "1\nInput\nImmagine",   "#7c3aed"),
        (2.7,  "2\nRilevamento\nVolto", "#0ea5e9"),
        (4.5,  "3\nEncoding\n512D",     "#00ff9f"),
        (6.3,  "4\nOSINT\nSearch",      "#ff6b35"),
        (8.1,  "5\nSocial\nLookup",     "#ffd166"),
        (9.9,  "6\nReport\nPDF",        "#00e5ff"),
    ]
    def hexrgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2],16)/255 for i in (0,2,4))
    for i, (x, txt, col) in enumerate(steps):
        circ = plt.Circle((x, 1.5), 0.55, color=(*hexrgb(col), 0.2), ec=col, lw=2, zorder=3)
        ax.add_patch(circ)
        ax.text(x, 1.5, txt, ha="center", va="center", color="#f0f6fc", fontsize=7,
                fontweight="bold", linespacing=1.4, zorder=4)
        if i < len(steps)-1:
            ax.annotate("", xy=(steps[i+1][0]-0.57, 1.5), xytext=(x+0.57, 1.5),
                        arrowprops=dict(arrowstyle="->", color="#8b949e", lw=1.5))
    fig.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


def _make_risk_gauge(risk_score: float) -> io.BytesIO:
    """Gauge semicircolare per risk_score (0.0 – 1.0)."""
    fig, ax = plt.subplots(figsize=(4, 2.2))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.axis("off")

    theta_bg = np.linspace(np.pi, 0, 200)
    ax.plot(np.cos(theta_bg)*0.85, np.sin(theta_bg)*0.85, color="#2e3350", lw=12)

    if risk_score < 0.4:
        arc_color, label = "#00ff9f", "BASSO"
    elif risk_score < 0.7:
        arc_color, label = "#ffd166", "MEDIO"
    else:
        arc_color, label = "#ef233c", "ALTO"

    end_angle = np.pi - risk_score * np.pi
    theta_fill = np.linspace(np.pi, end_angle, 200)
    ax.plot(np.cos(theta_fill)*0.85, np.sin(theta_fill)*0.85, color=arc_color, lw=12)

    ax.text(0, 0.1, f"{risk_score:.0%}", ha="center", va="center",
            color=arc_color, fontsize=20, fontweight="bold")
    ax.text(0, -0.28, f"RISK: {label}", ha="center", va="center",
            color=arc_color, fontsize=9, fontweight="bold")

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-0.45, 1.0)
    fig.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── Builder principale ────────────────────────────────────────────────────────

_REVERSE_META_KEYS = frozenset({
    "faces_detected", "face_cropped", "image_hash",
    "timestamp", "total_results", "external_calls", "from_cache", "sources",
})


def build_pdf(
    osint_data: dict,
    target_image_bytes: Optional[bytes] = None,
) -> bytes:
    """
    Genera il PDF OSINT e restituisce i bytes.

    Args:
        osint_data: dizionario restituito da /osint/full (include risk_score)
        target_image_bytes: bytes JPEG/PNG del volto target (opzionale)
    """
    buf = io.BytesIO()
    deco = _PageDeco()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=14*mm,
        topMargin=22*mm, bottomMargin=18*mm,
    )

    story = []
    now        = datetime.datetime.now().strftime("%d %B %Y  %H:%M")
    target     = osint_data.get("target_name", "Target Sconosciuto")
    faces      = osint_data.get("faces_detected", 0)
    reverse    = osint_data.get("reverse_image", {})
    social     = osint_data.get("social", {})
    osint_links= osint_data.get("osint_links", {})
    variants   = osint_data.get("username_variants", [])
    maigret    = osint_data.get("maigret") or {}
    risk_score = float(osint_data.get("risk_score", 0.0))

    # ─── COPERTINA ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 12*mm))

    cover_data = [
        [Paragraph('<font color="#00e5ff"><b>OSINT Report</b></font>', sTitle)],
        [Paragraph(f'Target: <b>{target}</b>', sSubtitle)],
        [Paragraph(f'Generato il {now}', sMeta)],
        [Paragraph('face_recognition-ng  |  Confidenziale', sMeta)],
    ]
    ct = Table(cover_data, colWidths=[W-34*mm])
    ct.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), SURFACE),
        ("GRID",          (0,0), (-1,-1), 1.5, CYAN),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(ct)
    story.append(Spacer(1, 6*mm))

    # KPI cards
    platforms_list = []
    if isinstance(social, dict) and "platforms" in social:
        platforms_list = social["platforms"]
    elif isinstance(social, list):
        platforms_list = social

    kpi_items = [
        ("Volti rilevati",     str(faces),           CYAN),
        ("Fonti OSINT",        str(len(reverse.get("sources", reverse))), ORANGE),
        ("Profili social",     str(len(platforms_list)), GREEN),
        ("Username variants",  str(len(variants)),   VIOLET),
    ]
    kpi_cells = []
    for label, val, col in kpi_items:
        t = Table(
            [[Paragraph(f'<font color="{col.hexval()}" size="20"><b>{val}</b></font>', sLabel)],
             [Paragraph(f'<font color="#8b949e" size="8">{label}</font>', sLabel)]],
            colWidths=[38*mm],
        )
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), CARD),
            ("GRID",          (0,0), (-1,-1), 1, col),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ]))
        kpi_cells.append(t)

    kpi_row = Table([kpi_cells], colWidths=[40*mm]*4, hAlign="CENTER")
    kpi_row.setStyle(TableStyle([
        ("ALIGN",  (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]))

    # Gauge risk_score
    gauge_buf = _make_risk_gauge(risk_score)
    gauge_img = RLImage(gauge_buf, width=50*mm, height=28*mm)

    if target_image_bytes:
        img_buf  = io.BytesIO(target_image_bytes)
        face_img = RLImage(img_buf, width=40*mm, height=40*mm)
        layout   = Table(
            [[face_img, kpi_row, gauge_img]],
            colWidths=[44*mm, W-34*mm-44*mm-54*mm, 54*mm],
        )
    else:
        layout = Table(
            [[kpi_row, gauge_img]],
            colWidths=[W-34*mm-54*mm, 54*mm],
        )
    layout.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(layout)
    story.append(Spacer(1, 5*mm))

    pipe_buf = _make_pipeline_chart()
    story.append(RLImage(pipe_buf, width=W-34*mm, height=(W-34*mm)*0.26))
    story.append(Paragraph("Pipeline OSINT eseguita su questo target", sCaption))
    story.append(PageBreak())

    # ─── PAGINA 2: REVERSE IMAGE SEARCH ─────────────────────────────────────
    story.append(Paragraph("1. Reverse Image Search", sH1))
    story.append(HRFlowable(width="100%", thickness=1, color=ORANGE, spaceAfter=5))
    story.append(Paragraph(
        "Ricerca del volto target su motori di immagini pubblici. "
        "I link seguenti aprono direttamente la ricerca con il volto ritagliato.", sBody))

    # Tabella risultati per fonte da sources dict (dati reali)
    sources_dict = reverse.get("sources", {}) if isinstance(reverse, dict) else {}
    if sources_dict:
        src_rows = [["Fonte", "N. risultati", "Search URL", "Stato"]]
        for src_name, src_data in sources_dict.items():
            n   = len(src_data.get("results", []))
            err = src_data.get("error")
            url = src_data.get("search_url", "")
            src_rows.append([
                src_name.replace("_"," ").title(),
                str(n),
                Paragraph(f'<font size="6.5" color="#00e5ff">{str(url)[:60]}</font>', sBody) if url else "—",
                Paragraph('<font color="#ef233c">Errore</font>', sBody) if err
                else Paragraph('<font color="#00ff9f">OK</font>', sBody),
            ])
        src_t = Table(src_rows, colWidths=[35*mm, 20*mm, 90*mm, 15*mm])
        src_t.setStyle(_dark_table(ORANGE))
        story.append(src_t)
    else:
        story.append(Paragraph("Nessun risultato reverse image disponibile.", sWarn))

    story.append(Spacer(1, 5*mm))
    source_scores = {
        "Google Lens": 90, "Yandex": 85, "TinEye": 75, "PimEyes": 95, "Bing Visual": 70,
    }
    radar_buf = _make_radar_chart(source_scores)
    story.append(RLImage(radar_buf, width=80*mm, height=80*mm))
    story.append(Paragraph("Fig. 1 — Score di efficacia per motore di ricerca", sCaption))
    story.append(PageBreak())

    # ─── PAGINA 3: SOCIAL MEDIA ──────────────────────────────────────────────
    story.append(Paragraph("2. Ricerca Social Media", sH1))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#ec4899"), spaceAfter=5))

    if platforms_list:
        soc_rows = [["Piattaforma", "URL trovato", "Stato"]]
        for p in platforms_list:
            soc_rows.append([
                p.get("platform", ""),
                Paragraph(f'<font size="7" color="#00e5ff">{p.get("url","—")[:70]}</font>', sBody),
                Paragraph('<font color="#00ff9f">TROVATO</font>', sBody) if p.get("found")
                else Paragraph('<font color="#ef233c">Non trovato</font>', sBody),
            ])
        soc_t = Table(soc_rows, colWidths=[35*mm, 100*mm, 25*mm])
        soc_t.setStyle(_dark_table(HexColor("#ec4899")))
        story.append(soc_t)
        story.append(Spacer(1, 4*mm))
        bar_buf = _make_social_bar(platforms_list)
        story.append(RLImage(bar_buf, width=W-34*mm, height=max(35*mm, len(platforms_list)*8*mm)))
        story.append(Paragraph("Fig. 2 — Stato profili social per piattaforma", sCaption))
    else:
        story.append(Paragraph("Nessun dato social disponibile.", sWarn))

    if osint_links:
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("2.1  Link OSINT Diretti", sH2))
        link_rows = [["Tipo", "Query / URL"]]
        for k, v in osint_links.items():
            link_rows.append([
                k.replace("_"," ").title(),
                Paragraph(f'<font size="7" color="#00e5ff">{str(v)[:90]}</font>', sBody),
            ])
        lt = Table(link_rows, colWidths=[40*mm, 120*mm])
        lt.setStyle(_dark_table(HexColor("#0ea5e9")))
        story.append(lt)
    story.append(PageBreak())

    # ─── PAGINA 4: MAIGRET USERNAME DISCOVERY ───────────────────────────────
    story.append(Paragraph("3. Username Discovery — Maigret", sH1))
    story.append(HRFlowable(width="100%", thickness=1, color=CYAN, spaceAfter=5))
    story.append(Paragraph("3.1  Varianti username generate", sH2))
    if variants:
        story.append(Paragraph(
            f'<font name="Courier" color="#00ff9f">{"  |  ".join(variants)}</font>', sBody))
    else:
        story.append(Paragraph("Nessuna variante generata.", sWarn))

    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("3.2  Risultati Maigret", sH2))
    if maigret:
        found_sites = []
        if isinstance(maigret, dict):
            for username, data in maigret.items():
                results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for site in results:
                    found_sites.append({"username": username, **site})
        if found_sites:
            mg_rows = [["Username", "Sito", "Categoria", "URL"]]
            for s in found_sites[:30]:
                mg_rows.append([
                    s.get("username", ""),
                    s.get("site", ""),
                    s.get("category", "—"),
                    Paragraph(f'<font size="6.5" color="#00e5ff">{s.get("url","—")[:55]}</font>', sBody),
                ])
            mg_t = Table(mg_rows, colWidths=[28*mm, 35*mm, 30*mm, 68*mm])
            mg_t.setStyle(_dark_table(CYAN))
            story.append(mg_t)
        else:
            story.append(Paragraph("Maigret eseguito ma nessun profilo confermato.", sWarn))
    else:
        story.append(Paragraph("Maigret non eseguito (run_maigret=False o non installato).", sWarn))

    story.append(Spacer(1, 6*mm))

    # ─── NOTE LEGALI ─────────────────────────────────────────────────────────
    story.append(Paragraph("4. Note Legali", sH1))
    story.append(HRFlowable(width="100%", thickness=1, color=RED, spaceAfter=5))
    legal = Table(
        [[Paragraph(
            "<b>AVVERTENZA:</b> Questo report e' destinato esclusivamente a indagini "
            "legalmente autorizzate. L'uso non autorizzato costituisce violazione del "
            "GDPR (Reg. UE 2016/679) e del D.Lgs. 196/2003. "
            "L'autore declina ogni responsabilita' per usi impropri.",
            _S("LT", fontSize=8, fontName="Helvetica", textColor=ORANGE,
               leading=12, alignment=TA_JUSTIFY))]],
        colWidths=[W-34*mm],
    )
    legal.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), HexColor("#1a0a00")),
        ("GRID",          (0,0), (-1,-1), 1.5, RED),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    story.append(legal)

    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# ── CLI standalone ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera un PDF OSINT da un file JSON di risultati")
    parser.add_argument("--data",  required=True, help="Path al file JSON con i dati OSINT")
    parser.add_argument("--image", default=None,  help="Path opzionale all'immagine del target")
    parser.add_argument("--out",   default="osint_report.pdf", help="Path del PDF di output")
    args = parser.parse_args()
    with open(args.data) as f:
        data = json.load(f)
    img_bytes = None
    if args.image:
        with open(args.image, "rb") as f:
            img_bytes = f.read()
    pdf = build_pdf(data, img_bytes)
    with open(args.out, "wb") as f:
        f.write(pdf)
    print(f"PDF salvato: {args.out}  ({len(pdf)//1024} KB)")
