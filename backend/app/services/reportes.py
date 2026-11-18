"""Reportes exportables en CSV (abren directo en Excel con configuración chilena).

* Separador `;` y BOM UTF-8, para que Excel en español reconozca columnas y tildes.
* Cada celda se neutraliza contra inyección de fórmulas (OWASP "CSV Injection"):
  si empieza con = + - @ o tabulador, se antepone un apóstrofo.
* Ningún reporte incluye RUT ni nombres de pacientes, salvo el libro de
  controlados, que exige el permiso del Q.F. y muestra el RUT enmascarado.
"""

import csv
import io
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..models import (AsientosControlados, DetallesDispensacion, DetallesReceta, Dispensaciones, Lotes, Medicamentos,
                      MovimientosStock, ProgramasSalud, Usuarios)
from .inventario import describir_lote

MAX_DIAS_RANGO = 366
_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def celda_segura(valor) -> str:
    texto = "" if valor is None else str(valor)
    if texto.startswith(_PELIGROSOS) and not _es_numero(texto):
        return "'" + texto
    return texto


def _es_numero(texto: str) -> bool:
    try:
        float(texto.replace(",", "."))
        return True
    except ValueError:
        return False


def a_csv(encabezados: list[str], filas: list[list]) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(encabezados)
    for fila in filas:
        escritor.writerow([celda_segura(v) for v in fila])
    return "﻿" + salida.getvalue()


def validar_rango(desde: date, hasta: date) -> tuple[datetime, datetime]:
    if desde > hasta:
        raise ReglaNegocioError("RANGO_INVALIDO", "La fecha inicial es posterior a la final.")
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise ReglaNegocioError("RANGO_INVALIDO", f"El rango no puede superar {MAX_DIAS_RANGO} días.")
    return (datetime.combine(desde, time.min).astimezone(UTC),
            datetime.combine(hasta + timedelta(days=1), time.min).astimezone(UTC))


def _fecha_hora(valor: datetime) -> str:
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone().strftime("%d-%m-%Y %H:%M")


def kardex(db: Session, desde: date, hasta: date) -> str:
    inicio, fin = validar_rango(desde, hasta)
    filas = db.execute(
        select(MovimientosStock, Lotes.codigo_lote, Medicamentos.nombre, Usuarios.nombre)
        .join(Lotes, Lotes.id_lote == MovimientosStock.id_lote)
        .join(Medicamentos, Medicamentos.id_medicamento == Lotes.id_medicamento)
        .join(Usuarios, Usuarios.id_usuario == MovimientosStock.id_usuario)
        .where(MovimientosStock.fecha_hora >= inicio, MovimientosStock.fecha_hora < fin)
        .order_by(MovimientosStock.fecha_hora, MovimientosStock.id_movimiento)).all()
    return a_csv(["Fecha", "Medicamento", "Lote", "Tipo", "Cantidad", "Stock anterior", "Stock posterior",
                  "Responsable", "Motivo", "Referencia"],
                 [[_fecha_hora(m.fecha_hora), medicamento, lote, m.tipo, m.cantidad, m.saldo_resultante - m.cantidad,
                   m.saldo_resultante, responsable, m.motivo or "",
                   f"{m.referencia_tipo} #{m.referencia_id}" if m.referencia_tipo else ""]
                  for m, lote, medicamento, responsable in filas])


def vencimientos(db: Session, hoy: date, dias: int) -> str:
    limite = hoy + timedelta(days=dias)
    lotes = db.scalars(select(Lotes).where(Lotes.unidades_disp > 0, Lotes.fecha_vencimiento <= limite,
                                           Lotes.estado.in_(["DISPONIBLE", "ALERTA_SANITARIA"]))
                       .order_by(Lotes.fecha_vencimiento)).unique()
    return a_csv(["Medicamento", "Lote", "Vence", "Días para vencer", "Unidades", "Estado", "Ubicación"],
                 [[d["medicamento"], d["codigo_lote"], date.fromisoformat(d["fecha_vencimiento"]).strftime("%d-%m-%Y"),
                   d["dias_para_vencer"], d["unidades_disp"], d["estado"], d["ubicacion"]]
                  for d in (describir_lote(l, hoy) for l in lotes)])


def entregas_por_programa(db: Session, desde: date, hasta: date) -> str:
    """Consumo agregado (sin datos de pacientes): base para el pedido mensual a CENABAST."""
    inicio, fin = validar_rango(desde, hasta)
    filas = db.execute(
        select(func.coalesce(ProgramasSalud.nombre, "Sin programa"), Medicamentos.nombre,
               func.count(func.distinct(Dispensaciones.id_dispensacion)), func.sum(DetallesDispensacion.cantidad))
        .select_from(DetallesDispensacion)
        .join(Dispensaciones, Dispensaciones.id_dispensacion == DetallesDispensacion.id_dispensacion)
        .join(DetallesReceta, DetallesReceta.id_detalle_receta == DetallesDispensacion.id_detalle_receta)
        .join(Medicamentos, Medicamentos.id_medicamento == DetallesReceta.id_medicamento)
        .outerjoin(ProgramasSalud, ProgramasSalud.id_programa == Medicamentos.id_programa)
        .where(Dispensaciones.estado == "VIGENTE", Dispensaciones.fecha_hora >= inicio, Dispensaciones.fecha_hora < fin)
        .group_by(ProgramasSalud.nombre, Medicamentos.nombre)
        .order_by(func.coalesce(ProgramasSalud.nombre, "Sin programa"), Medicamentos.nombre)).all()
    return a_csv(["Programa", "Medicamento", "Entregas", "Unidades entregadas"], [list(f) for f in filas])


ENTRADAS_LIBRO = ("INGRESO", "RECTIFICACION")


def _movimiento_libro(a: AsientosControlados) -> tuple[int | str, int | str]:
    """(entrada, salida) del asiento según el D.S. 404/405: ingresos, egresos y saldos."""
    c = a.contenido
    cantidad = c.get("cantidad", c.get("cantidad_repuesta", 0)) or 0
    if a.tipo == "AJUSTE":
        return (cantidad, "") if cantidad > 0 else ("", -cantidad)
    if a.tipo in ENTRADAS_LIBRO or (a.tipo == "DEVOLUCION" and c.get("destino") == "REINGRESO"):
        return cantidad, ""
    if a.tipo == "DEVOLUCION":
        return "", ""  # devolución descartada: no vuelve al stock, queda solo el registro
    return "", cantidad


def libro_controlados(db: Session) -> str:
    asientos = db.scalars(select(AsientosControlados).order_by(AsientosControlados.nro_asiento)).all()
    filas = []
    for a in asientos:
        c = a.contenido
        entrada, salida = _movimiento_libro(a)
        filas.append([a.nro_asiento, _fecha_hora(a.fecha_hora), a.tipo, c.get("medicamento", ""), c.get("nombre", ""),
                      c.get("lote", ""), entrada, salida, c.get("saldo", ""), c.get("proveedor", ""),
                      c.get("documento", ""), c.get("folio", ""), c.get("receta_cheque", ""),
                      c.get("prescriptor", ""), c.get("rut_prescriptor", ""), c.get("paciente", ""),
                      c.get("domicilio", ""), c.get("rut_retira", ""), c.get("relacion", ""),
                      c.get("motivo", ""), c.get("qf", ""), a.hash_actual])
    return a_csv(["N.º asiento", "Fecha", "Tipo", "Código", "Medicamento", "Lote", "Entrada", "Salida", "Saldo",
                  "Proveedor", "Documento", "Folio receta", "Receta cheque", "Prescriptor", "RUT prescriptor",
                  "Paciente", "Domicilio", "RUT retira", "Relación", "Detalle", "Q.F.", "Hash"], filas)
