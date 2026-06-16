import xml.etree.ElementTree as ET
import jinja2
from weasyprint import HTML
import os
from datetime import datetime

def procesar_xml(ruta_xml, carpeta_salida):
    """
    Parsea un XML de factura electrónica del SRI, extrae los datos relevantes
    y genera un archivo PDF (RIDE) en la carpeta de salida.
    Retorna el nombre del archivo generado o None si falla.
    """
    try:
        # 1. Parsear el XML
        tree = ET.parse(ruta_xml)
        root = tree.getroot()
        
        # El comprobante a menudo viene envuelto en <autorizacion><comprobante><![CDATA[...]]></comprobante>
        comprobante_str = None
        if 'autorizacion' in root.tag.lower():
            comprobante_node = root.find('.//comprobante')
            if comprobante_node is not None and comprobante_node.text:
                comprobante_str = comprobante_node.text
        
        # Si comprobante_str existe, parseamos el string CDATA (que es un XML embebido)
        if comprobante_str:
            root_factura = ET.fromstring(comprobante_str)
        else:
            # Asumimos que el root original ya es la factura (sin la envoltura de autorización)
            root_factura = root

        # 2. Extracción segura de campos
        # find() devuelve el nodo, findtext() devuelve el contenido (o un valor por defecto si no existe)
        info_tributaria = root_factura.find('.//infoTributaria')
        info_factura = root_factura.find('.//infoFactura')
        
        if info_tributaria is None or info_factura is None:
            raise ValueError("El XML no contiene los nodos <infoTributaria> o <infoFactura> esperados.")

        razon_social = info_tributaria.findtext('razonSocial', 'Desconocido')
        ruc = info_tributaria.findtext('ruc', 'Desconocido')
        clave_acceso = info_tributaria.findtext('claveAcceso', 'Desconocido')
        
        estab = info_tributaria.findtext('estab', '000')
        pto_emi = info_tributaria.findtext('ptoEmi', '000')
        secuencial = info_tributaria.findtext('secuencial', '000000000')
        num_secuencial = f"{estab}-{pto_emi}-{secuencial}"
        
        fecha = info_factura.findtext('fechaEmision', 'Desconocida')
        cliente = info_factura.findtext('razonSocialComprador', 'Consumidor Final')
        total = info_factura.findtext('importeTotal', '0.00')

        # 3. Plantilla HTML corporativa embebida
        html_template = """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; margin: 0; padding: 40px; }
                .header { border-bottom: 3px solid #1e3a8a; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; }
                .header-title h1 { color: #1e3a8a; margin: 0 0 5px 0; font-size: 26px; text-transform: uppercase; }
                .header-title p { margin: 0; color: #64748b; font-size: 14px; }
                .badge { background-color: #dbeafe; color: #1e40af; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 14px; border: 1px solid #bfdbfe; }
                .info-grid { display: table; width: 100%; margin-bottom: 30px; }
                .info-col { display: table-cell; width: 50%; padding: 15px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
                .info-col h3 { margin-top: 0; color: #0f172a; font-size: 16px; margin-bottom: 15px; border-bottom: 1px solid #cbd5e1; padding-bottom: 5px; }
                .data-row { margin-bottom: 8px; font-size: 14px; }
                .data-label { font-weight: bold; color: #475569; display: inline-block; width: 120px; }
                .clave-acceso { background: #e2e8f0; padding: 8px; border-radius: 4px; font-family: monospace; font-size: 13px; text-align: center; word-break: break-all; letter-spacing: 2px;}
                table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                th, td { text-align: left; padding: 12px; border-bottom: 1px solid #e2e8f0; }
                th { background-color: #1e3a8a; color: white; font-weight: 500; }
                tr:nth-child(even) { background-color: #f8fafc; }
                .total-box { float: right; width: 300px; background: #f1f5f9; padding: 20px; border-radius: 8px; margin-top: 20px; text-align: right; }
                .total-line { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 15px; }
                .total-final { font-size: 22px; font-weight: bold; color: #0f172a; border-top: 2px solid #cbd5e1; padding-top: 10px; margin-top: 10px; }
                .footer { clear: both; margin-top: 60px; padding-top: 20px; border-top: 1px dashed #cbd5e1; font-size: 11px; text-align: center; color: #94a3b8; }
            </style>
        </head>
        <body>
            <div class="header">
                <div class="header-title">
                    <h1>FACTURA</h1>
                    <p>Comprobante Electrónico (RIDE)</p>
                </div>
                <div>
                    <span class="badge">Nº {{ num_secuencial }}</span>
                </div>
            </div>
            
            <div class="info-grid">
                <div class="info-col" style="border-right: 5px solid white;">
                    <h3>Datos del Emisor</h3>
                    <div class="data-row"><span class="data-label">Razón Social:</span> {{ razon_social }}</div>
                    <div class="data-row"><span class="data-label">RUC:</span> {{ ruc }}</div>
                    <div class="data-row"><span class="data-label">Fecha Emisión:</span> {{ fecha }}</div>
                </div>
                <div class="info-col">
                    <h3>Datos del Cliente</h3>
                    <div class="data-row"><span class="data-label">Cliente:</span> {{ cliente }}</div>
                    <div class="data-row" style="margin-top: 15px;"><span class="data-label">Clave de Acceso:</span></div>
                    <div class="clave-acceso">{{ clave_acceso }}</div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Descripción</th>
                        <th style="text-align: right;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Servicios / Productos facturados (Resumen)</td>
                        <td style="text-align: right;">${{ total }}</td>
                    </tr>
                </tbody>
            </table>

            <div class="total-box">
                <div class="total-line">
                    <span>Subtotal:</span>
                    <span>${{ total }}</span>
                </div>
                <div class="total-final">
                    <span>TOTAL:</span>
                    <span>${{ total }}</span>
                </div>
            </div>

            <div class="footer">
                <p>Este documento es una representación impresa de un comprobante electrónico (RIDE).</p>
                <p>Generado automáticamente el {{ fecha_generacion }} por el Sistema Automatizado.</p>
            </div>
        </body>
        </html>
        """

        # 4. Renderizar plantilla usando Jinja2
        template = jinja2.Template(html_template)
        html_rendered = template.render(
            razon_social=razon_social,
            ruc=ruc,
            clave_acceso=clave_acceso,
            num_secuencial=num_secuencial,
            fecha=fecha,
            cliente=cliente,
            total=total,
            fecha_generacion=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        # 5. Configuración y Generación del PDF con weasyprint
        pdf_filename = f"Factura_{ruc}_{num_secuencial}.pdf"
        pdf_path = os.path.join(carpeta_salida, pdf_filename)
        
        # weasyprint no requiere binarios del sistema como wkhtmltopdf
        HTML(string=html_rendered).write_pdf(pdf_path)
        
        return pdf_filename

    except ET.ParseError:
        print(f"[ERROR] El archivo '{ruta_xml}' está malformado y no se puede parsear como XML.")
        return None
    except Exception as e:
        print(f"[ERROR] Error inesperado al procesar '{ruta_xml}': {e}")
        return None
