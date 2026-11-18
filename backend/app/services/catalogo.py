"""Casos de uso de catálogos con baja lógica: medicamentos y usuarios.

"Eliminar" un producto o un usuario significa desactivarlo con motivo,
fecha y responsable. La fila se conserva porque recetas, lotes y
dispensaciones antiguas la siguen referenciando (trazabilidad legal).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.catalogo import FORMAS_FARMACEUTICAS, UNIDADES_DISPENSACION
from ..domain.codigo_barras import codigo_interno, es_codigo_interno, normalizar_ean13
from ..domain.errores import ReglaNegocioError
from ..domain.lotes import es_dispensable, estado_lote
from ..domain.rut import normalizar_rut
from ..models import Lotes, Medicamentos, Roles, Usuarios
from ..reloj import ahora, iso_utc
from ..security.claves import hashear
from .auditoria import registrar_evento
from .inventario import exigir_motivo

CAMPOS_EDITABLES_MEDICAMENTO = {"codigo_barras", "nombre", "principio_activo", "concentracion",
                                "forma_farmaceutica", "unidad_dispensacion", "es_ges", "unidades_envase", "umbral_critico", "id_programa", "tipo_control"}


def describir_medicamento(m: Medicamentos) -> dict:
    return {"id_medicamento": m.id_medicamento, "codigo": m.codigo, "codigo_barras": m.codigo_barras, "nombre": m.nombre,
            "principio_activo": m.principio_activo, "concentracion": m.concentracion,
            "forma_farmaceutica": m.forma_farmaceutica, "unidad_dispensacion": m.unidad_dispensacion, "es_ges": m.es_ges,
            "unidades_envase": m.unidades_envase, "es_controlado": m.es_controlado, "tipo_control": m.tipo_control,
            "requiere_receta_cheque": m.requiere_receta_cheque,
            "umbral_critico": m.umbral_critico, "id_programa": m.id_programa,
            "programa": m.programa.nombre if m.programa else None, "activo": m.activo,
            "fecha_baja": iso_utc(m.fecha_baja), "motivo_baja": m.motivo_baja}


def listar_medicamentos(db: Session, incluir_inactivos: bool = False) -> list[Medicamentos]:
    consulta = select(Medicamentos).order_by(Medicamentos.nombre)
    if not incluir_inactivos:
        consulta = consulta.where(Medicamentos.activo.is_(True))
    return list(db.scalars(consulta))


def obtener_medicamento(db: Session, id_medicamento: int) -> Medicamentos:
    med = db.get(Medicamentos, id_medicamento)
    if med is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El medicamento no existe.")
    return med


def validar_codigo_barras(db: Session, codigo_barras: str, id_medicamento: int | None = None) -> str:
    """Código del fabricante: EAN-13 válido, fuera del rango interno y sin repetir."""
    codigo_barras = normalizar_ean13(codigo_barras)
    if es_codigo_interno(codigo_barras):
        raise ReglaNegocioError("CODIGO_BARRAS_RESERVADO",
                                "Los códigos que empiezan con 200 se reservan para los códigos internos del sistema.")
    otro = db.scalar(select(Medicamentos).where(Medicamentos.codigo_barras == codigo_barras))
    if otro is not None and otro.id_medicamento != id_medicamento:
        raise ReglaNegocioError("CODIGO_BARRAS_DUPLICADO", f"El código de barras ya está asignado a {otro.nombre}.")
    return codigo_barras


def validar_vocabulario(datos: dict) -> None:
    if datos.get("forma_farmaceutica") and datos["forma_farmaceutica"] not in FORMAS_FARMACEUTICAS:
        raise ReglaNegocioError("FORMA_INVALIDA", "La forma farmacéutica no está en el catálogo.")
    if datos.get("unidad_dispensacion") and datos["unidad_dispensacion"] not in UNIDADES_DISPENSACION:
        raise ReglaNegocioError("UNIDAD_INVALIDA", "La unidad de dispensación no está en el catálogo.")


def crear_medicamento(db: Session, usuario: Usuarios, **datos) -> Medicamentos:
    datos["principio_activo"] = datos.get("principio_activo") or datos["nombre"]
    validar_vocabulario(datos)
    if datos.get("requiere_receta_cheque") and not datos.get("es_controlado"):
        raise ReglaNegocioError("RECETA_CHEQUE_SOLO_CONTROLADO", "Solo un medicamento controlado exige receta cheque.")
    if db.scalar(select(Medicamentos.id_medicamento).where(Medicamentos.codigo == datos["codigo"])):
        raise ReglaNegocioError("CODIGO_DUPLICADO", f"Ya existe un medicamento con código {datos['codigo']}.")
    if datos.get("codigo_barras"):
        datos["codigo_barras"] = validar_codigo_barras(db, datos["codigo_barras"])
    med = Medicamentos(**datos, creado_por=usuario.id_usuario)
    db.add(med)
    db.flush()
    if not med.codigo_barras:  # sin código del fabricante: se asigna uno interno
        med.codigo_barras = codigo_interno(med.id_medicamento)
    registrar_evento(db, tipo="MEDICAMENTO_CREADO", entidad="medicamentos", id_entidad=med.id_medicamento,
                     id_usuario=usuario.id_usuario, codigo=med.codigo)
    return med


def actualizar_medicamento(db: Session, usuario: Usuarios, id_medicamento: int, **cambios) -> Medicamentos:
    med = obtener_medicamento(db, id_medicamento)
    if not med.activo:
        raise ReglaNegocioError("MEDICAMENTO_INACTIVO", "Reactive el medicamento antes de editarlo.")
    antes = {}
    validar_vocabulario(cambios)
    if cambios.get("codigo_barras"):
        cambios["codigo_barras"] = validar_codigo_barras(db, cambios["codigo_barras"], med.id_medicamento)
    for campo, valor in cambios.items():
        if campo in CAMPOS_EDITABLES_MEDICAMENTO and valor is not None and getattr(med, campo) != valor:
            antes[campo] = getattr(med, campo)
            setattr(med, campo, valor)
    med.actualizado_por = usuario.id_usuario
    registrar_evento(db, tipo="MEDICAMENTO_ACTUALIZADO", entidad="medicamentos", id_entidad=med.id_medicamento,
                     id_usuario=usuario.id_usuario, valores_anteriores=antes)
    return med


def dar_de_baja_medicamento(db: Session, usuario: Usuarios, id_medicamento: int, motivo: str, hoy: date) -> Medicamentos:
    motivo = exigir_motivo(motivo)
    med = obtener_medicamento(db, id_medicamento)
    if not med.activo:
        raise ReglaNegocioError("YA_DADO_DE_BAJA", "El medicamento ya está dado de baja.")
    lotes = db.scalars(select(Lotes).where(Lotes.id_medicamento == id_medicamento, Lotes.unidades_disp > 0)).unique()
    con_stock = [l.codigo_lote for l in lotes
                 if es_dispensable(estado_lote(l.fecha_vencimiento, l.unidades_disp, hoy, l.estado))]
    if con_stock:
        raise ReglaNegocioError("CON_STOCK", "El medicamento tiene stock dispensable en los lotes "
                                f"{', '.join(con_stock)}; retírelos a merma antes de darlo de baja.")
    med.activo, med.fecha_baja, med.baja_por, med.motivo_baja = False, ahora(), usuario.id_usuario, motivo
    registrar_evento(db, tipo="MEDICAMENTO_DADO_DE_BAJA", entidad="medicamentos", id_entidad=med.id_medicamento,
                     id_usuario=usuario.id_usuario, motivo=motivo)
    return med


def reactivar_medicamento(db: Session, usuario: Usuarios, id_medicamento: int) -> Medicamentos:
    med = obtener_medicamento(db, id_medicamento)
    if med.activo:
        raise ReglaNegocioError("YA_ACTIVO", "El medicamento ya está activo.")
    med.activo, med.fecha_baja, med.baja_por, med.motivo_baja = True, None, None, None
    med.actualizado_por = usuario.id_usuario
    registrar_evento(db, tipo="MEDICAMENTO_REACTIVADO", entidad="medicamentos", id_entidad=med.id_medicamento,
                     id_usuario=usuario.id_usuario)
    return med


# ------------------------------------------------------------------ usuarios
def describir_usuario(u: Usuarios) -> dict:
    return {"id_usuario": u.id_usuario, "rut": u.rut, "nombre": u.nombre, "rol": u.rol.nombre, "activo": u.activo,
            "ultimo_acceso": iso_utc(u.ultimo_acceso),
            "motivo_baja": u.motivo_baja}


def crear_usuario(db: Session, admin: Usuarios, *, rut: str, nombre: str, rol: str, password: str,
                  pin: str | None = None) -> Usuarios:
    rut = normalizar_rut(rut)
    if db.scalar(select(Usuarios.id_usuario).where(Usuarios.rut == rut)):
        raise ReglaNegocioError("RUT_DUPLICADO", "Ya existe un usuario con ese RUT.")
    rol_db = db.scalar(select(Roles).where(Roles.nombre == rol))
    if rol_db is None:
        raise ReglaNegocioError("ROL_INVALIDO", f"El rol {rol} no existe.")
    if rol == "QF" and not pin:
        raise ReglaNegocioError("PIN_REQUERIDO", "Un Q.F. necesita un PIN para firmar controlados.")
    usuario = Usuarios(rut=rut, nombre=nombre, id_rol=rol_db.id_rol, password_hash=hashear(password),
                       pin_hash=hashear(pin) if pin else None, creado_por=admin.id_usuario)
    db.add(usuario)
    db.flush()
    registrar_evento(db, tipo="USUARIO_CREADO", entidad="usuarios", id_entidad=usuario.id_usuario,
                     id_usuario=admin.id_usuario, rol=rol)
    return usuario


def dar_de_baja_usuario(db: Session, admin: Usuarios, id_usuario: int, motivo: str) -> Usuarios:
    motivo = exigir_motivo(motivo)
    usuario = db.get(Usuarios, id_usuario)
    if usuario is None:
        raise ReglaNegocioError("NO_ENCONTRADO", "El usuario no existe.")
    if usuario.id_usuario == admin.id_usuario:
        raise ReglaNegocioError("AUTO_BAJA", "No puede darse de baja a sí mismo.")
    if not usuario.activo:
        raise ReglaNegocioError("YA_DADO_DE_BAJA", "El usuario ya está dado de baja.")
    usuario.activo, usuario.fecha_baja, usuario.baja_por, usuario.motivo_baja = False, ahora(), admin.id_usuario, motivo
    registrar_evento(db, tipo="USUARIO_DADO_DE_BAJA", entidad="usuarios", id_entidad=usuario.id_usuario,
                     id_usuario=admin.id_usuario, motivo=motivo)
    return usuario
