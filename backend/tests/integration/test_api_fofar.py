"""Integración v0.6: libro de controlados completo (D.S. 404/405) y Programa Fondo de Farmacia.

Datos del seed usados aquí: la receta RX-5006 (Luis Herrera, cardiovascular) quedó con
carvedilol sin entregar por quiebre de stock (compromiso de 24 h hábiles) y con un
reclamo OIRS abierto; hay 3 actividades farmacéuticas programadas sobre 40 y un
préstamo de 60 paracetamol otorgado al CESFAM Los Volcanes.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.models import Lotes, MovimientosStock
from app.reloj import hoy
from tests.conftest import FIRMA_QF

HOY = hoy().isoformat()
FACTURA = {"proveedor": "CENABAST", "tipo_documento": "FACTURA", "numero_documento": "F-50001",
           "fecha_documento": HOY}
DATOS_LIBRO = {"prescriptor_nombre": "Dr. Andrés Molina Soto", "prescriptor_rut": "10203040-0",
               "domicilio_paciente": "Av. Los Carrera 1550, depto. 32"}


def lote_nuevo(datos, codigo_med, codigo_lote, unidades, ubicacion, **extra):
    return {"id_medicamento": datos["medicamentos"][codigo_med], "codigo_lote": codigo_lote,
            "fecha_vencimiento": (hoy() + timedelta(days=300)).isoformat(), "unidades": unidades,
            "id_ubicacion": datos["ubicaciones"][ubicacion], **extra}


def libro(cliente, cabeceras):
    return cliente.get("/api/controlados/libro", headers=cabeceras("QF")).json()


def id_lote(db, codigo):
    return db.scalar(select(Lotes.id_lote).where(Lotes.codigo_lote == codigo))


def stock(db, codigo):
    db.expire_all()
    return db.scalar(select(Lotes.unidades_disp).where(Lotes.codigo_lote == codigo))


def ficha(cliente, cabeceras, rut):
    return cliente.post("/api/pacientes/buscar", json={"rut": rut}, headers=cabeceras("QF")).json()


def entregar(cliente, cabeceras, receta, cantidades, rol="TECNICO", **extra):
    """Entrega las líneas indicadas ({índice: cantidad}) escaneando el plan FEFO."""
    lineas = []
    for i, cantidad in cantidades.items():
        d = receta["detalles"][i]
        plan = cliente.get(f"/api/dispensaciones/plan?id_detalle_receta={d['id_detalle_receta']}&cantidad={cantidad}",
                           headers=cabeceras(rol)).json()
        lineas.append({"id_detalle_receta": d["id_detalle_receta"], "cantidad": cantidad,
                       "lotes_escaneados": [p["codigo_lote"] for p in plan]})
    return cliente.post("/api/dispensaciones", headers=cabeceras(rol), json={
        "id_receta": receta["id_receta"], "clave_idempotencia": uuid.uuid4().hex, "lineas": lineas, **extra})


def receta_de(cliente, cabeceras, rut, folio):
    return next(r for r in ficha(cliente, cabeceras, rut)["recetas"] if r["folio"] == folio)


# --------------------------------------------------------- libro D.S. 404/405
def test_it120_recepcion_de_controlado_exige_qf_y_documento_y_queda_en_el_libro(cliente, cabeceras, datos):
    cuerpo = lote_nuevo(datos, "CLZ2", "C-2611", 40, "CS-01")
    assert cliente.post("/api/lotes", headers=cabeceras("BODEGUERO"), json={**cuerpo, **FACTURA}).json()["codigo"] \
        == "REQUIERE_QF"
    assert cliente.post("/api/lotes", headers=cabeceras("QF"), json=cuerpo).json()["codigo"] == "DOCUMENTO_REQUERIDO"
    r = cliente.post("/api/lotes", headers=cabeceras("QF"), json={**cuerpo, **FACTURA, "costo_total": 1000})
    assert r.status_code == 201 and r.json()["lote"]["costo_unitario"] == 25
    ingreso = libro(cliente, cabeceras)[-1]
    assert ingreso["tipo"] == "INGRESO" and ingreso["contenido"]["proveedor"] == "CENABAST"
    assert ingreso["contenido"]["documento"] == "Factura N.º F-50001" and ingreso["saldo"] == 160 + 40


def test_it121_merma_y_ajuste_de_controlado_quedan_en_el_libro_con_saldo(cliente, cabeceras, db):
    c2504 = id_lote(db, "C-2504")
    merma = {"cantidad": 5, "motivo": "DANO", "observacion": "Blíster roto"}
    assert cliente.post(f"/api/lotes/{c2504}/merma", headers=cabeceras("BODEGUERO"), json=merma).json()["codigo"] \
        == "REQUIERE_QF"
    assert cliente.post(f"/api/lotes/{c2504}/merma", headers=cabeceras("QF"), json=merma).status_code == 201
    assert cliente.post(f"/api/lotes/{c2504}/ajuste", headers=cabeceras("QF"),
                        json={"unidades_correctas": 54, "motivo": "Recuento en arqueo semanal"}).status_code == 200
    ultimos = libro(cliente, cabeceras)[-2:]
    assert [(a["tipo"], a["contenido"]["cantidad"], a["saldo"]) for a in ultimos] == [("MERMA", 5, 155),
                                                                                       ("AJUSTE", -1, 154)]
    assert cliente.get("/api/controlados/verificar", headers=cabeceras("QF")).json()["integra"] is True


def test_it122_receta_de_controlado_exige_datos_del_libro_y_receta_cheque(cliente, cabeceras, datos):
    id_pac = ficha(cliente, cabeceras, "14141414-3")["paciente"]["id_paciente"]

    def receta(codigo, folio, **extra):
        return {"id_paciente": id_pac, "folio": folio, "fecha_emision": HOY, "es_retenida": True,
                "lineas": [{"id_medicamento": datos["medicamentos"][codigo], "cant_prescrita": 30,
                            "posologia": "1 comprimido al día"}], **extra}
    sin_datos = cliente.post("/api/recetas", headers=cabeceras("QF"), json=receta("CLZ2", "RX-7001"))
    assert sin_datos.json()["codigo"] == "DATOS_LIBRO_REQUERIDOS"
    sin_cheque = cliente.post("/api/recetas", headers=cabeceras("QF"), json=receta("MTF10", "RX-7002", **DATOS_LIBRO))
    assert sin_cheque.json()["codigo"] == "RECETA_CHEQUE_REQUERIDA"
    r = cliente.post("/api/recetas", headers=cabeceras("QF"),
                     json=receta("MTF10", "RX-7003", numero_receta_cheque="RC-889123", **DATOS_LIBRO))
    assert r.status_code == 201 and r.json()["numero_receta_cheque"] == "RC-889123"
    assert entregar(cliente, cabeceras, r.json(), {0: 30}, rol="QF", rut_retira="14141414-3", relacion="Titular",
                    firma_qf=FIRMA_QF).status_code == 201
    salida = libro(cliente, cabeceras)[-1]["contenido"]
    assert salida["receta_cheque"] == "RC-889123" and salida["rut_prescriptor"] == "10203040-0"
    assert salida["saldo"] == 30


def test_it123_libro_csv_tiene_entradas_salidas_y_saldo(cliente, cabeceras):
    texto = cliente.get("/api/reportes/libro.csv", headers=cabeceras("QF")).content.decode()
    assert "Entrada;Salida;Saldo;Proveedor;Documento;Folio receta;Receta cheque;Prescriptor" in texto
    assert ";INGRESO;CLZ2;Clonazepam 2 mg comprimidos;C-2504;60;;60;CENABAST;Factura N.º F-48208;" in texto


# ------------------------------------------------- faltantes y despacho oportuno
def test_it124_quiebre_del_seed_queda_como_compromiso_de_24_horas_habiles(cliente, cabeceras):
    pendientes = cliente.get("/api/faltantes?estado=PENDIENTE", headers=cabeceras("TECNICO")).json()
    carvedilol = next(f for f in pendientes if f["folio"] == "RX-5006")
    assert carvedilol["medicamento"] == "Carvedilol 25 mg comprimidos" and carvedilol["cantidad"] == 30
    assert carvedilol["vencido"] is False and 0 < carvedilol["horas_habiles_restantes"] <= 24
    reclamo = cliente.get("/api/reclamos", headers=cabeceras("TECNICO")).json()[0]
    assert reclamo["canal"] == "OIRS" and reclamo["estado"] == "ABIERTO"
    assert reclamo["faltante"]["id_faltante"] == carvedilol["id_faltante"]
    assert cliente.get("/api/faltantes", headers=cabeceras("BODEGUERO")).status_code == 403


def test_it125_lo_no_entregado_se_clasifica_por_stock_o_rechazo(cliente, cabeceras):
    rx = receta_de(cliente, cabeceras, "12345678-5", "RX-1001")       # losartán y metformina con stock
    r = entregar(cliente, cabeceras, rx, {0: 30})
    assert r.status_code == 201 and r.json()["resultado"] == "RECHAZO"
    assert [(f["motivo"], f["estado"]) for f in r.json()["faltantes"]] == [("RECHAZO_PACIENTE", "RECHAZO")]

    rx = receta_de(cliente, cabeceras, "14141414-3", "RX-1004")
    r = entregar(cliente, cabeceras, rx, {0: 30},
                 motivos_incompletos={str(rx["detalles"][1]["id_detalle_receta"]): "SIN_STOCK"})
    assert r.json()["resultado"] == "SIN_STOCK" and r.json()["faltantes"][0]["estado"] == "PENDIENTE"
    assert r.json()["faltantes"][0]["plazo"] is not None


def test_it126_sin_stock_solo_si_no_hay_nada_que_entregar(cliente, cabeceras):
    rx = receta_de(cliente, cabeceras, "14141414-3", "RX-1004")
    assert cliente.post(f"/api/recetas/{rx['id_receta']}/sin-stock", headers=cabeceras("TECNICO")).json()["codigo"] \
        == "HAY_STOCK"
    rx = receta_de(cliente, cabeceras, "8123456-6", "RX-5006")
    r = cliente.post(f"/api/recetas/{rx['id_receta']}/sin-stock", headers=cabeceras("TECNICO"))
    assert r.status_code == 201 and r.json()["resultado"] == "SIN_STOCK"
    assert r.json()["faltantes"] == []        # ya había un compromiso abierto: conserva su plazo original


def test_it127_entrega_cumple_el_compromiso_y_el_reclamo_se_cierra_con_acta(cliente, cabeceras, datos):
    reclamo = cliente.get("/api/reclamos", headers=cabeceras("TECNICO")).json()[0]
    cierre = {"solucion": "Se entregó el carvedilol comprometido", "recibe_nombre": "Luis Herrera Campos"}
    url = f"/api/reclamos/{reclamo['id_reclamo']}"
    assert cliente.post(url + "/cerrar", headers=cabeceras("TECNICO"), json=cierre).json()["codigo"] \
        == "FALTANTE_PENDIENTE"

    assert cliente.post("/api/lotes", headers=cabeceras("BODEGUERO"),
                        json=lote_nuevo(datos, "CAR25", "CV-2701", 300, "B-01", **FACTURA, costo_total=3000)
                        ).status_code == 201
    rx = receta_de(cliente, cabeceras, "8123456-6", "RX-5006")
    r = entregar(cliente, cabeceras, rx, {1: 30})
    assert r.status_code == 201 and r.json()["resultado"] == "COMPLETA"
    faltante = cliente.get("/api/faltantes?estado=ENTREGADO", headers=cabeceras("TECNICO")).json()[0]
    assert faltante["folio"] == "RX-5006" and faltante["a_tiempo"] is True

    cerrado = cliente.post(url + "/cerrar", headers=cabeceras("TECNICO"), json=cierre).json()
    assert cerrado["estado"] == "RESUELTO" and cerrado["dentro_de_plazo"] is True
    acta = cliente.get(url + "/acta", headers=cabeceras("TECNICO")).json()
    assert acta["recibe_nombre"] == "Luis Herrera Campos" and acta["faltante"]["medicamento"].startswith("Carvedilol")
    indicador = cliente.get(f"/api/indicadores/fofar?desde={HOY}&hasta={HOY}", headers=cabeceras("QF")).json()
    assert indicador["reclamos"] == {"reclamos": 1, "resueltos_en_plazo": 1, "fuera_de_plazo": 0, "en_curso": 0,
                                     "porcentaje": 100.0, "meta": 100, "cumple": True}

    # Anular la entrega que cumplió el compromiso lo deja pendiente otra vez
    id_disp = r.json()["id_dispensacion"]
    cliente.post(f"/api/dispensaciones/{id_disp}/anular", headers=cabeceras("QF"),
                 json={"motivo": "Se registró en la receta equivocada"})
    pendientes = cliente.get("/api/faltantes?estado=PENDIENTE", headers=cabeceras("TECNICO")).json()
    assert any(f["folio"] == "RX-5006" for f in pendientes)


def test_it128_reclamo_por_rut_y_no_atingente(cliente, cabeceras):
    r = cliente.post("/api/reclamos", headers=cabeceras("TECNICO"), json={
        "canal": "SALUD_RESPONDE", "rut": "7654321-6", "descripcion": "Consulta por el horario de la farmacia"})
    assert r.status_code == 201 and r.json()["paciente"]["nombre"] == "Rosa Fuentes Muñoz"
    cerrado = cliente.post(f"/api/reclamos/{r.json()['id_reclamo']}/no-atingente", headers=cabeceras("TECNICO"),
                           json={"motivo": "No es por entrega de medicamentos del programa"}).json()
    assert cerrado["estado"] == "NO_ATINGENTE"
    assert cliente.post("/api/reclamos", headers=cabeceras("TECNICO"), json={
        "canal": "OIRS", "descripcion": "Sin paciente identificado"}).json()["codigo"] == "PACIENTE_REQUERIDO"


def test_it129_indicador_de_despacho_oportuno_y_rem_a04_j(cliente, cabeceras):
    indicador = cliente.get(f"/api/indicadores/fofar?desde={HOY}&hasta={HOY}", headers=cabeceras("QF")).json()
    despacho = indicador["despacho"]   # RX-5001 completa y RX-5006 con quiebre de carvedilol
    assert (despacho["solicitudes"], despacho["cumplidas"], despacho["sin_stock"]) == (2, 1, 1)
    assert despacho["porcentaje"] == 50.0 and despacho["cumple"] is False
    assert despacho["brechas"][0] == {"medicamento": "Carvedilol 25 mg comprimidos", "faltantes": 1,
                                      "entregados_despues": 0, "pendientes": 1, "dias_promedio": None}
    texto = cliente.get(f"/api/reportes/rem-a04-j.csv?desde={HOY}&hasta={HOY}", headers=cabeceras("QF")).content.decode()
    assert "Programa;Medicamento;Solicitadas;Despacho total y oportuno" in texto
    assert "Cardiovascular;Carvedilol 25 mg comprimidos;1;0;0;1;0;" in texto
    assert "Cardiovascular;Enalapril 10 mg comprimidos;2;2;0;0;0;" in texto
    assert cliente.get(f"/api/indicadores/fofar?desde={HOY}&hasta={HOY}", headers=cabeceras("TECNICO")).status_code == 403


# ------------------------------------------------------------ toma de inventario
def test_it130_toma_a_ciegas_y_el_qf_aplica_las_diferencias(cliente, cabeceras, datos, db):
    toma = cliente.post("/api/inventario/tomas", headers=cabeceras("QF"),
                        json={"id_ubicacion": datos["ubicaciones"]["CS-01"]})
    assert toma.status_code == 201 and toma.json()["resumen"]["lotes"] == 3
    assert cliente.post("/api/inventario/tomas", headers=cabeceras("QF"), json={}).json()["codigo"] == "TOMA_ABIERTA"
    id_toma = toma.json()["id_toma"]
    ciega = cliente.get(f"/api/inventario/tomas/{id_toma}", headers=cabeceras("TECNICO")).json()
    assert all("stock_al_contar" not in c for c in ciega["conteos"])          # el que cuenta no ve el sistema
    contado = {"C-2504": 58, "C-2510": 100, "MF-2608": 60}
    primero = ciega["conteos"][0]
    cliente.post(f"/api/inventario/tomas/{id_toma}/conteos", headers=cabeceras("TECNICO"),
                 json={"id_conteo": primero["id_conteo"], "cantidad": contado[primero["codigo_lote"]]})
    assert cliente.post(f"/api/inventario/tomas/{id_toma}/cerrar", headers=cabeceras("QF"),
                        json={}).json()["codigo"] == "CONTEO_INCOMPLETO"
    for c in ciega["conteos"][1:]:
        cliente.post(f"/api/inventario/tomas/{id_toma}/conteos", headers=cabeceras("BODEGUERO"),
                     json={"id_conteo": c["id_conteo"], "cantidad": contado[c["codigo_lote"]]})
    revision = cliente.get(f"/api/inventario/tomas/{id_toma}", headers=cabeceras("QF")).json()
    assert revision["resumen"]["con_diferencia"] == 1 and revision["resumen"]["valor_diferencias"] == -50
    assert cliente.post(f"/api/inventario/tomas/{id_toma}/cerrar", headers=cabeceras("TECNICO"), json={}).status_code == 403
    cerrada = cliente.post(f"/api/inventario/tomas/{id_toma}/cerrar", headers=cabeceras("QF"),
                           json={"observacion": "Arqueo mensual de controlados"})
    assert cerrada.json()["estado"] == "CERRADA" and stock(db, "C-2504") == 58
    ajuste = libro(cliente, cabeceras)[-1]
    assert ajuste["tipo"] == "AJUSTE" and ajuste["contenido"]["cantidad"] == -2 and ajuste["saldo"] == 158
    assert cliente.post(f"/api/inventario/tomas/{id_toma}/conteos", headers=cabeceras("TECNICO"),
                        json={"id_conteo": primero["id_conteo"], "cantidad": 1}).json()["codigo"] == "TOMA_CERRADA"


def test_it131_merma_valorizada_excluye_insulinas(cliente, cabeceras, db):
    cliente.post(f"/api/lotes/{id_lote(db, 'SE-2512')}/merma", headers=cabeceras("BODEGUERO"),
                 json={"cantidad": 30, "motivo": "VENCIMIENTO"})                   # 30 × $20
    cliente.post(f"/api/lotes/{id_lote(db, 'IN-2603')}/merma", headers=cabeceras("BODEGUERO"),
                 json={"cantidad": 1, "motivo": "DANO"})                           # insulina: no cuenta
    merma = cliente.get(f"/api/indicadores/fofar?desde={HOY}&hasta={HOY}", headers=cabeceras("QF")).json()["merma"]
    assert merma["merma_valorizada"] == 600 and merma["inventario_valorizado"] > 0
    assert merma["porcentaje"] == round(600 * 100 / merma["inventario_valorizado"], 2)
    assert merma["meta"] == 0.99 and merma["lotes_sin_costo"] == 0


# ------------------------------------------------------- actividades farmacéuticas
def test_it132_actividades_validan_y_suman_al_indicador(cliente, cabeceras, datos):
    qf = cabeceras("QF")
    base = {"fecha": HOY, "descripcion": "Paciente con náuseas tras iniciar el tratamiento"}
    assert cliente.post("/api/actividades", headers=qf, json={**base, "tipo": "RAM", "rut_paciente": "16234567-2",
                        "id_medicamento": datos["medicamentos"]["SER50"]}).json()["codigo"] == "GRAVEDAD_REQUERIDA"
    assert cliente.post("/api/actividades", headers=qf, json={**base, "tipo": "TALLER", "participantes": 10,
                        "rut_paciente": "16234567-2"}).json()["codigo"] == "PACIENTE_NO_CORRESPONDE"
    assert cliente.post("/api/actividades", headers=qf, json={**base, "tipo": "CONCILIACION"}).json()["codigo"] \
        == "PACIENTE_REQUERIDO"
    r = cliente.post("/api/actividades", headers=qf, json={
        **base, "tipo": "CONCILIACION", "rut_paciente": "7654321-6",
        "descripcion": "Conciliación al alta hospitalaria: se suspende AINE duplicado"})
    assert r.status_code == 201 and r.json()["categoria"] == "ATENCION"

    ram = next(a for a in cliente.get("/api/actividades", headers=qf).json() if a["tipo"] == "RAM")
    assert ram["pendiente_notificar"] is True and ram["paciente"]["nombre"] == "Patricia Soto Lagos"
    notificada = cliente.post(f"/api/actividades/{ram['id_actividad']}/notificacion", headers=qf,
                              json={"fecha_notificacion": HOY, "folio_isp": "SVI-2026-55871"}).json()
    assert notificada["folio_isp"] == "SVI-2026-55871" and notificada["pendiente_notificar"] is False

    actividades = cliente.get(f"/api/indicadores/fofar?desde={HOY}&hasta={HOY}", headers=qf).json()["actividades"]
    assert (actividades["realizadas"], actividades["programadas"], actividades["porcentaje"]) == (4, 40, 10.0)
    assert actividades["meta"] == (50 if hoy().month <= 6 else 100)
    assert cliente.post("/api/actividades", headers=cabeceras("BODEGUERO"), json=base).status_code == 403


# -------------------------------------------------------------------- préstamos
def test_it133_prestamos_mueven_stock_por_el_kardex(cliente, cabeceras, datos, db):
    bod = cabeceras("BODEGUERO")
    otorgado = cliente.get("/api/prestamos", headers=bod).json()[0]
    assert (otorgado["tipo"], otorgado["cantidad"], otorgado["estado"]) == ("OTORGADO", 60, "PENDIENTE")
    assert stock(db, "PC-2610") == 1000 - 60
    url = f"/api/prestamos/{otorgado['id_prestamo']}/devolver"
    assert cliente.post(url, headers=bod, json={}).json()["codigo"] == "LOTE_REQUERIDO"
    devuelto = cliente.post(url, headers=bod, json={"codigo_lote": "PV-2702", "id_ubicacion": datos["ubicaciones"]["C-01"],
                                                    "fecha_vencimiento": (hoy() + timedelta(days=400)).isoformat()})
    assert devuelto.json()["estado"] == "DEVUELTO" and stock(db, "PV-2702") == 60

    controlado = {"tipo": "RECIBIDO", "establecimiento": "Hospital Regional", "id_medicamento": datos["medicamentos"]["CLZ2"],
                  "cantidad": 10, "fecha_compromiso": HOY}
    assert cliente.post("/api/prestamos", headers=bod, json=controlado).json()["codigo"] == "CONTROLADO_NO_PRESTABLE"
    recibido = cliente.post("/api/prestamos", headers=bod, json={
        **controlado, "id_medicamento": datos["medicamentos"]["AML5"], "cantidad": 100,
        "codigo_lote": "AM-2703", "fecha_vencimiento": (hoy() + timedelta(days=500)).isoformat(),
        "id_ubicacion": datos["ubicaciones"]["B-01"]})
    assert recibido.status_code == 201 and stock(db, "AM-2703") == 100
    cliente.post(f"/api/prestamos/{recibido.json()['id_prestamo']}/devolver", headers=bod, json={})
    assert stock(db, "AM-2605") == 50        # FEFO: se devuelve desde el lote que vence primero
    tipos = db.scalars(select(MovimientosStock.tipo).where(MovimientosStock.referencia_tipo == "prestamos")
                       .order_by(MovimientosStock.id_movimiento)).all()
    assert tipos == ["PRESTAMO_SALIDA", "PRESTAMO_ENTRADA", "PRESTAMO_ENTRADA", "PRESTAMO_SALIDA"]
    assert cliente.get("/api/prestamos", headers=cabeceras("TECNICO")).status_code == 403


# ------------------------------------------------------------------- gráficos
def test_it134_series_para_graficos(cliente, cabeceras):
    entregas = cliente.get("/api/panel/entregas?dias=30", headers=cabeceras("TECNICO")).json()
    assert len(entregas) == 30 and entregas[-1]["fecha"] == HOY
    assert entregas[-1]["entregas"] == 2 and entregas[-1]["unidades"] == 30 + 30 + 60 + 30   # RX-5001 y RX-5006
    assert all(e["entregas"] == 0 for e in entregas[:-1])

    desde = (hoy().replace(day=1) - timedelta(days=150)).replace(day=1).isoformat()
    mensual = cliente.get(f"/api/indicadores/fofar/mensual?desde={desde}&hasta={HOY}", headers=cabeceras("QF")).json()
    assert [m["mes"] for m in mensual["meses"]][-1] == HOY[:7] and len(mensual["meses"]) == 6
    assert mensual["meses"][-1]["despacho"] == 50.0 and mensual["meses"][0]["despacho"] is None
    assert mensual["actividades"][-1]["acumuladas"] == 3 and mensual["programadas"] == 40

    venc = cliente.get("/api/inventario/vencimientos-por-mes", headers=cabeceras("BODEGUERO")).json()
    assert len(venc) == 6 and sum(v["lotes"] for v in venc) >= 4      # L-2411, M-2501, SE-2512, L-2502...
    # L-2411 (40 u. a $12) vence en 9 días: cae en este mes o el siguiente
    assert venc[0]["unidades"] + venc[1]["unidades"] >= 40 and venc[0]["valor"] + venc[1]["valor"] >= 480
    assert all(v["sin_costo"] == 0 for v in venc)
    assert cliente.get(f"/api/indicadores/fofar/mensual?desde={HOY}&hasta={HOY}",
                       headers=cabeceras("TECNICO")).status_code == 403
