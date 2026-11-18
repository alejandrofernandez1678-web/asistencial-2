"""Datos de demostración con volumen: un CESFAM con seis meses de historia.

Uso:  python -m app.seed --reiniciar --volumen 150

Genera pacientes ficticios (RUT válidos que no pertenecen a nadie conocido: se
eligen al azar con semilla fija) y recorre día a día los últimos ~6 meses usando
los mismos servicios de la aplicación, con el reloj simulado (reloj.simular):
  * recetas crónicas del PSCV, hipotiroidismo, salud mental y respiratorio, con
    renovación cuando se completan; recetas agudas; recetas retenidas de clonazepam
    dispensadas con firma del Q.F.;
  * retiros mensuales con atrasos y adelantos realistas; despacho a domicilio de
    los pacientes postrados;
  * una alerta sanitaria que retira un lote de atorvastatina: una semana de quiebre de
    stock, compromisos de 24 horas hábiles, reclamos OIRS y su cierre con acta;
  * merma por vencimiento, una toma de inventario, préstamos entre establecimientos
    y actividades farmacéuticas semanales.
Como todo pasa por los servicios, el kardex, el libro de controlados, los
indicadores FOFAR y la auditoría quedan coherentes.

La historia se genera antes de los lotes y recetas de demostración "de hoy", con
lotes propios (prefijo V) que vencen después que los del seed base: así los
ejemplos documentados en el README siguen funcionando igual.
"""

import heapq
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from itertools import count

from sqlalchemy.orm import Session

from . import models as m
from .domain.horas_habiles import es_dia_habil
from .domain.recetas import receta_vigente, saldo_entrega_actual
from .domain.rut import calcular_dv
from .reloj import ahora, simular
from .services import actividades, apoderados, despachos, faltantes, pacientes, prestamos, recetas, toma_inventario
from .services import dispensacion as servicio
from .services.inventario import ingresar_lote, registrar_merma

DIAS_HISTORIA = 180
NOMBRES = ["María", "José", "Juan", "Ana", "Luis", "Carmen", "Pedro", "Rosa", "Jorge", "Patricia", "Manuel", "Elena",
           "Carlos", "Gloria", "Francisco", "Teresa", "Sergio", "Marta", "Víctor", "Isabel", "Ricardo", "Silvia",
           "Hernán", "Margarita", "Raúl", "Verónica", "Héctor", "Claudia", "Osvaldo", "Lorena", "Patricio", "Ximena",
           "Fernando", "Cecilia", "Alejandro", "Paola", "Cristián", "Soledad", "Mauricio", "Camila", "Rodrigo", "Javiera"]
APELLIDOS = ["González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras", "Silva", "Martínez", "Sepúlveda",
             "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres", "Araya", "Flores", "Espinoza",
             "Valenzuela", "Castillo", "Tapia", "Reyes", "Gutiérrez", "Castro", "Pizarro", "Álvarez", "Vásquez",
             "Sánchez", "Fernández", "Ramírez", "Carrasco", "Gómez", "Cortés", "Herrera", "Núñez", "Jara", "Vergara"]
CALLES = ["Los Aromos", "Las Acacias", "Pasaje El Roble", "Av. Libertad", "Los Boldos", "Calle Esmeralda",
          "Villa Los Héroes", "Av. Valparaíso", "Pasaje Las Camelias", "Los Quillayes", "Calle Prat", "Av. Argentina"]
ALERGIAS = ["Penicilina", "Sulfas", "AINE (ibuprofeno)", "Ácido acetilsalicílico", "Látex", "Metamizol"]
ESTABLECIMIENTOS = ["CESFAM Villa Alemana", "CESFAM El Sol", "Hospital de Quilpué", "CESFAM Belloto Sur"]

# código: (unidades por lote, días para vencer del 1er y 2º lote desde hoy, ubicación). Vencen después que los del seed base.
LOTES_HISTORIA = {
    "LOS50": (5000, (330, 520), "A-01"), "MET850": (7000, (340, 560), "A-01"), "ENAL10": (5000, (360, 540), "B-01"),
    "AML5": (3000, (300, 500), "B-01"), "HCT50": (2000, (320, 480), "B-02"), "AAS100": (3000, (310, 500), "B-02"),
    "GLI5": (3000, (330, 520), "B-02"), "LEV100": (2500, (300, 500), "C-02"), "SER50": (1500, (320, 470), "C-02"),
    "OME20": (1500, (310, 450), "C-02"), "PCT500": (2000, (360, 540), "C-01"), "SAL100": (120, (330, 480), "C-01"),
    "NPH100": (80, (280, 400), "R-01"),
}
POSOLOGIA = {
    "LOS50": "1 comprimido cada 24 h", "ENAL10": "1 comprimido cada 12 h", "AML5": "1 comprimido cada 24 h",
    "HCT50": "½ comprimido en la mañana", "AAS100": "1 comprimido al almuerzo", "ATV20": "1 comprimido en la noche",
    "MET850": "1 comprimido con desayuno y cena", "GLI5": "1 comprimido antes del desayuno",
    "NPH100": "20 UI antes del desayuno y 10 UI antes de la cena", "LEV100": "1 comprimido en ayunas",
    "SER50": "1 comprimido en la mañana", "SAL100": "2 inhalaciones si hay disnea", "CLZ2": "1 comprimido en la noche",
    "PCT500": "1 comprimido cada 8 h si hay dolor, por 7 días", "OME20": "1 cápsula en ayunas por 14 días",
}


def _momento(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto)).astimezone().astimezone(UTC)


def _dia_habil(dia: date) -> date:
    while not es_dia_habil(dia):
        dia += timedelta(days=1)
    return dia


@dataclass
class Paciente:
    id_paciente: int
    rut: str
    nombre: str
    medicamentos: list[tuple[str, int]] = field(default_factory=list)   # crónicos: (código, unidades por mes)
    postrado: bool = False
    cuidador: str | None = None
    domicilio: str = ""
    controlado: bool = False


class Historia:
    def __init__(self, db: Session, hoy: date, base: dict, pacientes_n: int, semilla: int):
        # nosec B311: azar reproducible solo para inventar datos ficticios de demostración, no para seguridad
        self.db, self.hoy, self.rnd = db, hoy, random.Random(semilla)  # nosec B311
        self.usuarios, self.meds = base["usuarios"], base["medicamentos"]
        self.ubicaciones, self.programas, self.sectores = base["ubicaciones"], base["programas"], base["sectores"]
        self.ruts_usados = set(base["ruts_reservados"])
        self.pacientes_n = pacientes_n
        self.agenda: list = []
        self.orden = count()
        self.folios = count(30001)
        self.limite = datetime.now(UTC) - timedelta(minutes=10)
        self.inicio = hoy - timedelta(days=DIAS_HISTORIA)
        self.reclamos_por_receta: dict[int, list[int]] = {}
        self.reintentos: dict[int, int] = {}
        self.cuenta = {"pacientes": 0, "recetas": 0, "entregas": 0, "faltantes": 0, "reclamos": 0, "actividades": 0}
        self.lotes_v: dict[str, list[m.Lotes]] = {}
        self.retiro_atv = _dia_habil(hoy - timedelta(days=77))
        self.reposicion_atv = _dia_habil(self.retiro_atv + timedelta(days=7))

    # ------------------------------------------------------------------ agenda
    def en(self, momento: datetime, accion) -> None:
        if momento < self.limite:
            heapq.heappush(self.agenda, (momento, next(self.orden), accion))

    def ejecutar(self) -> None:
        while self.agenda:
            momento, _, accion = heapq.heappop(self.agenda)
            with simular(momento):
                accion(momento.astimezone().date())

    def hora(self, dia: date, desde: int = 8, hasta: int = 16) -> datetime:
        return _momento(dia, self.rnd.randint(desde, hasta), self.rnd.choice((0, 10, 20, 30, 40, 50)))

    # --------------------------------------------------------------- generación
    def generar(self) -> dict:
        with simular(_momento(self.inicio - timedelta(days=10), 9)):
            self._lotes_iniciales(self.inicio - timedelta(days=10))
            self._pacientes(self.inicio - timedelta(days=10))
        self._planificar_eventos()
        self.ejecutar()
        self.db.flush()
        return self.cuenta

    def _lotes_iniciales(self, dia: date) -> None:
        bod, qf = self.usuarios["BODEGUERO"], self.usuarios["QF"]
        numero = count(71001)
        for codigo, (unidades, vencimientos, ubicacion) in LOTES_HISTORIA.items():
            for i, dias in enumerate(vencimientos):
                lote, _ = ingresar_lote(
                    self.db, bod, id_medicamento=self.meds[codigo].id_medicamento, codigo_lote=f"V{codigo[:3]}-{i + 1}",
                    fecha_vencimiento=self.hoy + timedelta(days=dias), unidades=unidades,
                    id_ubicacion=self.ubicaciones[ubicacion].id_ubicacion, hoy=dia, proveedor="CENABAST",
                    tipo_documento="FACTURA", numero_documento=f"F-{next(numero)}", fecha_documento=dia,
                    costo_total=unidades * _costo(codigo))
                self.lotes_v.setdefault(codigo, []).append(lote)
        # Atorvastatina: el lote que el ISP retirará; sertralina: un lote corto que terminará en merma
        for codigo, nombre, unidades, vence, ubicacion in (("ATV20", "VATV-1", 4000, 420, "C-01"),
                                                           ("SER50", "VSER-C", 400, -20, "C-02")):
            lote, _ = ingresar_lote(self.db, bod, id_medicamento=self.meds[codigo].id_medicamento, codigo_lote=nombre,
                                    fecha_vencimiento=self.hoy + timedelta(days=vence), unidades=unidades,
                                    id_ubicacion=self.ubicaciones[ubicacion].id_ubicacion, hoy=dia, proveedor="CENABAST",
                                    tipo_documento="FACTURA", numero_documento=f"F-{next(numero)}", fecha_documento=dia,
                                    costo_total=unidades * _costo(codigo))
            self.lotes_v.setdefault(codigo, []).append(lote)
        ingresar_lote(self.db, qf, id_medicamento=self.meds["CLZ2"].id_medicamento, codigo_lote="VCLZ-1",
                      fecha_vencimiento=self.hoy + timedelta(days=400), unidades=3000,
                      id_ubicacion=self.ubicaciones["CS-01"].id_ubicacion, hoy=dia, proveedor="CENABAST",
                      tipo_documento="FACTURA", numero_documento=f"F-{next(numero)}", fecha_documento=dia,
                      costo_total=3000 * _costo("CLZ2"))

    def _rut(self) -> str:
        while True:
            cuerpo = self.rnd.randint(4_500_000, 24_900_000)
            if cuerpo not in self.ruts_usados:
                self.ruts_usados.add(cuerpo)
                return f"{cuerpo}-{calcular_dv(str(cuerpo))}"

    def _nombre(self) -> str:
        return f"{self.rnd.choice(NOMBRES)} {self.rnd.choice(APELLIDOS)} {self.rnd.choice(APELLIDOS)}"

    def _pacientes(self, dia: date) -> None:
        rnd, tens = self.rnd, self.usuarios["TECNICO"]
        self.lista: list[Paciente] = []
        for _ in range(self.pacientes_n):
            perfil = rnd.choices(["PSCV", "TIROIDES", "MENTAL", "RESPIRATORIO", "AGUDO"], weights=(55, 10, 10, 8, 17))[0]
            meds, programas = [], []
            if perfil == "PSCV":
                programas.append("Cardiovascular")
                meds.append(rnd.choice([("LOS50", 30), ("ENAL10", 60)]))
                if rnd.random() < .35:
                    meds.append(("AML5", 30))
                if rnd.random() < .25:
                    meds.append(("HCT50", 15))
                if rnd.random() < .55:
                    meds.append(("ATV20", 30))
                if rnd.random() < .30:
                    meds.append(("AAS100", 30))
                if rnd.random() < .45:
                    programas.append("Diabetes")
                    meds.append(("MET850", 60))
                    if rnd.random() < .35:
                        meds.append(("GLI5", 30))
                    if rnd.random() < .12:
                        meds.append(("NPH100", 1))
            elif perfil == "TIROIDES":
                programas.append("Hipotiroidismo")
                meds.append(("LEV100", 30))
            elif perfil == "MENTAL":
                programas.append("Salud Mental")
                meds.append(("SER50", 30))
            elif perfil == "RESPIRATORIO":
                programas.append("Respiratorio crónico")
                meds.append(("SAL100", 1))
            postrado = perfil == "PSCV" and rnd.random() < .06
            if postrado:
                programas.append("Atención domiciliaria")
            edad = rnd.randint(70, 92) if postrado else rnd.randint(28, 85) if perfil != "AGUDO" else rnd.randint(5, 70)
            domicilio = f"{rnd.choice(CALLES)} {rnd.randint(10, 2999)}"
            rut, nombre = self._rut(), self._nombre()
            p = pacientes.registrar_paciente(
                self.db, tens, rut=rut, nombre=nombre, hoy=dia,
                fecha_nacimiento=dia - timedelta(days=edad * 365 + rnd.randint(0, 364)),
                tramo_fonasa=rnd.choices("ABCD", weights=(25, 40, 20, 15))[0],
                programas=[self.programas[x].id_programa for x in programas],
                id_sector=rnd.choice(list(self.sectores.values())).id_sector, es_prais=rnd.random() < .04,
                es_postrado=postrado, alergias=rnd.choice(ALERGIAS) if rnd.random() < .10 else None,
                direccion=domicilio + (", " + rnd.choice(["Villa El Bosque", "Pob. Los Andes", "Sector Rural"]) if postrado else "")
                if postrado else None)
            paciente = Paciente(p.id_paciente, rut, nombre, meds, postrado, domicilio=domicilio,
                                controlado=perfil == "MENTAL" and rnd.random() < .35)
            if postrado:
                paciente.cuidador = f"{rnd.choice(NOMBRES)} {nombre.split()[1]} {rnd.choice(APELLIDOS)}"
                apoderados.registrar_apoderado(self.db, tens, id_paciente=p.id_paciente, rut=self._rut(),
                                               nombre=paciente.cuidador, parentesco=rnd.choice(["Hijo/a", "Cónyuge o pareja", "Cuidador/a"]),
                                               hoy=dia, telefono=f"+56 9 {rnd.randint(4000, 9999)} {rnd.randint(1000, 9999)}")
            self.lista.append(paciente)
            self.cuenta["pacientes"] += 1

    def _planificar_eventos(self) -> None:
        rnd = self.rnd
        for p in self.lista:
            if p.medicamentos:
                emision = _dia_habil(self.hoy - timedelta(days=rnd.randint(8, DIAS_HISTORIA - 5)))
                self.en(self.hora(emision, 8, 11), lambda d, p=p: self.nueva_cronica(p, d))
            if p.controlado:
                dia = _dia_habil(self.inicio + timedelta(days=rnd.randint(0, 25)))
                self.en(self.hora(dia, 9, 12), lambda d, p=p: self.retenida_clonazepam(p, d))
            for _ in range(rnd.choices([0, 1, 2], weights=(45, 40, 15))[0]):
                dia = _dia_habil(self.inicio + timedelta(days=rnd.randint(0, DIAS_HISTORIA - 1)))
                self.en(self.hora(dia), lambda d, p=p: self.aguda(p, d))
        # Alerta sanitaria del ISP: se retira el lote de atorvastatina; llega la reposición una semana después
        self.en(_momento(self.retiro_atv, 8, 15), self.alerta_atorvastatina)
        self.en(_momento(self.reposicion_atv, 8, 30), self.reposicion_atorvastatina)
        self.en(_momento(_dia_habil(self.hoy - timedelta(days=34)), 17), self.merma_sertralina)
        self.en(_momento(_dia_habil(self.hoy - timedelta(days=30)), 17, 30), self.toma_b02)
        self._prestamos()
        self._actividades()

    # ------------------------------------------------------------------ recetas
    def _folio(self) -> str:
        return f"RX-{next(self.folios)}"

    def nueva_cronica(self, p: Paciente, dia: date) -> None:
        receta = recetas.registrar_receta(
            self.db, self.usuarios["MEDICO"], id_paciente=p.id_paciente, folio=self._folio(), fecha_emision=dia,
            hoy=dia, tipo_receta="CRONICA", total_entregas=6, intervalo_dias=30,
            lineas=[recetas.LineaReceta(id_medicamento=self.meds[c].id_medicamento, posologia=POSOLOGIA[c],
                                        cant_por_entrega=n) for c, n in p.medicamentos])
        self.cuenta["recetas"] += 1
        self.en(self._despues(self.rnd.randint(30, 300)) if self.rnd.random() < .7
                else self.hora(_dia_habil(dia + timedelta(days=1))), lambda d, r=receta.id_receta, p=p: self.retirar(p, r, d))

    def aguda(self, p: Paciente, dia: date) -> None:
        opciones = [("PCT500", 20), ("OME20", 14)] if not p.medicamentos or self.rnd.random() < .7 else [("SAL100", 1)]
        lineas = self.rnd.sample(opciones, k=self.rnd.randint(1, len(opciones)))
        receta = recetas.registrar_receta(
            self.db, self.usuarios["MEDICO"], id_paciente=p.id_paciente, folio=self._folio(), fecha_emision=dia, hoy=dia,
            tipo_receta="AGUDA", lineas=[recetas.LineaReceta(id_medicamento=self.meds[c].id_medicamento,
                                                             posologia=POSOLOGIA[c], cant_por_entrega=n) for c, n in lineas])
        self.cuenta["recetas"] += 1
        if self.rnd.random() < .93:
            self.en(self._despues(self.rnd.randint(15, 240)), lambda d, r=receta.id_receta, p=p: self.retirar(p, r, d, cronica=False))

    def retenida_clonazepam(self, p: Paciente, dia: date) -> None:
        qf = self.usuarios["QF"]
        receta = recetas.registrar_receta(
            self.db, qf, id_paciente=p.id_paciente, folio=self._folio(), fecha_emision=dia, hoy=dia,
            tipo_receta="RETENIDA", prescriptor_nombre="Dr. Andrés Molina Soto", prescriptor_rut="10203040-0",
            domicilio_paciente=p.domicilio,
            lineas=[recetas.LineaReceta(id_medicamento=self.meds["CLZ2"].id_medicamento, posologia=POSOLOGIA["CLZ2"],
                                        cant_por_entrega=30)])
        self.cuenta["recetas"] += 1
        self.en(self._despues(self.rnd.randint(20, 180)), lambda d, r=receta.id_receta, p=p: self.retirar(p, r, d, cronica=False))
        siguiente = _dia_habil(dia + timedelta(days=self.rnd.randint(28, 33)))
        self.en(self.hora(siguiente, 9, 12), lambda d, p=p: self.retenida_clonazepam(p, d))

    # ----------------------------------------------------------------- retiros
    def retirar(self, p: Paciente, id_receta: int, dia: date, cronica: bool = True) -> None:
        db, rnd = self.db, self.rnd
        receta = db.get(m.Recetas, id_receta)
        if receta.estado in ("DISPENSADA", "ANULADA"):
            return
        if not receta_vigente(receta.fecha_emision, dia, receta.tipo_receta, receta.entregas_realizadas):
            if cronica:  # se le venció la receta por atraso: vuelve a control y recibe una nueva
                self.en(self.hora(_dia_habil(dia + timedelta(days=rnd.randint(1, 7))), 8, 11),
                        lambda d, p=p: self.nueva_cronica(p, d))
            return
        lineas, pendientes = [], 0
        for det in receta.detalles:
            saldo = saldo_entrega_actual(faltantes._linea(det), receta.entregas_realizadas)
            if saldo <= 0:
                continue
            pendientes += 1
            cantidad = min(saldo, faltantes.stock_dispensable(db, det.id_medicamento, dia))
            if cantidad > 0:
                plan = servicio.planificar_linea(db, det.id_detalle_receta, cantidad, dia)
                lineas.append(servicio.LineaDispensacion(det.id_detalle_receta, cantidad, [x["codigo_lote"] for x in plan]))
        if not pendientes:
            return
        if not lineas:
            resultado = faltantes.registrar_sin_stock(db, self.usuarios["TECNICO"], id_receta, dia)
        else:
            controlado = receta.tipo_receta == "RETENIDA"
            resultado = servicio.dispensar(
                db, self.usuarios["QF" if controlado else "TECNICO"], id_receta=id_receta, lineas=lineas,
                clave_idempotencia=f"hist-{next(self.orden)}", hoy=dia, confirma_alergias=True,
                rut_retira=p.rut if controlado else None, relacion="Titular" if controlado else None,
                firma_qf=servicio.FirmaQF(self.usuarios["QF"].rut, self.pin_qf) if controlado else None,
                a_domicilio=p.postrado)
            self.cuenta["entregas"] += 1
            if resultado.get("id_despacho"):
                self._despacho(p, resultado["id_despacho"], dia)
        for f in resultado["faltantes"]:
            if f["motivo"] != "SIN_STOCK":
                continue
            self.cuenta["faltantes"] += 1
            if rnd.random() < .7:
                self.en(self._despues(minutos=rnd.randint(60, 240)), lambda d, f=f: self.reclamo(f, id_receta))
        if any(f["motivo"] == "SIN_STOCK" for f in resultado["faltantes"]) or (
                resultado.get("resultado") == "SIN_STOCK"):
            self.reintentos[id_receta] = self.reintentos.get(id_receta, 0) + 1
            if self.reintentos[id_receta] > 3:
                return  # después de tres intentos el paciente deja de venir por ese medicamento
            vuelta = max(self.reposicion_atv if dia < self.reposicion_atv else dia, dia + timedelta(days=1))
            vuelta = _dia_habil(vuelta + timedelta(days=rnd.choice((0, 0, 0, 1, 1, 2))))
            self.en(self.hora(vuelta, 9, 17), lambda d, p=p: self.retirar(p, id_receta, d, cronica))
            return
        for id_reclamo in self.reclamos_por_receta.pop(id_receta, []):
            self.en(self._despues(minutos=15), lambda d, i=id_reclamo, p=p: self.cerrar_reclamo(i, p))
        db.flush()  # (refresh descartaría el estado de la receta recién recalculado)
        if not cronica:
            return
        if receta.estado == "DISPENSADA":  # completó las 6 entregas: control médico y receta nueva
            control = _dia_habil(dia + timedelta(days=rnd.randint(25, 32)))
            self.en(self.hora(control, 8, 11), lambda d, p=p: self.nueva_cronica(p, d))
        elif receta.proxima_fecha_retiro:
            desfase = rnd.choices([rnd.randint(-3, 0), rnd.randint(1, 4), rnd.randint(6, 18)], weights=(55, 33, 12))[0]
            proximo = _dia_habil(max(receta.proxima_fecha_retiro + timedelta(days=desfase), dia + timedelta(days=1)))
            self.en(self.hora(proximo), lambda d, p=p: self.retirar(p, id_receta, d))

    def _despues(self, minutos: int) -> datetime:
        """Un momento posterior al simulado (el reloj de la historia nunca retrocede)."""
        return ahora() + timedelta(minutes=minutos)

    def _despacho(self, p: Paciente, id_despacho: int, dia: date) -> None:
        tens = self.usuarios["TECNICO"]
        self.en(self._despues(90), lambda d: despachos.cambiar_estado(self.db, tens, id_despacho, "EN_RUTA"))
        self.en(self._despues(220), lambda d: despachos.cambiar_estado(
            self.db, tens, id_despacho, "ENTREGADO", recibe_nombre=p.cuidador or p.nombre))

    def reclamo(self, f: dict, id_receta: int) -> None:
        if self.db.get(m.Faltantes, f["id_faltante"]).estado != "PENDIENTE":
            return
        canal = self.rnd.choices(["OIRS", "SALUD_RESPONDE", "PRESENCIAL"], weights=(60, 25, 15))[0]
        reclamo = faltantes.registrar_reclamo(
            self.db, self.usuarios["TECNICO"], canal=canal, id_faltante=f["id_faltante"],
            folio_externo=f"{'OIRS' if canal == 'OIRS' else 'SR'}-{self.hoy.year}-{self.rnd.randint(1000, 9999)}"
            if canal != "PRESENCIAL" else None,
            descripcion=f"No se entregó {f['medicamento'].split(' ')[0].lower()} en el retiro; solicita entrega a la brevedad.")
        self.reclamos_por_receta.setdefault(id_receta, []).append(reclamo.id_reclamo)
        self.cuenta["reclamos"] += 1

    def cerrar_reclamo(self, id_reclamo: int, p: Paciente) -> None:
        reclamo = self.db.get(m.Reclamos, id_reclamo)
        if reclamo.estado == "ABIERTO" and (reclamo.faltante is None or reclamo.faltante.estado != "PENDIENTE"):
            faltantes.cerrar_reclamo(self.db, self.usuarios["TECNICO"], id_reclamo, recibe_nombre=p.nombre,
                                     solucion="Se entregó el medicamento comprometido; firma acta de recepción.")

    # -------------------------------------------------------- eventos de bodega
    def alerta_atorvastatina(self, dia: date) -> None:
        lote = self.lotes_v["ATV20"][0]
        if lote.unidades_disp:
            registrar_merma(self.db, self.usuarios["QF"], lote.id_lote, lote.unidades_disp, "ALERTA_SANITARIA",
                            "Alerta sanitaria ISP: retiro del lote del mercado")

    def reposicion_atorvastatina(self, dia: date) -> None:
        ingresar_lote(self.db, self.usuarios["BODEGUERO"], id_medicamento=self.meds["ATV20"].id_medicamento,
                      codigo_lote="VATV-2", fecha_vencimiento=self.hoy + timedelta(days=500), unidades=4000,
                      id_ubicacion=self.ubicaciones["C-01"].id_ubicacion, hoy=dia, proveedor="CENABAST",
                      tipo_documento="GUIA", numero_documento="GD-90412", fecha_documento=dia,
                      costo_total=4000 * _costo("ATV20"))

    def merma_sertralina(self, dia: date) -> None:
        lote = self.lotes_v["SER50"][-1]
        if lote.unidades_disp:
            registrar_merma(self.db, self.usuarios["BODEGUERO"], lote.id_lote, lote.unidades_disp, "VENCIMIENTO",
                            "Vence en menos de 14 días: retiro obligatorio")

    def toma_b02(self, dia: date) -> None:
        qf = self.usuarios["QF"]
        toma = toma_inventario.abrir_toma(self.db, qf, id_ubicacion=self.ubicaciones["B-02"].id_ubicacion,
                                          observacion="Inventario mensual del casillero B-02")
        for i, conteo in enumerate(toma.conteos):
            diferencia = -3 if i == 0 else 0
            toma_inventario.registrar_conteo(self.db, self.usuarios["BODEGUERO"], toma.id_toma, conteo.id_conteo,
                                             conteo.lote.unidades_disp + diferencia)
        toma_inventario.cerrar_toma(self.db, qf, toma.id_toma, "Faltan 3 unidades: blíster dañado sin registrar")

    def _prestamos(self) -> None:
        bod = self.usuarios["BODEGUERO"]
        recibido_dia = _dia_habil(self.hoy - timedelta(days=62))
        estado = {}

        def recibir(d):
            estado["recibido"] = prestamos.registrar_prestamo(
                self.db, bod, tipo="RECIBIDO", establecimiento=ESTABLECIMIENTOS[2], id_medicamento=self.meds["AML5"].id_medicamento,
                cantidad=300, fecha_compromiso=d + timedelta(days=21), hoy=d, documento="FP-0188", codigo_lote="VAML-P",
                fecha_vencimiento=self.hoy + timedelta(days=600), id_ubicacion=self.ubicaciones["B-01"].id_ubicacion).id_prestamo

        def otorgar(d):
            estado["otorgado"] = prestamos.registrar_prestamo(
                self.db, bod, tipo="OTORGADO", establecimiento=ESTABLECIMIENTOS[1], id_medicamento=self.meds["LOS50"].id_medicamento,
                cantidad=200, fecha_compromiso=d + timedelta(days=14), hoy=d, documento="FP-0203").id_prestamo

        self.en(_momento(recibido_dia, 10), recibir)
        self.en(_momento(_dia_habil(recibido_dia + timedelta(days=18)), 11),
                lambda d: prestamos.devolver_prestamo(self.db, bod, estado["recibido"], d))
        otorgado_dia = _dia_habil(self.hoy - timedelta(days=41))
        self.en(_momento(otorgado_dia, 12), otorgar)
        self.en(_momento(_dia_habil(otorgado_dia + timedelta(days=13)), 15), lambda d: prestamos.devolver_prestamo(
            self.db, bod, estado["otorgado"], d, codigo_lote="VLOS-D", fecha_vencimiento=self.hoy + timedelta(days=480),
            id_ubicacion=self.ubicaciones["A-01"].id_ubicacion))

    def _actividades(self) -> None:
        rnd, qf = self.rnd, self.usuarios["QF"]
        cronicos = [p for p in self.lista if p.medicamentos]
        registrar = actividades.registrar_actividad

        def atencion(d):
            p = rnd.choice(cronicos)
            tipo = rnd.choice(["SEGUIMIENTO_FT", "EDUCACION", "REVISION_MEDICACION", "CONCILIACION"])
            textos = {"SEGUIMIENTO_FT": ("Control de adherencia: revisión de retiros y uso de pastillero.",
                                         "Adherente; se refuerzan horarios."),
                      "EDUCACION": ("Educación sobre la enfermedad y el uso correcto de sus medicamentos.",
                                    "Comprende indicaciones; se entrega material escrito."),
                      "REVISION_MEDICACION": ("Revisión de la medicación con entrevista: duplicidades e interacciones.",
                                              "Sin problemas relacionados con medicamentos."),
                      "CONCILIACION": ("Conciliación al alta hospitalaria con la receta del CESFAM.",
                                       "Se informa discrepancia al médico tratante.")}
            descripcion, resultado = textos[tipo]
            registrar(self.db, qf, tipo=tipo, fecha=d, hoy=d, rut_paciente=p.rut, descripcion=descripcion, resultado=resultado)
            self.cuenta["actividades"] += 1

        def taller(d, tema):
            registrar(self.db, qf, tipo="TALLER", fecha=d, hoy=d, participantes=rnd.randint(8, 22), descripcion=f"Taller grupal: {tema}.")
            self.cuenta["actividades"] += 1

        dia = _dia_habil(self.inicio + timedelta(days=3))
        while dia < self.hoy:
            self.en(self.hora(dia, 14, 16), atencion)
            dia = _dia_habil(dia + timedelta(days=7))
        temas = ["uso racional de medicamentos", "resistencia antimicrobiana", "uso de benzodiacepinas",
                 "medicamentos herbarios", "insulinoterapia en domicilio"]
        for i, tema in enumerate(temas):
            self.en(_momento(_dia_habil(self.inicio + timedelta(days=15 + 33 * i)), 15),
                    lambda d, tema=tema: taller(d, tema))

        def ram(d, medicamento, gravedad, texto, notificar):
            p = rnd.choice(cronicos)
            a = registrar(self.db, qf, tipo="RAM", fecha=d, hoy=d, rut_paciente=p.rut, gravedad=gravedad,
                          id_medicamento=self.meds[medicamento].id_medicamento, descripcion=texto,
                          resultado="Se informa al médico tratante.")
            self.cuenta["actividades"] += 1
            if notificar:
                self.en(self._despues(60 * 24 * 2), lambda d2, i=a.id_actividad: actividades.registrar_notificacion(
                    self.db, qf, i, fecha_notificacion=d2, folio_isp=f"SVI-{self.hoy.year}-{rnd.randint(40000, 69999)}", hoy=d2))

        self.en(_momento(_dia_habil(self.hoy - timedelta(days=120)), 11), lambda d: ram(
            d, "ENAL10", "MODERADA", "Tos seca persistente desde el inicio de enalapril.", True))
        self.en(_momento(_dia_habil(self.hoy - timedelta(days=45)), 11), lambda d: ram(
            d, "MET850", "LEVE", "Molestias gastrointestinales con metformina.", True))
        self.en(_momento(_dia_habil(self.hoy - timedelta(days=88)), 12), lambda d: registrar(
            self.db, qf, tipo="FALLA_CALIDAD", fecha=d, hoy=d, id_medicamento=self.meds["LOS50"].id_medicamento,
            id_lote=self.lotes_v["LOS50"][0].id_lote, descripcion="Blíster con comprimidos partidos en una caja sellada."))


def _costo(codigo: str) -> int:
    from .seed import COSTOS  # evita la importación circular (seed importa este módulo)
    return COSTOS[codigo]


def poblar_historia(db: Session, hoy: date, base: dict, pacientes_n: int = 150, semilla: int = 2026,
                    pin_qf: str = "4321") -> dict:
    historia = Historia(db, hoy, base, pacientes_n, semilla)
    historia.pin_qf = pin_qf
    return historia.generar()
