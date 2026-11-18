# Plan v0.5 – Diagnóstico y migración hacia el esquema CESFAM completo

**Estado:** plan aprobado (D1-D6 según las recomendaciones). **Pasos A, B y C implementados** el 17/11/2026. Pendiente: verificación contra PostgreSQL.
**Base:** código v0.4 (17/11/2026): FEFO, unidosis, libro de controlados, registro de pacientes y recetas, código de barras EAN-13.
**Objetivo:** recetas crónicas fraccionadas, apoderados, despacho a domicilio para postrados, catálogo farmacéutico completo, consulta pública de disponibilidad y reportes, **sin perder datos ni romper lo que ya funciona**.

---

## 1. Diagnóstico

### 1.1 Lo que ya está cubierto (y no hay que rehacer)

| Requisito del esquema objetivo | Cómo está hoy | Dónde |
|---|---|---|
| RUT con dígito verificador | Validación módulo 11 en servidor y en la interfaz; el RUT del paciente se guarda como HMAC + versión enmascarada (Ley 19.628) | `domain/rut.py`, `security/claves.py` |
| Stock por lote, no como número editable | El medicamento no tiene stock; el stock vive en cada lote | `models.Lotes` |
| Lote con número, vencimiento, cantidad inicial y actual, estado | `codigo_lote`, `fecha_vencimiento`, `unidades_ingresadas`, `unidades_disp`, `estado` (+ ubicación física) | `models.Lotes` |
| FEFO con reparto en varios lotes | El planificador reparte la cantidad entre lotes dispensables, del que vence primero al último; además bloquea lotes a ≤ 30 días | `domain/fefo.py` |
| Verificación física del lote | El técnico escanea el lote; si no coincide con el plan FEFO, se bloquea | `services/dispensacion.py` |
| Entregas parciales | `detalles_receta.cant_entregada` y estados PENDIENTE / PARCIAL / DISPENSADA / ANULADA | `models.DetallesReceta` |
| Dispensación ligada al lote exacto | `detalles_dispensacion.id_lote` | `models.DetallesDispensacion` |
| Control de psicotrópicos | Receta retenida, RUT y relación de quien retira, firma del Q.F. con PIN, libro encadenado por hash e inmutable | `services/dispensacion.py`, `domain/libro.py` |
| Kardex append-only | `movimientos_stock` con triggers que rechazan UPDATE/DELETE; errores se corrigen con movimiento inverso (anulación, ajuste) | `models.MovimientosStock` |
| Un solo punto para mover stock | `services/inventario.mover_stock` | |
| Mermas y vencimientos | Estados por fecha (60/30/14 días) y merma con motivo | `domain/lotes.py` |
| Stock mínimo de alerta | `medicamentos.umbral_critico` + panel con "bajo umbral" | |
| RBAC del lado servidor | Matriz de permisos por rol; accesos denegados auditados | `security/rbac.py` |
| Concurrencia e idempotencia | `SELECT … FOR UPDATE` + clave de idempotencia por dispensación | |
| Auditoría de negocio | Bandeja outbox `eventos_pendientes` | |

Tablas que el proyecto tiene y el esquema objetivo **no** menciona, pero que conviene conservar: `ubicaciones` (casillero / caja de seguridad), `mermas`, `asientos_controlados` (libro D.S. 404/405/466), `programas_salud` + `pacientes_programas`, `eventos_pendientes`.

### 1.2 Equivalencia de nombres

El esquema objetivo usa otros nombres para tablas que ya existen. **Recomendación: no renombrar.** Renombrar no agrega funcionalidad, rompe el MER y los diagramas ya corregidos del Informe 3 y obliga a reescribir pruebas. La equivalencia queda documentada así:

| Esquema objetivo | Proyecto | Nota |
|---|---|---|
| `lotes_inventario` | `lotes` | `numero_lote` = `codigo_lote`; `cantidad_inicial` = `unidades_ingresadas`; `cantidad_actual` = `unidades_disp` |
| `detalle_recetas` | `detalles_receta` | |
| `detalle_dispensaciones` | `detalles_dispensacion` | |
| `movimientos_inventario` | `movimientos_stock` | `stock_posterior` = `saldo_resultante`; `stock_anterior` = `saldo_resultante − cantidad` (se calcula, no se guarda: evita redundancia) |
| `stock_minimo_alerta` | `medicamentos.umbral_critico` | |
| `TENS` | rol `TECNICO` | Se muestra como "TENS de farmacia"; el código interno no cambia |

### 1.3 Conflictos con el esquema nuevo

| # | Conflicto | Propuesta |
|---|---|---|
| C1 | La receta tiene `es_retenida` (sí/no) y el esquema pide `tipo` AGUDA / CRONICA / RETENIDA | Columna `tipo_receta`; los datos se migran (`es_retenida = true` → RETENIDA, si no → AGUDA). `es_retenida` pasa a ser un valor derivado y se elimina con Alembic |
| C2 | Vigencia única de 30 días (RN-04) para toda receta | Vigencia por tipo: AGUDA y RETENIDA 30 días; CRONICA hasta completar sus entregas (máx. 6 meses). **Confirmar el plazo con el profesor o un Q.F.** |
| C3 | `cant_prescrita` es el total; una crónica necesita cantidad **por entrega** | `cant_por_entrega` en la línea; `cant_prescrita` = `cant_por_entrega × total_entregas` |
| C4 | Hoy una receta retenida admite completar una entrega parcial | Con `total_entregas = 1` se mantiene: se puede completar **esa única entrega** si hubo quiebre de stock, pero no abrir una segunda |
| C5 | Roles TECNICO y BODEGUERO vs. TENS, MEDICO, PACIENTE | Mantener los 4 actuales (el bodeguero sí existe en un CESFAM), agregar **MEDICO**. **PACIENTE sin cuenta en esta etapa** (ver 1.4) |
| C6 | El esquema pone PRAIS como una opción de previsión junto a FONASA A-D | PRAIS **no es un tramo**: es un programa de reparación que se suma a FONASA. Se modela como `tramo_fonasa` (A-D) + `es_prais` (sí/no) |
| C7 | GES hoy está en el programa; el esquema lo pide en el medicamento | `medicamentos.es_ges`; el programa conserva su marca |
| C8 | El CHECK de `movimientos_stock.tipo` no admite `DEVOLUCION`, y cambiar un CHECK en SQLite obliga a reconstruir una tabla con triggers | Hacerlo con Alembic en modo *batch*, que reconstruye la tabla y vuelve a crear los triggers |
| C9 | El esquema pide "descuento automático del lote más próximo a vencer"; el proyecto además exige escanear el lote | Mantener el escaneo: el plan sigue siendo automático y el escaneo confirma que se entregó el lote correcto (es más seguro). Se agregará un aviso cuando falte lector |
| C10 | Las columnas nuevas no se agregan con `create_all`, y hoy hay una migración casera (`migraciones.py`) | Adoptar **Alembic** (pendiente n.º 5 de `AVANCE.md`): versiones numeradas, modo *batch* para SQLite y el mismo camino en PostgreSQL |

### 1.4 Lo que falta crear

1. Tabla `apoderados` y "quién retiró" en cada dispensación (paciente, apoderado o tercero).
2. Tabla `despachos_domicilio` con estados PREPARANDO → EN_RUTA → ENTREGADO (y FALLIDO).
3. Campos del paciente: `sector`, `es_prais`, `es_postrado`, `alergias`, `direccion` (solo para despacho).
4. Catálogo farmacéutico: `principio_activo`, `concentracion`, `forma_farmaceutica`, `unidad_dispensacion`, `es_ges`.
5. Recetas crónicas: `tipo_receta`, `total_entregas`, `entregas_realizadas`, `intervalo_dias`, `proxima_fecha_retiro`, `id_medico`, y `numero_entrega` en cada dispensación.
6. Rol MEDICO y permisos nuevos.
7. Consulta pública de disponibilidad (sin login).
8. Reportes exportables (CSV) y etiqueta de posología imprimible por entrega.

**Sobre el rol PACIENTE:** dar cuentas a los pacientes exige alta de cuentas, recuperación de contraseña y protección de datos de salud, lo que es un proyecto aparte. La propuesta es una **consulta pública sin login** que muestre solo "Disponible / Pocas unidades / Sin stock" por medicamento, nunca datos de pacientes ni cantidades exactas.

---

## 2. Plan de migración

### 2.0 Herramienta: Alembic

- Agregar `alembic` (versión fija) a `requirements.txt`.
- **Revisión 0001 (base):** el esquema v0.4 tal como está, incluido `codigo_barras`. Una base existente se marca con `alembic stamp 0001` sin tocar datos.
- Cada paso siguiente es una revisión con `upgrade` y `downgrade`.
- `migraciones.py` se retira; en desarrollo, el arranque ejecuta `alembic upgrade head`.
- Las pruebas siguen creando el esquema desde los modelos, más una prueba nueva que compara `upgrade head` con los modelos para detectar diferencias.

### 2.1 Cambios por tabla (revisión 0002)

**`roles`**: insertar `MEDICO`.

**`pacientes`** (todas las columnas nuevas admiten nulo o tienen valor por defecto, así que los registros existentes no se rompen):

| Columna | Tipo | Regla |
|---|---|---|
| `sector` | VARCHAR(30) | Lista configurable (p. ej. Sector Verde, Azul, Rural) |
| `es_prais` | BOOLEAN NOT NULL DEFAULT false | |
| `es_postrado` | BOOLEAN NOT NULL DEFAULT false | Habilita despacho a domicilio |
| `alergias` | VARCHAR(500) | Se muestra como alerta al dispensar |
| `direccion` | VARCHAR(200) | Solo si `es_postrado`; nunca aparece en listados |

**`apoderados`** (nueva, con baja lógica y campos de control):
`id_apoderado`, `id_paciente` FK, `rut_hmac`, `rut_enmascarado`, `nombre`, `parentesco`, `telefono`, `vigente_hasta` (opcional), `activo`… Índice único (`id_paciente`, `rut_hmac`).

**`medicamentos`**:

| Columna | Tipo | Migración de datos existentes |
|---|---|---|
| `principio_activo` | VARCHAR(120) | Se toma del nombre ("Losartán 50 mg comprimidos" → "Losartán") |
| `concentracion` | VARCHAR(40) | "50 mg" |
| `forma_farmaceutica` | VARCHAR(40) | Lista: comprimido, cápsula, jarabe, inhalador, solución inyectable… |
| `unidad_dispensacion` | VARCHAR(20) | Unidad mínima que se descuenta: comprimido, frasco, inhalador, ampolla |
| `es_ges` | BOOLEAN NOT NULL DEFAULT false | Desde el programa del medicamento |

**`recetas`**:

| Columna | Tipo | Regla |
|---|---|---|
| `tipo_receta` | VARCHAR(10) CHECK IN (AGUDA, CRONICA, RETENIDA) | Desde `es_retenida` |
| `total_entregas` | SMALLINT CHECK 1-6 | RETENIDA → siempre 1 (CHECK) |
| `entregas_realizadas` | SMALLINT CHECK 0..total | Se recalcula al dispensar o anular |
| `intervalo_dias` | SMALLINT DEFAULT 30 | |
| `proxima_fecha_retiro` | DATE NULL | Índice: lista de retiros del día |
| `id_medico` | FK usuarios NULL | Si la emitió un médico del sistema |
| `es_retenida` | — | Se elimina tras migrar (C1) |

**`detalles_receta`**: + `cant_por_entrega` INTEGER (los existentes: = `cant_prescrita`).

**`dispensaciones`**: + `numero_entrega` SMALLINT, `retira_tipo` (PACIENTE / APODERADO / TERCERO), `id_apoderado` FK NULL. Los `rut_retira_*` actuales se mantienen para el caso TERCERO.

**`despachos_domicilio`** (nueva): `id_despacho`, `id_dispensacion` FK única, `estado` CHECK (PREPARANDO, EN_RUTA, ENTREGADO, FALLIDO), `responsable` FK usuarios, `fecha_salida`, `fecha_entrega`, `recibe_nombre`, `observacion`. Cada cambio de estado queda también en la auditoría (outbox).

**`movimientos_stock`** (*batch*): el CHECK de `tipo` admite además `DEVOLUCION`. Se vuelven a crear los triggers de solo inserción.

**Índices nuevos:** `recetas(proxima_fecha_retiro)`, `apoderados(id_paciente)`, `despachos_domicilio(estado)`, `medicamentos(principio_activo)`.

### 2.2 Reglas que cambian (Paso B)

1. **Entrega X de Y:** cada dispensación indica su `numero_entrega`. Una entrega se completa cuando todas las líneas recibieron su `cant_por_entrega`. Al completarla: `entregas_realizadas + 1` y `proxima_fecha_retiro = fecha + intervalo_dias`.
2. **No retirar antes de tiempo:** una entrega posterior solo se permite desde `proxima_fecha_retiro − 5 días` (tolerancia configurable).
3. **Quiebre de stock:** se entrega lo que haya (FEFO en varios lotes) y la diferencia queda pendiente **dentro de la misma entrega**, sin adelantar la siguiente.
4. **Controlados:** tipo RETENIDA obligatorio, `total_entregas = 1`, firma del Q.F. y asiento en el libro (se mantiene).
5. **Quién retira:** paciente, apoderado registrado y vigente, o tercero con RUT y relación (obligatorio en controlados).
6. **Alergias:** si el paciente tiene alergias registradas, la ventanilla muestra un aviso que debe confirmarse antes de entregar.
7. **Anulación:** repone stock con movimiento inverso, descuenta `entregas_realizadas` y recalcula la próxima fecha (se mantiene el kardex inmutable).
8. **Devolución:** un paciente devuelve medicamento no usado → movimiento `DEVOLUCION`; se reingresa solo si el Q.F. lo aprueba, si no va a merma.

### 2.3 Pantallas y endpoints (Paso C)

| Módulo | Qué agrega |
|---|---|
| Ventanilla (Dispensar) | Ficha del paciente con alergias, sector, PRAIS y postrado; recetas con "Entrega 2 de 6 · próxima 15/12"; selector de quién retira; etiqueta de posología por entrega |
| Retiros del día | Lista de recetas crónicas con `proxima_fecha_retiro` hoy o atrasada |
| Despachos a domicilio | Tablero PREPARANDO / EN RUTA / ENTREGADO para pacientes postrados |
| Inventario | Alertas de vencimiento (60/30/14 días) y stock crítico en una sola vista, con filtros |
| Consulta pública | `/disponibilidad` sin login: medicamento + Disponible / Pocas unidades / Sin stock; con límite de peticiones |
| Reportes | CSV de kardex por rango de fechas, vencimientos próximos, entregas por programa y libro de controlados |
| Médico | Emitir receta (AGUDA o CRONICA; RETENIDA solo con validación del Q.F.) |

### 2.4 Datos de demostración realistas (Paso A)

- Unos **15 medicamentos frecuentes de APS**: losartán, enalapril, amlodipino, hidroclorotiazida, atorvastatina, ácido acetilsalicílico 100 mg, metformina, glibenclamida, insulina NPH (frasco), levotiroxina, salbutamol, sertralina, omeprazol, paracetamol y clonazepam (controlado). Todos con principio activo, forma, concentración y código de barras.
- 3 sectores; unos 10 pacientes ficticios con RUT válido: crónicos en distintas entregas, una persona postrada con apoderado y despacho en ruta, un paciente PRAIS y uno con alergia registrada.
- Lotes con vencimientos repartidos para que se vean todas las alertas, y recetas con retiro hoy, atrasado y futuro.
- Usuarios: Q.F., TENS, bodeguero, médico y administrador.

### 2.5 Pruebas y documentación

- Cada paso agrega pruebas unitarias (reglas de entregas y vigencia), de integración (API) y E2E (ventanilla, despacho, consulta pública).
- **PostgreSQL:** el `CLAUDE.md` exige probar contra PostgreSQL antes de cerrar. En este Windows no hay Podman ni PostgreSQL; hay que instalar uno de los dos (guía `INSTALACION_WINDOWS.md`, paso 8) antes de terminar el Paso A.
- Actualizar `docs/diagramas/09_mer.puml`, el diagrama de clases, un nuevo diagrama de estados de la receta y del despacho, `AVANCE.md` y el informe (`construir_informe.py`).

### 2.6 Orden y tamaño estimado

| Paso | Contenido | Tamaño |
|---|---|---|
| A | Alembic, revisiones 0001-0002, migración de datos, seed CESFAM, pruebas de migración | Grande |
| B | Reglas de entregas crónicas, apoderados, alergias, devoluciones, despacho | Grande |
| C | Ventanilla ampliada, retiros del día, despachos, alertas, consulta pública, reportes CSV, pantalla del médico | Grande |

Cada paso termina con la suite completa en verde (SQLite y PostgreSQL) y un resumen para revisar antes de seguir.

---

## 3. Decisiones que necesito confirmar

| # | Decisión | Recomendación |
|---|---|---|
| D1 | ¿Renombrar tablas a los nombres del esquema objetivo? | **No**; documentar la equivalencia (1.2) |
| D2 | ¿Cuentas de PACIENTE? | **No** en esta etapa; consulta pública sin login |
| D3 | ¿Adoptar Alembic? | **Sí** (necesario para C8 y C10) |
| D4 | Vigencia de receta crónica | Hasta completar las entregas, máximo 6 meses; confirmar con el profesor o un Q.F. |
| D5 | Tolerancia para retirar antes de la fecha | 5 días |
| D6 | PRAIS | Marca aparte (`es_prais`), no como tramo FONASA |

---

## 4. Registro de implementación

### Paso A (17/11/2026)

| Elemento | Dónde |
|---|---|
| Alembic 1.20.1, revisiones `0001` (esquema v0.4 + triggers) y `0002` (esquema v0.5 + migración de datos) | `backend/alembic.ini`, `backend/migraciones/` |
| Aplicación automática al arrancar en desarrollo, con respaldo previo de la base SQLite | `backend/app/esquema.py` |
| Modelos v0.5 | `backend/app/models.py` |
| Vocabulario controlado (formas, unidades, tipos de receta) | `backend/app/domain/catalogo.py` |
| Cálculo de entregas completas y próxima fecha de retiro | `backend/app/domain/recetas.py`, `services/dispensacion.py` |
| Seed CESFAM: 15 medicamentos, 22 lotes, 3 sectores, 8 pacientes, 9 recetas, 1 apoderada, 1 despacho en ruta, rol médico | `backend/app/seed.py` |
| Interfaz mínima: ficha del paciente (sector, FONASA, PRAIS, postrado, alergias), columnas de entregas y próximo retiro, datos farmacéuticos al crear medicamentos, rol médico | `frontend/app.js` |
| Pruebas nuevas: 15 unitarias, 13 de integración (incluye migración ida y vuelta y comparación modelo/migración) | `tests/unit/test_recetas_cronicas.py`, `tests/integration/test_migraciones.py`, `tests/integration/test_api_esquema_v05.py` |

**Diferencias con el plan:**
- `sector` quedó como tabla `sectores` (clave foránea) en vez de texto libre: evita que el mismo sector se escriba de varias formas (normalización).
- La regla "entrega X de Y" y la próxima fecha de retiro ya se calculan en el Paso A, porque la base exige que `entregas_realizadas` sea coherente. El Paso B agrega las validaciones (retiro anticipado, vigencia de crónicas, quién retira).
- Las recetas que se registran desde la interfaz siguen siendo AGUDA o RETENIDA de una entrega; las crónicas se crean en el Paso B.

**Pendiente antes de cerrar el Paso A del todo:** ejecutar `tests/integration` y `alembic upgrade head` contra **PostgreSQL** (no disponible en el equipo Windows actual).

### Paso B (17/11/2026)

| Regla o función | Dónde | Código de error |
|---|---|---|
| Vigencia por tipo: aguda y retenida 30 días; crónica 30 días para la 1.ª entrega y 180 para las siguientes | `domain/recetas.py` | `RECETA_VENCIDA` |
| Estructura: crónica de 2 a 6 entregas; aguda/retenida, 1; controlado solo retenida | `domain/recetas.validar_estructura` | `ENTREGAS_INVALIDAS`, `RECETA_NO_RETENIDA` |
| Receta crónica con cantidad por entrega (el total se calcula) | `services/recetas.py`, `POST /api/recetas` | `CANTIDADES_INCONSISTENTES` |
| No se lleva la entrega siguiente en la misma visita | `domain/recetas.saldo_entrega_actual` | `CANTIDAD_EXCEDE` |
| Retiro desde 5 días antes de la fecha; completar una entrega parcial, siempre | `domain/recetas.exigir_fecha_de_retiro` | `RETIRO_ANTICIPADO` |
| Quién retira: paciente (en controlados con su RUT), apoderado registrado y vigente, o tercero con RUT y relación | `services/dispensacion._resolver_retiro` | `APODERADO_INVALIDO`, `RUT_NO_COINCIDE`, `IDENTIFICACION_REQUERIDA` |
| Alergias registradas deben confirmarse | `services/dispensacion.py` | `ALERGIAS_SIN_CONFIRMAR` |
| Despacho a domicilio (solo postrados, nunca controlados); PREPARANDO → EN_RUTA → ENTREGADO / FALLIDO → EN_RUTA | `services/despachos.py`, `/api/despachos` | `TRANSICION_INVALIDA`, `RECEPTOR_REQUERIDO` |
| Anulación bloqueada si el despacho salió o hay devoluciones | `services/dispensacion.anular_dispensacion` | `DESPACHO_EN_CURSO`, `TIENE_DEVOLUCIONES` |
| Devoluciones del paciente: REINGRESO (kardex `DEVOLUCION`) o DESCARTE; en controlados, asiento `DEVOLUCION` en el libro | `services/devoluciones.py`, `POST /api/devoluciones` (solo Q.F.), migración `0003` | `REINGRESO_NO_PERMITIDO`, `CANTIDAD_INVALIDA` |
| Apoderados: alta y baja lógica, RUT protegido como el del paciente | `services/apoderados.py`, `/api/pacientes/{id}/apoderados` | `APODERADO_DUPLICADO`, `APODERADO_ES_PACIENTE` |

**Interfaz (lo mínimo para usar las reglas):** receta crónica en "Nueva receta" (tipo, n.º de entregas e intervalo), tarjeta de retiro con "Entrega X de Y", selector de quién retira, confirmación de alergias y despacho a domicilio; botón "Atender receta" desactivado antes de la fecha de retiro. Quedan para el Paso C: tablero de despachos, pantalla de devoluciones, gestión de apoderados, retiros del día y la pantalla del médico.

**Pruebas:** 15 unitarias y 16 de integración nuevas (`tests/unit/test_recetas_cronicas.py`, `tests/integration/test_api_paso_b.py`) y 2 E2E. Suite completa: 229 aprobadas, 1 omitida (concurrencia, requiere PostgreSQL).

### Paso C (17/11/2026)

| Pantalla / endpoint | Para quién | Notas |
|---|---|---|
| **Retiros** · `GET /api/recetas/retiros?dias=` | TENS, Q.F. | Entregas de hoy y atrasadas (o próximos 7/30 días); "Atender" abre la ficha sin reescribir el RUT (`GET /api/pacientes/{id}/ficha`) |
| **Despachos** · `/api/despachos` | TENS, Q.F. | Tablero Preparando / En ruta / No entregados / Entregados con dirección, medicamentos y acciones |
| **Entregas** (ampliada) | Q.F. | Devolución por línea, reimpresión de rótulos (`GET /api/dispensaciones/{id}/rotulos`), "Entrega X de Y" y quién retiró |
| **Apoderados** en la ficha | TENS, Q.F. | Alta con parentesco, teléfono y vigencia; baja con motivo |
| **Alertas** · `GET /api/inventario/alertas` | Todos con stock | Vencimientos (60/30/14 días, alerta sanitaria) con acción sugerida y stock bajo umbral ordenado por déficit |
| **Reportes** · `/api/reportes/*.csv` | Q.F., bodeguero, administrador (libro: solo Q.F.) | Kardex con stock anterior y posterior, entregas por programa, vencimientos y libro. CSV `;` con BOM, celdas neutralizadas contra inyección de fórmulas, exportación auditada |
| **Consulta pública** · `/#/disponibilidad` y `GET /api/publico/disponibilidad` | Cualquiera, sin login | Disponible / Pocas unidades / Sin stock; sin cantidades ni controlados; límite de 60 consultas por minuto por IP (429 + `Retry-After`) |
| **Recetar** (vista del médico) | Médico | Busca pacientes y emite recetas agudas o crónicas; no ve retiros ni puede dispensar |
| Rótulos imprimibles | TENS, Q.F. | Al imprimir sale solo la etiqueta, sin menús |

**Optimización:** el panel de stock leía los lotes con una consulta por medicamento; ahora usa una sola consulta (se reutiliza en alertas y en la consulta pública).

**Decisión:** el médico no registra recetas de controlados en el sistema (la receta retenida en papel la valida y registra el Q.F.); un flujo de validación médico → Q.F. queda como mejora futura.

**Pruebas:** 16 de integración (`tests/integration/test_api_paso_c.py`) y 6 E2E nuevas. Suite completa: 251 aprobadas, 1 omitida (concurrencia, requiere PostgreSQL). Bandit: 0 hallazgos.
