from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..domain.rut import normalizar_rut
from ..models import Dispensaciones, Pacientes, Recetas, Usuarios
from ..security.claves import hmac_rut
from ..security.rbac import Permisos as P
from ..services import dispensacion as servicio
from ..services import apoderados, pacientes, recetas
from .deps import fecha_hoy, requiere, sesion
from ..reloj import iso_utc
from .schemas import DispensacionNueva, Entrada, Motivo, PacienteNuevo, RecetaNueva

router = APIRouter(prefix="/api", tags=["dispensación"])


class BusquedaPaciente(Entrada):
    rut: str = Field(max_length=12)


@router.post("/pacientes", status_code=201)
def registrar_paciente(datos: PacienteNuevo, db: Session = Depends(sesion),
                       usuario: Usuarios = Depends(requiere(P.REGISTRAR_PACIENTE)),
                       hoy: date = Depends(fecha_hoy)):
    paciente = pacientes.registrar_paciente(db, usuario, hoy=hoy, **datos.model_dump())
    db.commit()
    return pacientes.describir_paciente(paciente)


def _ficha(db: Session, paciente: Pacientes, hoy: date) -> dict:
    filas = db.scalars(select(Recetas).where(Recetas.id_paciente == paciente.id_paciente)
                       .order_by(Recetas.fecha_emision.desc(), Recetas.id_receta.desc())).unique()
    return {
        "paciente": pacientes.describir_paciente(paciente),
        "apoderados": [apoderados.describir_apoderado(a, hoy)
                       for a in apoderados.listar_apoderados(db, paciente.id_paciente)],
        "recetas": [recetas.describir_receta(r, hoy) for r in filas],
    }


@router.post("/pacientes/buscar")
def buscar_paciente(datos: BusquedaPaciente, db: Session = Depends(sesion),
                    _: Usuarios = Depends(requiere(P.DISPENSAR, P.REGISTRAR_RECETA)), hoy: date = Depends(fecha_hoy)):
    """El RUT va en el cuerpo (POST) y no en la URL para que no quede en registros de acceso."""
    paciente = db.scalar(select(Pacientes).where(Pacientes.rut_hmac == hmac_rut(normalizar_rut(datos.rut))))
    if paciente is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "No hay un paciente registrado con ese RUT.")
    return _ficha(db, paciente, hoy)


@router.get("/pacientes/{id_paciente}/ficha")
def ficha_paciente(id_paciente: int, db: Session = Depends(sesion),
                   _: Usuarios = Depends(requiere(P.DISPENSAR, P.REGISTRAR_RECETA)), hoy: date = Depends(fecha_hoy)):
    """Ficha por identificador interno (desde la lista de retiros, sin volver a escribir el RUT)."""
    paciente = db.get(Pacientes, id_paciente)
    if paciente is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El paciente no existe.")
    return _ficha(db, paciente, hoy)


@router.get("/recetas/retiros")
def retiros(dias: int = Query(0, ge=0, le=30), db: Session = Depends(sesion),
            _: Usuarios = Depends(requiere(P.DISPENSAR)), hoy: date = Depends(fecha_hoy)):
    return recetas.retiros_pendientes(db, hoy, dias)


@router.post("/recetas", status_code=201)
def registrar_receta(datos: RecetaNueva, db: Session = Depends(sesion),
                     usuario: Usuarios = Depends(requiere(P.REGISTRAR_RECETA)), hoy: date = Depends(fecha_hoy)):
    receta = recetas.registrar_receta(
        db, usuario, id_paciente=datos.id_paciente, folio=datos.folio, fecha_emision=datos.fecha_emision,
        es_retenida=datos.es_retenida, tipo_receta=datos.tipo_receta, total_entregas=datos.total_entregas,
        intervalo_dias=datos.intervalo_dias, hoy=hoy, prescriptor_nombre=datos.prescriptor_nombre,
        prescriptor_rut=datos.prescriptor_rut, domicilio_paciente=datos.domicilio_paciente,
        numero_receta_cheque=datos.numero_receta_cheque,
        lineas=[recetas.LineaReceta(**l.model_dump()) for l in datos.lineas])
    db.commit()
    return recetas.describir_receta(receta, hoy)


@router.get("/dispensaciones/plan")
def plan_fefo(id_detalle_receta: int, cantidad: int = Query(gt=0, le=10000), db: Session = Depends(sesion),
              _: Usuarios = Depends(requiere(P.DISPENSAR)), hoy: date = Depends(fecha_hoy)):
    return servicio.planificar_linea(db, id_detalle_receta, cantidad, hoy)


@router.post("/dispensaciones", status_code=201)
def dispensar(datos: DispensacionNueva, db: Session = Depends(sesion),
              usuario: Usuarios = Depends(requiere(P.DISPENSAR)), hoy: date = Depends(fecha_hoy)):
    resultado = servicio.dispensar(
        db, usuario, id_receta=datos.id_receta, clave_idempotencia=datos.clave_idempotencia, hoy=hoy,
        lineas=[servicio.LineaDispensacion(**l.model_dump()) for l in datos.lineas],
        rut_retira=datos.rut_retira, relacion=datos.relacion, retira_tipo=datos.retira_tipo,
        id_apoderado=datos.id_apoderado, confirma_alergias=datos.confirma_alergias, a_domicilio=datos.a_domicilio,
        motivos_incompletos=datos.motivos_incompletos,
        firma_qf=servicio.FirmaQF(**datos.firma_qf.model_dump()) if datos.firma_qf else None)
    db.commit()
    return resultado


@router.get("/dispensaciones")
def listar_dispensaciones(limite: int = Query(30, le=200), db: Session = Depends(sesion),
                          _: Usuarios = Depends(requiere(P.ANULAR_DISPENSACION))):
    filas = db.scalars(select(Dispensaciones).order_by(Dispensaciones.id_dispensacion.desc()).limit(limite)).unique()
    return [{"id_dispensacion": d.id_dispensacion, "folio": d.receta.folio, "paciente": d.receta.paciente.nombre,
             "fecha_hora": iso_utc(d.fecha_hora), "estado": d.estado, "motivo_anulacion": d.motivo_anulacion,
             "numero_entrega": d.numero_entrega, "total_entregas": d.receta.total_entregas,
             "retira_tipo": d.retira_tipo, "relacion": d.relacion,
             "lineas": [{"id_detalle_disp": x.id_detalle_disp, "medicamento": x.lote.medicamento.nombre,
                         "es_controlado": x.lote.medicamento.es_controlado, "lote": x.lote.codigo_lote,
                         "cantidad": x.cantidad} for x in d.detalles]} for d in filas]


@router.get("/dispensaciones/{id_dispensacion}/rotulos")
def rotulos(id_dispensacion: int, db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.DISPENSAR))):
    """Reimpresión de las etiquetas de posología de una entrega."""
    return servicio.rotulos_de(db, id_dispensacion)


@router.post("/dispensaciones/{id_dispensacion}/anular")
def anular(id_dispensacion: int, datos: Motivo, db: Session = Depends(sesion),
           usuario: Usuarios = Depends(requiere(P.ANULAR_DISPENSACION))):
    resultado = servicio.anular_dispensacion(db, usuario, id_dispensacion, datos.motivo)
    db.commit()
    return resultado


@router.get("/controlados/libro")
def libro(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_LIBRO))):
    return servicio.listar_libro(db)


@router.get("/controlados/verificar")
def verificar(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_LIBRO))):
    return servicio.verificar_libro(db)
