"""Datos de demostración de un CESFAM, para desarrollo y pruebas.

Uso:  python -m app.seed --reiniciar

Las fechas se calculan respecto de hoy, por lo que la demo siempre muestra
lotes vigentes, en alerta, no dispensables y por retirar, y recetas con
retiro para hoy. Todos los nombres y RUT son ficticios. Nunca se ejecuta
en producción.

Orden: primero los datos de la v0.3/v0.4 (las pruebas automáticas dependen de
esos lotes, folios y códigos), después los agregados en la v0.5 y al final los
de la v0.6 (FOFAR): costos y facturas de cada lote, un quiebre de stock con su
reclamo, actividades farmacéuticas y un préstamo a otro CESFAM.
"""

import argparse
import os
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import models as m
from .config import config
from .db import Base, SesionLocal, motor
from .domain.codigo_barras import codigo_interno
from .domain.rut import calcular_dv, enmascarar_rut
from .esquema import actualizar_esquema, marcar_al_dia
from .reloj import ahora
from .reloj import hoy as fecha_hoy
from .security.claves import hashear, hmac_rut
from .services import actividades as servicio_actividades
from .services import dispensacion as servicio_dispensacion
from .services import faltantes as servicio_faltantes
from .services import prestamos as servicio_prestamos
from .services.inventario import ingresar_lote

PASSWORD_DEMO = os.getenv("SISGEF_PASSWORD_DEMO", "Farmacia2026!")
PIN_QF_DEMO = os.getenv("SISGEF_PIN_QF_DEMO", "4321")


def rut(cuerpo: int) -> str:
    return f"{cuerpo}-{calcular_dv(str(cuerpo))}"


USUARIOS_DEMO = {  # rol: (rut, nombre)
    "ADMIN": (rut(11111111), "Admin Sistema"),
    "QF": (rut(15555555), "Q.F. Carolina Rojas"),
    "TECNICO": (rut(17777777), "TENS Pedro Soto"),
    "BODEGUERO": (rut(18888888), "Bod. Luis Muñoz"),
    "MEDICO": (rut(13579246), "Dra. Valentina Pérez"),
}

ROLES = [("ADMIN", "Administrador del sistema"), ("QF", "Químico farmacéutico"),
         ("TECNICO", "TENS de farmacia"), ("BODEGUERO", "Bodeguero"), ("MEDICO", "Médico: emite recetas")]

PROGRAMAS = [("Cardiovascular", True), ("Diabetes", True), ("Salud Mental", False), ("Respiratorio crónico", True),
             ("Hipotiroidismo", True), ("Atención domiciliaria", False)]

UBICACIONES = [("A-01", "CASILLERO"), ("A-02", "CASILLERO"), ("B-03", "CASILLERO"), ("C-01", "ESTANTE"),
               ("CS-01", "CAJA_SEGURIDAD"), ("B-01", "CASILLERO"), ("B-02", "CASILLERO"), ("C-02", "ESTANTE"),
               ("R-01", "REFRIGERADOR")]

# codigo, nombre, principio activo, concentración, forma, unidad, envase, programa, umbral, control
MEDICAMENTOS = [
    ("LOS50", "Losartán 50 mg comprimidos", "Losartán", "50 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 200, None),
    ("MET850", "Metformina 850 mg comprimidos", "Metformina", "850 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Diabetes", 300, None),
    ("ATV20", "Atorvastatina 20 mg comprimidos", "Atorvastatina", "20 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 100, None),
    ("SAL100", "Salbutamol 100 mcg inhalador", "Salbutamol", "100 mcg", "INHALADOR", "INHALADOR", 1, "Respiratorio crónico", 20, None),
    ("CLZ2", "Clonazepam 2 mg comprimidos", "Clonazepam", "2 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Salud Mental", 50, "PSICOTROPICO"),
    # v0.5: arsenal frecuente de APS
    ("ENAL10", "Enalapril 10 mg comprimidos", "Enalapril", "10 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 300, None),
    ("AML5", "Amlodipino 5 mg comprimidos", "Amlodipino", "5 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 250, None),
    ("HCT50", "Hidroclorotiazida 50 mg comprimidos", "Hidroclorotiazida", "50 mg", "COMPRIMIDO", "COMPRIMIDO", 20, "Cardiovascular", 150, None),
    ("AAS100", "Ácido acetilsalicílico 100 mg comprimidos", "Ácido acetilsalicílico", "100 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 300, None),
    ("GLI5", "Glibenclamida 5 mg comprimidos", "Glibenclamida", "5 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Diabetes", 200, None),
    ("NPH100", "Insulina NPH 100 UI/ml frasco 10 ml", "Insulina humana NPH", "100 UI/ml", "SOLUCION_INYECTABLE", "FRASCO", 1, "Diabetes", 15, None),
    ("LEV100", "Levotiroxina 100 mcg comprimidos", "Levotiroxina", "100 mcg", "COMPRIMIDO", "COMPRIMIDO", 30, "Hipotiroidismo", 120, None),
    ("SER50", "Sertralina 50 mg comprimidos", "Sertralina", "50 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Salud Mental", 120, None),
    ("OME20", "Omeprazol 20 mg cápsulas", "Omeprazol", "20 mg", "CAPSULA", "CAPSULA", 30, None, 100, None),
    ("PCT500", "Paracetamol 500 mg comprimidos", "Paracetamol", "500 mg", "COMPRIMIDO", "COMPRIMIDO", 20, None, 200, None),
    # v0.6: un medicamento en quiebre de stock y uno que exige receta cheque (psicotrópico lista II)
    ("CAR25", "Carvedilol 25 mg comprimidos", "Carvedilol", "25 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Cardiovascular", 120, None),
    ("MTF10", "Metilfenidato 10 mg comprimidos", "Metilfenidato", "10 mg", "COMPRIMIDO", "COMPRIMIDO", 30, "Salud Mental", 30, "PSICOTROPICO"),
]
RECETA_CHEQUE = {"MTF10"}

# Costo unitario referencial (pesos por unidad mínima, compra vía CENABAST) para valorizar el inventario
COSTOS = {"LOS50": 12, "MET850": 10, "ATV20": 18, "SAL100": 1450, "CLZ2": 25, "ENAL10": 6, "AML5": 8, "HCT50": 7,
          "AAS100": 5, "GLI5": 6, "NPH100": 3900, "LEV100": 15, "SER50": 20, "OME20": 9, "PCT500": 4, "MTF10": 120}

# medicamento, lote, días para vencer, unidades, ubicación
LOTES = [
    ("LOS50", "L-2411", 9, 40, "A-02"),      # retiro obligatorio (<= 14 días)
    ("LOS50", "L-2502", 45, 60, "B-03"),     # en alerta: es el que indica FEFO
    ("LOS50", "L-2507", 200, 300, "A-01"),   # vigente, vence después
    ("MET850", "M-2501", 25, 50, "A-02"),    # no dispensable (<= 30 días)
    ("MET850", "M-2509", 150, 400, "A-01"),
    ("ATV20", "A-2601", 300, 80, "C-01"),    # bajo el umbral crítico
    ("SAL100", "S-2512", 120, 25, "C-01"),
    ("CLZ2", "C-2504", 90, 60, "CS-01"),
    ("CLZ2", "C-2510", 250, 100, "CS-01"),
    # v0.5
    ("ENAL10", "EN-2603", 120, 240, "B-01"),
    ("ENAL10", "EN-2611", 340, 600, "B-01"),
    ("AML5", "AM-2605", 180, 150, "B-01"),   # bajo el umbral crítico
    ("HCT50", "HC-2604", 150, 400, "B-02"),
    ("AAS100", "AS-2602", 55, 120, "B-02"),  # en alerta
    ("AAS100", "AS-2609", 290, 900, "B-02"),
    ("GLI5", "GL-2606", 210, 500, "B-02"),
    ("NPH100", "IN-2603", 100, 40, "R-01"),
    ("LEV100", "LV-2608", 260, 360, "C-02"),
    ("SER50", "SE-2512", 20, 30, "C-02"),    # no dispensable: debe ir a merma
    ("SER50", "SE-2607", 230, 300, "C-02"),
    ("OME20", "OM-2604", 160, 450, "C-02"),
    ("PCT500", "PC-2610", 330, 1000, "C-01"),
    # v0.6
    ("MTF10", "MF-2608", 260, 60, "CS-01"),
]

SECTORES = ["Sector Verde", "Sector Azul", "Sector Rural"]

# rut, nombre, tramo, sector, programas, PRAIS, postrado, alergias, dirección
PACIENTES = [
    (12345678, "María González", "B", "Sector Verde", ["Cardiovascular", "Diabetes"], False, False, None, None),
    (9876543, "Juan Pérez", "B", "Sector Azul", ["Salud Mental"], False, False, None, None),
    (14141414, "Ana Torres", "B", "Sector Verde", ["Cardiovascular", "Respiratorio crónico"], False, False, None, None),
    # v0.5
    (7654321, "Rosa Fuentes Muñoz", "A", "Sector Rural", ["Cardiovascular", "Diabetes", "Atención domiciliaria"],
     False, True, None, "Pasaje Los Aromos 245, Villa El Bosque"),
    (8123456, "Luis Herrera Campos", "C", "Sector Azul", ["Cardiovascular"], True, False, None, None),
    (16234567, "Patricia Soto Lagos", "D", "Sector Verde", ["Salud Mental"], False, False,
     "Penicilina (urticaria). AINE: ibuprofeno.", None),
    (10987654, "Jorge Contreras Vidal", "B", "Sector Rural", ["Diabetes", "Hipotiroidismo"], False, False, None, None),
    (19876543, "Elena Rivas Paredes", "A", "Sector Azul", [], True, False, "Sulfas", None),
]

# folio, paciente, días desde la emisión, tipo, entregas, [(medicamento, unidades por entrega, posología)]
RECETAS = [
    ("RX-1001", 12345678, 5, "AGUDA", 1, [("LOS50", 30, "1 comprimido cada 24 h"),
                                          ("MET850", 60, "1 comprimido cada 12 h")]),
    ("RX-1002", 9876543, 40, "AGUDA", 1, [("LOS50", 30, "1 comprimido cada 24 h")]),        # vencida (RN-04)
    ("RX-1003", 9876543, 2, "RETENIDA", 1, [("CLZ2", 30, "1 comprimido en la noche")]),     # controlado
    ("RX-1004", 14141414, 10, "AGUDA", 1, [("ATV20", 30, "1 comprimido en la noche"),
                                           ("SAL100", 1, "2 inhalaciones si hay disnea")]),
    # v0.5: recetas crónicas de 3 y 6 entregas mensuales
    ("RX-5001", 7654321, 3, "CRONICA", 6, [("ENAL10", 30, "1 comprimido cada 24 h"),
                                           ("AAS100", 30, "1 comprimido al almuerzo"),
                                           ("GLI5", 60, "1 comprimido antes de desayuno y cena")]),
    ("RX-5002", 8123456, 1, "CRONICA", 3, [("AML5", 30, "1 comprimido cada 24 h"),
                                           ("HCT50", 15, "½ comprimido en la mañana")]),
    ("RX-5003", 16234567, 6, "CRONICA", 6, [("SER50", 30, "1 comprimido en la mañana")]),
    ("RX-5004", 10987654, 0, "CRONICA", 6, [("LEV100", 30, "1 comprimido en ayunas"),
                                            ("NPH100", 1, "20 UI antes del desayuno y 10 UI antes de la cena")]),
    ("RX-5005", 19876543, 0, "AGUDA", 1, [("PCT500", 20, "1 comprimido cada 8 h si hay dolor, por 7 días"),
                                          ("OME20", 14, "1 cápsula en ayunas por 14 días")]),
    # v0.6: crónica cardiovascular con quiebre de stock de carvedilol (compromiso FOFAR de 24 h hábiles)
    ("RX-5006", 8123456, 2, "CRONICA", 3, [("ENAL10", 30, "1 comprimido cada 24 h"),
                                           ("CAR25", 30, "1 comprimido cada 12 h con comida")]),
]
# Receta retenida en papel: datos que exige el libro de controlados (D.S. 404/405 art. 18)
DATOS_RETENIDAS = {"RX-1003": ("Dr. Andrés Molina Soto", rut(10203040), "Av. Los Carrera 1550, depto. 32")}


# RUT que la historia generada no debe usar: usuarios, pacientes y apoderados de la demo y RUT de las pruebas
RUTS_RESERVADOS = {11111111, 15555555, 17777777, 18888888, 13579246, 16543210, 10203040, 13131313,
                   *(p[0] for p in PACIENTES)}


def poblar(db: Session, hoy: date, iteraciones: int | None = None, volumen: int = 0) -> dict:
    """Datos de demostración. Con volumen > 0 agrega ese número de pacientes con seis meses de historia."""
    roles = {nombre: m.Roles(nombre=nombre, descripcion=desc) for nombre, desc in ROLES}
    db.add_all(roles.values())
    db.flush()

    usuarios = {}
    for rol, (rut_u, nombre) in USUARIOS_DEMO.items():
        usuarios[rol] = m.Usuarios(rut=rut_u, nombre=nombre, id_rol=roles[rol].id_rol,
                                   password_hash=hashear(PASSWORD_DEMO, iteraciones),
                                   pin_hash=hashear(PIN_QF_DEMO, iteraciones) if rol == "QF" else None)
    db.add_all(usuarios.values())
    db.flush()
    admin, bodeguero, qf = usuarios["ADMIN"], usuarios["BODEGUERO"], usuarios["QF"]

    programas = {n: m.ProgramasSalud(nombre=n, es_ges=ges, creado_por=admin.id_usuario) for n, ges in PROGRAMAS}
    sectores = {n: m.Sectores(nombre=n, creado_por=admin.id_usuario) for n in SECTORES}
    ubicaciones = {c: m.Ubicaciones(codigo=c, tipo=t, creado_por=admin.id_usuario) for c, t in UBICACIONES}
    db.add_all([*programas.values(), *sectores.values(), *ubicaciones.values()])
    db.flush()

    meds = {}
    for codigo, nombre, activo, conc, forma, unidad, envase, programa, umbral, control in MEDICAMENTOS:
        meds[codigo] = m.Medicamentos(
            codigo=codigo, nombre=nombre, principio_activo=activo, concentracion=conc, forma_farmaceutica=forma,
            unidad_dispensacion=unidad, unidades_envase=envase, umbral_critico=umbral,
            id_programa=programas[programa].id_programa if programa else None,
            es_ges=programas[programa].es_ges if programa else False,
            es_controlado=control is not None, tipo_control=control,
            requiere_receta_cheque=codigo in RECETA_CHEQUE, creado_por=admin.id_usuario)
    db.add_all(meds.values())
    db.flush()
    for med in meds.values():
        med.codigo_barras = codigo_interno(med.id_medicamento)

    historia = None
    if volumen:  # antes de los lotes "de hoy": la historia ocurre en los últimos seis meses
        from .seed_historia import poblar_historia
        historia = poblar_historia(db, hoy, {"usuarios": usuarios, "medicamentos": meds, "ubicaciones": ubicaciones,
                                             "programas": programas, "sectores": sectores,
                                             "ruts_reservados": RUTS_RESERVADOS}, volumen, pin_qf=PIN_QF_DEMO)

    for numero, (med, codigo_lote, dias, unidades, ubicacion) in enumerate(LOTES, start=1):
        ingresar_lote(db, qf if meds[med].es_controlado else bodeguero, id_medicamento=meds[med].id_medicamento,
                      codigo_lote=codigo_lote, fecha_vencimiento=hoy + timedelta(days=dias), unidades=unidades,
                      id_ubicacion=ubicaciones[ubicacion].id_ubicacion, hoy=hoy, proveedor="CENABAST",
                      tipo_documento="FACTURA", numero_documento=f"F-{48200 + numero}",
                      fecha_documento=hoy - timedelta(days=20), costo_total=unidades * COSTOS[med])

    pacientes = {}
    for cuerpo, nombre, tramo, sector, programas_p, prais, postrado, alergias, direccion in PACIENTES:
        rut_p = rut(cuerpo)
        paciente = m.Pacientes(rut_hmac=hmac_rut(rut_p), rut_enmascarado=enmascarar_rut(rut_p), nombre=nombre,
                               tramo_fonasa=tramo, id_sector=sectores[sector].id_sector, es_prais=prais,
                               es_postrado=postrado, alergias=alergias, direccion=direccion,
                               creado_por=admin.id_usuario)
        db.add(paciente)
        db.flush()
        for p in programas_p:
            db.add(m.PacientesProgramas(id_paciente=paciente.id_paciente,
                                        id_programa=programas[p].id_programa, fecha_ingreso=hoy - timedelta(days=400)))
        pacientes[cuerpo] = paciente

    rosa = pacientes[7654321]
    apoderados = {"Carmen Fuentes": m.Apoderados(
        id_paciente=rosa.id_paciente, rut_hmac=hmac_rut(rut(16543210)), rut_enmascarado=enmascarar_rut(rut(16543210)),
        nombre="Carmen Fuentes Muñoz", parentesco="Hija", telefono="+56 9 5555 0101", creado_por=admin.id_usuario)}
    db.add_all(apoderados.values())

    recetas = {}
    for folio, paciente, dias, tipo, entregas, lineas in RECETAS:
        emision = hoy - timedelta(days=dias)
        medico = usuarios["MEDICO"] if folio >= "RX-5000" else None
        prescriptor, rut_prescriptor, domicilio = DATOS_RETENIDAS.get(
            folio, (medico.nombre, medico.rut, None) if medico else (None, None, None))
        receta = m.Recetas(folio=folio, id_paciente=pacientes[paciente].id_paciente, fecha_emision=emision,
                           tipo_receta=tipo, total_entregas=entregas, entregas_realizadas=0, intervalo_dias=30,
                           proxima_fecha_retiro=emision, id_medico=medico.id_usuario if medico else None,
                           prescriptor_nombre=prescriptor, prescriptor_rut=rut_prescriptor,
                           domicilio_paciente=domicilio, creado_por=admin.id_usuario)
        db.add(receta)
        db.flush()
        for codigo, por_entrega, posologia in lineas:
            db.add(m.DetallesReceta(id_receta=receta.id_receta, id_medicamento=meds[codigo].id_medicamento,
                                    cant_prescrita=por_entrega * entregas, cant_por_entrega=por_entrega,
                                    posologia=posologia, creado_por=admin.id_usuario))
        recetas[folio] = receta
    db.flush()

    despacho = _despacho_en_ruta(db, recetas["RX-5001"], usuarios["TECNICO"], hoy)
    reclamo = _quiebre_con_reclamo(db, recetas["RX-5006"], usuarios["TECNICO"], hoy)
    _actividades_farmaceuticas(db, qf, meds, hoy)
    servicio_prestamos.registrar_prestamo(
        db, bodeguero, tipo="OTORGADO", establecimiento="CESFAM Los Volcanes", id_medicamento=meds["PCT500"].id_medicamento,
        cantidad=60, fecha_compromiso=hoy + timedelta(days=15), hoy=hoy, documento="FP-0217",
        observacion="Quiebre de paracetamol en CESFAM vecino; devuelven con su próxima entrega CENABAST.")
    return {"usuarios": usuarios, "medicamentos": meds, "recetas": recetas, "ubicaciones": ubicaciones,
            "pacientes": pacientes, "sectores": sectores, "apoderados": apoderados, "despacho": despacho,
            "reclamo": reclamo, "historia": historia}


def _despacho_en_ruta(db: Session, receta: m.Recetas, tens: m.Usuarios, hoy: date) -> m.DespachosDomicilio:
    """Entrega 1 de 6 de la paciente postrada, preparada con FEFO y ya en ruta a su domicilio."""
    db.refresh(receta)
    lineas = []
    for detalle in receta.detalles:
        plan = servicio_dispensacion.planificar_linea(db, detalle.id_detalle_receta, detalle.cant_por_entrega, hoy)
        lineas.append(servicio_dispensacion.LineaDispensacion(
            id_detalle_receta=detalle.id_detalle_receta, cantidad=detalle.cant_por_entrega,
            lotes_escaneados=[p["codigo_lote"] for p in plan]))
    resultado = servicio_dispensacion.dispensar(db, tens, id_receta=receta.id_receta, lineas=lineas,
                                                clave_idempotencia="seed-despacho-rx-5001", hoy=hoy)
    despacho = m.DespachosDomicilio(id_dispensacion=resultado["id_dispensacion"], estado="EN_RUTA",
                                    id_responsable=tens.id_usuario, fecha_salida=ahora(),
                                    observacion="Entrega mensual a domicilio (paciente postrada).",
                                    creado_por=tens.id_usuario)
    db.add(despacho)
    db.flush()
    return despacho


def _quiebre_con_reclamo(db: Session, receta: m.Recetas, tens: m.Usuarios, hoy: date) -> m.Reclamos:
    """Entrega 1 de 3 de un paciente cardiovascular: hay enalapril pero no carvedilol. Queda el
    compromiso de entregarlo en 24 horas hábiles y el paciente reclamó en la OIRS."""
    db.refresh(receta)
    lineas = []
    for detalle in receta.detalles:
        if detalle.medicamento.codigo == "ENAL10":
            plan = servicio_dispensacion.planificar_linea(db, detalle.id_detalle_receta, detalle.cant_por_entrega, hoy)
            lineas.append(servicio_dispensacion.LineaDispensacion(
                id_detalle_receta=detalle.id_detalle_receta, cantidad=detalle.cant_por_entrega,
                lotes_escaneados=[p["codigo_lote"] for p in plan]))
    resultado = servicio_dispensacion.dispensar(db, tens, id_receta=receta.id_receta, lineas=lineas,
                                                clave_idempotencia="seed-quiebre-rx-5006", hoy=hoy)
    return servicio_faltantes.registrar_reclamo(
        db, tens, canal="OIRS", folio_externo="OIRS-2026-1184", id_faltante=resultado["faltantes"][0]["id_faltante"],
        descripcion="El paciente no recibió carvedilol en su retiro mensual y pide que se le entregue a la brevedad.")


def _actividades_farmaceuticas(db: Session, qf: m.Usuarios, meds: dict, hoy: date) -> None:
    servicio_actividades.programar(db, qf, hoy.year, 40)
    registro = servicio_actividades.registrar_actividad
    registro(db, qf, tipo="SEGUIMIENTO_FT", fecha=hoy - timedelta(days=12), hoy=hoy, rut_paciente=rut(7654321),
             descripcion="Control de adherencia y técnica de administración en domicilio; glicemias capilares.",
             resultado="Adherente; se refuerza horario de glibenclamida antes de las comidas.")
    registro(db, qf, tipo="RAM", fecha=hoy - timedelta(days=5), hoy=hoy, rut_paciente=rut(16234567),
             id_medicamento=meds["SER50"].id_medicamento, gravedad="LEVE",
             descripcion="Náuseas y cefalea la primera semana de sertralina 50 mg; sin otros síntomas.",
             resultado="Se indica tomar con desayuno; se informa al médico tratante.")
    registro(db, qf, tipo="TALLER", fecha=hoy - timedelta(days=30), hoy=hoy, participantes=18,
             descripcion="Taller grupal: uso racional de benzodiacepinas y riesgos de la automedicación.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos de demostración de SISGEF-Asistencial.")
    parser.add_argument("--reiniciar", action="store_true", help="borra y recrea todas las tablas")
    parser.add_argument("--volumen", type=int, default=0, metavar="N",
                        help="agrega N pacientes ficticios con seis meses de historia (p. ej. 150)")
    args = parser.parse_args()
    if config.entorno == "produccion":
        raise SystemExit("El seed de demostración no se ejecuta en producción.")
    if args.reiniciar:
        m.borrar_esquema(motor)
        Base.metadata.create_all(motor)
        marcar_al_dia(motor)  # base nueva creada desde los modelos: ya está en la última migración
    else:
        actualizar_esquema(motor)
    with SesionLocal() as db:
        resultado = poblar(db, fecha_hoy(), volumen=args.volumen)
        db.commit()
    if resultado["historia"]:
        h = resultado["historia"]
        print(f"Historia de 6 meses: {h['pacientes']} pacientes, {h['recetas']} recetas, {h['entregas']} entregas, "
              f"{h['faltantes']} faltantes, {h['reclamos']} reclamos y {h['actividades']} actividades del Q.F.")
    print("Datos de demostración cargados. Usuarios (contraseña común definida en SISGEF_PASSWORD_DEMO):")
    for rol, (rut_u, nombre) in USUARIOS_DEMO.items():
        print(f"  {rol:<10} {rut_u:<12} {nombre}")
    print(f"PIN de firma del Q.F.: {PIN_QF_DEMO}")


if __name__ == "__main__":
    main()
