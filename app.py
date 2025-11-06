from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib import colors
from datetime import datetime
import textwrap
import os

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

# ---------- Helpers para el PDF (canvas) ----------
def draw_wrapped(c, text, x, y, max_width, fontname="Helvetica", fontsize=10, leading=12):
    """
    Dibuja texto ajustado en canvas. Devuelve la nueva coordenada y (moviéndose hacia abajo).
    - text: string (puede contener saltos de línea)
    - x,y: coordenada de inicio (y es la línea superior)
    - max_width: ancho máximo en puntos
    - fontsize: tamaño de fuente
    - leading: espacio vertical entre líneas
    """
    if not text:
        return y - leading
    # Asegurarnos de usar la fuente indicada
    c.setFont(fontname, fontsize)

    # Separar en párrafos por saltos de línea y envolver cada párrafo
    paragraphs = text.splitlines()
    for para in paragraphs:
        # quitar espacios extras
        para = para.strip()
        if not para:
            y -= leading
            continue

        # Usar textwrap para generar líneas aproximadas en caracteres,
        # pero ajustaremos a ancho real con stringWidth para mayor precisión.
        # Estimamos chars_per_line y luego refinamos
        avg_char_width = pdfmetrics.stringWidth("M", fontname, fontsize)
        if avg_char_width == 0:
            avg_char_width = fontsize * 0.5
        est_chars = max(int(max_width / avg_char_width), 20)
        wrapped = textwrap.wrap(para, width=est_chars)

        # Refinar: asegurar que cada línea no exceda max_width
        refined = []
        for line in wrapped:
            # Si la línea es corta en ancho, ok; si no, partir por palabras
            if pdfmetrics.stringWidth(line, fontname, fontsize) <= max_width:
                refined.append(line)
            else:
                words = line.split(' ')
                cur = ""
                for w in words:
                    test = (cur + " " + w).strip()
                    if pdfmetrics.stringWidth(test, fontname, fontsize) <= max_width:
                        cur = test
                    else:
                        if cur:
                            refined.append(cur)
                        cur = w
                if cur:
                    refined.append(cur)

        for rl in refined:
            # Si la Y baja demasiado, retornar una señal especial (None) para nueva página
            if y < 60:  # margen inferior aproximado
                return None, rl  # señal para crear nueva página y re-dibujar esta línea ahí
            c.drawString(x, y, rl)
            y -= leading
    return y, None

def draw_separator(c, x1, x2, y):
    c.setStrokeColor(colors.grey)
    c.setLineWidth(0.5)
    c.line(x1, y, x2, y)

# Generar PDF y descargar (usa reportlab canvas) - versión corregida
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
    line_height = 12

    # Intento de registrar una fuente TrueType (opcional). Si falla, queda Helvetica.
    try:
        # Si tienes una fuente ttf local, puedes registrarla aquí. Ej:
        # pdfmetrics.registerFont(TTFont('Inter', '/ruta/a/Inter-Regular.ttf'))
        pass
    except Exception:
        pass

    # Página 1: encabezado y resumen + informe del auditor
    p.setFont("Helvetica-Bold", 16)
    y = height - margin
    p.drawString(margin, y, "Informe de Auditoría")
    p.setFont("Helvetica", 9)
    p.drawRightString(width - margin, y, f"Fecha: {ar.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 18
    draw_separator(p, margin, width - margin, y)
    y -= 12

    # Resumen
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Resumen (conteo por estado):")
    y -= 14
    p.setFont("Helvetica", 10)
    for s in STATES:
        text = f"- {s}: {summary.get(s,0)}"
        # dibujar resumen (no suelen ser largos)
        p.drawString(margin + 8, y, text)
        y -= line_height
    y -= 8
    draw_separator(p, margin, width - margin, y)
    y -= 12

    # Informe del auditor (puede ser largo) - usar wrapper con chequeo de nueva página
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Informe del auditor:")
    y -= 14
    p.setFont("Helvetica", 10)
    max_text_width = width - margin*2 - 10
    auditor_text = ar.auditor_text or "(sin texto)"

    # Llamar a draw_wrapped. Si devuelve None, crear nueva página y reintentar con la línea sobrante
    remaining = None
    wrapped_y = y
    # draw_wrapped returns (new_y, None) on success, or (None, leftover_line) to signal new page
    result = draw_wrapped(p, auditor_text, margin + 6, wrapped_y, max_text_width, fontname="Helvetica", fontsize=10, leading=14)
    if result is None:
        # safety, shouldn't happen
        pass
    else:
        new_y, leftover = result
        # Si leftover es not None, significa que precisamos nueva página y dibujar el leftover ahí
        if new_y is None and leftover:
            # nueva página
            p.showPage()
            p.setFont("Helvetica-Bold", 16)
            y = height - margin
            p.setFont("Helvetica-Bold", 11)
            p.drawString(margin, y, "Informe de Auditoría (continuación)")
            y -= 20
            p.setFont("Helvetica", 10)
            # dibujar leftover y continuar dibujando el resto text (llamamos otra vez con el texto completo
            # para simplificar: volveremos a usar draw_wrapped sobre todo el auditor_text desde top of new page)
            result2 = draw_wrapped(p, auditor_text, margin + 6, y, max_text_width, fontname="Helvetica", fontsize=10, leading=14)
            if result2 and result2[0] is not None:
                y = result2[0]
            else:
                y = height - margin  # fallback
        else:
            y = new_y

    # Espacio antes de siguientes secciones
    y -= 10
    # Si ya no hay espacio, nueva página antes de preguntas
    if y < 120:
        p.showPage()
        y = height - margin

    # Lista de preguntas con estado y observación (cada pregunta puede ocupar varias líneas)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(margin, y, "Preguntas respondidas:")
    y -= 16
    p.setFont("Helvetica", 9)

    max_text_width = width - margin*2 - 20

    for q in questions:
        # Si espacio insuficiente, nueva página
        if y < 100:
            p.showPage()
            y = height - margin
            p.setFont("Helvetica", 9)

        # Pregunta (negrita)
        p.setFont("Helvetica-Bold", 10)
        q_text = f"{q.id}. {q.text}"
        # usar draw_wrapped para la pregunta. Si necesita nueva página, manejarlo
        res = draw_wrapped(p, q_text, margin+4, y, max_text_width, fontname="Helvetica-Bold", fontsize=10, leading=13)
        if res is None:
            # safety fallback
            p.showPage()
            y = height - margin
            res = draw_wrapped(p, q_text, margin+4, y, max_text_width, fontname="Helvetica-Bold", fontsize=10, leading=13)
        y, leftover = res

        # Estado
        estado = q.state or "(sin marcar)"
        p.setFont("Helvetica", 9)
        if y < 80:
            p.showPage()
            y = height - margin
        p.drawString(margin+12, y, f"Estado: {estado}")
        y -= 12

        # Observación (wrap)
        obs = q.observation or ""
        if obs:
            res_obs = draw_wrapped(p, f"Obs: {obs}", margin+12, y, max_text_width, fontname="Helvetica", fontsize=9, leading=12)
            if res_obs is None:
                # nueva página y re-dibujar el resto del texto desde top
                p.showPage()
                y = height - margin
                res_obs = draw_wrapped(p, f"Obs: {obs}", margin+12, y, max_text_width, fontname="Helvetica", fontsize=9, leading=12)
            y, leftover = res_obs
        else:
            p.drawString(margin+12, y, "Obs: (sin observación)")
            y -= 12

        # separador entre preguntas
        y -= 6
        draw_separator(p, margin+4, width - margin - 4, y)
        y -= 10

    # Finalizar
    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"informe_auditoria_{ar.created_at.strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
