from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.catalogo import FORMAS_FARMACEUTICAS, UNIDADES_DISPENSACION
from ..models import Lotes, MovimientosStock, ProgramasSalud, Sectores, Ubicaciones, Usuarios
from ..security.rbac import Permisos as P
from ..services import catalogo, inventario, series
from .deps import fecha_hoy, requiere, sesion
from ..reloj import iso_utc
from .schemas import AjusteLote, LoteNuevo, MedicamentoCambios, MedicamentoNuevo, MermaNueva, Motivo

router = APIRouter(prefix="/api", tags=["inventario"])


# ------------------------------------------------------------------ stock
@router.get("/stock")
def stock(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_STOCK)),
          hoy: date = Depends(fecha_hoy)):
    return inventario.panel_stock(db, hoy)


@router.get("/catalogos")
def catalogos(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_STOCK))):
    return {
        "programas": [{"id_programa": p.id_programa, "nombre": p.nombre}
                      for p in db.scalars(select(ProgramasSalud).order_by(ProgramasSalud.nombre))],
        "sectores": [{"id_sector": s.id_sector, "nombre": s.nombre}
                     for s in db.scalars(select(Sectores).where(Sectores.activo.is_(True)).order_by(Sectores.nombre))],
        "formas_farmaceuticas": [{"codigo": c, "nombre": n} for c, n in FORMAS_FARMACEUTICAS.items()],
        "unidades_dispensacion": [{"codigo": c, "nombre": n} for c, n in UNIDADES_DISPENSACION.items()],
        "ubicaciones": [{"id_ubicacion": u.id_ubicacion, "codigo": u.codigo, "tipo": u.tipo}
                        for u in db.scalars(select(Ubicaciones).where(Ubicaciones.activo.is_(True))
                                            .order_by(Ubicaciones.codigo))],
    }


@router.get("/panel/entregas")
def entregas_por_dia(dias: int = Query(30, ge=7, le=90), db: Session = Depends(sesion),
                     _: Usuarios = Depends(requiere(P.VER_STOCK)), hoy: date = Depends(fecha_hoy)):
    """Entregas y unidades por día (gráfico del panel)."""
    return series.entregas_por_dia(db, hoy, dias)


@router.get("/inventario/vencimientos-por-mes")
def vencimientos_por_mes(meses: int = Query(6, ge=1, le=12), db: Session = Depends(sesion),
                         _: Usuarios = Depends(requiere(P.VER_STOCK)), hoy: date = Depends(fecha_hoy)):
    return series.vencimientos_por_mes(db, hoy, meses)


@router.get("/inventario/alertas")
def alertas(db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_STOCK)),
            hoy: date = Depends(fecha_hoy)):
    return inventario.alertas_inventario(db, hoy)


# ------------------------------------------------------------ medicamentos
@router.get("/medicamentos")
def listar_medicamentos(incluir_inactivos: bool = False, db: Session = Depends(sesion),
                        _: Usuarios = Depends(requiere(P.VER_STOCK))):
    return [catalogo.describir_medicamento(m) for m in catalogo.listar_medicamentos(db, incluir_inactivos)]


@router.post("/medicamentos", status_code=201)
def crear_medicamento(datos: MedicamentoNuevo, db: Session = Depends(sesion),
                      usuario: Usuarios = Depends(requiere(P.GESTIONAR_MEDICAMENTOS))):
    med = catalogo.crear_medicamento(db, usuario, **datos.model_dump())
    db.commit()
    return catalogo.describir_medicamento(med)


@router.patch("/medicamentos/{id_medicamento}")
def actualizar_medicamento(id_medicamento: int, datos: MedicamentoCambios, db: Session = Depends(sesion),
                           usuario: Usuarios = Depends(requiere(P.GESTIONAR_MEDICAMENTOS))):
    med = catalogo.actualizar_medicamento(db, usuario, id_medicamento, **datos.model_dump(exclude_unset=True))
    db.commit()
    return catalogo.describir_medicamento(med)


@router.post("/medicamentos/{id_medicamento}/baja")
def dar_de_baja_medicamento(id_medicamento: int, datos: Motivo, db: Session = Depends(sesion),
                            usuario: Usuarios = Depends(requiere(P.GESTIONAR_MEDICAMENTOS)),
                            hoy: date = Depends(fecha_hoy)):
    med = catalogo.dar_de_baja_medicamento(db, usuario, id_medicamento, datos.motivo, hoy)
    db.commit()
    return catalogo.describir_medicamento(med)


@router.post("/medicamentos/{id_medicamento}/reactivar")
def reactivar_medicamento(id_medicamento: int, db: Session = Depends(sesion),
                          usuario: Usuarios = Depends(requiere(P.GESTIONAR_MEDICAMENTOS))):
    med = catalogo.reactivar_medicamento(db, usuario, id_medicamento)
    db.commit()
    return catalogo.describir_medicamento(med)


# ------------------------------------------------------------------ lotes
@router.get("/lotes")
def listar_lotes(id_medicamento: int | None = None, incluir_cerrados: bool = False,
                 db: Session = Depends(sesion), _: Usuarios = Depends(requiere(P.VER_STOCK)),
                 hoy: date = Depends(fecha_hoy)):
    consulta = select(Lotes).order_by(Lotes.fecha_vencimiento, Lotes.id_lote)
    if id_medicamento is not None:
        consulta = consulta.where(Lotes.id_medicamento == id_medicamento)
    if not incluir_cerrados:
        consulta = consulta.where(Lotes.estado.in_(["DISPONIBLE", "ALERTA_SANITARIA"]))
    return [inventario.describir_lote(l, hoy) for l in db.scalars(consulta).unique()]


@router.post("/lotes", status_code=201)
def ingresar_lote(datos: LoteNuevo, db: Session = Depends(sesion),
                  usuario: Usuarios = Depends(requiere(P.GESTIONAR_LOTES)), hoy: date = Depends(fecha_hoy)):
    lote, alertas = inventario.ingresar_lote(db, usuario, hoy=hoy, **datos.model_dump())
    db.commit()
    return {"lote": inventario.describir_lote(lote, hoy), "alertas": alertas}


@router.post("/lotes/{id_lote}/ajuste")
def ajustar_lote(id_lote: int, datos: AjusteLote, db: Session = Depends(sesion),
                 usuario: Usuarios = Depends(requiere(P.GESTIONAR_LOTES)), hoy: date = Depends(fecha_hoy)):
    lote = inventario.ajustar_lote(db, usuario, id_lote, datos.unidades_correctas, datos.motivo)
    db.commit()
    return inventario.describir_lote(lote, hoy)


@router.post("/lotes/{id_lote}/anular")
def anular_lote(id_lote: int, datos: Motivo, db: Session = Depends(sesion),
                usuario: Usuarios = Depends(requiere(P.ANULAR_LOTE)), hoy: date = Depends(fecha_hoy)):
    lote = inventario.anular_lote(db, usuario, id_lote, datos.motivo)
    db.commit()
    return inventario.describir_lote(lote, hoy)


@router.post("/lotes/{id_lote}/merma", status_code=201)
def registrar_merma(id_lote: int, datos: MermaNueva, db: Session = Depends(sesion),
                    usuario: Usuarios = Depends(requiere(P.REGISTRAR_MERMA)), hoy: date = Depends(fecha_hoy)):
    merma = inventario.registrar_merma(db, usuario, id_lote, datos.cantidad, datos.motivo, datos.observacion)
    db.commit()
    return {"id_merma": merma.id_merma, "lote": inventario.describir_lote(db.get(Lotes, id_lote), hoy)}


@router.get("/lotes/{id_lote}/kardex")
def kardex(id_lote: int, limite: int = Query(100, le=500), db: Session = Depends(sesion),
           _: Usuarios = Depends(requiere(P.VER_STOCK))):
    """Los últimos `limite` movimientos del lote, en orden cronológico (el último es el saldo actual)."""
    recientes = db.scalars(select(MovimientosStock).where(MovimientosStock.id_lote == id_lote)
                           .order_by(MovimientosStock.id_movimiento.desc()).limit(limite)).all()
    movimientos = reversed(recientes)
    return [{"id_movimiento": m.id_movimiento, "tipo": m.tipo, "cantidad": m.cantidad,
             "saldo_resultante": m.saldo_resultante, "motivo": m.motivo, "id_usuario": m.id_usuario,
             "referencia": f"{m.referencia_tipo}#{m.referencia_id}" if m.referencia_tipo else None,
             "fecha_hora": iso_utc(m.fecha_hora)} for m in movimientos]
