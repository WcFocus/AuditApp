from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///audit.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'cambiar-esta-clave'  # cambia en producción

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
        auditor_text = request.form.get('auditor_text','').strip()
        ar = AuditReport(auditor_text=auditor_text)
        db.session.add(ar)
        db.session.commit()
        return redirect(url_for('export_pdf', report_id=ar.id))
    return render_template('audit_form.html', questions=questions, summary=summary)

@app.route('/report/pdf/<int:report_id>')
def export_pdf(report_id):
    ar = AuditReport.query.get_or_404(report_id)
    questions = Question.query.order_by(Question.id).all()

    # resumen por estado
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

    # *** Nuevo estilo para el texto del auditor ***
    auditor_style = ParagraphStyle(
        name="AuditorText",
        parent=styles["BodyText"],
        fontSize=11,
        leading=16,
        spaceBefore=6,
        spaceAfter=6
    )

    body = []

    body.append(Paragraph("INFORME DE AUDITORÍA", title_style))
    body.append(Paragraph(f"Fecha de generación: {ar.created_at.strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
    body.append(Spacer(1, 12))

    body.append(Paragraph("Resumen por Estado", heading_style))
    summary_data = [[Paragraph("<b>Estado</b>", small_style), Paragraph("<b>Cantidad</b>", small_style)]]
    for s in STATES:
        summary_data.append([Paragraph(s, small_style), Paragraph(str(summary[s]), small_style)])
    summary_table = Table(summary_data, colWidths=[300, 60], hAlign='LEFT')
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    body.append(summary_table)
    body.append(Spacer(1, 18))

    body.append(Paragraph("Resultados Detallados", heading_style))

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
            Paragraph(q.state or "(sin marcar)", cell_style),
            Paragraph(q.observation or "(sin observación)", cell_style)
        ])

    details_table = Table(table_data, colWidths=[30, 260, 120, 150], repeatRows=1, hAlign='LEFT')
    details_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    body.append(details_table)
    body.append(Spacer(1, 18))

    # *** Aquí aplicamos la corrección de SALTOS DE LÍNEA ***
    body.append(Paragraph("Informe Final del Auditor", heading_style))
    auditor_text = (ar.auditor_text or "(sin observaciones)").replace("\n", "<br/>")
    body.append(Paragraph(auditor_text, auditor_style))

    doc.build(body)
    buffer.seek(0)

    filename = f"informe_auditoria_{ar.created_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
