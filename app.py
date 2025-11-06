from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

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
    state = db.Column(db.String(100), nullable=True)  # uno de STATES o None
    observation = db.Column(db.Text, nullable=True)

class AuditReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    auditor_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Crear la BD
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    questions = Question.query.order_by(Question.id).all()
    return render_template('index.html', questions=questions, states=STATES)

# Crear pregunta
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

# Editar pregunta (texto y/o estado y/o observación)
@app.route('/question/<int:q_id>/edit', methods=['GET','POST'])
def edit_question(q_id):
    q = Question.query.get_or_404(q_id)
    if request.method == 'POST':
        # Si se edita el texto:
        if 'text' in request.form:
            q.text = request.form.get('text','').strip() or q.text
            db.session.commit()
            flash('Pregunta actualizada', 'success')
            return redirect(url_for('index'))
        # Si se diligencian estado/observación desde el formulario de diligenciamiento:
        q.state = request.form.get('state')
        q.observation = request.form.get('observation','').strip()
        db.session.commit()
        flash('Respuesta guardada', 'success')
        return redirect(url_for('index'))
    return render_template('question_edit.html', q=q, states=STATES)

# Eliminar pregunta
@app.route('/question/<int:q_id>/delete', methods=['POST'])
def delete_question(q_id):
    q = Question.query.get_or_404(q_id)
    db.session.delete(q)
    db.session.commit()
    flash('Pregunta eliminada', 'success')
    return redirect(url_for('index'))

# Página para diligenciar todas las preguntas (mostrar todas con radios)
@app.route('/diligenciar', methods=['GET','POST'])
def diligenciar():
    questions = Question.query.order_by(Question.id).all()
    if request.method == 'POST':
        # Recorrer preguntas y guardar estados/observaciones
        for q in questions:
            state_key = f'state_{q.id}'
            obs_key = f'obs_{q.id}'
            state = request.form.get(state_key)
            obs = request.form.get(obs_key, '').strip()
            q.state = state
            q.observation = obs
        db.session.commit()
        flash('Todas las respuestas guardadas', 'success')
        return redirect(url_for('audit_form'))
    return render_template('diligenciar.html', questions=questions, states=STATES)

# Form para el informe del auditor y vista resumen
@app.route('/audit', methods=['GET','POST'])
def audit_form():
    questions = Question.query.order_by(Question.id).all()
    # conteo por estado
    summary = {s: 0 for s in STATES}
    for q in questions:
        if q.state in summary:
            summary[q.state] += 1
    if request.method == 'POST':
        auditor_text = request.form.get('auditor_text','').strip()
        ar = AuditReport(auditor_text=auditor_text)
        db.session.add(ar)
        db.session.commit()
        flash('Informe del auditor guardado. Generando PDF...', 'success')
        # redirigir a generar PDF
        return redirect(url_for('export_pdf', report_id=ar.id))
    return render_template('audit_form.html', questions=questions, summary=summary)

# Generar PDF y descargar (usa reportlab)
@app.route('/report/pdf/<int:report_id>')
def export_pdf(report_id):
    ar = AuditReport.query.get_or_404(report_id)
    questions = Question.query.order_by(Question.id).all()

    # Conteo por estado
    summary = {s: 0 for s in STATES}
    for q in questions:
        if q.state in summary:
            summary[q.state] += 1

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 40
    y = height - margin

    # Encabezado
    p.setFont("Helvetica-Bold", 14)
    p.drawString(margin, y, "Informe de Auditoría")
    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(margin, y, f"Fecha: {ar.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 25

    # Totales
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Resumen (conteo por estado):")
    y -= 15
    p.setFont("Helvetica", 10)
    for s in STATES:
        p.drawString(margin + 10, y, f"- {s}: {summary.get(s,0)}")
        y -= 12
    y -= 8

    # Informe del auditor
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Informe del auditor:")
    y -= 14
    p.setFont("Helvetica", 10)

    # dividir el texto del auditor en líneas
    auditor_lines = ar.auditor_text.splitlines() if ar.auditor_text else ["(sin texto)"]
    for line in auditor_lines:
        if y < margin + 60:  # nueva página si no hay espacio
            p.showPage()
            y = height - margin
        p.drawString(margin + 10, y, line)
        y -= 12
    y -= 10

    # Lista de preguntas con estado y observación
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Preguntas respondidas:")
    y -= 14
    p.setFont("Helvetica", 9)
    for q in questions:
        # Si no hay espacio suficiente, nueva página
        if y < margin + 60:
            p.showPage()
            y = height - margin
        # Pregunta
        p.drawString(margin+4, y, f"{q.id}. {q.text}")
        y -= 12
        # Estado
        estado = q.state or "(sin marcar)"
        p.drawString(margin+16, y, f"Estado: {estado}")
        y -= 12
        # Observación (puede necesitar varias líneas)
        obs = q.observation or ""
        if obs:
            # partir la observacion en trozos de 95 chars aproximados
            max_chars = 95
            parts = [obs[i:i+max_chars] for i in range(0, len(obs), max_chars)]
            for part in parts:
                if y < margin + 40:
                    p.showPage()
                    y = height - margin
                p.drawString(margin+16, y, f"Obs: {part}")
                y -= 12
        else:
            p.drawString(margin+16, y, "Obs: (sin observación)")
            y -= 12
        y -= 6

    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"informe_auditoria_{ar.created_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
