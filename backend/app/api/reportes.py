"""Descarga de reportes CSV. Cada exportación queda en la auditoría (quién, qué y qué rango)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..models import Usuarios
from ..security.rbac import Permisos as P
from ..services import indicadores, reportes
from ..services.auditoria import registrar_evento
from .deps import fecha_hoy, requiere, sesion

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


def _descarga(db: Session, usuario: Usuarios, nombre: str, contenido: str, **filtros) -> Response:
    registrar_evento(db, tipo="REPORTE_EXPORTADO", entidad="reportes", id_entidad=None,
                     id_usuario=usuario.id_usuario, reporte=nombre, **{k: str(v) for k, v in filtros.items()})
    db.commit()
    return Response(contenido, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'})


@router.get("/kardex.csv")
def kardex(desde: date, hasta: date, db: Session = Depends(sesion),
           usuario: Usuarios = Depends(requiere(P.VER_REPORTES))):
    return _descarga(db, usuario, f"kardex_{desde}_{hasta}", reportes.kardex(db, desde, hasta), desde=desde, hasta=hasta)


@router.get("/vencimientos.csv")
def vencimientos(dias: int = Query(90, ge=1, le=365), db: Session = Depends(sesion),
                 usuario: Usuarios = Depends(requiere(P.VER_REPORTES)), hoy: date = Depends(fecha_hoy)):
    return _descarga(db, usuario, f"vencimientos_{hoy}_{dias}d", reportes.vencimientos(db, hoy, dias), dias=dias)


@router.get("/entregas.csv")
def entregas(desde: date, hasta: date, db: Session = Depends(sesion),
             usuario: Usuarios = Depends(requiere(P.VER_REPORTES))):
    return _descarga(db, usuario, f"entregas_por_programa_{desde}_{hasta}",
                     reportes.entregas_por_programa(db, desde, hasta), desde=desde, hasta=hasta)


@router.get("/rem-a04-j.csv")
def rem_a04_j(desde: date, hasta: date, db: Session = Depends(sesion),
              usuario: Usuarios = Depends(requiere(P.VER_REPORTES))):
    """Recetas cardiovasculares por medicamento: despacho oportuno, brechas y días de demora (FOFAR)."""
    return _descarga(db, usuario, f"rem_a04_j_{desde}_{hasta}", indicadores.rem_a04_j(db, desde, hasta),
                     desde=desde, hasta=hasta)


@router.get("/libro.csv")
def libro(db: Session = Depends(sesion), usuario: Usuarios = Depends(requiere(P.VER_LIBRO)),
          hoy: date = Depends(fecha_hoy)):
    return _descarga(db, usuario, f"libro_controlados_{hoy}", reportes.libro_controlados(db))


@router.get("/rango-sugerido")
def rango_sugerido(_: Usuarios = Depends(requiere(P.VER_REPORTES, P.VER_LIBRO)), hoy: date = Depends(fecha_hoy)):
    """Mes en curso, para precargar el formulario."""
    return {"desde": hoy.replace(day=1).isoformat(), "hasta": hoy.isoformat(),
            "hace_30": (hoy - timedelta(days=30)).isoformat()}
