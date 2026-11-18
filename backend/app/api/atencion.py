"""Atención al paciente más allá de la ventanilla: apoderados, despachos a domicilio y devoluciones."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..models import Usuarios
from ..security.rbac import Permisos as P
from ..services import apoderados, despachos, devoluciones
from .deps import fecha_hoy, requiere, sesion
from .schemas import ApoderadoNuevo, CambioDespacho, DevolucionNueva, Motivo

router = APIRouter(prefix="/api", tags=["atención"])


# ---------------------------------------------------------------- apoderados
@router.get("/pacientes/{id_paciente}/apoderados")
def listar_apoderados(id_paciente: int, incluir_inactivos: bool = False, db: Session = Depends(sesion),
                      _: Usuarios = Depends(requiere(P.DISPENSAR)), hoy: date = Depends(fecha_hoy)):
    return [apoderados.describir_apoderado(a, hoy)
            for a in apoderados.listar_apoderados(db, id_paciente, incluir_inactivos)]


@router.post("/pacientes/{id_paciente}/apoderados", status_code=201)
def registrar_apoderado(id_paciente: int, datos: ApoderadoNuevo, db: Session = Depends(sesion),
                        usuario: Usuarios = Depends(requiere(P.REGISTRAR_PACIENTE)), hoy: date = Depends(fecha_hoy)):
    apoderado = apoderados.registrar_apoderado(db, usuario, id_paciente=id_paciente, hoy=hoy, **datos.model_dump())
    db.commit()
    return apoderados.describir_apoderado(apoderado, hoy)


@router.post("/apoderados/{id_apoderado}/baja")
def dar_de_baja_apoderado(id_apoderado: int, datos: Motivo, db: Session = Depends(sesion),
                          usuario: Usuarios = Depends(requiere(P.REGISTRAR_PACIENTE)), hoy: date = Depends(fecha_hoy)):
    apoderado = apoderados.dar_de_baja_apoderado(db, usuario, id_apoderado, datos.motivo)
    db.commit()
    return apoderados.describir_apoderado(apoderado, hoy)


# ----------------------------------------------------------------- despachos
@router.get("/despachos")
def listar_despachos(estado: list[str] | None = Query(None), db: Session = Depends(sesion),
                     _: Usuarios = Depends(requiere(P.GESTIONAR_DESPACHOS))):
    return [despachos.describir_despacho(d) for d in despachos.listar_despachos(db, estado)]


@router.post("/despachos/{id_despacho}/estado")
def cambiar_estado_despacho(id_despacho: int, datos: CambioDespacho, db: Session = Depends(sesion),
                            usuario: Usuarios = Depends(requiere(P.GESTIONAR_DESPACHOS))):
    despacho = despachos.cambiar_estado(db, usuario, id_despacho, datos.estado, recibe_nombre=datos.recibe_nombre,
                                        observacion=datos.observacion)
    db.commit()
    return despachos.describir_despacho(despacho)


# -------------------------------------------------------------- devoluciones
@router.post("/devoluciones", status_code=201)
def registrar_devolucion(datos: DevolucionNueva, db: Session = Depends(sesion),
                         usuario: Usuarios = Depends(requiere(P.REGISTRAR_DEVOLUCION)), hoy: date = Depends(fecha_hoy)):
    devolucion = devoluciones.registrar_devolucion(db, usuario, hoy=hoy, **datos.model_dump())
    db.commit()
    return devoluciones.describir_devolucion(devolucion)
