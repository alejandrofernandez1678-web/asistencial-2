"""Planificador FEFO (First Expired, First Out) - RF-02, RN-02, RN-06.

Es un servicio de dominio puro: recibe los lotes ya leídos y no conoce la
base de datos, por lo que se prueba sin infraestructura.
"""

from dataclasses import dataclass
from datetime import date

from .errores import ReglaNegocioError
from .lotes import EstadosRegistroLote, es_dispensable, estado_lote


@dataclass(frozen=True)
class LoteFEFO:
    id_lote: int
    codigo_lote: str
    id_medicamento: int
    fecha_vencimiento: date
    unidades_disp: int
    ubicacion: str = ""
    estado_registro: str = EstadosRegistroLote.DISPONIBLE

    def estado(self, hoy: date):
        return estado_lote(self.fecha_vencimiento, self.unidades_disp, hoy, self.estado_registro)


@dataclass(frozen=True)
class Asignacion:
    lote: LoteFEFO
    cantidad: int


def planificar(lotes: list[LoteFEFO], id_medicamento: int, cantidad: int, hoy: date) -> list[Asignacion]:
    """Reparte la cantidad entre los lotes dispensables, del que vence primero al último."""
    if not isinstance(cantidad, int) or cantidad <= 0:
        raise ReglaNegocioError("CANTIDAD_INVALIDA", "La cantidad debe ser un entero mayor que cero.")

    candidatos = sorted(
        (l for l in lotes if l.id_medicamento == id_medicamento and es_dispensable(l.estado(hoy))),
        key=lambda l: (l.fecha_vencimiento, l.id_lote),
    )
    disponible = sum(l.unidades_disp for l in candidatos)
    if disponible < cantidad:
        raise ReglaNegocioError(
            "STOCK_INSUFICIENTE",
            f"Stock dispensable insuficiente: se piden {cantidad} y hay {disponible}.",
        )

    plan, pendiente = [], cantidad
    for lote in candidatos:
        tomar = min(lote.unidades_disp, pendiente)
        plan.append(Asignacion(lote, tomar))
        pendiente -= tomar
        if pendiente == 0:
            break
    return plan


def validar_lote_escaneado(lotes: list[LoteFEFO], id_medicamento: int, codigo_escaneado: str,
                           plan: list[Asignacion], hoy: date) -> Asignacion:
    """RN-06: el lote escaneado debe ser uno de los indicados por el plan FEFO."""
    for asignacion in plan:
        if asignacion.lote.codigo_lote == codigo_escaneado:
            return asignacion

    lote = next((l for l in lotes if l.codigo_lote == codigo_escaneado), None)
    esperado = plan[0].lote
    indicacion = f"Debe entregar el lote {esperado.codigo_lote} del casillero {esperado.ubicacion}."
    if lote is None:
        raise ReglaNegocioError("LOTE_DESCONOCIDO", f"El lote {codigo_escaneado} no existe. {indicacion}")
    if lote.id_medicamento != id_medicamento:
        raise ReglaNegocioError("LOTE_OTRO_MEDICAMENTO",
                                f"El lote {codigo_escaneado} es de otro medicamento. {indicacion}")
    if not es_dispensable(lote.estado(hoy)):
        raise ReglaNegocioError("LOTE_NO_DISPENSABLE",
                                f"El lote {codigo_escaneado} está {lote.estado(hoy).value} (RN-02). {indicacion}")
    raise ReglaNegocioError("FEFO", f"El lote {codigo_escaneado} vence después que otro disponible. {indicacion}")
