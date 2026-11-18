"""Reglas de recetas, entregas fraccionadas, unidosis y rótulo (RN-04, RF-01, RF-06).

Tipos de receta (D.S. 466 y práctica de APS):
  * AGUDA: una entrega, vigente 30 días desde la emisión.
  * RETENIDA: medicamentos controlados; una entrega, vigente 30 días.
  * CRONICA: de 2 a 6 entregas cada `intervalo_dias`. La primera se retira dentro
    de 30 días; las siguientes, hasta 6 meses (180 días) desde la emisión.
Una entrega posterior no se puede retirar más de 5 días antes de su fecha.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from .errores import ReglaNegocioError

DIAS_VIGENCIA_RECETA = 30      # RN-04: primera entrega (y única, en agudas y retenidas)
DIAS_VIGENCIA_CRONICA = 180    # D4: hasta completar las entregas, máximo 6 meses
TOLERANCIA_RETIRO_DIAS = 5     # D5: se puede retirar hasta 5 días antes de la fecha
MAX_ENTREGAS_CRONICA = 6


def dias_de_vigencia(tipo_receta: str = "AGUDA", entregas_realizadas: int = 0) -> int:
    if tipo_receta == "CRONICA" and entregas_realizadas > 0:
        return DIAS_VIGENCIA_CRONICA
    return DIAS_VIGENCIA_RECETA


def receta_vigente(fecha_emision: date, hoy: date, tipo_receta: str = "AGUDA", entregas_realizadas: int = 0) -> bool:
    dias = (hoy - fecha_emision).days
    return 0 <= dias <= dias_de_vigencia(tipo_receta, entregas_realizadas)


def exigir_receta_vigente(fecha_emision: date, hoy: date, tipo_receta: str = "AGUDA",
                          entregas_realizadas: int = 0) -> None:
    if fecha_emision > hoy:
        raise ReglaNegocioError("RECETA_INVALIDA", "La receta tiene fecha de emisión futura.")
    if not receta_vigente(fecha_emision, hoy, tipo_receta, entregas_realizadas):
        dias = dias_de_vigencia(tipo_receta, entregas_realizadas)
        raise ReglaNegocioError("RECETA_VENCIDA", f"La receta tiene más de {dias} días (RN-04).")


def validar_estructura(tipo_receta: str, total_entregas: int, intervalo_dias: int, hay_controlados: bool) -> None:
    """Combinaciones válidas de tipo y número de entregas (la base también las exige)."""
    if tipo_receta not in ("AGUDA", "CRONICA", "RETENIDA"):
        raise ReglaNegocioError("TIPO_RECETA_INVALIDO", "El tipo de receta debe ser AGUDA, CRONICA o RETENIDA.")
    if hay_controlados and tipo_receta != "RETENIDA":
        raise ReglaNegocioError("RECETA_NO_RETENIDA", "Un medicamento controlado exige receta retenida (D.S. 466).")
    if tipo_receta == "CRONICA" and not 2 <= total_entregas <= MAX_ENTREGAS_CRONICA:
        raise ReglaNegocioError("ENTREGAS_INVALIDAS",
                                f"Una receta crónica tiene entre 2 y {MAX_ENTREGAS_CRONICA} entregas.")
    if tipo_receta != "CRONICA" and total_entregas != 1:
        raise ReglaNegocioError("ENTREGAS_INVALIDAS",
                                "Una receta aguda o retenida tiene una sola entrega; use una receta crónica.")
    if not 7 <= intervalo_dias <= 90:
        raise ReglaNegocioError("INTERVALO_INVALIDO", "El intervalo entre entregas debe ser de 7 a 90 días.")


def pendiente(cant_prescrita: int, cant_entregada: int) -> int:
    return max(cant_prescrita - cant_entregada, 0)


def entregas_completas(lineas: list[tuple[int, int]]) -> int:
    """Entregas completas de una receta: la línea más atrasada manda.

    Cada línea es (cantidad entregada, cantidad por entrega). Si en la entrega 2
    faltó un medicamento por quiebre de stock, la entrega 2 no está completa.
    """
    if not lineas:
        return 0
    return min(entregada // por_entrega for entregada, por_entrega in lineas)


@dataclass(frozen=True)
class LineaEntrega:
    cant_prescrita: int
    cant_por_entrega: int
    cant_entregada: int


def saldo_entrega_actual(linea: LineaEntrega, entregas_realizadas: int) -> int:
    """Lo que falta entregar de esta línea en la entrega en curso (la n.º entregas_realizadas + 1).

    Impide adelantar en una sola visita las unidades de la entrega siguiente.
    """
    tope = min(linea.cant_por_entrega * (entregas_realizadas + 1), linea.cant_prescrita)
    return max(tope - linea.cant_entregada, 0)


def entrega_en_curso_iniciada(lineas: list[LineaEntrega], entregas_realizadas: int) -> bool:
    """True si la entrega en curso ya tuvo una entrega parcial (por ejemplo, por quiebre de stock)."""
    return any(l.cant_entregada > l.cant_por_entrega * entregas_realizadas for l in lineas)


def exigir_fecha_de_retiro(proxima_fecha: date | None, hoy: date, iniciada: bool) -> None:
    """No se adelanta una entrega: se retira desde `proxima_fecha − 5 días`.

    Completar una entrega que quedó parcial se permite en cualquier momento.
    """
    if iniciada or proxima_fecha is None:
        return
    desde = proxima_fecha - timedelta(days=TOLERANCIA_RETIRO_DIAS)
    if hoy < desde:
        raise ReglaNegocioError("RETIRO_ANTICIPADO",
                                f"La próxima entrega se puede retirar desde el {desde.strftime('%d-%m-%Y')} "
                                f"(fecha programada {proxima_fecha.strftime('%d-%m-%Y')}).")


def proxima_fecha_retiro(*, fecha_emision: date, total_entregas: int, entregas_realizadas: int,
                         fecha_ultima_entrega: date | None, intervalo_dias: int) -> date | None:
    """Desde cuándo el paciente puede retirar su siguiente entrega (None si ya no quedan)."""
    if entregas_realizadas >= total_entregas:
        return None
    if entregas_realizadas == 0 or fecha_ultima_entrega is None:
        return fecha_emision
    return fecha_ultima_entrega + timedelta(days=intervalo_dias)


def requiere_fraccion(cantidad: int, unidades_envase: int) -> bool:
    """Unidosis: indica si la entrega obliga a fraccionar un envase."""
    return cantidad % unidades_envase != 0


def generar_rotulo(*, medicamento: str, codigo_lote: str, fecha_vencimiento: date,
                   cantidad: int, posologia: str, paciente: str, programa: str | None,
                   entrega: str | None = None) -> dict:
    return {
        "medicamento": medicamento,
        "lote": codigo_lote,
        "vencimiento": fecha_vencimiento.isoformat(),
        "cantidad": cantidad,
        "posologia": posologia,
        "paciente": paciente,
        "programa": programa or "-",
        "entrega": entrega,
    }
