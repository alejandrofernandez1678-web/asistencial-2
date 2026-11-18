"""Integración: autenticación, autorización (RBAC) y cabeceras de seguridad."""

from sqlalchemy import select

from app.models import EventosPendientes
from app.seed import PASSWORD_DEMO, USUARIOS_DEMO

RUT_TECNICO = USUARIOS_DEMO["TECNICO"][0]


def test_it01_login_correcto_entrega_token_y_rol(cliente):
    r = cliente.post("/api/auth/login", json={"rut": RUT_TECNICO, "password": PASSWORD_DEMO})
    assert r.status_code == 200
    assert r.json()["usuario"]["rol"] == "TECNICO"


def test_it02_login_fallido_usa_mensaje_generico(cliente):
    mal_password = cliente.post("/api/auth/login", json={"rut": RUT_TECNICO, "password": "incorrecta"})
    no_existe = cliente.post("/api/auth/login", json={"rut": "22222222-2", "password": "incorrecta"})
    rut_invalido = cliente.post("/api/auth/login", json={"rut": "12345678-9", "password": "x"})
    assert mal_password.status_code == no_existe.status_code == rut_invalido.status_code == 401
    assert mal_password.json()["detail"] == no_existe.json()["detail"]  # no revela si el RUT existe


def test_it03_cuenta_se_bloquea_tras_5_intentos(cliente):
    for _ in range(5):
        cliente.post("/api/auth/login", json={"rut": RUT_TECNICO, "password": "incorrecta"})
    r = cliente.post("/api/auth/login", json={"rut": RUT_TECNICO, "password": PASSWORD_DEMO})
    assert r.status_code == 423  # bloqueada aunque ahora la contraseña sea correcta


def test_it04_sin_token_o_token_falso_se_rechaza(cliente):
    assert cliente.get("/api/stock").status_code == 401
    assert cliente.get("/api/stock", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401


def test_it05_acceso_fuera_de_rol_se_deniega_y_audita(cliente, cabeceras, db):
    assert cliente.get("/api/controlados/libro", headers=cabeceras("TECNICO")).status_code == 403
    assert cliente.get("/api/usuarios", headers=cabeceras("QF")).status_code == 403
    assert cliente.post("/api/pacientes/buscar", json={"rut": "12345678-5"},
                        headers=cabeceras("BODEGUERO")).status_code == 403
    eventos = db.scalars(select(EventosPendientes).where(EventosPendientes.tipo_evento == "ACCESO_DENEGADO")).all()
    assert len(eventos) == 3 and eventos[0].payload["ruta"] == "/api/controlados/libro"


def test_it06_usuario_dado_de_baja_pierde_acceso_inmediato(cliente, cabeceras, datos):
    token_tecnico = cabeceras("TECNICO")
    assert cliente.get("/api/stock", headers=token_tecnico).status_code == 200
    r = cliente.post(f"/api/usuarios/{datos['usuarios']['TECNICO']}/baja",
                     json={"motivo": "Término de contrato del funcionario"}, headers=cabeceras("ADMIN"))
    assert r.status_code == 200 and r.json()["activo"] is False
    assert cliente.get("/api/stock", headers=token_tecnico).status_code == 401  # su token ya no sirve


def test_it07_entrada_con_campos_extra_o_fuera_de_rango_se_rechaza(cliente, cabeceras):
    r = cliente.post("/api/auth/login", json={"rut": RUT_TECNICO, "password": "x", "rol": "ADMIN"})
    assert r.status_code == 422
    r = cliente.get("/api/dispensaciones/plan?id_detalle_receta=1&cantidad=-1", headers=cabeceras("TECNICO"))
    assert r.status_code == 422


def test_it08_cabeceras_de_seguridad_presentes(cliente):
    r = cliente.get("/api/salud")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_it09_admin_crea_usuarios_con_reglas(cliente, cabeceras):
    admin = cabeceras("ADMIN")
    base = {"rut": "13131313-6", "nombre": "Nueva Q.F.", "rol": "QF", "password": "Clave-Muy-Segura-1"}
    assert cliente.post("/api/usuarios", json=base, headers=admin).json()["codigo"] == "PIN_REQUERIDO"
    assert cliente.post("/api/usuarios", json={**base, "password": "corta"}, headers=admin).status_code == 422
    r = cliente.post("/api/usuarios", json={**base, "pin": "2468"}, headers=admin)
    assert r.status_code == 201 and r.json()["rol"] == "QF"
