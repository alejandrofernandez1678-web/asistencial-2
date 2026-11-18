# Guía de instalación en Windows 10 – SISGEF-Asistencial

Esta guía deja el proyecto funcionando en un computador nuevo con **Windows 10 de 64 bits**
(también sirve para Windows 11). Parte de cero: no supone nada instalado.

| | |
|---|---|
| **Tiempo estimado** | 30 a 45 minutos (la mayor parte es descarga) |
| **Requisitos** | Windows 10 de 64 bits, 4 GB de RAM, 2 GB libres en disco, internet |
| **Acceso** | Una cuenta de GitHub con acceso al repositorio (el repositorio es privado) |
| **Resultado** | La aplicación corriendo en `http://127.0.0.1:8000` y las pruebas pasando |

Los pasos 1 a 7 son **obligatorios**. Los pasos 8 y 9 son **opcionales**: PostgreSQL y la
regeneración de diagramas e informe.

> **Dónde escribir los comandos.** Todos los comandos se escriben en **PowerShell**: menú
> Inicio → escribir `PowerShell` → *Windows PowerShell*. **No hace falta abrirlo como
> administrador**, salvo donde se indica. Copie cada bloque completo y presione Enter.

---

## 1. Instalar Git

1. Descargue el instalador desde <https://git-scm.com/download/win> (versión *64-bit Git for Windows Setup*).
2. Ejecútelo y deje **todas las opciones por defecto**. El instalador incluye *Git Credential Manager*,
   que permite iniciar sesión en GitHub desde el navegador **sin crear tokens**.
3. Cierre PowerShell si lo tenía abierto, ábralo de nuevo y verifique:

```powershell
git --version
```

Debe mostrar algo como `git version 2.x`.

Configure su nombre y correo (aparecen en los commits):

```powershell
git config --global user.name "Su Nombre"
git config --global user.email "su_correo@ejemplo.cl"
```

---

## 2. Instalar Python 3.12 o 3.13

> Use **Python 3.12 o 3.13**. Con ellas se verificó que todas las dependencias tienen
> paquetes precompilados para Windows, así que no hace falta instalar compiladores.

1. Descargue el instalador **Windows installer (64-bit)** de Python 3.13 desde
   <https://www.python.org/downloads/windows/>.
2. En la **primera pantalla** del instalador marque **"Add python.exe to PATH"** (abajo).
   Este paso es importante.
3. Presione **Install Now**.
4. Al final, si aparece **"Disable path length limit"**, haga clic en esa opción.
5. Cierre y vuelva a abrir PowerShell, y verifique:

```powershell
py --version
python --version
```

Ambos deben mostrar `Python 3.13.x` (o 3.12.x).

> Si `python` abre la **Microsoft Store**, desactive el alias: Configuración → Aplicaciones →
> *Alias de ejecución de aplicaciones* → apague **python.exe** y **python3.exe**.

---

## 3. Descargar el proyecto (clonar el repositorio)

Elija una carpeta de trabajo, por ejemplo *Documentos*, y clone la rama de trabajo:

```powershell
cd $HOME\Documents
git clone -b trabajo-con-claude https://github.com/alejandrofernandez1678-web/Proyecto-farmacia-asistencial.git
cd Proyecto-farmacia-asistencial
```

- La **primera vez** se abrirá una ventana para iniciar sesión en GitHub. Elija
  **"Sign in with your browser"**, autorice y listo: Windows recuerda la sesión.
- Si GitHub responde *"Repository not found"* o *403*, su cuenta no tiene acceso. El dueño
  del repositorio debe invitarla en **Settings → Collaborators → Add people** y usted debe
  **aceptar la invitación** (llega por correo).

Para ver las versiones guardadas:

```powershell
git tag
```

Verá `v0.3.0-avance` (código del avance) y `v0.3.1-informe-base` (informe base y diagramas).

---

## 4. Crear el entorno virtual e instalar dependencias

El entorno virtual (`.venv`) aísla las librerías del proyecto del resto de Windows.

```powershell
cd backend
py -3.13 -m venv .venv
```

> Si instaló Python 3.12, use `py -3.12 -m venv .venv`.

**Active el entorno.** Debe hacerlo cada vez que abra una PowerShell nueva para trabajar:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si funciona, la línea de comandos empieza con `(.venv)`.

> **Error "la ejecución de scripts está deshabilitada en este sistema".** Ejecute una sola vez
> lo siguiente y responda `S` (Sí); después vuelva a activar:
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
>
> Otra opción es usar **Símbolo del sistema (cmd)** y activar con `.venv\Scripts\activate.bat`.

Con el entorno activo, instale las dependencias (tarda unos minutos):

```powershell
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

---

## 5. Configurar las variables de entorno (archivo `.env`)

El archivo `.env` guarda la configuración y los secretos. **Nunca se sube a GitHub**, porque
está en `.gitignore`. Por eso cada computador necesita el suyo.

```powershell
Copy-Item .env.ejemplo .env
```

Genere **dos** secretos distintos. Ejecute este comando **dos veces** y copie cada resultado:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Abra el archivo:

```powershell
notepad .env
```

y reemplace estas dos líneas con los secretos generados (uno distinto en cada una):

```
SISGEF_JWT_SECRETO=pegue-aqui-el-primer-secreto
SISGEF_HMAC_SECRETO=pegue-aqui-el-segundo-secreto
```

Guarde con **Ctrl + S** y cierre el Bloc de notas. El resto de los valores sirven tal como vienen:
la base de datos por defecto es SQLite y no necesita instalación.

---

## 6. Cargar datos de demostración y levantar el sistema

Con el entorno activo y dentro de la carpeta `backend`:

```powershell
python -m app.seed --reiniciar
uvicorn app.main:app --reload
```

Cuando aparezca `Application startup complete`, abra en el navegador:

- **Aplicación:** <http://127.0.0.1:8000>
- **Documentación de la API:** <http://127.0.0.1:8000/docs>

> Si Windows muestra una alerta del **Firewall**, puede presionar *Cancelar*: el servidor solo
> escucha en su propio computador (`127.0.0.1`) y no necesita acceso a la red.

**Usuarios de demostración.** La contraseña de todos es `Farmacia2026!` y el PIN de firma del Q.F. es `4321`.

| Rol | RUT |
|---|---|
| Químico farmacéutico | `15555555-6` |
| Técnico de farmacia | `17777777-3` |
| Bodeguero | `18888888-7` |
| Administrador | `11111111-1` |

**Pacientes de prueba:**
- `12345678-5`: receta vigente.
- `9876543-3`: una receta vencida y una receta de controlado.
- `14141414-3`: receta vigente.

Para **detener** el servidor presione **Ctrl + C** en la PowerShell.

---

## 7. Ejecutar las pruebas

Abra **otra** PowerShell para no detener el servidor, active el entorno y ejecute:

```powershell
cd $HOME\Documents\Proyecto-farmacia-asistencial\backend
.\.venv\Scripts\Activate.ps1

pytest -m "not e2e"          # unitarias + integración (rápidas, sin navegador)
pytest --cov                 # todas, incluidas las E2E, con cobertura
bandit -c pyproject.toml -r app
```

Resultado esperado: **116 pruebas aprobadas y 1 omitida**. La omitida es la de concurrencia,
que solo corre sobre PostgreSQL (paso 8).

> **Pruebas E2E.** Usan **Microsoft Edge**, que ya viene en Windows 10, o Chrome si está
> instalado. Si aparecen como *skipped* (omitidas), instale el navegador de Playwright:
>
> ```powershell
> playwright install chromium
> ```

---

## 8. (Opcional) Usar PostgreSQL 16

SQLite basta para desarrollar. PostgreSQL es el motor de producción y es necesario para la
prueba de concurrencia. Elija **una** de estas dos opciones.

### Opción A: instalador de PostgreSQL (recomendada en Windows 10)

1. Descargue **PostgreSQL 16** para Windows desde <https://www.postgresql.org/download/windows/>
   (instalador de EDB).
2. Instale con las opciones por defecto. Anote la contraseña que elija para el usuario
   `postgres` y deje el puerto **5432**. En *Stack Builder* puede presionar *Cancelar*.
3. Abra **SQL Shell (psql)** desde el menú Inicio. Presione Enter en todo y escriba la
   contraseña de `postgres`. Luego ejecute:

```sql
CREATE USER sisgef WITH PASSWORD 'sisgef_local';
CREATE DATABASE sisgef OWNER sisgef;
\q
```

### Opción B: contenedor (Docker Desktop o Podman Desktop)

Requiere Windows 10 versión 2004 o superior con WSL 2. Instale **Docker Desktop**
(<https://www.docker.com/products/docker-desktop/>) y, desde la raíz del proyecto, ejecute:

```powershell
cd $HOME\Documents\Proyecto-farmacia-asistencial
docker compose up -d
```

### Conectar el sistema a PostgreSQL

En `backend\.env` cambie la línea de la base de datos:

```
SISGEF_DATABASE_URL=postgresql+psycopg://sisgef:sisgef_local@localhost:5432/sisgef
```

y vuelva a cargar los datos:

```powershell
python -m app.seed --reiniciar
```

Para ejecutar las pruebas sobre PostgreSQL, incluida la de concurrencia:

```powershell
$env:SISGEF_PRUEBAS_DATABASE_URL = "postgresql+psycopg://sisgef:sisgef_local@localhost:5432/sisgef"
pytest tests/unit tests/integration
Remove-Item Env:SISGEF_PRUEBAS_DATABASE_URL
```

Resultado esperado: **106 pruebas aprobadas**.

> Las pruebas **borran y recrean** las tablas de esa base. Úselas solo con la base de
> desarrollo, nunca con datos que quiera conservar.

---

## 9. (Opcional) Regenerar diagramas e informe

Solo lo necesita quien edite los diagramas PlantUML o el informe.

**Instalaciones:**
- Java 21: <https://adoptium.net> (Temurin). Marque *"Set JAVA_HOME"* y *"Add to PATH"*.
- Graphviz: <https://graphviz.org/download/>. Marque *"Add Graphviz to the system PATH"*.
- LibreOffice, solo para exportar el PDF: <https://es.libreoffice.org/descarga/>.

**Diagramas** (desde la raíz del proyecto):

```powershell
cd $HOME\Documents\Proyecto-farmacia-asistencial\docs\diagramas
New-Item -ItemType Directory -Force herramientas, png | Out-Null
Invoke-WebRequest -OutFile herramientas\plantuml.jar `
  https://github.com/plantuml/plantuml/releases/download/v1.2025.4/plantuml-1.2025.4.jar
java -Djava.awt.headless=true -jar herramientas\plantuml.jar -charset UTF-8 -tpng -o png *.puml
```

> Sin Graphviz, ejecute antes `$env:SISGEF_SMETANA = "1"` para usar el motor interno de PlantUML.

**Informe** (con el entorno virtual del backend activo, desde la raíz del proyecto):

```powershell
cd $HOME\Documents\Proyecto-farmacia-asistencial
python docs\informe\construir_informe.py
& "C:\Program Files\LibreOffice\program\python.exe" docs\informe\exportar_pdf.py
```

El primer comando genera `Proyecto_Integrado_Informe_3_base.docx` y el segundo el PDF con el
índice actualizado. **No edite el `.docx` a mano**: los cambios se hacen en el script o en los
`.puml` y luego se regenera.

---

## Trabajo diario

Cada vez que vaya a trabajar:

```powershell
cd $HOME\Documents\Proyecto-farmacia-asistencial
git pull                                 # traer los cambios del compañero
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt      # solo si cambiaron las dependencias
uvicorn app.main:app --reload
```

Para guardar y compartir su trabajo:

```powershell
git add -A
git commit -m "Descripción breve del cambio"
git push
```

---

## Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `py` o `python` no se reconoce | Python no quedó en el PATH | Reinstale Python marcando **"Add python.exe to PATH"** y abra una PowerShell nueva |
| `python` abre la Microsoft Store | Alias de Windows | Desactive los alias (ver paso 2) |
| `Activate.ps1 no se puede cargar… deshabilitada` | Política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `pip` intenta compilar algo y falla (*Microsoft Visual C++ … is required*) | Versión de Python sin paquetes precompilados | Use Python **3.12 o 3.13** y recree el entorno (`Remove-Item -Recurse .venv` y repita el paso 4) |
| `No module named app` | Comando ejecutado fuera de `backend` | `cd backend` antes de `python -m app.seed` o `uvicorn` |
| `[Errno 10048]` o *address already in use* | El puerto 8000 está ocupado | `uvicorn app.main:app --reload --port 8001` y abra `http://127.0.0.1:8001` |
| Al entrar dice *"Sesión inválida o expirada"* | Se recargaron los datos o pasaron 30 minutos | Presione *Cerrar sesión* e ingrese de nuevo |
| *"RUT o contraseña incorrectos"* con los usuarios demo | No se cargaron los datos | `python -m app.seed --reiniciar` |
| La cuenta queda *bloqueada temporalmente* | 5 intentos fallidos seguidos | Espere 15 minutos o recargue los datos con el seed |
| Las pruebas E2E aparecen *skipped* | Playwright no encontró un navegador | `playwright install chromium` |
| `git push` pide usuario y contraseña | Sin sesión de GitHub en Windows | Cancele y vuelva a intentar: elija *Sign in with your browser*. No use la contraseña de la cuenta: si se la pide en texto, use un token |
| `connection refused` con PostgreSQL | El servicio no está iniciado | Opción A: *Servicios de Windows* → `postgresql-x64-16` → Iniciar. Opción B: abra Docker Desktop y `docker compose up -d` |
