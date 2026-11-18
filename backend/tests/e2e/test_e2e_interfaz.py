"""Pruebas E2E sobre la interfaz real (Playwright + Chromium/Brave).

Levantan la API como proceso aparte (uvicorn) con una base SQLite en archivo,
recargan los datos demo antes de cada prueba y recorren las pantallas como
lo haría un funcionario. Se omiten si Playwright o el navegador no están
instalados. Navegador: variable SISGEF_E2E_NAVEGADOR (ruta), o Chromium,
Chrome o Brave del sistema, o el Chromium descargado por Playwright.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

from app.reloj import hoy  # noqa: E402
from app.seed import PASSWORD_DEMO, PIN_QF_DEMO, USUARIOS_DEMO  # noqa: E402

pytestmark = pytest.mark.e2e
CARPETA_BACKEND = Path(__file__).resolve().parents[2]


def _ruta_navegador() -> str | None:
    if os.getenv("SISGEF_E2E_NAVEGADOR"):
        return os.getenv("SISGEF_E2E_NAVEGADOR")
    for nombre in ("chromium", "chromium-browser", "google-chrome", "brave-browser", "chrome", "msedge"):
        if ruta := shutil.which(nombre):
            return ruta
    # Windows: Edge viene instalado en Windows 10/11 y Chrome no suele estar en el PATH
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        for relativa in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            if base and Path(base, relativa).exists():
                return str(Path(base, relativa))
    return None  # se intentará con el Chromium descargado por Playwright


@pytest.fixture(scope="module")
def entorno_e2e(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e") / "sisgef_e2e.db"
    return {**os.environ, "SISGEF_ENTORNO": "desarrollo", "SISGEF_DATABASE_URL": f"sqlite:///{base}"}


@pytest.fixture(scope="module")
def servidor(entorno_e2e):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    subprocess.run([sys.executable, "-m", "app.seed", "--reiniciar"], cwd=CARPETA_BACKEND, env=entorno_e2e,
                   check=True, capture_output=True)
    proceso = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", str(puerto), "--log-level", "warning"], cwd=CARPETA_BACKEND, env=entorno_e2e)
    url = f"http://127.0.0.1:{puerto}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{url}/api/salud", timeout=1)  # nosec B310 (URL local fija)
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proceso.terminate()
    proceso.wait(timeout=10)


@pytest.fixture
def datos(entorno_e2e, servidor):
    """Reemplaza el fixture general: recarga los datos demo en la base del servidor E2E."""
    subprocess.run([sys.executable, "-m", "app.seed", "--reiniciar"], cwd=CARPETA_BACKEND, env=entorno_e2e,
                   check=True, capture_output=True)


@pytest.fixture(scope="module")
def navegador():
    with playwright_api.sync_playwright() as p:
        try:
            nav = p.chromium.launch(executable_path=_ruta_navegador(), headless=True)
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"No hay navegador disponible para E2E: {error}")
        yield nav
        nav.close()


@pytest.fixture
def pagina(navegador, servidor, datos):
    contexto = navegador.new_context(viewport={"width": 1280, "height": 860}, color_scheme="light")
    pagina = contexto.new_page()
    errores = []
    pagina.on("pageerror", lambda e: errores.append(str(e)))
    pagina.goto(servidor)
    yield pagina
    contexto.close()
    assert errores == [], f"Errores de JavaScript: {errores}"


def ingresar(pagina, rol):
    pagina.get_by_label("RUT", exact=True).fill(USUARIOS_DEMO[rol][0])
    pagina.get_by_label("Contraseña").fill(PASSWORD_DEMO)
    pagina.get_by_role("button", name="Ingresar").click()
    pagina.get_by_role("navigation").wait_for()


def abrir_receta(pagina, rut, folio):
    pagina.get_by_label("RUT del paciente").fill(rut)
    pagina.get_by_role("button", name="Buscar recetas").click()
    pagina.get_by_role("row", name=folio).get_by_role("button", name="Atender receta").click()


def escanear(pagina, indice, codigo):
    campo = pagina.get_by_label("Escanear lote").nth(indice)
    campo.fill(codigo)
    campo.press("Enter")


def test_e2e01_ingreso_rechaza_rut_con_dv_incorrecto(pagina):
    pagina.get_by_label("RUT", exact=True).fill("12345678-9")
    pagina.get_by_label("Contraseña").fill("cualquiera")
    pagina.get_by_role("button", name="Ingresar").click()
    playwright_api.expect(pagina.get_by_role("alert")).to_contain_text("dígito verificador")
    assert pagina.get_by_role("navigation").count() == 0


def test_e2e02_tecnico_no_ve_menus_fuera_de_su_rol(pagina):
    ingresar(pagina, "TECNICO")
    menu = pagina.get_by_role("navigation").inner_text()
    assert "Dispensar" in menu and "Panel" in menu
    for oculto in ("Libro", "Usuarios", "Entregas", "Auditoría"):
        assert oculto not in menu


def test_e2e03_e2e04_fefo_bloquea_lote_nuevo_y_lote_por_vencer(pagina):
    ingresar(pagina, "TECNICO")
    abrir_receta(pagina, "12345678-5", "RX-1001")
    pagina.get_by_role("button", name="Calcular plan FEFO").first.click()
    playwright_api.expect(pagina.locator(".lote.elegido").first).to_contain_text("L-2502")
    playwright_api.expect(pagina.locator(".lote", has_text="L-2411")).to_contain_text("Retiro obligatorio")
    escanear(pagina, 0, "L-2507")
    playwright_api.expect(pagina.get_by_role("alert")).to_contain_text("Entregue L-2502 del casillero B-03")


def test_e2e05_lote_correcto_registra_entrega_y_rotulo(pagina):
    ingresar(pagina, "TECNICO")
    abrir_receta(pagina, "12345678-5", "RX-1001")
    for boton in pagina.get_by_role("button", name="Calcular plan FEFO").all():
        boton.click()
        pagina.wait_for_timeout(150)
    escanear(pagina, 0, "L-2502")
    escanear(pagina, 1, "M-2509")
    pagina.get_by_role("button", name="Confirmar entrega").click()
    rotulos = pagina.locator(".rotulo")
    playwright_api.expect(rotulos).to_have_count(2)
    playwright_api.expect(rotulos.first).to_contain_text("Lote L-2502")
    playwright_api.expect(rotulos.first).to_contain_text("María González")


def test_e2e06_controlado_exige_pin_y_crea_asiento_integro(pagina):
    ingresar(pagina, "QF")
    abrir_receta(pagina, "9876543-3", "RX-1003")
    pagina.get_by_role("button", name="Calcular plan FEFO").click()
    escanear(pagina, 0, "C-2504")
    pagina.get_by_label("RUT de quien retira").fill("12345678-5")
    pagina.get_by_label("Relación con el paciente").fill("Hija")
    pagina.get_by_label("RUT del Q.F.").fill(USUARIOS_DEMO["QF"][0])
    pagina.get_by_label("PIN de firma del Q.F.").fill("0000")
    pagina.get_by_role("button", name="Confirmar entrega").click()
    playwright_api.expect(pagina.get_by_role("alert")).to_contain_text("PIN del Q.F. incorrectos")
    pagina.get_by_label("PIN de firma del Q.F.").fill(PIN_QF_DEMO)
    pagina.get_by_role("button", name="Confirmar entrega").click()
    playwright_api.expect(pagina.locator(".rotulo")).to_have_count(1)
    pagina.get_by_role("button", name="Libro").click()
    pagina.get_by_role("button", name="Verificar integridad").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Cadena íntegra: 4 asiento")   # 3 recepciones del seed + la salida


def test_e2e07_recepcion_alerta_vencimiento_menor_a_6_meses(pagina):
    ingresar(pagina, "BODEGUERO")
    pagina.get_by_role("button", name="Lotes").click()
    pagina.get_by_role("button", name="Ingresar lote").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Código de lote").fill("L-E2E07")
    dialogo.get_by_label("Fecha de vencimiento").fill((hoy() + timedelta(days=132)).isoformat())
    dialogo.get_by_label("Unidades").fill("100")
    dialogo.get_by_role("button", name="Ingresar").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("menos de 6 meses")


def test_e2e08_acceso_fuera_de_rol_se_deniega_y_queda_en_auditoria(pagina, servidor):
    ingresar(pagina, "TECNICO")
    estado = pagina.evaluate("""async () => (await fetch('/api/usuarios',
        {headers: {Authorization: 'Bearer ' + sessionStorage.getItem('sisgef_token')}})).status""")
    assert estado == 403
    pagina.get_by_role("button", name="Cerrar sesión").click()
    ingresar(pagina, "ADMIN")
    pagina.get_by_role("button", name="Auditoría").click()
    playwright_api.expect(pagina.locator("table")).to_contain_text("ACCESO_DENEGADO")


def test_e2e09_vista_pda_360px_sin_desplazamiento_horizontal(navegador, servidor, datos):
    contexto = navegador.new_context(viewport={"width": 360, "height": 740})
    pagina = contexto.new_page()
    pagina.goto(servidor)
    ingresar(pagina, "TECNICO")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 360
    contexto.close()


def test_e2e10_respeta_tema_oscuro_del_sistema(navegador, servidor, datos):
    contexto = navegador.new_context(color_scheme="dark")
    pagina = contexto.new_page()
    pagina.goto(servidor)
    assert pagina.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(14, 22, 33)"
    contexto.close()


def test_e2e11_baja_logica_de_medicamento_y_reactivacion(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Medicamentos").click()
    fila = pagina.get_by_role("row", name="LOS50")
    fila.get_by_role("button", name="Dar de baja").click()
    pagina.get_by_role("dialog").get_by_label("Motivo").fill("Prueba con stock disponible")
    pagina.get_by_role("dialog").get_by_role("button", name="Dar de baja").click()
    playwright_api.expect(pagina.get_by_role("dialog").get_by_role("alert")).to_contain_text("retírelos a merma")


def test_e2e12_anular_dispensacion_desde_entregas(pagina):
    ingresar(pagina, "QF")
    abrir_receta(pagina, "12345678-5", "RX-1001")
    pagina.get_by_label("Cantidad a entregar (unidades)").nth(1).fill("0")
    pagina.get_by_role("button", name="Calcular plan FEFO").first.click()
    escanear(pagina, 0, "L-2502")
    pagina.get_by_role("button", name="Confirmar entrega").click()
    playwright_api.expect(pagina.locator(".rotulo")).to_have_count(1)
    pagina.get_by_role("button", name="Entregas").click()
    pagina.get_by_role("button", name="Anular").first.click()
    pagina.get_by_role("dialog").get_by_label("Motivo de la anulación").fill("Se entregó al paciente equivocado")
    pagina.get_by_role("dialog").get_by_role("button", name="Anular").click()
    playwright_api.expect(pagina.locator("table")).to_contain_text("Anulada")


def test_e2e13_rut_no_encontrado_permite_registrar_paciente(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_label("RUT del paciente").fill("11222333-9")
    pagina.get_by_role("button", name="Buscar recetas").click()
    playwright_api.expect(pagina.get_by_role("alert")).to_contain_text("No hay un paciente registrado")
    pagina.get_by_role("button", name="Registrar este paciente").click()
    dialogo = pagina.get_by_role("dialog")
    playwright_api.expect(dialogo.get_by_label("RUT")).to_have_value("11222333-9")
    dialogo.get_by_label("Nombre completo").fill("Pedro Rojas")
    dialogo.get_by_label("Tramo FONASA").select_option("C")
    dialogo.get_by_label("Diabetes").check()
    dialogo.get_by_role("button", name="Registrar").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Paciente Pedro Rojas registrado")
    playwright_api.expect(pagina.locator(".tarjeta", has_text="Pedro Rojas")).to_contain_text("Programas: Diabetes")
    playwright_api.expect(pagina.locator("table")).to_contain_text("no tiene recetas")


def test_e2e14_asignar_medicamentos_con_nueva_receta_y_atenderla(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_label("RUT del paciente").fill("14141414-3")
    pagina.get_by_role("button", name="Buscar recetas").click()
    pagina.get_by_role("button", name="Nueva receta").click()
    dialogo = pagina.get_by_role("dialog", name="Nueva receta")
    dialogo.get_by_label("Folio").fill("RX-3001")
    controlado = dialogo.locator("#r-med-0 option", has_text="Clonazepam")
    assert controlado.is_disabled()  # el técnico no puede recetar controlados
    dialogo.locator("#r-med-0").select_option(label="Metformina 850 mg comprimidos")
    dialogo.locator("#r-cant-0").fill("60")
    dialogo.locator("#r-pos-0").fill("1 comprimido cada 12 h")
    dialogo.get_by_role("button", name="+ Agregar otro medicamento").click()
    dialogo.locator("#r-med-1").select_option(label="Losartán 50 mg comprimidos")
    dialogo.locator("#r-cant-1").fill("30")
    dialogo.locator("#r-pos-1").fill("1 comprimido cada 24 h")
    dialogo.get_by_role("button", name="Guardar receta").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Receta RX-3001 registrada con 2 medicamento(s)")
    pagina.get_by_role("row", name="RX-3001").get_by_role("button", name="Atender receta").click()
    playwright_api.expect(pagina.get_by_role("heading", name="Metformina 850 mg comprimidos")).to_be_visible()
    playwright_api.expect(pagina.get_by_role("heading", name="Losartán 50 mg comprimidos")).to_be_visible()


def test_e2e15_codigo_de_barras_del_navegador_coincide_con_el_backend(pagina):
    from app.domain.codigo_barras import codigo_interno, modulos_ean13
    codigos = ["4006381333931", "7801234567894", "0123456789012"] + [codigo_interno(i) for i in (1, 5, 987654)]
    dibujados = pagina.evaluate("(cs) => cs.map((c) => window.CodigoBarras.modulos(c))", codigos)
    assert dibujados == [modulos_ean13(c) for c in codigos]
    assert pagina.evaluate("window.CodigoBarras.modulos('4006381333932')") is None  # dígito verificador malo


def test_e2e16_medicamento_nuevo_muestra_etiqueta_con_codigo_de_barras(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Medicamentos").click()
    fila = pagina.get_by_role("row", name="LOS50")
    playwright_api.expect(fila).to_contain_text("2000000000015")
    pagina.get_by_role("button", name="Nuevo medicamento").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.locator("#d-codigo").fill("PAR500")
    dialogo.get_by_label("Nombre", exact=True).fill("Paracetamol 500 mg comprimidos")
    dialogo.get_by_label("Principio activo").fill("Paracetamol")
    dialogo.get_by_label("Concentración").fill("500 mg")
    dialogo.get_by_label("Código de barras EAN-13").fill("7801234567894")
    dialogo.get_by_label("Unidades por envase").fill("20")
    dialogo.get_by_role("button", name="Crear").click()
    etiqueta = pagina.get_by_role("dialog", name="Etiqueta de Paracetamol 500 mg comprimidos")
    playwright_api.expect(etiqueta.get_by_role("img", name="Código de barras 7801234567894")).to_be_visible()
    playwright_api.expect(etiqueta).to_contain_text("Código del fabricante")
    etiqueta.get_by_role("button", name="Cerrar").click()
    pagina.get_by_label("Buscar medicamento").fill("7801234567894")
    playwright_api.expect(pagina.locator("tbody tr")).to_have_count(1)


def test_e2e17_receta_agrega_medicamento_escaneando_su_codigo(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_label("RUT del paciente").fill("14141414-3")
    pagina.get_by_role("button", name="Buscar recetas").click()
    pagina.get_by_role("button", name="Nueva receta").click()
    dialogo = pagina.get_by_role("dialog", name="Nueva receta")
    escaneo = dialogo.get_by_label("Agregar por código de barras")
    escaneo.fill("2000000000022")   # Metformina
    escaneo.press("Enter")
    playwright_api.expect(dialogo.locator("#r-med-0")).to_have_value(
        dialogo.locator("#r-med-0 option", has_text="Metformina").get_attribute("value"))
    escaneo.fill("2000000000053")   # Clonazepam: controlado, el técnico no puede
    escaneo.press("Enter")
    playwright_api.expect(dialogo.get_by_role("alert")).to_contain_text("solo un Q.F.")
    escaneo.fill("2000000000015")   # Losartán: se agrega una segunda línea
    escaneo.press("Enter")
    playwright_api.expect(dialogo.locator("#r-med-1 option:checked")).to_have_text("Losartán 50 mg comprimidos")


def test_e2e18_selector_de_tema_claro_oscuro_y_sistema(pagina):
    fondo = "() => getComputedStyle(document.body).backgroundColor"
    assert pagina.evaluate(fondo) == "rgb(244, 246, 249)"           # sistema en claro
    pagina.get_by_role("button", name="Tema oscuro").click()        # disponible ya en el ingreso
    assert pagina.evaluate(fondo) == "rgb(14, 22, 33)"
    ingresar(pagina, "TECNICO")
    pagina.reload()                                                 # la elección se recuerda
    pagina.get_by_role("navigation").wait_for()
    assert pagina.evaluate(fondo) == "rgb(14, 22, 33)"
    playwright_api.expect(pagina.get_by_role("button", name="Tema oscuro")).to_have_attribute("aria-pressed", "true")
    pagina.get_by_role("button", name="Tema claro").click()
    assert pagina.evaluate(fondo) == "rgb(244, 246, 249)"
    pagina.get_by_role("button", name="Tema del sistema").click()
    assert pagina.evaluate("document.documentElement.hasAttribute('data-theme')") is False


def test_e2e19_entrega_cronica_exige_confirmar_alergias(pagina):
    ingresar(pagina, "TECNICO")
    abrir_receta(pagina, "16234567-2", "RX-5003")
    pagina.get_by_role("button", name="Calcular plan FEFO").click()
    escanear(pagina, 0, "SE-2607")      # SE-2512 vence en 20 días: FEFO lo salta
    pagina.get_by_role("button", name="Confirmar entrega").click()
    playwright_api.expect(pagina.get_by_role("alert")).to_contain_text("alergias registradas")
    pagina.get_by_label("Revisé las alergias").check()
    pagina.get_by_role("button", name="Confirmar entrega").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Entrega 1 de 6 registrada")
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Próximo retiro")
    playwright_api.expect(pagina.locator(".rotulo")).to_contain_text("Entrega 1 de 6")


def test_e2e20_entrega_siguiente_no_se_atiende_antes_de_tiempo(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_label("RUT del paciente").fill("7654321-6")
    pagina.get_by_role("button", name="Buscar recetas").click()
    fila = pagina.get_by_role("row", name="RX-5001")
    playwright_api.expect(fila).to_contain_text("1 de 6")
    playwright_api.expect(fila).to_contain_text("Se retira desde")
    playwright_api.expect(fila.get_by_role("button", name="Atender receta")).to_be_disabled()


def test_e2e21_retiros_del_dia_abren_la_ficha_del_paciente(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_role("button", name="Retiros").click()
    fila = pagina.get_by_role("row", name="RX-1001")
    playwright_api.expect(fila).to_contain_text("Atrasado 5 d")
    fila.get_by_role("button", name="Atender").click()
    playwright_api.expect(pagina.get_by_role("heading", name="María González")).to_be_visible()
    playwright_api.expect(pagina.get_by_role("row", name="RX-1001").get_by_role("button", name="Atender receta")).to_be_enabled()


def test_e2e22_despacho_a_domicilio_se_marca_entregado(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_role("button", name="Despachos").click()
    en_ruta = pagina.get_by_role("region", name="En ruta")
    playwright_api.expect(en_ruta).to_contain_text("Rosa Fuentes Muñoz")
    playwright_api.expect(en_ruta).to_contain_text("Pasaje Los Aromos 245")
    en_ruta.get_by_role("button", name="Entregado").click()
    pagina.get_by_role("dialog").get_by_label("Nombre de quien recibe").fill("Carmen Fuentes")
    pagina.get_by_role("dialog").get_by_role("button", name="Registrar entrega").click()
    playwright_api.expect(pagina.get_by_role("region", name="Entregados", exact=True)).to_contain_text("Recibió Carmen Fuentes")


def test_e2e23_consulta_publica_sin_iniciar_sesion(pagina, servidor):
    pagina.get_by_role("link", name="Consultar disponibilidad de medicamentos").click()
    playwright_api.expect(pagina.get_by_role("heading", name="Disponibilidad de medicamentos")).to_be_visible()
    tabla = pagina.locator("table")
    playwright_api.expect(tabla).to_contain_text("Losartán 50 mg comprimidos")
    playwright_api.expect(tabla).not_to_contain_text("Clonazepam")
    playwright_api.expect(pagina.get_by_role("row", name="Atorvastatina")).to_contain_text("Pocas unidades")
    pagina.get_by_label("Buscar medicamento").fill("metfor")
    pagina.get_by_role("button", name="Buscar").click()
    playwright_api.expect(pagina.locator("tbody tr")).to_have_count(1)
    assert pagina.get_by_role("navigation").count() == 0   # no se ve nada interno


def test_e2e24_devolucion_desde_entregas(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Entregas").click()
    fila = pagina.get_by_role("row", name="RX-5001")
    playwright_api.expect(fila).to_contain_text("Entrega 1 de 6")
    fila.get_by_role("button", name="Devolver").first.click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Unidades devueltas").fill("5")
    dialogo.get_by_label("Destino").select_option("DESCARTE")
    dialogo.get_by_label("Motivo").fill("Cambio de tratamiento por el médico tratante")
    dialogo.get_by_role("button", name="Registrar devolución").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Devolución registrada: 5 u.")


def test_e2e25_reporte_kardex_se_descarga_en_csv(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Reportes").click()
    with pagina.expect_download() as descarga:
        pagina.get_by_role("button", name="Descargar kardex").click()
    archivo = descarga.value
    assert archivo.suggested_filename.startswith("kardex_") and archivo.suggested_filename.endswith(".csv")
    contenido = open(archivo.path(), encoding="utf-8-sig").read()
    assert contenido.startswith("Fecha;Medicamento;Lote;Tipo;Cantidad;Stock anterior;Stock posterior")


def test_e2e26_medico_receta_pero_no_dispensa(pagina):
    ingresar(pagina, "MEDICO")
    menu = pagina.get_by_role("navigation").inner_text()
    assert "Recetar" in menu and "Dispensar" not in menu and "Retiros" not in menu
    pagina.get_by_label("RUT del paciente").fill("14141414-3")
    pagina.get_by_role("button", name="Buscar recetas").click()
    playwright_api.expect(pagina.get_by_role("button", name="Nueva receta")).to_be_visible()
    playwright_api.expect(pagina.get_by_role("button", name="Atender receta")).to_have_count(0)


# ------------------------------------------------------------------ v0.6: FOFAR y libro
def test_e2e27_pendientes_muestran_el_compromiso_y_el_reclamo_exige_entregar_primero(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_role("button", name="Pendientes").click()
    compromiso = pagina.get_by_role("row", name="Carvedilol")
    playwright_api.expect(compromiso.first).to_contain_text("RX-5006")
    playwright_api.expect(compromiso.first).to_contain_text("h hábiles")
    reclamo = pagina.get_by_role("row", name="OIRS-2026-1184")
    reclamo.get_by_role("button", name="Cerrar con acta").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_role("button", name="Cerrar y emitir acta").click()
    playwright_api.expect(dialogo.get_by_role("alert")).to_contain_text("Primero entregue el medicamento")


def test_e2e28_sin_stock_registra_la_solicitud_sin_duplicar_el_compromiso(pagina):
    ingresar(pagina, "TECNICO")
    pagina.get_by_label("RUT del paciente").fill("8123456-6")
    pagina.get_by_role("button", name="Buscar recetas").click()
    pagina.get_by_role("row", name="RX-5006").get_by_role("button", name="Sin stock").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Ya tenía un compromiso de entrega abierto")


def test_e2e29_toma_de_inventario_a_ciegas_ajusta_el_libro(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Inventario físico").click()
    pagina.get_by_role("button", name="Abrir toma de inventario").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Alcance").select_option(label="CS-01 (CAJA_SEGURIDAD)")
    dialogo.get_by_role("button", name="Abrir toma").click()
    for lote, contado in (("C-2504", "58"), ("C-2510", "100"), ("MF-2608", "60")):
        pagina.get_by_label(f"Unidades contadas del lote {lote}").fill(contado)
        pagina.get_by_role("row", name=lote).get_by_role("button", name="Guardar").click()
        playwright_api.expect(pagina.get_by_role("row", name=lote).get_by_role("button", name="Corregir")).to_be_visible()
    pagina.get_by_role("button", name="Cerrar toma").click()
    pagina.get_by_role("dialog").get_by_role("button", name="Cerrar y aplicar diferencias").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("cerrada")
    pagina.get_by_role("button", name="Libro").click()
    ajuste = pagina.get_by_role("row", name="Toma de inventario")
    playwright_api.expect(ajuste).to_contain_text("Ajuste")
    playwright_api.expect(ajuste).to_contain_text("158")


def test_e2e30_indicadores_fofar_y_rem_a04_j(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Indicadores FOFAR").click()
    tarjeta = pagina.locator(".kpi", has_text="Despacho total y oportuno")
    playwright_api.expect(tarjeta).to_contain_text("50 %")
    playwright_api.expect(tarjeta).to_contain_text("No cumple")
    playwright_api.expect(pagina.get_by_role("row", name="Carvedilol")).to_be_visible()
    with pagina.expect_download() as descarga:
        pagina.get_by_role("button", name="REM A04 sección J").click()
    contenido = open(descarga.value.path(), encoding="utf-8-sig").read()
    assert "Cardiovascular;Carvedilol 25 mg comprimidos;1;0;0;1;0;" in contenido


def test_e2e31_ram_se_notifica_al_isp_y_su_ficha_se_imprime(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Atención farmacéutica").click()
    fila = pagina.get_by_role("row", name="Sospecha de reacción adversa")
    playwright_api.expect(fila).to_contain_text("Por notificar al ISP")
    fila.get_by_role("button", name="Notificar").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Folio del ISP").fill("SVI-2026-55871")
    dialogo.get_by_role("button", name="Registrar notificación").click()
    playwright_api.expect(fila).to_contain_text("ISP SVI-2026-55871")
    fila.get_by_role("button", name="Ficha").click()
    playwright_api.expect(pagina.get_by_role("dialog")).to_contain_text("Patricia Soto Lagos")
    playwright_api.expect(pagina.get_by_role("dialog")).to_contain_text("SVI-2026-55871")


def test_e2e32_bodega_registra_la_devolucion_de_un_prestamo(pagina):
    ingresar(pagina, "BODEGUERO")
    pagina.get_by_role("button", name="Préstamos").click()
    fila = pagina.get_by_role("row", name="CESFAM Los Volcanes")
    fila.get_by_role("button", name="Registrar devolución").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Código de lote").fill("PV-2702")
    dialogo.get_by_label("Vencimiento del lote").fill((hoy() + timedelta(days=400)).isoformat())
    dialogo.get_by_role("button", name="Registrar devolución").click()
    playwright_api.expect(fila).to_contain_text("Devuelto")


def test_e2e33_receta_de_controlado_pide_los_datos_del_libro_y_la_receta_cheque(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_label("RUT del paciente").fill("14141414-3")
    pagina.get_by_role("button", name="Buscar recetas").click()
    pagina.get_by_role("button", name="Nueva receta").click()
    dialogo = pagina.get_by_role("dialog")
    dialogo.get_by_label("Medicamento", exact=True).select_option(label="Metilfenidato 10 mg comprimidos (controlado)")
    playwright_api.expect(dialogo.get_by_label("Médico prescriptor")).to_be_visible()
    playwright_api.expect(dialogo.get_by_label("N.º de receta cheque")).to_be_visible()
    dialogo.get_by_label("Folio").fill("RX-7101")
    dialogo.get_by_label("Cantidad").fill("30")
    dialogo.get_by_label("Posología").fill("1 comprimido en la mañana")
    dialogo.get_by_label("Médico prescriptor").fill("Dr. Andrés Molina Soto")
    dialogo.get_by_label("RUT del prescriptor").fill("10203040-0")
    dialogo.get_by_label("Domicilio del paciente").fill("Av. Los Carrera 1550, depto. 32")
    dialogo.get_by_label("N.º de receta cheque").fill("RC-889123")
    dialogo.get_by_role("button", name="Guardar receta").click()
    playwright_api.expect(pagina.get_by_role("status")).to_contain_text("Receta RX-7101 registrada")


def test_e2e34_panel_e_indicadores_muestran_graficos_con_tabla_accesible(pagina):
    ingresar(pagina, "QF")
    pagina.get_by_role("button", name="Panel").click()
    grafico = pagina.get_by_role("img", name="Entregas por día")
    playwright_api.expect(grafico).to_be_visible()
    grafico.focus()
    pagina.keyboard.press("ArrowRight")                       # el teclado recorre los valores como el mouse
    playwright_api.expect(pagina.locator(".grafico-tooltip")).to_contain_text("entrega")
    pagina.get_by_text("Ver los datos en una tabla").first.click()
    playwright_api.expect(pagina.locator(".grafico-tabla table").first).to_be_visible()
    pagina.get_by_role("button", name="Indicadores FOFAR").click()
    playwright_api.expect(pagina.locator("figure.grafico")).to_have_count(3)
    playwright_api.expect(pagina.get_by_role("img", name="1 · Despacho total y oportuno, por mes")).to_be_visible()
