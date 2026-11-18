"""Utilidades para editar el informe .docx respetando el formato de la plantilla INACAP.

El Informe 2 usa formato directo (no estilos) en leyendas, tablas y bloques de código;
estas funciones generan XML con exactamente ese formato.
"""

import re
import struct
from copy import deepcopy
from xml.sax.saxutils import escape

from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = f'xmlns:w="{W}"'
ANCHO_TABLA = 9495            # twips, igual que las tablas del Informe 2
ROJO_ENCABEZADO = "E31D1A"
ROJO_LEYENDA = "B3161A"
FILA_ALTERNA = "FDF4F3"
BORDE_TABLA = "EBB9B7"
EMU_POR_CM = 360000


# ------------------------------------------------------------------ runs
def _rpr(b=False, i=False, color=None, size=None, mono=False, fondo=None):
    partes = []
    if mono:
        partes.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>')
    if b:
        partes.append("<w:b/><w:bCs/>")
    if i:
        partes.append("<w:i/><w:iCs/>")
    if color:
        partes.append(f'<w:color w:val="{color}"/>')
    if size:
        partes.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if fondo:
        partes.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fondo}"/>')
    return f"<w:rPr>{''.join(partes)}</w:rPr>" if partes else ""


def run(texto, **formato):
    return f'<w:r>{_rpr(**formato)}<w:t xml:space="preserve">{escape(texto)}</w:t></w:r>'


def runs_enriquecidos(texto, **base):
    """**negrita** y `código` dentro del texto."""
    salida = []
    for parte in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", texto):
        if not parte:
            continue
        if parte.startswith("**"):
            salida.append(run(parte[2:-2], **{**base, "b": True}))
        elif parte.startswith("`"):
            salida.append(run(parte[1:-1], **{**base, "mono": True, "fondo": "EEF1F0"}))
        else:
            salida.append(run(parte, **base))
    return "".join(salida)


def _p(ppr, contenido):
    return parse_xml(f"<w:p {NS}><w:pPr>{ppr}</w:pPr>{contenido}</w:p>")


# ------------------------------------------------------------ párrafos
def parrafo(texto, mantener=False):
    keep = "<w:keepNext/>" if mantener else ""
    return _p(f'{keep}<w:spacing w:after="100" w:line="264" w:lineRule="auto"/><w:jc w:val="both"/>',
              runs_enriquecidos(texto))


def titulo(texto, nivel):
    if nivel == 1:
        ppr = ('<w:pStyle w:val="Ttulo1"/><w:pageBreakBefore/><w:spacing w:before="360" w:after="120"/>'
               '<w:ind w:left="567" w:hanging="567"/>')
    else:
        ppr = '<w:pStyle w:val="Ttulo2"/><w:spacing w:before="240" w:after="120"/><w:ind w:left="680" w:hanging="680"/>'
    return _p(ppr, run(texto))


def vineta(texto, num_id="3"):
    return _p(f'<w:pStyle w:val="Prrafodelista"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
              '<w:spacing w:after="60" w:line="259" w:lineRule="auto"/>', runs_enriquecidos(texto))


def leyenda(tipo, clave, texto):
    """La numeración definitiva la asigna renumerar(); aquí se deja una marca ⟦tipo:clave⟧."""
    return _p('<w:keepNext/><w:spacing w:before="60" w:after="80"/><w:jc w:val="left"/>',
              run(f"⟦{tipo}:{clave}⟧.", b=True, color=ROJO_LEYENDA, size=19)
              + run(" ", color=ROJO_LEYENDA, size=19) + run(texto, i=True, color="595959", size=19))


def fuente(texto="Elaboración propia."):
    return _p('<w:spacing w:after="180" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/>',
              run("Fuente: ", i=True, color="595959", size=17) + run(texto, i=True, color="595959", size=17))


def codigo(lineas):
    elementos = []
    for n, linea in enumerate(lineas):
        keep = "<w:keepNext/>" if n < len(lineas) - 1 else ""
        elementos.append(_p(
            f'{keep}<w:pBdr><w:top w:val="single" w:sz="4" w:space="4" w:color="BFC9C6"/>'
            '<w:left w:val="single" w:sz="4" w:space="4" w:color="BFC9C6"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="4" w:color="BFC9C6"/>'
            '<w:right w:val="single" w:sz="4" w:space="4" w:color="BFC9C6"/></w:pBdr>'
            '<w:shd w:val="clear" w:color="auto" w:fill="F4F6F5"/><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
            '<w:ind w:left="113" w:right="113"/><w:jc w:val="left"/>',
            run(linea if linea else " ", mono=True, color="1E2B30", size=16)))
    return elementos


# --------------------------------------------------------------- tablas
def tabla(encabezados, filas, pesos=None, primera_negrita=True):
    pesos = pesos or [1] * len(encabezados)
    total = sum(pesos)
    anchos = [round(ANCHO_TABLA * p / total) for p in pesos]
    anchos[-1] = ANCHO_TABLA - sum(anchos[:-1])

    def celda(texto, ancho, encabezado=False, alterna=False, negrita=False):
        fondo = ROJO_ENCABEZADO if encabezado else (FILA_ALTERNA if alterna else None)
        shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fondo}"/>' if fondo else ""
        valign = "center" if encabezado else "top"
        jc = "center" if encabezado else "left"
        parrafos = []
        for linea in str(texto).split("\n"):
            contenido = (run(linea, b=True, color="FFFFFF", size=18) if encabezado
                         else runs_enriquecidos(linea, color="262626", size=18) if not negrita
                         else run(linea, b=True, color="262626", size=18))
            parrafos.append(f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                            f'<w:jc w:val="{jc}"/></w:pPr>{contenido}</w:p>')
        return (f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>{shd}<w:vAlign w:val="{valign}"/></w:tcPr>'
                f'{"".join(parrafos)}</w:tc>')

    bordes = "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="{BORDE_TABLA}"/>'
                     for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    xml = [f'<w:tbl {NS}><w:tblPr><w:tblW w:w="{ANCHO_TABLA}" w:type="dxa"/><w:tblBorders>{bordes}</w:tblBorders>'
           '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
           '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>']
    xml += [f'<w:gridCol w:w="{a}"/>' for a in anchos]
    xml.append('</w:tblGrid><w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>')
    xml += [celda(e, a, encabezado=True) for e, a in zip(encabezados, anchos)]
    xml.append("</w:tr>")
    for n, fila in enumerate(filas):
        xml.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>")
        xml += [celda(v, a, alterna=n % 2 == 1, negrita=primera_negrita and c == 0)
                for c, (v, a) in enumerate(zip(fila, anchos))]
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    return parse_xml("".join(xml))


def filas_de(tbl, con_encabezado=False):
    """Texto de cada celda de una tabla existente (elemento w:tbl), sin el encabezado por defecto."""
    filas = [["\n".join(texto(p) for p in tc.findall(qn("w:p"))) for tc in tr.findall(qn("w:tc"))]
             for tr in tbl.findall(qn("w:tr"))]
    return filas if con_encabezado else filas[1:]


# -------------------------------------------------------------- imágenes
def tamano_png(ruta):
    with open(ruta, "rb") as f:
        return struct.unpack(">II", f.read()[16:24])


def medidas(ruta, ancho_cm, alto_max_cm):
    ancho, alto = tamano_png(ruta)
    cx = ancho_cm * EMU_POR_CM
    cy = cx * alto / ancho
    if cy > alto_max_cm * EMU_POR_CM:
        factor = alto_max_cm * EMU_POR_CM / cy
        cx, cy = cx * factor, cy * factor
    return int(cx), int(cy)


def figura(documento, ruta, ancho_cm=16.0, alto_max_cm=19.5):
    cx, cy = medidas(ruta, ancho_cm, alto_max_cm)
    p = documento.add_paragraph()
    p.add_run().add_picture(ruta, width=Emu(cx), height=Emu(cy))
    elemento = p._p
    elemento.getparent().remove(elemento)
    ppr = parse_xml(f'<w:pPr {NS}><w:keepNext/><w:spacing w:before="60" w:after="40"/><w:jc w:val="center"/></w:pPr>')
    elemento.insert(0, ppr)
    return elemento


def reemplazar_imagen(documento, parrafo_imagen, ruta, ancho_cm=16.0, alto_max_cm=19.5):
    blip = parrafo_imagen.find(".//" + qn("a:blip"))
    rid = blip.get(qn("r:embed"))
    with open(ruta, "rb") as f:
        documento.part.related_parts[rid]._blob = f.read()
    cx, cy = medidas(ruta, ancho_cm, alto_max_cm)
    parrafo_imagen.find(".//" + qn("wp:extent")).set("cx", str(cx))
    parrafo_imagen.find(".//" + qn("wp:extent")).set("cy", str(cy))
    ext = parrafo_imagen.find(".//" + qn("a:ext"))
    ext.set("cx", str(cx))
    ext.set("cy", str(cy))


# ---------------------------------------------------- navegación y edición
def texto(elemento):
    return "".join(t.text or "" for t in elemento.iter(qn("w:t")))


class Cuerpo:
    def __init__(self, documento):
        self.doc = documento
        self.body = documento.element.body

    def hijos(self):
        return list(self.body)

    def parrafo(self, prefijo, despues_de=None):
        hijos = self.hijos()
        inicio = hijos.index(despues_de) + 1 if despues_de is not None else 0
        for el in hijos[inicio:]:
            if el.tag == qn("w:p") and texto(el).startswith(prefijo):
                return el
        raise KeyError(f"No se encontró un párrafo que empiece con: {prefijo!r}")

    def siguiente(self, elemento, etiqueta="w:tbl"):
        hijos = self.hijos()
        for el in hijos[hijos.index(elemento) + 1:]:
            if el.tag == qn(etiqueta):
                return el
        raise KeyError("No hay elemento siguiente")

    def imagen_tras(self, leyenda_el):
        """Párrafo con la imagen que sigue a una leyenda de figura."""
        hijos = self.hijos()
        for el in hijos[hijos.index(leyenda_el) + 1:]:
            if el.find(".//" + qn("w:drawing")) is not None:
                return el
        raise KeyError("No hay imagen tras la leyenda")

    @staticmethod
    def insertar_despues(ancla, *elementos):
        for el in elementos:
            if isinstance(el, list):
                for sub in el:
                    ancla.addnext(sub)
                    ancla = sub
            else:
                ancla.addnext(el)
                ancla = el
        return ancla

    @staticmethod
    def eliminar(*elementos):
        for el in elementos:
            el.getparent().remove(el)

    def eliminar_entre(self, desde, hasta):
        """Elimina los elementos estrictamente entre desde y hasta."""
        hijos = self.hijos()
        for el in hijos[hijos.index(desde) + 1:hijos.index(hasta)]:
            self.body.remove(el)

    @staticmethod
    def poner_texto(parrafo_el, nuevo):
        """Reemplaza el texto conservando pPr y el formato del primer run."""
        runs = parrafo_el.findall(qn("w:r"))
        rpr = runs[0].find(qn("w:rPr")) if runs else None
        for r in runs:
            parrafo_el.remove(r)
        for sub in parse_xml(f"<w:p {NS}>{runs_enriquecidos(nuevo)}</w:p>").findall(qn("w:r")):
            if rpr is not None and sub.find(qn("w:rPr")) is None:
                sub.insert(0, deepcopy(rpr))
            parrafo_el.append(sub)

    @staticmethod
    def poner_texto_leyenda(leyenda_el, nuevo):
        """Cambia solo la descripción (tercer run) de una leyenda Tabla/Figura/Código."""
        runs = leyenda_el.findall(qn("w:r"))
        runs[-1].find(qn("w:t")).text = nuevo
        for r in runs[2:-1]:
            leyenda_el.remove(r)

    def reemplazar_tabla(self, leyenda_el, nueva):
        vieja = self.siguiente(leyenda_el)
        vieja.addprevious(nueva)
        self.body.remove(vieja)


# ------------------------------------------------------------ numeración
PATRON_LEYENDA = re.compile(r"^(?:(Tabla|Figura|Código) (\d+)|⟦(Tabla|Figura|Código):([^⟧]+)⟧)\.$")
PATRON_REF = re.compile(r"(Tabla|Figura|Código) (\d+)\b|⟦(Tabla|Figura|Código):([^⟧]+)⟧")


def renumerar(cuerpo):
    """Numera leyendas en orden de aparición y actualiza todas las referencias del texto."""
    mapa = {"Tabla": {}, "Figura": {}, "Código": {}}
    contador = {k: 0 for k in mapa}
    for el in cuerpo.hijos():
        if el.tag != qn("w:p"):
            continue
        primer = el.find(qn("w:r"))
        if primer is None:
            continue
        t = texto(primer).strip()
        m = PATRON_LEYENDA.match(t)
        if m:
            tipo, clave = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            contador[tipo] += 1
            mapa[tipo][clave] = contador[tipo]

    def sustituir(m):
        if m.group(1):
            tipo, clave = m.group(1), m.group(2)
        else:
            tipo, clave = m.group(3), m.group(4)
        numero = mapa[tipo].get(clave)
        if numero is None:
            return m.group(0) if m.group(1) else f"{tipo} ??"
        return f"{tipo} {numero}"

    for t in cuerpo.body.iter(qn("w:t")):
        if t.text:
            t.text = PATRON_REF.sub(sustituir, t.text)

    # Referencias partidas entre runs ("Tabla" en un run y el número en otro) no se pueden
    # actualizar de forma segura: se informan para revisarlas a mano.
    partidas = []
    for p in cuerpo.body.iter(qn("w:p")):
        for r in p.findall(qn("w:r")):
            if re.search(r"(Tabla|Figura|Código)\s*$", texto(r)) and texto(p).strip() not in ("Tabla", "Figura", "Código"):
                partidas.append(texto(p)[:80])
                break
    return mapa, contador, partidas
