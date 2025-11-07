from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from datetime import datetime
import os
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

# NUEVO PARA WORD
from docx import Document
from docx.shared import Inches, Pt

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///audit.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'cambiar-esta-clave'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# Estados permitidos
STATES = [
    "Fortalezas",
    "Hallazgos",
    "No conformidad menor",
    "No conformidad mayor",
    "Observaciones"
]

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    state = db.Column(db.String(100), nullable=True)
    observation = db.Column(db.Text, nullable=True)

class AuditReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa = db.Column(db.String(200), nullable=True)
    auditor_nombre = db.Column(db.String(200), nullable=True)
    firma_auditor = db.Column(db.String(200), nullable=True)
    firma_empresa = db.Column(db.String(200), nullable=True)
    auditor_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    questions = Question.query.order_by(Question.id).all()
    return render_template('index.html', questions=questions, states=STATES)

@app.route('/question/new', methods=['GET','POST'])
def new_question():
    if request.method == 'POST':
        text = request.form.get('text','').strip()
        if not text:
            flash('La pregunta no puede estar vacía', 'danger')
            return redirect(url_for('new_question'))
        q = Question(text=text)
        db.session.add(q)
        db.session.commit()
        flash('Pregunta creada', 'success')
        return redirect(url_for('index'))
    return render_template('question_form.html')

@app.route('/question/<int:q_id>/edit', methods=['GET','POST'])
def edit_question(q_id):
    q = Question.query.get_or_404(q_id)
    if request.method == 'POST':
        if 'text' in request.form:
            q.text = request.form.get('text','').strip() or q.text
            db.session.commit()
            flash('Pregunta actualizada', 'success')
            return redirect(url_for('index'))
        q.state = request.form.get('state')
        q.observation = request.form.get('observation','').strip()
        db.session.commit()
        flash('Respuesta guardada', 'success')
        return redirect(url_for('index'))
    return render_template('question_edit.html', q=q, states=STATES)

@app.route('/question/<int:q_id>/delete', methods=['POST'])
def delete_question(q_id):
    q = Question.query.get_or_404(q_id)
    db.session.delete(q)
    db.session.commit()
    flash('Pregunta eliminada', 'success')
    return redirect(url_for('index'))

@app.route('/diligenciar', methods=['GET','POST'])
def diligenciar():
    questions = Question.query.order_by(Question.id).all()
    if request.method == 'POST':
        for q in questions:
            q.state = request.form.get(f'state_{q.id}')
            q.observation = request.form.get(f'obs_{q.id}','').strip()
        db.session.commit()
        flash('Todas las respuestas guardadas', 'success')
        return redirect(url_for('audit_form'))
    return render_template('diligenciar.html', questions=questions, states=STATES)

@app.route('/audit', methods=['GET','POST'])
def audit_form():
    questions = Question.query.order_by(Question.id).all()
    summary = {s: 0 for s in STATES}
    for q in questions:
        if q.state in summary:
            summary[q.state] += 1

    if request.method == 'POST':
        empresa = request.form.get('empresa','').strip()
        auditor_nombre = request.form.get('auditor_nombre','').strip()
        auditor_text = request.form.get('auditor_text','').strip()

        firma_auditor_file = request.files.get('firma_auditor')
        firma_empresa_file = request.files.get('firma_empresa')
        firma_auditor_path = None
        firma_empresa_path = None

        if firma_auditor_file and firma_auditor_file.filename != '':
            filename = secure_filename(f"{datetime.utcnow().timestamp()}_auditor_{firma_auditor_file.filename}")
            firma_auditor_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            firma_auditor_file.save(firma_auditor_path)

        if firma_empresa_file and firma_empresa_file.filename != '':
            filename = secure_filename(f"{datetime.utcnow().timestamp()}_empresa_{firma_empresa_file.filename}")
            firma_empresa_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            firma_empresa_file.save(firma_empresa_path)

        ar = AuditReport(
            empresa=empresa,
            auditor_nombre=auditor_nombre,
            auditor_text=auditor_text,
            firma_auditor=firma_auditor_path,
            firma_empresa=firma_empresa_path
        )
        db.session.add(ar)
        db.session.commit()

        if request.form.get("generate") == "word":
            return redirect(url_for('export_word', report_id=ar.id))
        return redirect(url_for('export_pdf', report_id=ar.id))

    return render_template('audit_form.html', questions=questions, summary=summary)

# ---------- EXPORTAR WORD (CORREGIDO) ----------
@app.route('/report/word/<int:report_id>')
def export_word(report_id):
    ar = AuditReport.query.get_or_404(report_id)
    questions = Question.query.order_by(Question.id).all()

    summary = {s: 0 for s in STATES}
    for q in questions:
        if q.state in summary:
            summary[q.state] += 1

    doc = Document()
    doc.add_heading('INFORME DE AUDITORÍA', level=1)
    doc.add_paragraph(f"Fecha de generación: {ar.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    doc.add_paragraph(f"Empresa auditada: {ar.empresa or '(no definida)'}")
    doc.add_paragraph(f"Auditor: {ar.auditor_nombre or '(no definido)'}")
    doc.add_paragraph("")

    doc.add_heading("Resumen de hallazgos", level=2)
    table = doc.add_table(rows=1, cols=2)
    hdr = table.rows[0].cells
    hdr[0].text = "Estado"
    hdr[1].text = "Cantidad"
    for s in STATES:
        row = table.add_row().cells
        row[0].text = s
        row[1].text = str(summary[s])

    doc.add_paragraph("")
    doc.add_heading("Resultados Detallados", level=2)
    
    table = doc.add_table(rows=1, cols=4)
    hdr = table.rows[0].cells
    hdr[0].text = "#"
    hdr[1].text = "Pregunta"
    hdr[2].text = "Estado"
    hdr[3].text = "Observación"

    for q in questions:
        row = table.add_row().cells
        row[0].text = str(q.id)
        row[1].text = q.text
        row[2].text = q.state or "(sin estado)"
        row[3].text = q.observation or "(sin observación)"

    doc.add_paragraph("")
    doc.add_heading("Informe Final del Auditor", level=2)
    doc.add_paragraph(ar.auditor_text or "(sin observaciones)")

    doc.add_paragraph("")
    doc.add_heading("Firmas", level=2)

    signatures = doc.add_table(rows=2, cols=2)
    sig_titles = signatures.rows[0].cells
    sig_titles[0].text = "Auditor"
    sig_titles[1].text = "Empresa"

    sig_images = signatures.rows[1].cells

    if ar.firma_auditor:
        sig_images[0].paragraphs[0].add_run().add_picture(ar.firma_auditor, width=Inches(2))
    else:
        sig_images[0].text = "______________________"

    if ar.firma_empresa:
        sig_images[1].paragraphs[0].add_run().add_picture(ar.firma_empresa, width=Inches(2))
    else:
        sig_images[1].text = "______________________"

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    filename = f"informe_auditoria_{ar.created_at.strftime('%Y%m%d_%H%M%S')}.docx"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

# ---------- EXPORTAR PDF (SIN CAMBIOS) ----------
@app.route('/report/pdf/<int:report_id>')
def export_pdf(report_id):
    ar = AuditReport.query.get_or_404(report_id)
    questions = Question.query.order_by(Question.id).all()

    summary = {s: 0 for s in STATES}
    for q in questions:
        if q.state in summary:
            summary[q.state] += 1

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(name="Title", parent=styles["Title"], alignment=1, fontSize=16, leading=20, spaceAfter=12)
    heading_style = ParagraphStyle(name="Heading", parent=styles["Heading2"], fontSize=12, leading=14, spaceAfter=6)
    small_style = ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=9, leading=11)
    cell_style = ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=9, leading=11, spaceBefore=2, spaceAfter=2)
    auditor_style = ParagraphStyle(name="AuditorText", parent=styles["BodyText"], fontSize=11, leading=16, spaceBefore=6, spaceAfter=6)

    body = []

    body.append(Paragraph("INFORME DE AUDITORÍA", title_style))
    body.append(Paragraph(f"Fecha de generación: {ar.created_at.strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    body.append(Spacer(1, 12))
    body.append(Paragraph(f"Empresa auditada: {ar.empresa or '(no definida)'}", styles["Normal"]))
    body.append(Paragraph(f"Auditor: {ar.auditor_nombre or '(no definido)'}", styles["Normal"]))
    body.append(Spacer(1, 12))

    body.append(Paragraph("Resumen de hallazgos", heading_style))
    body.append(Spacer(1, 12))
    summary_data = [[Paragraph("<b>Estado</b>", small_style), Paragraph("<b>Cantidad</b>", small_style)]]
    for s in STATES:
        summary_data.append([Paragraph(s, small_style), Paragraph(str(summary[s]), small_style)])
    summary_table = Table(summary_data, colWidths=[130, 90], hAlign='LEFT')
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    body.append(summary_table)
    body.append(Spacer(1, 15))

    body.append(Paragraph("Resultados Detallados", heading_style))
    body.append(Spacer(1, 12))
    table_data = [
        [Paragraph("<b>#</b>", small_style),
         Paragraph("<b>Pregunta</b>", small_style),
         Paragraph("<b>Estado</b>", small_style),
         Paragraph("<b>Observación</b>", small_style)]
    ]
    for q in questions:
        table_data.append([
            Paragraph(str(q.id), small_style),
            Paragraph(q.text or "(sin texto)", cell_style),
            Paragraph(q.state or "OK", cell_style),
            Paragraph(q.observation or "(sin observación)", cell_style)
        ])
    details_table = Table(table_data, colWidths=[30, 200, 80, 210], repeatRows=1, hAlign='LEFT')
    details_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    body.append(details_table)
    body.append(Spacer(1, 18))

    body.append(Paragraph("Informe Final del Auditor", heading_style))
    body.append(Spacer(1, 12))
    auditor_text = (ar.auditor_text or "(sin observaciones)").replace("\n", "<br/>")
    body.append(Paragraph(auditor_text, auditor_style))
    body.append(Spacer(1, 18))

    firma_row = []
    if ar.firma_auditor:
        firma_row.append(Image(ar.firma_auditor, width=200, height=50))
    else:
        firma_row.append(Paragraph("____________________", styles["Normal"]))

    if ar.firma_empresa:
        firma_row.append(Image(ar.firma_empresa, width=200, height=50))
    else:
        firma_row.append(Paragraph("____________________", styles["Normal"]))

    firma_table = Table([firma_row], colWidths=[270, 270], hAlign='CENTER')
    body.append(firma_table)

    nombre_row = [
        Paragraph("Auditor", styles["Normal"]),
        Paragraph("Empresa", styles["Normal"])
    ]
    nombre_table = Table([nombre_row], colWidths=[270, 270], hAlign='CENTER')
    body.append(nombre_table)

    doc.build(body)
    buffer.seek(0)

    filename = f"informe_auditoria_{ar.created_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
