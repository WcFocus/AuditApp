# 📝 AuditApp

AuditApp es una aplicación para gestión de auditorías que permite registrar preguntas, asignar estados (fortalezas, hallazgos, no conformidades u observaciones), agregar comentarios y generar un informe final en PDF.

---

## 🚀 Características

- CRUD completo de preguntas (crear, editar, eliminar y listar).
- Estados disponibles:
  - ✅ Fortaleza
  - 🔍 Hallazgo
  - ⚠️ No Conformidad Menor
  - ❌ No Conformidad Mayor
  - 🗒️ Observación
- Campo para descripción u observación adicional.
- Conteo automático de resultados por estado.
- Generación de informe final en **PDF**.

---

## ✅ Requisitos Previos

Antes de ejecutar la aplicación, asegúrate de tener instalado:

| Requisito | Versión Requerida |
|----------|-------------------|
| Python   | **3.11** |
| pip      | Última versión recomendada |
| Git (opcional) | Para clonar el repositorio |

Verificar versión:
```bash
python --version

📦 Instalación

Clona este repositorio:

git clone https://github.com/WcFocus/AuditApp.git
cd AuditApp


Crea un entorno virtual:

python -m venv venv


Activa el entorno virtual:

Windows:

venv\Scripts\activate


Linux / Mac:

source venv/bin/activate


Instala las dependencias:

pip install -r requirements.txt

▶️ Ejecución

Con el entorno virtual activo, inicia la aplicación:

python app.py


La aplicación se ejecutará en:

http://127.0.0.1:5000


Ábrelo en tu navegador.
