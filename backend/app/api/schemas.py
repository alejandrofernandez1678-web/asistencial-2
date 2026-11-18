"""Esquemas Pydantic de entrada: toda la entrada se valida (tipo, largo, rango)
antes de llegar a los servicios. Campos desconocidos se rechazan."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Entrada):
    rut: str = Field(min_length=3, max_length=12)
    password: str = Field(min_length=1, max_length=128)


class MedicamentoNuevo(Entrada):
    codigo: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9-]+$")
    codigo_barras: str | None = Field(default=None, max_length=13, pattern=r"^\d{13}$")
    nombre: str = Field(min_length=2, max_length=120)
    principio_activo: str | None = Field(default=None, min_length=2, max_length=120)
    concentracion: str | None = Field(default=None, max_length=40)
    forma_farmaceutica: str = Field(default="OTRO", max_length=30)
    unidad_dispensacion: str = Field(default="UNIDAD", max_length=20)
    es_ges: bool = False
    unidades_envase: int = Field(gt=0, le=10000)
    es_controlado: bool = False
    tipo_control: Literal["PSICOTROPICO", "ESTUPEFACIENTE"] | None = None
    requiere_receta_cheque: bool = False
    umbral_critico: int = Field(default=0, ge=0, le=1_000_000)
    id_programa: int | None = None


class MedicamentoCambios(Entrada):
    codigo_barras: str | None = Field(default=None, max_length=13, pattern=r"^\d{13}$")
    principio_activo: str | None = Field(default=None, min_length=2, max_length=120)
    concentracion: str | None = Field(default=None, max_length=40)
    forma_farmaceutica: str | None = Field(default=None, max_length=30)
    unidad_dispensacion: str | None = Field(default=None, max_length=20)
    es_ges: bool | None = None
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    unidades_envase: int | None = Field(default=None, gt=0, le=10000)
    umbral_critico: int | None = Field(default=None, ge=0, le=1_000_000)
    id_programa: int | None = None


class Motivo(Entrada):
    motivo: str = Field(min_length=10, max_length=250)


class LoteNuevo(Entrada):
    id_medicamento: int
    codigo_lote: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    fecha_vencimiento: date
    unidades: int = Field(gt=0, le=1_000_000)
    id_ubicacion: int
    proveedor: str | None = Field(default=None, max_length=120)
    tipo_documento: Literal["FACTURA", "GUIA", "DONACION"] | None = None
    numero_documento: str | None = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9./-]*$")
    fecha_documento: date | None = None
    costo_total: int | None = Field(default=None, ge=0, le=1_000_000_000)


class AjusteLote(Entrada):
    unidades_correctas: int = Field(ge=0, le=1_000_000)
    motivo: str = Field(min_length=10, max_length=250)


class MermaNueva(Entrada):
    cantidad: int = Field(gt=0, le=1_000_000)
    motivo: Literal["VENCIMIENTO", "DANO", "ALERTA_SANITARIA"]
    observacion: str | None = Field(default=None, max_length=250)


class Linea(Entrada):
    id_detalle_receta: int
    cantidad: int = Field(gt=0, le=10000)
    lotes_escaneados: list[str] = Field(default_factory=list, max_length=20)


class Firma(Entrada):
    rut: str = Field(max_length=12)
    pin: str = Field(min_length=4, max_length=12)


class DispensacionNueva(Entrada):
    id_receta: int
    lineas: list[Linea] = Field(min_length=1, max_length=30)
    clave_idempotencia: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    rut_retira: str | None = Field(default=None, max_length=12)
    relacion: str | None = Field(default=None, max_length=30)
    firma_qf: Firma | None = None
    retira_tipo: Literal["PACIENTE", "APODERADO", "TERCERO"] | None = None
    id_apoderado: int | None = None
    confirma_alergias: bool = False
    a_domicilio: bool = False
    motivos_incompletos: dict[int, Literal["SIN_STOCK", "RECHAZO_PACIENTE"]] | None = None


class UsuarioNuevo(Entrada):
    rut: str = Field(max_length=12)
    nombre: str = Field(min_length=3, max_length=120)
    rol: Literal["TECNICO", "BODEGUERO", "QF", "MEDICO", "ADMIN"]
    password: str = Field(min_length=12, max_length=128)
    pin: str | None = Field(default=None, min_length=4, max_length=12, pattern=r"^\d+$")


class PacienteNuevo(Entrada):
    rut: str = Field(max_length=12)
    nombre: str = Field(min_length=3, max_length=120)
    fecha_nacimiento: date | None = None
    tramo_fonasa: Literal["A", "B", "C", "D"] | None = None
    programas: list[int] = Field(default_factory=list, max_length=10)
    id_sector: int | None = None
    es_prais: bool = False
    es_postrado: bool = False
    alergias: str | None = Field(default=None, max_length=500)
    direccion: str | None = Field(default=None, max_length=200)


class LineaRecetaNueva(Entrada):
    id_medicamento: int
    cant_por_entrega: int | None = Field(default=None, gt=0, le=10000)   # unidades mínimas por entrega
    cant_prescrita: int | None = Field(default=None, gt=0, le=60000)     # total (opcional)
    posologia: str = Field(min_length=3, max_length=200)


class RecetaNueva(Entrada):
    id_paciente: int
    folio: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9-]+$")
    fecha_emision: date
    es_retenida: bool = False
    tipo_receta: Literal["AGUDA", "CRONICA", "RETENIDA"] | None = None
    total_entregas: int = Field(default=1, ge=1, le=6)
    intervalo_dias: int = Field(default=30, ge=7, le=90)
    lineas: list[LineaRecetaNueva] = Field(min_length=1, max_length=30)
    prescriptor_nombre: str | None = Field(default=None, min_length=3, max_length=120)
    prescriptor_rut: str | None = Field(default=None, max_length=12)
    domicilio_paciente: str | None = Field(default=None, min_length=5, max_length=200)
    numero_receta_cheque: str | None = Field(default=None, max_length=20, pattern=r"^[A-Za-z0-9-]+$")


class ApoderadoNuevo(Entrada):
    rut: str = Field(max_length=12)
    nombre: str = Field(min_length=3, max_length=120)
    parentesco: str = Field(min_length=2, max_length=30)
    telefono: str | None = Field(default=None, max_length=20, pattern=r"^[0-9 +()-]*$")
    vigente_hasta: date | None = None


class CambioDespacho(Entrada):
    estado: Literal["EN_RUTA", "ENTREGADO", "FALLIDO"]
    recibe_nombre: str | None = Field(default=None, max_length=120)
    observacion: str | None = Field(default=None, max_length=250)


class DevolucionNueva(Entrada):
    id_detalle_disp: int
    cantidad: int = Field(gt=0, le=10000)
    destino: Literal["REINGRESO", "DESCARTE"]
    motivo: str = Field(min_length=10, max_length=250)


# ------------------------------------------------------------------ FOFAR (v0.6)
class ReclamoNuevo(Entrada):
    canal: Literal["OIRS", "SALUD_RESPONDE", "PRESENCIAL"]
    descripcion: str = Field(min_length=10, max_length=500)
    folio_externo: str | None = Field(default=None, max_length=30)
    id_faltante: int | None = None
    rut: str | None = Field(default=None, max_length=12)


class CierreReclamo(Entrada):
    solucion: str = Field(min_length=10, max_length=250)
    recibe_nombre: str = Field(min_length=3, max_length=120)


class TomaNueva(Entrada):
    id_ubicacion: int | None = None
    observacion: str | None = Field(default=None, max_length=250)


class Conteo(Entrada):
    id_conteo: int
    cantidad: int = Field(ge=0, le=1_000_000)


class CierreToma(Entrada):
    observacion: str | None = Field(default=None, max_length=250)


class ActividadNueva(Entrada):
    tipo: Literal["REVISION_MEDICACION", "CONCILIACION", "EDUCACION", "SEGUIMIENTO_FT", "RAM", "FALLA_CALIDAD",
                  "EVENTO_ADVERSO", "TALLER"]
    fecha: date
    descripcion: str = Field(min_length=10, max_length=1000)
    rut_paciente: str | None = Field(default=None, max_length=12)
    id_medicamento: int | None = None
    id_lote: int | None = None
    resultado: str | None = Field(default=None, max_length=500)
    participantes: int | None = Field(default=None, gt=0, le=1000)
    gravedad: Literal["LEVE", "MODERADA", "GRAVE"] | None = None


class NotificacionIsp(Entrada):
    fecha_notificacion: date
    folio_isp: str = Field(min_length=3, max_length=30)


class Programacion(Entrada):
    cantidad: int = Field(gt=0, le=10000)


class PrestamoNuevo(Entrada):
    tipo: Literal["OTORGADO", "RECIBIDO"]
    establecimiento: str = Field(min_length=3, max_length=120)
    id_medicamento: int
    cantidad: int = Field(gt=0, le=100000)
    fecha_compromiso: date
    documento: str | None = Field(default=None, max_length=30)
    observacion: str | None = Field(default=None, max_length=250)
    codigo_lote: str | None = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    fecha_vencimiento: date | None = None
    id_ubicacion: int | None = None


class DevolucionPrestamo(Entrada):
    codigo_lote: str | None = Field(default=None, min_length=2, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    fecha_vencimiento: date | None = None
    id_ubicacion: int | None = None
