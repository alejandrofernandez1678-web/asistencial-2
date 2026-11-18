"""Exporta el informe a PDF con la tabla de contenido actualizada (LibreOffice + UNO).

Uso en Linux:    python3 docs/informe/exportar_pdf.py   (python del sistema, trae el módulo uno)
Uso en Windows:  & "C:\\Program Files\\LibreOffice\\program\\python.exe" docs\\informe\\exportar_pdf.py
No modifica el .docx: solo actualiza los índices en memoria antes de exportar.
"""

import shutil
import subprocess
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue

RAIZ = Path(__file__).resolve().parents[2]
DOCX = RAIZ / "Proyecto_Integrado_Informe_3_base.docx"
PDF = DOCX.with_suffix(".pdf")
PUERTO = 2083


def propiedad(nombre, valor):
    p = PropertyValue()
    p.Name, p.Value = nombre, valor
    return p


SOFFICE = (shutil.which("soffice") or shutil.which("soffice.exe")
           or r"C:\Program Files\LibreOffice\program\soffice.exe")

oficina = subprocess.Popen([SOFFICE, "--headless", "--invisible", "--norestore",
                            f"--accept=socket,host=127.0.0.1,port={PUERTO};urp;"])
try:
    resolvedor = uno.getComponentContext().ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", uno.getComponentContext())
    for _ in range(60):
        try:
            contexto = resolvedor.resolve(f"uno:socket,host=127.0.0.1,port={PUERTO};urp;StarOffice.ComponentContext")
            break
        except Exception:  # noqa: BLE001 - LibreOffice todavía está iniciando
            time.sleep(0.5)
    escritorio = contexto.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", contexto)
    documento = escritorio.loadComponentFromURL(DOCX.as_uri(), "_blank", 0, (propiedad("Hidden", True),))
    indices = documento.getDocumentIndexes()
    for _ in range(2):  # dos pasadas: el índice cambia de largo y desplaza las páginas
        for i in range(indices.getCount()):
            indices.getByIndex(i).update()
        documento.refresh()
    documento.storeToURL(PDF.as_uri(), (propiedad("FilterName", "writer_pdf_Export"),))
    documento.close(True)
    print(f"PDF generado: {PDF}")
finally:
    oficina.terminate()
