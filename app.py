import os
import requests
import urllib3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, render_template_string
from flask_cors import CORS
from zeep import Client
from zeep.transports import Transport
import logging

# El SRI Ecuador tiene un problema conocido: su certificado SSL no coincide con la IP
# a la que redirige (181.113.227.222). Se desactivan las advertencias para evitar ruido en logs.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# ==========================================
# CONFIGURACIÓN DEL SISTEMA SRI (PDFs)
# ==========================================
CARPETA_PDFS = os.path.join(os.path.dirname(__file__), 'static', 'pdfs')
os.makedirs(CARPETA_PDFS, exist_ok=True)

# Plantilla HTML inyectada directamente para el dashboard
INDEX_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Facturas Procesadas</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f4f8; margin: 0; padding: 40px 20px; color: #334155; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 30px; }
        h1 { color: #0f172a; margin: 0; font-size: 24px; }
        .badge { background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 20px; font-size: 13px; font-weight: bold; border: 1px solid #bbf7d0; }
        .status { font-size: 13px; color: #64748b; margin-bottom: 20px; background: #f8fafc; padding: 10px; border-radius: 6px; text-align: center; border: 1px dashed #cbd5e1; }
        ul { list-style-type: none; padding: 0; margin: 0; }
        li { background: #ffffff; border: 1px solid #e2e8f0; margin-bottom: 15px; padding: 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
        li:hover { border-color: #94a3b8; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transform: translateY(-2px); }
        .file-info { display: flex; align-items: center; gap: 15px; }
        .icon { background: #ef4444; color: white; width: 40px; height: 40px; border-radius: 8px; display: flex; justify-content: center; align-items: center; font-weight: bold; font-size: 12px; }
        .file-name { font-weight: 600; color: #1e293b; font-size: 15px; }
        .file-date { color: #64748b; font-size: 13px; margin-top: 5px; }
        a.btn { background: #3b82f6; color: white; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; font-size: 14px; transition: background 0.2s; border: none; }
        a.btn:hover { background: #2563eb; }
        .empty { text-align: center; color: #94a3b8; padding: 60px 20px; font-style: italic; background: #f8fafc; border-radius: 8px; border: 2px dashed #e2e8f0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Visor de RIDE (PDFs)</h1>
            <div class="badge">{{ cantidad }} Facturas Procesadas</div>
        </div>
        
        <p class="status">🔄 Auto-actualización activada (10s) | Última revisión: <strong>{{ hora }}</strong> | <a href="/" style="color: #3b82f6;">Volver al Validador</a></p>
        
        {% if archivos %}
            <ul>
                {% for archivo in archivos %}
                <li>
                    <div class="file-info">
                        <div class="icon">PDF</div>
                        <div>
                            <div class="file-name">{{ archivo.nombre }}</div>
                            <div class="file-date">Generado el: {{ archivo.fecha }}</div>
                        </div>
                    </div>
                    <a class="btn" href="/ver/{{ archivo.nombre }}" target="_blank">Abrir PDF</a>
                </li>
                {% endfor %}
            </ul>
        {% else %}
            <div class="empty">
                <div style="font-size: 30px; margin-bottom: 15px;">📂</div>
                No hay facturas procesadas aún.<br>
                <small style="margin-top: 10px; display: block; color: #cbd5e1;">Depositando archivos XML en la carpeta, aparecerán aquí.</small>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""


# ==========================================
# VALIDADOR SRI LOGIC
# ==========================================
class ValidadorSRI:
    def __init__(self):
        self.wsdl_produccion = 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl'
        self.wsdl_pruebas = 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl'
        self.timeout = 30
        self.max_reintentos = 3
        # Headers que simulan un navegador real para evitar bloqueos por User-Agent
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-EC,es;q=0.9',
            'Connection': 'keep-alive',
        }

    def _crear_session(self):
        """Crea una sesión HTTP configurada para conectarse al SRI."""
        session = requests.Session()
        session.verify = False  # SRI tiene certificado SSL con mismatch de IP conocido
        session.headers.update(self.headers)

        # Retry automático ante connection reset (hasta 3 veces con backoff)
        retry = urllib3.util.retry.Retry(
            total=self.max_reintentos,
            backoff_factor=1.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session

    def validar_factura(self, clave_acceso, ambiente='produccion'):
        wsdl_url = self.wsdl_produccion if ambiente == 'produccion' else self.wsdl_pruebas

        if len(clave_acceso) != 49:
            return {"error": "La clave debe tener 49 dígitos."}

        ultimo_error = None
        for intento in range(1, self.max_reintentos + 1):
            try:
                logging.info(f"[SRI] Intento {intento}/{self.max_reintentos} — ambiente: {ambiente}")
                session = self._crear_session()
                transport = Transport(session=session, timeout=self.timeout, operation_timeout=self.timeout)
                client = Client(wsdl_url, transport=transport)

                respuesta = client.service.autorizacionComprobante(claveAccesoComprobante=clave_acceso)
                autorizaciones = respuesta.autorizaciones

                if not autorizaciones or not autorizaciones.autorizacion:
                    return {"valida": False, "estado": "NO ENCONTRADO", "mensaje": "Clave no existe en este ambiente."}

                info = autorizaciones.autorizacion[0]
                return {
                    "valida": info.estado == "AUTORIZADO",
                    "estado": info.estado,
                    "fecha_autorizacion": str(info.fechaAutorizacion),
                    "ambiente": info.ambiente
                }

            except requests.exceptions.ConnectionError as e:
                ultimo_error = str(e)
                logging.warning(f"[SRI] Intento {intento} fallido — ConnectionError: {ultimo_error}")
                if intento < self.max_reintentos:
                    import time
                    time.sleep(intento * 2)  # backoff: 2s, 4s
            except requests.exceptions.Timeout:
                ultimo_error = f"El SRI no respondió en {self.timeout}s (timeout)."
                logging.warning(f"[SRI] Intento {intento} fallido — Timeout")
                if intento < self.max_reintentos:
                    import time
                    time.sleep(intento * 2)
            except Exception as e:
                ultimo_error = str(e)
                logging.error(f"[SRI] Error inesperado en intento {intento}: {ultimo_error}")
                break  # Errores no-red no se reintentan

        logging.error(f"[SRI] Todos los intentos fallaron. Último error: {ultimo_error}")
        return {"error": f"No se pudo conectar al SRI después de {self.max_reintentos} intentos. Detalle: {ultimo_error}"}

validador = ValidadorSRI()

# ==========================================
# RUTAS DE LA APLICACIÓN
# ==========================================

@app.route('/')
def index():
    """Ruta raíz para el Validador de Facturas."""
    return render_template('index.html')

@app.route('/api/validar', methods=['POST'])
def validar():
    """Ruta API para validar la factura con el SRI."""
    datos = request.get_json()
    if not datos or 'clave_acceso' not in datos:
        return jsonify({"error": "No se proporcionó la clave_acceso."}), 400
    
    clave_acceso = str(datos['clave_acceso']).strip()
    ambiente = datos.get('ambiente', 'produccion')
    
    if len(clave_acceso) != 49 or not clave_acceso.isdigit():
        return jsonify({"error": "La clave de acceso debe contener exactamente 49 dígitos numéricos."}), 400

    resultado = validador.validar_factura(clave_acceso, ambiente)
    return jsonify(resultado)

@app.route('/dashboard')
def dashboard():
    """Dashboard para ver los RIDE generados."""
    try:
        archivos_pdf = []
        if os.path.exists(CARPETA_PDFS):
            for filename in os.listdir(CARPETA_PDFS):
                if filename.lower().endswith('.pdf'):
                    ruta_completa = os.path.join(CARPETA_PDFS, filename)
                    timestamp = os.path.getmtime(ruta_completa)
                    fecha_formateada = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    archivos_pdf.append({
                        'nombre': filename,
                        'fecha_raw': timestamp,
                        'fecha': fecha_formateada
                    })
        
        archivos_pdf.sort(key=lambda x: x['fecha_raw'], reverse=True)
        hora_actual = datetime.now().strftime('%H:%M:%S')
        
        return render_template_string(INDEX_HTML, archivos=archivos_pdf, hora=hora_actual, cantidad=len(archivos_pdf))
        
    except Exception as e:
        return f"<h1>Error Interno</h1><p>No se pudo leer el directorio de PDFs: {str(e)}</p>", 500

@app.route('/ver/<pdf_nombre>')
def ver_pdf(pdf_nombre):
    """Ruta para servir el PDF generado."""
    return send_from_directory(CARPETA_PDFS, pdf_nombre)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
