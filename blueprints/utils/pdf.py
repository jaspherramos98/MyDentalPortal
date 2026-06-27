# File: MyDentalPortal/blueprints/utils/pdf.py
# Build a printable PDF of a patient record with reportlab (pure-Python).

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)

_GENDER = {'M': 'Male', 'F': 'Female'}
_BLUE = colors.HexColor('#0d6efd')
_LINE = colors.HexColor('#e3e6ea')


def _yesno(v):
    return 'Yes' if v == 'yes' else 'No'


def _photo_flowable(photo_bytes):
    """Return a square Image flowable for the patient photo, or None.

    Pillow normalises the bytes to PNG so reportlab never chokes on an exotic
    format (HEIC/WEBP) and any embedded badness is dropped in re-encoding.
    """
    if not photo_bytes:
        return None
    try:
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(photo_bytes))
        im = im.convert('RGB')
        # Centre-crop to a square so it sits neatly in the corner.
        w, h = im.size
        side = min(w, h)
        im = im.crop(((w - side) // 2, (h - side) // 2,
                      (w - side) // 2 + side, (h - side) // 2 + side))
        out = io.BytesIO()
        im.save(out, format='PNG')
        out.seek(0)
        return Image(out, width=1.1 * inch, height=1.1 * inch)
    except Exception:
        return None


def build_patient_pdf(patient, clinic, photo_bytes=None):
    """Return a BytesIO PDF of the patient record. All values are XML-escaped."""
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    title = ParagraphStyle('title', parent=styles['Heading1'], fontSize=18)
    name_style = ParagraphStyle('name', parent=styles['Heading2'], fontSize=14)
    section = ParagraphStyle('section', parent=styles['Heading2'], fontSize=12,
                             textColor=_BLUE, spaceBefore=12, spaceAfter=4)

    def P(text):
        return Paragraph(escape('' if text is None else str(text)), normal)

    def kv(rows):
        data = [[Paragraph('<b>%s</b>' % escape(k), normal),
                 P(v if (v not in (None, '')) else '—')] for k, v in rows]
        t = Table(data, colWidths=[2.2 * inch, 4.3 * inch])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, _LINE),
        ]))
        return t

    pi = patient.get('personal_info', {})
    ci = patient.get('contact_info', {})
    ec = patient.get('emergency_contact', {})
    mh = patient.get('medical_history', {})
    al = mh.get('allergies', {})
    cond = mh.get('conditions', {})
    wh = mh.get('women_health', {})

    story = []
    full = ('%s %s' % (pi.get('first_name', ''), pi.get('last_name', ''))).strip()
    if pi.get('nickname'):
        full += ' "%s"' % pi.get('nickname')

    header_cell = [
        Paragraph('Patient Record', title),
        P(clinic.get('name', '')),
        Spacer(1, 6),
        Paragraph(escape(full), name_style),
    ]
    photo = _photo_flowable(photo_bytes)
    if photo is not None:
        head = Table([[header_cell, photo]], colWidths=[5.4 * inch, 1.2 * inch])
        head.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('VALIGN', (1, 0), (1, 0), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
    else:
        story.extend(header_cell)

    story.append(Paragraph('Personal Information', section))
    story.append(kv([
        ('Full Name', ('%s %s %s' % (pi.get('first_name', ''), pi.get('middle_name', ''),
                                     pi.get('last_name', ''))).strip()),
        ('Gender', _GENDER.get(pi.get('gender'), '—')),
        ('Birthday', pi.get('birthday')),
        ('Age', pi.get('age')),
        ('Religion', pi.get('religion')),
        ('Nationality', pi.get('nationality')),
        ('Occupation', pi.get('occupation')),
    ]))

    story.append(Paragraph('Contact Information', section))
    story.append(kv([
        ('Home Address', ci.get('home_address')),
        ('Landline', ci.get('landline')),
        ('Cell Phone', ci.get('cell_phone')),
        ('Office No.', ci.get('office_number')),
        ('Email', ci.get('email')),
    ]))

    story.append(Paragraph('Emergency Contact', section))
    story.append(kv([
        ('Name', ec.get('name')),
        ('Relationship', ec.get('relationship')),
        ('Phone', ec.get('phone')),
    ]))

    story.append(Paragraph('Physician & General Health', section))
    story.append(kv([
        ('Physician', mh.get('physician_name')),
        ('Specialty', mh.get('physician_specialty')),
        ('Office No.', mh.get('physician_address')),
        ('In Good Health', _yesno(mh.get('q1_good_health'))),
        ('Under Treatment', _yesno(mh.get('q2_under_treatment'))),
        ('Treatment Condition', mh.get('q2_condition')),
        ('Tobacco Use', _yesno(mh.get('q6_tobacco'))),
        ('Alcohol/Drugs', _yesno(mh.get('q7_dangerous_drugs'))),
        ('Current Medications', mh.get('current_medications')),
    ]))

    story.append(Paragraph('Vital Signs', section))
    story.append(kv([
        ('Blood Type', mh.get('blood_type')),
        ('Blood Pressure', mh.get('blood_pressure')),
        ('Weight', mh.get('weight')),
        ('Bleeding Time', mh.get('bleeding_time')),
    ]))

    allergy_labels = {
        'local_anesthesia': 'Local Anesthetic', 'penicillin': 'Penicillin',
        'sulfa_drugs': 'Sulfa Drugs', 'aspirin': 'Aspirin', 'latex': 'Latex',
    }
    allergies = [lbl for key, lbl in allergy_labels.items() if al.get(key)]
    if al.get('other'):
        allergies.append(al.get('other'))
    story.append(Paragraph('Allergies', section))
    story.append(P(', '.join(allergies) if allergies else 'None reported'))

    cond_labels = {
        'high_blood_pressure': 'High Blood Pressure', 'heart_disease': 'Heart Disease',
        'diabetes': 'Diabetes', 'asthma': 'Asthma', 'cancer_tumors': 'Cancer/Tumors',
        'heart_murmur': 'Heart Murmur', 'epilepsy_convulsions': 'Epilepsy',
        'hepatitis_liver': 'Hepatitis/Liver Disease', 'kidney_disease': 'Kidney Disease',
        'arthritis_rheumatism': 'Arthritis', 'thyroid_problem': 'Thyroid Problem',
        'bleeding_problems': 'Bleeding Problems',
    }
    conditions = [lbl for key, lbl in cond_labels.items() if cond.get(key)]
    if cond.get('other'):
        conditions.append(cond.get('other'))
    story.append(Paragraph('Medical Conditions', section))
    story.append(P(', '.join(conditions) if conditions else 'None reported'))

    if pi.get('gender') == 'F':
        story.append(Paragraph("Women's Health", section))
        story.append(kv([
            ('Pregnant', _yesno(wh.get('pregnant'))),
            ('Nursing', _yesno(wh.get('nursing'))),
            ('Birth Control', _yesno(wh.get('birth_control'))),
        ]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, title='Patient Record',
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    doc.build(story)
    buf.seek(0)
    return buf
