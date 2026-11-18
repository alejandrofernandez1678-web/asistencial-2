from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..domain.errores import ReglaNegocioError
from ..models import Usuarios
from ..security.rbac import MATRIZ_RBAC
from ..services.autenticacion import autenticar
from .deps import sesion, usuario_actual
from .schemas import Login

router = APIRouter(prefix="/api/auth", tags=["autenticación"])


@router.post("/login")
def login(datos: Login, db: Session = Depends(sesion)):
    try:
        resultado = autenticar(db, datos.rut, datos.password)
    except ReglaNegocioError as error:
        db.commit()  # se guardan el intento fallido y su evento de auditoría
        codigo = status.HTTP_423_LOCKED if error.codigo == "CUENTA_BLOQUEADA" else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(codigo, error.mensaje) from None
    db.commit()
    return resultado


@router.get("/yo")
def yo(usuario: Usuarios = Depends(usuario_actual)):
    return {"id_usuario": usuario.id_usuario, "nombre": usuario.nombre, "rol": usuario.rol.nombre,
            "permisos": sorted(p.value for p in MATRIZ_RBAC.get(usuario.rol.nombre, ()))}
