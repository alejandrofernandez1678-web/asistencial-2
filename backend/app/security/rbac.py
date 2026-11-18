"""Matriz RBAC (Tabla 24 del informe): qué puede hacer cada rol.

El principio es mínimo privilegio: un permiso que no está en la lista se
deniega. La interfaz usa la misma matriz para ocultar menús, pero la
decisión real siempre se toma aquí, en el servidor.
"""

from enum import StrEnum


class Permisos(StrEnum):
    VER_STOCK = "ver_stock"
    DISPENSAR = "dispensar"
    REGISTRAR_PACIENTE = "registrar_paciente"
    REGISTRAR_RECETA = "registrar_receta"
    GESTIONAR_DESPACHOS = "gestionar_despachos"
    REGISTRAR_DEVOLUCION = "registrar_devolucion"
    FIRMAR_CONTROLADOS = "firmar_controlados"
    ANULAR_DISPENSACION = "anular_dispensacion"
    VER_LIBRO = "ver_libro"
    GESTIONAR_LOTES = "gestionar_lotes"
    ANULAR_LOTE = "anular_lote"
    REGISTRAR_MERMA = "registrar_merma"
    GESTIONAR_MEDICAMENTOS = "gestionar_medicamentos"
    GESTIONAR_USUARIOS = "gestionar_usuarios"
    VER_AUDITORIA = "ver_auditoria"
    VER_REPORTES = "ver_reportes"
    GESTIONAR_RECLAMOS = "gestionar_reclamos"        # faltantes y reclamos FOFAR (ventanilla)
    CONTAR_INVENTARIO = "contar_inventario"          # registrar conteos a ciegas
    APROBAR_INVENTARIO = "aprobar_inventario"        # abrir y cerrar tomas, aplicar diferencias
    REGISTRAR_ACTIVIDAD = "registrar_actividad"      # atención farmacéutica y farmacovigilancia
    GESTIONAR_PRESTAMOS = "gestionar_prestamos"      # préstamos con otros establecimientos


P = Permisos

MATRIZ_RBAC: dict[str, frozenset[Permisos]] = {
    "TECNICO": frozenset({P.VER_STOCK, P.DISPENSAR, P.REGISTRAR_PACIENTE, P.REGISTRAR_RECETA,
                          P.GESTIONAR_DESPACHOS, P.GESTIONAR_RECLAMOS, P.CONTAR_INVENTARIO}),
    "BODEGUERO": frozenset({P.VER_STOCK, P.GESTIONAR_LOTES, P.REGISTRAR_MERMA, P.VER_REPORTES,
                            P.CONTAR_INVENTARIO, P.GESTIONAR_PRESTAMOS}),
    "QF": frozenset({P.VER_STOCK, P.DISPENSAR, P.REGISTRAR_PACIENTE, P.REGISTRAR_RECETA, P.FIRMAR_CONTROLADOS,
                     P.ANULAR_DISPENSACION, P.VER_LIBRO, P.GESTIONAR_LOTES, P.ANULAR_LOTE, P.REGISTRAR_MERMA,
                     P.GESTIONAR_MEDICAMENTOS, P.VER_AUDITORIA, P.GESTIONAR_DESPACHOS, P.REGISTRAR_DEVOLUCION,
                     P.VER_REPORTES, P.GESTIONAR_RECLAMOS, P.CONTAR_INVENTARIO, P.APROBAR_INVENTARIO,
                     P.REGISTRAR_ACTIVIDAD, P.GESTIONAR_PRESTAMOS}),
    "MEDICO": frozenset({P.VER_STOCK, P.REGISTRAR_RECETA}),  # prescribe; no dispensa (separación de funciones)
    "ADMIN": frozenset({P.VER_STOCK, P.GESTIONAR_USUARIOS, P.GESTIONAR_MEDICAMENTOS, P.VER_AUDITORIA,
                        P.VER_REPORTES}),
}


def tiene_permiso(rol: str, permiso: Permisos) -> bool:
    return permiso in MATRIZ_RBAC.get(rol, frozenset())
