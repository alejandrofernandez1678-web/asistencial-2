# SISGEF-Asistencial

Sistema web de gestión para la farmacia asistencial de un CESFAM: dispensación con
**FEFO** (primero en vencer, primero en salir), **unidosis** con rótulo, **libro digital
de medicamentos controlados** encadenado por hash, control de vencimientos y mermas,
y control de acceso por rol.

> Estado: **avance de implementación (v0.3.0, Sprint 3)**. Qué está hecho, qué falta y
> cómo se abordó la retroalimentación del Informe 2 en [`docs/AVANCE.md`](docs/AVANCE.md).

## Estructura del repositorio

La estructura sigue el diagrama de paquetes del informe (regla de capas: `domain` no
depende de nada; `api` → `services` → `repositories`/`domain`).

```
backend/
  app/
    domain/         Reglas de negocio puras (RUT, estados de lote, FEFO, recetas, libro con hash)
    services/       Casos de uso: dispensar, anular, ingresar/ajustar/anular lotes, mermas, bajas
    repositories/   Consultas SQLAlchemy reutilizables (consulta FEFO con FOR UPDATE)
    security/       Hash PBKDF2, JWT, matriz RBAC
    api/            Routers FastAPI y validación de entrada (Pydantic)
    models.py       Modelo de datos (MER corregido: control, baja lógica, kardex)
    seed.py         Datos de demostración
  tests/
    unit/           Reglas de dominio y seguridad (sin base de datos)
    integration/    API completa contra SQLite o PostgreSQL
    e2e/            Interfaz real con Playwright
frontend/           Interfaz web (React 18 + htm, sin paso de compilación)
compose.yaml        PostgreSQL 16 local
docs/AVANCE.md      Informe de avance para revisión
```

## Configuración del entorno paso a paso

Probado en Fedora Linux con Python 3.15. Requiere Python 3.12 o superior.

> **¿Windows 10 u 11?** Siga la guía [`docs/INSTALACION_WINDOWS.md`](docs/INSTALACION_WINDOWS.md).

### 1. Requisitos del sistema

```bash
python3 --version          # 3.12 o superior
sudo dnf install -y python3-pip git           # Fedora (en Ubuntu: sudo apt install python3-venv python3-pip git)
# Opcional, para usar PostgreSQL en lugar de SQLite:
sudo dnf install -y podman podman-compose
```

### 2. Obtener el código y crear el entorno virtual

```bash
git clone <url-del-repositorio> Proyecto_Integrado
cd Proyecto_Integrado/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.ejemplo .env
# Generar dos secretos distintos y pegarlos en SISGEF_JWT_SECRETO y SISGEF_HMAC_SECRETO:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` está en `.gitignore`: los secretos nunca se suben al repositorio.

| Variable | Uso | Valor por defecto |
|---|---|---|
| `SISGEF_ENTORNO` | `desarrollo`, `pruebas` o `produccion` | `desarrollo` |
| `SISGEF_DATABASE_URL` | Conexión a la base de datos | `sqlite:///./sisgef.db` |
| `SISGEF_JWT_SECRETO` | Firma de los tokens de sesión | obligatorio en producción |
| `SISGEF_HMAC_SECRETO` | Huella del RUT para búsquedas | obligatorio en producción |
| `SISGEF_JWT_MINUTOS` | Duración de la sesión | `30` |
| `SISGEF_PBKDF2_ITERACIONES` | Costo del hash de contraseñas | `600000` |

### 4. (Opcional) Usar PostgreSQL 16

```bash
cd ..                       # raíz del repositorio
podman compose up -d        # o: docker compose up -d
# En backend/.env:
# SISGEF_DATABASE_URL=postgresql+psycopg://sisgef:sisgef_local@localhost:5432/sisgef
cd backend
```

### 5. Cargar datos de demostración y levantar el sistema

```bash
python -m app.seed --reiniciar
uvicorn app.main:app --reload
```

- Aplicación: <http://127.0.0.1:8000>
- Documentación interactiva de la API (solo en desarrollo): <http://127.0.0.1:8000/docs>
- Consulta pública de disponibilidad (sin iniciar sesión): <http://127.0.0.1:8000/#/disponibilidad>

Usuarios de demostración (contraseña `Farmacia2026!`, PIN de firma del Q.F. `4321`):

| Rol | RUT | Puede |
|---|---|---|
| Q.F. | 15555555-6 | Todo lo clínico: dispensar, firmar controlados, anular, libro, lotes, cerrar tomas de inventario, atención farmacéutica e indicadores FOFAR |
| TENS de farmacia | 17777777-3 | Panel, dispensación, registro de pacientes y recetas, compromisos y reclamos, conteo de inventario |
| Bodeguero | 18888888-7 | Ingreso, ajuste y merma de lotes, conteo de inventario, préstamos con otros establecimientos |
| Médico | 13579246-2 | Emitir recetas (no dispensa) |
| Administrador | 11111111-1 | Usuarios, catálogo de medicamentos y auditoría |

Pacientes de prueba (todos ficticios):

| RUT | Paciente | Para probar |
|---|---|---|
| `12345678-5` | María González | Receta aguda vigente |
| `9876543-3` | Juan Pérez | Receta vencida y receta retenida de controlado |
| `14141414-3` | Ana Torres | Receta aguda vigente |
| `7654321-6` | Rosa Fuentes | Postrada, con apoderada; crónica en entrega 1 de 6 y despacho en ruta |
| `8123456-6` | Luis Herrera | PRAIS; crónica de 3 entregas con retiro atrasado; RX-5006 con quiebre de carvedilol (compromiso de 24 h hábiles y reclamo OIRS abierto) |
| `16234567-2` | Patricia Soto | Alergias registradas; crónica de salud mental; sospecha de RAM por notificar al ISP |
| `10987654-2` | Jorge Contreras | Crónica con insulina (refrigerador) y levotiroxina |
| `19876543-0` | Elena Rivas | PRAIS con alergia; receta aguda |

El seed también trae costo y factura en cada lote (inventario valorizado), las recepciones de controlados
en el libro, metilfenidato (exige receta cheque), 3 actividades farmacéuticas sobre 40 programadas y un
préstamo de paracetamol otorgado a otro CESFAM. Detalle de la v0.6 en [`docs/PROPUESTA_v0.6.md`](docs/PROPUESTA_v0.6.md).

#### Base con volumen: un CESFAM con seis meses de historia

```bash
python -m app.seed --reiniciar --volumen 150
```

Agrega 150 pacientes ficticios (RUT válidos inventados, con semilla fija) y recorre los últimos seis
meses con los mismos servicios de la aplicación y el reloj simulado (`reloj.simular`): recetas crónicas
del PSCV, hipotiroidismo, salud mental y respiratorio con sus retiros mensuales, atrasos y renovaciones;
recetas agudas; recetas retenidas de clonazepam con firma del Q.F.; despachos a domicilio de postrados;
una alerta sanitaria que deja una semana sin atorvastatina (faltantes, reclamos y actas); merma por
vencimiento; una toma de inventario; préstamos y actividades farmacéuticas semanales. Así el kardex,
el libro, Retiros y los indicadores FOFAR tienen datos reales para mostrar. Los datos de la tabla
anterior se mantienen iguales. Tarda unos 20 segundos; con otro número se generan más o menos pacientes.

### Migraciones de la base de datos (Alembic)

El esquema se versiona con Alembic (`backend/migraciones/versions`). En desarrollo, el
servidor aplica las migraciones pendientes al arrancar; una base SQLite se respalda antes
como `sisgef.db.respaldo-<versión>`. A mano, desde `backend`:

```bash
alembic upgrade head        # llevar la base a la última versión
alembic current             # ver la versión actual
alembic downgrade -1        # volver una versión atrás
```

Para PostgreSQL, definir `SISGEF_DATABASE_URL` antes de ejecutar los comandos. Un cambio
de modelo se acompaña de una revisión nueva: `alembic revision --autogenerate -m "..."`,
revisada a mano (Alembic no detecta restricciones `CHECK` ni triggers).

### 6. Ejecutar las pruebas

```bash
pytest                                  # unitarias + integración + E2E (SQLite)
pytest --cov                            # con cobertura
pytest -m "not e2e"                     # sin navegador
bandit -c pyproject.toml -r app         # análisis estático de seguridad

# Contra PostgreSQL (incluye la prueba de concurrencia):
SISGEF_PRUEBAS_DATABASE_URL=postgresql+psycopg://sisgef:sisgef_local@localhost:5432/sisgef pytest tests/unit tests/integration

# Las E2E usan Chromium, Chrome o Brave del sistema; si no hay ninguno:
playwright install chromium
```

## Decisiones técnicas de este avance

- **Frontend sin compilación**: React 18 y htm se sirven desde `frontend/vendor/`, sin CDN.
  Esto permite que la política CSP sea `script-src 'self'` y que funcione sin internet.
  La migración a Vite + TypeScript (Informe 2) queda para cuando el equipo instale Node.js;
  los componentes no cambian.
- **Autenticación local con JWT** para desarrollo. En AWS se reemplaza por Amazon Cognito
  con MFA (ADR del Informe 2). La matriz RBAC y la validación del lado servidor no cambian.
- **Auditoría con outbox**: los eventos se guardan en `eventos_pendientes` en la misma
  transacción. El publicador hacia DynamoDB es trabajo del siguiente sprint.

## Informe y diagramas

```bash
cd docs/diagramas && ./renderizar.sh            # PlantUML → PNG (Java + Graphviz)
cd ../.. && python docs/informe/construir_informe.py   # genera Proyecto_Integrado_Informe_3_base.docx
python3 docs/informe/exportar_pdf.py            # PDF con índice actualizado (LibreOffice)
```
