import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from generador import procesar_xml

# Rutas de las carpetas (relativas al lugar desde donde se ejecuta el script)
CARPETA_XML = 'xml_entrantes'
CARPETA_PDFS = os.path.join('static', 'pdfs')

# Asegurarse de que las carpetas existan antes de iniciar
os.makedirs(CARPETA_XML, exist_ok=True)
os.makedirs(CARPETA_PDFS, exist_ok=True)

class ManejadorXML(FileSystemEventHandler):
    """
    Clase que hereda de FileSystemEventHandler para reaccionar a eventos del sistema de archivos.
    """
    def on_created(self, event):
        # 1. Ignorar la creación de nuevas carpetas, solo nos interesan archivos
        if event.is_directory:
            return
            
        ruta_archivo = event.src_path
        
        # 2. Filtrar solo los archivos que terminan en .xml
        if ruta_archivo.lower().endswith('.xml'):
            print(f"\n[+] Nuevo archivo XML detectado: {ruta_archivo}")
            
            # 3. Esperar 1 segundo: Esto es crucial en Windows/Linux porque el evento 'on_created'
            # se dispara en el momento en que se crea el archivo vacío. Si intentamos leerlo
            # inmediatamente, puede estar incompleto o bloqueado por el ERP que lo está guardando.
            time.sleep(1)
            
            try:
                # 4. Enviar a procesar el XML
                print("    Procesando datos y generando RIDE...")
                pdf_generado = procesar_xml(ruta_archivo, CARPETA_PDFS)
                
                if pdf_generado:
                    print(f"    [ÉXITO] RIDE generado: {pdf_generado}")
                    
                    # 5. Limpieza: Eliminar el archivo XML original si el PDF se generó bien
                    os.remove(ruta_archivo)
                    print(f"    [INFO] Archivo original '{ruta_archivo}' eliminado.")
                else:
                    print(f"    [FALLO] No se pudo procesar correctamente el archivo '{ruta_archivo}'.")
                    
            except Exception as e:
                # Manejo de errores a nivel de monitor para que no se detenga la vigilancia
                print(f"    [CRÍTICO] Ocurrió un error en el manejador: {e}")

if __name__ == "__main__":
    print(f"==================================================")
    print(f"  MONITOR SRI INICIADO")
    print(f"  Carpeta vigilada: ./{CARPETA_XML}")
    print(f"  Destino de PDFs : ./{CARPETA_PDFS}")
    print(f"==================================================")
    print("[*] Esperando nuevos archivos XML... (Presiona Ctrl+C para salir)")

    # Configurar el observer de Watchdog
    event_handler = ManejadorXML()
    observer = Observer()
    
    # Asociar el manejador con la carpeta a vigilar (recursive=False = solo esa carpeta, no subcarpetas)
    observer.schedule(event_handler, CARPETA_XML, recursive=False)
    
    # Iniciar el hilo de vigilancia
    observer.start()
    
    try:
        # Mantener el script vivo ejecutándose infinitamente
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Si el usuario presiona Ctrl+C, detener el observer de forma limpia
        print("\n[*] Monitor detenido por el usuario.")
        observer.stop()
    
    observer.join()
