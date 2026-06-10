# File: MyDentalPortal/blueprints/utils/chart_pdf.py
# Build a printable PDF of a patient's dental chart with reportlab (pure-Python).
#
# This re-creates the on-screen FDI (ISO 3950) cross-layout chart as closely as
# a flat PDF allows: the upper arch (deciduous row above the permanent row) sits
# above an occlusal line, the lower arch (permanent row above the deciduous row)
# below it. Each tooth is a circle split into four segments (mesial/distal/
# buccal/lingual) plus a centre, coloured exactly as saved on the chart, with the
# typed status code in a box and the tooth number beneath/above it. The legend
# and the periodontal/occlusion/appliance/TMD/X-ray assessments follow.
#
# The chart's saved data is read defensively: the live chart scatters colours and
# status codes across slightly different keys ("18", "temp_55", "temp-55"), so we
# merge every candidate key for a tooth rather than assume one shape.

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.graphics.shapes import Drawing, Circle, Wedge, Rect, String, Line

_BLUE = colors.HexColor('#0d6efd')
_INK = colors.HexColor('#333333')
_AXIS = colors.HexColor('#999999')
_GENDER = {'M': 'Male', 'F': 'Female'}

# Segment colours mirror the chart CSS (.tooth-segment.blue/.red/.light_red).
_SEG_FILL = {
    'blue': colors.HexColor('#0d6efd'),
    'red': colors.HexColor('#dc3545'),
    'light_red': colors.HexColor('#e6abb1'),
}

# Angular span (degrees, CCW from +x) of each segment — matched to the SVG paths
# in dental_chart.html: buccal=right, mesial=top, lingual=left, distal=bottom.
_SEG_ANGLES = {
    'buccal': (-45, 45),
    'mesial': (45, 135),
    'lingual': (135, 225),
    'distal': (225, 315),
}

# Tooth ordering left→right across the page (mirrors the cross layout).
_UPPER_PERM = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
_LOWER_PERM = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]
_UPPER_TEMP = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65]
_LOWER_TEMP = [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]


def _seg_color(v):
    return _SEG_FILL.get(v, colors.white)


def _tooth_info(teeth, n, temp):
    """Merge status text + segment colours for one tooth across candidate keys."""
    keys = ['temp_%d' % n, 'temp-%d' % n, str(n)] if temp else [str(n)]
    status, cmap = '', {}
    for k in keys:
        d = teeth.get(k)
        if not isinstance(d, dict):
            continue
        for f in ('upper_status', 'lower_status', 'temp_status'):
            if d.get(f):
                status = d[f]
        c = d.get('colors')
        if isinstance(c, dict):
            for seg, val in c.items():
                if val:
                    cmap[seg] = val
    return status, cmap


def _draw_tooth(d, cx, cy, r, cmap):
    for seg, (a0, a1) in _SEG_ANGLES.items():
        w = Wedge(cx, cy, r, a0, a1)
        w.fillColor = _seg_color(cmap.get(seg))
        w.strokeColor = _INK
        w.strokeWidth = 0.5
        d.add(w)
    center = Circle(cx, cy, r * 0.34)
    center.fillColor = _seg_color(cmap.get('center'))
    center.strokeColor = _INK
    center.strokeWidth = 0.5
    d.add(center)
    ring = Circle(cx, cy, r)
    ring.fillColor = None
    ring.strokeColor = _INK
    ring.strokeWidth = 0.8
    d.add(ring)


def _draw_status(d, cx, cy, text):
    bw, bh = 22, 13
    d.add(Rect(cx - bw / 2.0, cy - bh / 2.0, bw, bh,
               fillColor=colors.white, strokeColor=_INK, strokeWidth=0.5))
    if text:
        d.add(String(cx, cy - 3.5, escape(str(text)[:4]),
                     textAnchor='middle', fontSize=7, fillColor=_INK))


def _draw_number(d, cx, cy, n):
    d.add(String(cx, cy - 3, str(n), textAnchor='middle',
                 fontSize=7, fillColor=_INK))


def _draw_row(d, teeth, cx0, spacing, cy, r, orientation, temp, teeth_status):
    for i, n in enumerate(teeth):
        cx = cx0 + i * spacing
        status, cmap = _tooth_info(teeth_status, n, temp)
        _draw_tooth(d, cx, cy, r, cmap)
        if orientation == 'upper':       # status above the circle
            _draw_number(d, cx, cy + r + 7, n)
            _draw_status(d, cx, cy + r + 18, status)
        else:                             # status below the circle
            _draw_number(d, cx, cy - r - 7, n)
            _draw_status(d, cx, cy - r - 18, status)


def _build_chart_drawing(chart):
    teeth_status = (chart or {}).get('teeth_status', {}) or {}
    W, H = 720, 350
    d = Drawing(W, H)
    r, spacing = 12, 42

    perm_x0 = (W - (len(_UPPER_PERM) - 1) * spacing) / 2.0   # centred 16-tooth arch
    temp_x0 = (W - (len(_UPPER_TEMP) - 1) * spacing) / 2.0   # centred 10-tooth arch

    cy_upper_temp = 300
    cy_upper_perm = 235
    occlusal_y = 205
    cy_lower_perm = 175
    cy_lower_temp = 110

    # Cross axes (faint, like the on-screen chart).
    d.add(Line(40, occlusal_y, W - 40, occlusal_y, strokeColor=_AXIS, strokeWidth=1))
    d.add(Line(W / 2.0, 70, W / 2.0, 335, strokeColor=_AXIS, strokeWidth=1))

    # Upper arch: deciduous row above permanent row, status codes above each.
    _draw_row(d, _UPPER_TEMP, temp_x0, spacing, cy_upper_temp, r, 'upper', True, teeth_status)
    _draw_row(d, _UPPER_PERM, perm_x0, spacing, cy_upper_perm, r, 'upper', False, teeth_status)
    # Lower arch: permanent row above deciduous row, status codes below each.
    _draw_row(d, _LOWER_PERM, perm_x0, spacing, cy_lower_perm, r, 'lower', False, teeth_status)
    _draw_row(d, _LOWER_TEMP, temp_x0, spacing, cy_lower_temp, r, 'lower', True, teeth_status)
    return d


# ── legend + assessment helpers ──────────────────────────────────────────────
_LEGEND = [
    ('Condition', [
        ('✓', 'Present Teeth'), ('D', 'Decayed (for Filling)'),
        ('M', 'Missing (Caries)'), ('MO', 'Missing (Other)'),
        ('Im', 'Impacted'), ('Sp', 'Supernumerary'),
        ('Rf', 'Root Fragment'), ('Un', 'Unerupted'),
    ]),
    ('Restorations & Prosthetics', [
        ('Am', 'Amalgam Filling'), ('Co', 'Composite Filling'),
        ('JC', 'Jacket Crown'), ('Ab', 'Abutment'), ('Att', 'Attachment'),
        ('P', 'Pontic'), ('In', 'Inlay'), ('Imp', 'Implant'),
        ('S', 'Sealants'), ('Rm', 'Removable Denture'),
    ]),
    ('Surgery', [
        ('X', 'Extraction (Caries)'), ('XO', 'Extraction (Other)'),
    ]),
]


def _mark(v):
    return '☑' if v else '☐'   # checked / empty box


def build_chart_pdf(patient, clinic, chart):
    """Return a BytesIO PDF of the dental chart. All values are XML-escaped."""
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=10)
    title = ParagraphStyle('title', parent=styles['Heading1'], fontSize=16)
    section = ParagraphStyle('section', parent=styles['Heading2'], fontSize=11,
                             textColor=_BLUE, spaceBefore=8, spaceAfter=3)

    pi = patient.get('personal_info', {}) or {}
    full = ('%s %s' % (pi.get('first_name', ''), pi.get('last_name', ''))).strip()

    story = [Paragraph('Dental Chart', title)]
    info = '%s &nbsp;|&nbsp; Age: %s &nbsp;|&nbsp; %s &nbsp;|&nbsp; %s' % (
        escape(full or '—'),
        escape(str(pi.get('age', '—'))),
        _GENDER.get(pi.get('gender'), '—'),
        escape(clinic.get('name', '')),
    )
    story.append(Paragraph(info, small))
    story.append(Spacer(1, 6))

    drawing = _build_chart_drawing(chart)
    drawing.hAlign = 'CENTER'
    story.append(drawing)
    story.append(Spacer(1, 4))

    # ── Legend (3 columns) ──
    story.append(Paragraph('Legend', section))
    legend_cols = []
    for heading, items in _LEGEND:
        lines = '<br/>'.join('<b>%s</b>&nbsp; %s' % (escape(code), escape(label))
                             for code, label in items)
        legend_cols.append(Paragraph('<b>%s</b><br/>%s' % (escape(heading), lines), small))
    lt = Table([legend_cols], colWidths=[2.3 * inch] * 3)
    lt.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(lt)

    # ── Assessments ──
    perio = (chart or {}).get('periodontal_screening', {}) or {}
    occ = (chart or {}).get('occlusion', {}) or {}
    app = (chart or {}).get('appliances', {}) or {}
    tmd = (chart or {}).get('tmd_assessment', {}) or {}
    xray = (chart or {}).get('xray_taken', {}) or {}

    def block(heading, lines):
        body = '<br/>'.join(lines) if lines else '—'
        return Paragraph('<b>%s</b><br/>%s' % (escape(heading), body), small)

    perio_lines = [
        '%s Gingivitis' % _mark(perio.get('gingivitis')),
        '%s Early Periodontitis' % _mark(perio.get('early_periodontitis')),
        '%s Moderate Periodontitis' % _mark(perio.get('moderate_periodontitis')),
        '%s Advanced Periodontitis' % _mark(perio.get('advanced_periodontitis')),
    ]
    occ_lines = [
        'Class (Molar): %s' % escape(occ.get('class_molar') or '—'),
        'Overjet: %s' % escape(occ.get('overjet') or '—'),
        'Overbite: %s' % escape(occ.get('overbite') or '—'),
        'Midline Dev.: %s' % escape(occ.get('midline_deviation') or '—'),
        '%s Crossbite' % _mark(occ.get('crossbite')),
    ]
    app_lines = [
        '%s Orthodontic' % _mark(app.get('orthodontic')),
        '%s Stayplate' % _mark(app.get('stayplate')),
        'Others: %s' % escape(app.get('others') or '—'),
    ]
    tmd_lines = [
        '%s Clenching' % _mark(tmd.get('clenching')),
        '%s Clicking' % _mark(tmd.get('clicking')),
        '%s Trismus' % _mark(tmd.get('trismus')),
        '%s Muscle Spasm' % _mark(tmd.get('muscle_spasm')),
    ]

    story.append(Paragraph('Assessment', section))
    at = Table([[
        block('Periodontal Screening', perio_lines),
        block('Occlusion', occ_lines),
        block('Appliances', app_lines),
        block('TMD', tmd_lines),
    ]], colWidths=[1.725 * inch] * 4)
    at.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, _INK),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e3e6ea')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(at)

    def xr(key, label, extra=''):
        seg = xray.get(key, {}) or {}
        bits = [_mark(seg.get('taken')) + ' ' + label]
        if seg.get('tooth_number'):
            bits.append('Tooth %s' % escape(str(seg['tooth_number'])))
        if seg.get('upper_lower'):
            bits.append(escape(str(seg['upper_lower'])))
        if seg.get('type'):
            bits.append(escape(str(seg['type'])))
        if seg.get('date'):
            bits.append(escape(str(seg['date'])))
        return ' &nbsp; '.join(bits)

    xray_lines = [
        xr('periapical', 'Periapical'),
        xr('panoramic', 'Panoramic'),
        xr('cephalometric', 'Cephalometric'),
        xr('occlusal', 'Occlusal'),
        xr('others', 'Others'),
    ]
    story.append(Paragraph('X-ray Taken', section))
    story.append(Paragraph('<br/>'.join(xray_lines), small))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(LETTER), title='Dental Chart',
        topMargin=0.4 * inch, bottomMargin=0.4 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    doc.build(story)
    buf.seek(0)
    return buf
