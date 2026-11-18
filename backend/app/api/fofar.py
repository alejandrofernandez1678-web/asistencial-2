"""Programa Fondo de Farmacia: faltantes y reclamos, toma de inventario, actividades
farmacéuticas, préstamos e indicadores."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..models import Usuarios
from ..reloj import ahora
from ..security.rbac import Permisos as P
from ..security.rbac import tiene_permiso
from ..services import actividades, faltantes, indicadores, prestamos, series, toma_inventario
from .deps import fecha_hoy, requiere, sesion
from .schemas import (ActividadNueva, CierreReclamo, CierreToma, Conteo, DevolucionPrestamo, Motivo, NotificacionIsp,
                      PrestamoNuevo, Programacion, ReclamoNuevo, TomaNueva)

router = APIRouter(prefix="/api", tags=["fofar"])


# ------------------------------------------------------------ faltantes y reclamos
@router.post("/recetas/{id_receta}/sin-stock", status_code=201)
def registrar_sin_stock(id_receta: int, db: Session = Depends(sesion),
                        usuario: Usuarios = Depends(requiere(P.DISPENSAR)), hoy: date = Depends(fecha_hoy)):
    resultado = faltantes.registrar_sin_stock(db, usuario, id_receta, hoy)
    db.commit()
    return resultado


@router.get("/faltantes")
def listar_faltantes(estado: list[str] | None = Query(None), db: Session = Depends(sesion),
                     _: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    return faltantes.listar_faltantes(db, estado)


@router.get("/reclamos")
def listar_reclamos(estado: list[str] | None = Query(None), db: Session = Depends(sesion),
                    _: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    return faltantes.listar_reclamos(db, estado)


@router.post("/reclamos", status_code=201)
def registrar_reclamo(datos: ReclamoNuevo, db: Session = Depends(sesion),
                      usuario: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    reclamo = faltantes.registrar_reclamo(db, usuario, **datos.model_dump())
    db.commit()
    return faltantes.describir_reclamo(reclamo, ahora())


@router.post("/reclamos/{id_reclamo}/cerrar")
def cerrar_reclamo(id_reclamo: int, datos: CierreReclamo, db: Session = Depends(sesion),
                   usuario: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    reclamo = faltantes.cerrar_reclamo(db, usuario, id_reclamo, **datos.model_dump())
    db.commit()
    return faltantes.describir_reclamo(reclamo, ahora())


@router.post("/reclamos/{id_reclamo}/no-atingente")
def reclamo_no_atingente(id_reclamo: int, datos: Motivo, db: Session = Depends(sesion),
                         usuario: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    reclamo = faltantes.marcar_no_atingente(db, usuario, id_reclamo, datos.motivo)
    db.commit()
    return faltantes.describir_reclamo(reclamo, ahora())


@router.get("/reclamos/{id_reclamo}/acta")
def acta_reclamo(id_reclamo: int, db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.GESTIONAR_RECLAMOS))):
    return faltantes.acta_reclamo(db, id_reclamo)


# ---------------------------------------------------------------- toma de inventario
@router.get("/inventario/tomas")
def listar_tomas(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.CONTAR_INVENTARIO))):
    return toma_inventario.listar_tomas(db)


@router.post("/inventario/tomas", status_code=201)
def abrir_toma(datos: TomaNueva, db: Session = Depends(sesion),
               usuario: Usuarios = Depends(requiere(P.APROBAR_INVENTARIO))):
    toma = toma_inventario.abrir_toma(db, usuario, **datos.model_dump())
    db.commit()
    return toma_inventario.describir_toma(toma, ver_sistema=True)


@router.get("/inventario/tomas/{id_toma}")
def ver_toma(id_toma: int, db: Session = Depends(sesion), usuario: Usuarios = Depends(requiere(P.CONTAR_INVENTARIO))):
    """Quien solo cuenta ve la toma a ciegas; el Q.F. ve el stock del sistema y las diferencias."""
    return toma_inventario.describir_toma(toma_inventario.obtener_toma(db, id_toma),
                                          ver_sistema=tiene_permiso(usuario.rol.nombre, P.APROBAR_INVENTARIO))


@router.post("/inventario/tomas/{id_toma}/conteos")
def registrar_conteo(id_toma: int, datos: Conteo, db: Session = Depends(sesion),
                     usuario: Usuarios = Depends(requiere(P.CONTAR_INVENTARIO))):
    conteo = toma_inventario.registrar_conteo(db, usuario, id_toma, datos.id_conteo, datos.cantidad)
    db.commit()
    return {"id_conteo": conteo.id_conteo, "cantidad_contada": conteo.cantidad_contada}


@router.post("/inventario/tomas/{id_toma}/cerrar")
def cerrar_toma(id_toma: int, datos: CierreToma, db: Session = Depends(sesion),
                usuario: Usuarios = Depends(requiere(P.APROBAR_INVENTARIO))):
    toma = toma_inventario.cerrar_toma(db, usuario, id_toma, datos.observacion)
    db.commit()
    return toma_inventario.describir_toma(toma, ver_sistema=True)


# ---------------------------------------------------------- actividades farmacéuticas
@router.get("/actividades")
def listar_actividades(anio: int | None = Query(None, ge=2020, le=2100), tipo: str | None = None,
                       db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD)),
                       hoy: date = Depends(fecha_hoy)):
    return actividades.listar_actividades(db, anio or hoy.year, tipo)


@router.post("/actividades", status_code=201)
def registrar_actividad(datos: ActividadNueva, db: Session = Depends(sesion),
                        usuario: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD)), hoy: date = Depends(fecha_hoy)):
    actividad = actividades.registrar_actividad(db, usuario, hoy=hoy, **datos.model_dump())
    db.commit()
    return actividades.describir_actividad(actividad)


@router.get("/actividades/programacion/{anio}")
def ver_programacion(anio: int, db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD)),
                     hoy: date = Depends(fecha_hoy)):
    """Cumplimiento del año: al 31 de diciembre si ya terminó, a hoy si está en curso."""
    return indicadores.actividades_farmaceuticas(db, date(anio, 12, 31) if anio < hoy.year else hoy)


@router.put("/actividades/programacion/{anio}")
def programar_actividades(anio: int, datos: Programacion, db: Session = Depends(sesion),
                          usuario: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD))):
    programacion = actividades.programar(db, usuario, anio, datos.cantidad)
    db.commit()
    return {"anio": programacion.anio, "cantidad": programacion.cantidad}


@router.get("/actividades/{id_actividad}")
def ver_actividad(id_actividad: int, db: Session = Depends(sesion),
                  _: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD))):
    return actividades.describir_actividad(actividades.obtener_actividad(db, id_actividad))


@router.post("/actividades/{id_actividad}/anular")
def anular_actividad(id_actividad: int, datos: Motivo, db: Session = Depends(sesion),
                     usuario: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD))):
    actividad = actividades.anular_actividad(db, usuario, id_actividad, datos.motivo)
    db.commit()
    return actividades.describir_actividad(actividad)


@router.post("/actividades/{id_actividad}/notificacion")
def notificar_isp(id_actividad: int, datos: NotificacionIsp, db: Session = Depends(sesion),
                  usuario: Usuarios = Depends(requiere(P.REGISTRAR_ACTIVIDAD)), hoy: date = Depends(fecha_hoy)):
    actividad = actividades.registrar_notificacion(db, usuario, id_actividad, hoy=hoy, **datos.model_dump())
    db.commit()
    return actividades.describir_actividad(actividad)


# ------------------------------------------------------------------- préstamos
@router.get("/prestamos")
def listar_prestamos(solo_pendientes: bool = False, db: Session = Depends(sesion),
                     _: Usuarios = Depends(requiere(P.GESTIONAR_PRESTAMOS)), hoy: date = Depends(fecha_hoy)):
    return prestamos.listar_prestamos(db, hoy, solo_pendientes)


@router.post("/prestamos", status_code=201)
def registrar_prestamo(datos: PrestamoNuevo, db: Session = Depends(sesion),
                       usuario: Usuarios = Depends(requiere(P.GESTIONAR_PRESTAMOS)), hoy: date = Depends(fecha_hoy)):
    prestamo = prestamos.registrar_prestamo(db, usuario, hoy=hoy, **datos.model_dump())
    db.commit()
    return prestamos.describir_prestamo(prestamo, hoy)


@router.post("/prestamos/{id_prestamo}/devolver")
def devolver_prestamo(id_prestamo: int, datos: DevolucionPrestamo, db: Session = Depends(sesion),
                      usuario: Usuarios = Depends(requiere(P.GESTIONAR_PRESTAMOS)), hoy: date = Depends(fecha_hoy)):
    prestamo = prestamos.devolver_prestamo(db, usuario, id_prestamo, hoy, **datos.model_dump())
    db.commit()
    return prestamos.describir_prestamo(prestamo, hoy)


# ------------------------------------------------------------------ indicadores
@router.get("/indicadores/fofar/mensual")
def indicadores_mensuales(desde: date, hasta: date, db: Session = Depends(sesion),
                          _: Usuarios = Depends(requiere(P.VER_REPORTES))):
    """Evolución mes a mes de los indicadores 1 y 3 en el período y avance acumulado del 4 (gráficos)."""
    return series.fofar_mensual(db, desde, hasta)


@router.get("/indicadores/fofar")
def indicadores_fofar(desde: date, hasta: date, db: Session = Depends(sesion),
                      _: Usuarios = Depends(requiere(P.VER_REPORTES))):
    return indicadores.resumen_fofar(db, desde, hasta, ahora())
