"""Configuración común de pruebas: datos demo frescos por prueba.

Por defecto usa SQLite en memoria. Para probar contra PostgreSQL:
    SISGEF_PRUEBAS_DATABASE_URL=postgresql+psycopg://sisgef:sisgef_local@localhost:5432/sisgef pytest
"""

import os

os.environ.update({
    "SISGEF_ENTORNO": "pruebas",
    "SISGEF_DATABASE_URL": os.getenv("SISGEF_PRUEBAS_DATABASE_URL", "sqlite:///:memory:"),
    "SISGEF_JWT_SECRETO": "secreto-de-pruebas-con-largo-suficiente-para-hs256",
    "SISGEF_HMAC_SECRETO": "hmac-de-pruebas-con-largo-suficiente-para-sha256",
    "SISGEF_PBKDF2_ITERACIONES": "1000",  # rápido en pruebas; producción usa 600.000
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SesionLocal, motor  # noqa: E402
from app.main import app  # noqa: E402
from app.models import borrar_esquema  # noqa: E402
from app.reloj import hoy  # noqa: E402
from app.seed import PASSWORD_DEMO, PIN_QF_DEMO, USUARIOS_DEMO, poblar  # noqa: E402


@pytest.fixture
def datos():
    borrar_esquema(motor)
    Base.metadata.create_all(motor)
    with SesionLocal() as db:
        resultado = poblar(db, hoy())
        db.commit()
        ids = {
            "recetas": {folio: r.id_receta for folio, r in resultado["recetas"].items()},
            "detalles": {folio: [d.id_detalle_receta for d in r.detalles] for folio, r in resultado["recetas"].items()},
            "medicamentos": {c: med.id_medicamento for c, med in resultado["medicamentos"].items()},
            "ubicaciones": {c: u.id_ubicacion for c, u in resultado["ubicaciones"].items()},
            "usuarios": {rol: u.id_usuario for rol, u in resultado["usuarios"].items()},
        }
    return ids


@pytest.fixture
def cliente(datos):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def cabeceras(cliente):
    cache = {}

    def _obtener(rol: str) -> dict:
        if rol not in cache:
            r = cliente.post("/api/auth/login", json={"rut": USUARIOS_DEMO[rol][0], "password": PASSWORD_DEMO})
            assert r.status_code == 200, r.text
            cache[rol] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[rol]
    return _obtener


@pytest.fixture
def db():
    with SesionLocal() as sesion:
        yield sesion


FIRMA_QF = {"rut": USUARIOS_DEMO["QF"][0], "pin": PIN_QF_DEMO}
