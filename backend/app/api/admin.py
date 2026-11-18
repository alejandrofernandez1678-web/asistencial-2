from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventosPendientes, Usuarios
from ..security.rbac import Permisos as P
from ..services import catalogo
from .deps import requiere, sesion
from ..reloj import iso_utc
from .schemas import Motivo, UsuarioNuevo

router = APIRouter(prefix="/api", tags=["administración"])


@router.get("/usuarios")
def listar_usuarios(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.GESTIONAR_USUARIOS))):
    return [catalogo.describir_usuario(u) for u in db.scalars(select(Usuarios).order_by(Usuarios.nombre)).unique()]


@router.post("/usuarios", status_code=201)
def crear_usuario(datos: UsuarioNuevo, db: Session = Depends(sesion),
                  admin: Usuarios = Depends(requiere(P.GESTIONAR_USUARIOS))):
    usuario = catalogo.crear_usuario(db, admin, **datos.model_dump())
    db.commit()
    return catalogo.describir_usuario(usuario)


@router.post("/usuarios/{id_usuario}/baja")
def dar_de_baja_usuario(id_usuario: int, datos: Motivo, db: Session = Depends(sesion),
                        admin: Usuarios = Depends(requiere(P.GESTIONAR_USUARIOS))):
    usuario = catalogo.dar_de_baja_usuario(db, admin, id_usuario, datos.motivo)
    db.commit()
    return catalogo.describir_usuario(usuario)


@router.get("/auditoria")
def auditoria(limite: int = Query(50, le=500), tipo: str | None = None, db: Session = Depends(sesion),
              _: Usuarios = Depends(requiere(P.VER_AUDITORIA))):
    consulta = select(EventosPendientes).order_by(EventosPendientes.id_evento.desc()).limit(limite)
    if tipo:
        consulta = consulta.where(EventosPendientes.tipo_evento == tipo)
    return [{"id_evento": e.id_evento, "tipo_evento": e.tipo_evento, "entidad": e.entidad,
             "id_entidad": e.id_entidad, "id_usuario": e.id_usuario, "payload": e.payload,
             "creado_en": iso_utc(e.creado_en)} for e in db.scalars(consulta)]
