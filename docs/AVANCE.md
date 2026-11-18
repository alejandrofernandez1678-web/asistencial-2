# Avance de implementación – SISGEF-Asistencial v0.3.0

**Proyecto:** Sistema web farmacia asistencial (SISGEF-Asistencial)
**Equipo:** Joaquín Figueroa · Alejandro Fernández
**Fecha:** 17/11/2026 · **Sprint:** 3 (inventario con FEFO y dispensación)

Este documento resume el primer avance funcional del sistema para recibir
retroalimentación antes de la entrega final. Incluye qué se construyó, cómo se
abordaron los comentarios del Informe 2, los resultados de las pruebas
ejecutadas y lo que queda pendiente.

---

## 1. Qué se entrega

Una aplicación web funcional con el stack del Informe 2:

| Capa | Tecnología | Estado |
|---|---|---|
| Backend | Python + FastAPI + Pydantic | Implementado |
| Acceso a datos | SQLAlchemy 2 | Implementado |
| Base estructurada | PostgreSQL 16 (probado en contenedor) y SQLite para desarrollo rápido | Implementado |
| Frontend | React 18 (sin compilación, ver nota en el README) | Implementado |
| Pruebas | pytest, pytest-cov, Playwright, Bandit | Ejecutadas |
| Identidad | JWT local (Cognito con MFA en AWS) | Parcial |
| Auditoría | Outbox en PostgreSQL (publicación a DynamoDB pendiente) | Parcial |

Instrucciones de instalación y ejecución paso a paso: [`README.md`](../README.md).

## 2. Cobertura de las historias de usuario

| HU | Caso de uso | Estado | Qué se puede hacer hoy |
|---|---|---|---|
| HU-01 | E1 Dispensar receta con unidosis | ✅ | Buscar paciente por RUT, validar vigencia (30 días), entregar por unidad y emitir rótulo |
| HU-04 | E2 Validar lote según FEFO | ✅ | Plan FEFO con lote y casillero; el escaneo de otro lote se bloquea con la indicación correcta |
| HU-02 | E3 Despachar controlado y asentar libro | ✅ | Receta retenida, RUT y relación de quien retira, firma del Q.F. con PIN, asiento encadenado por hash |
| HU-05 | E7 Panel por programa | ✅ | Stock dispensable por medicamento y programa, unidades por estado, alerta de umbral crítico |
| HU-07 | E6 Retirar lote a merma | ✅ | Estados por vencimiento (60/30/14 días) y merma con motivo |
| HU-06 | E9 Gestionar usuarios y roles | ✅ | Alta y baja de usuarios, matriz RBAC, bloqueo por intentos fallidos (falta MFA) |
| HU-03 | E4 Recepcionar remesa CENABAST | 🟡 | Ingreso de lote con alerta de vencimiento < 6 meses; **falta** guía de remesa y conciliación |
| HU-09 | E8 Rastrear lote → pacientes | 🔴 | El modelo ya lo permite (`detalles_dispensacion.id_lote`); falta la pantalla |
| HU-08 | E5 Auditar estantería con PDA | 🔴 | La vista móvil está lista; falta el flujo de conteo |

**Cobertura: 6 de 9 historias completas, 1 parcial y 2 pendientes.**

## 3. Respuesta a la retroalimentación del Informe 2

### 3.1 Modelo de datos: campos de control y eliminación

> *"En el MER faltan campos mínimos en las tablas para el control, no se refleja la
> eliminación de un objeto, ¿cómo se da de baja un producto, una venta, un lote mal ingresado?"*

Se implementó en el código (`backend/app/models.py`) y queda probado:

| Pregunta del profesor | Solución implementada | Prueba |
|---|---|---|
| Campos de control | Todas las tablas de negocio tienen `creado_en`, `creado_por`, `actualizado_en`, `actualizado_por` | Todas |
| ¿Cómo se da de baja un **producto**? | **Baja lógica**: `activo = false` + `fecha_baja`, `baja_por`, `motivo_baja`. No se permite con stock dispensable. Se puede reactivar. | IT-37, IT-38, E2E-11 |
| ¿Cómo se anula una **venta** (dispensación)? | `estado = ANULADA` + quién, cuándo y por qué. Repone el stock a cada lote, libera la receta y, si es controlado, agrega un **asiento de rectificación** (el libro no se modifica). | IT-22, IT-23, IT-24, E2E-12 |
| ¿Y un **lote mal ingresado**? | Dos casos: **cantidad errónea** → movimiento `AJUSTE` con motivo; **lote equivocado** → `estado = ANULADO` con motivo, solo si nunca se dispensó. | IT-33, IT-34, IT-35 |
| ¿Y un **usuario**? | Baja lógica; su token deja de servir de inmediato. | IT-06 |
| Trazabilidad de todo lo anterior | Nueva tabla **`movimientos_stock` (kardex)**: cada entrada, salida, ajuste, merma o anulación queda con su saldo. Es de **solo inserción** (trigger). | IT-20, IT-30 |

**Regla general:** en SISGEF nunca se ejecuta un `DELETE` sobre datos de negocio. Todas
las FK usan `ON DELETE RESTRICT`, y el libro de controlados y el kardex tienen triggers
que rechazan `UPDATE` y `DELETE`.

**Cambios al MER que hay que reflejar en el diagrama del informe:**
- Tabla nueva `movimientos_stock` (id_movimiento, id_lote, tipo, cantidad, saldo_resultante, referencia_tipo, referencia_id, motivo, id_usuario, fecha_hora).
- `lotes`: + `unidades_ingresadas`, `fecha_anulacion`, `anulado_por`, `motivo_anulacion`; el estado admite `ANULADO`.
- `dispensaciones`: + `estado`, `fecha_anulacion`, `anulada_por`, `motivo_anulacion`.
- `asientos_controlados`: + `tipo` (SALIDA/RECTIFICACION), `id_asiento_origen`, `id_usuario_qf`, `contenido`.
- `detalles_receta`: + `cant_entregada` (permite entregas parciales).
- `usuarios`: + `password_hash`, `pin_hash`, `intentos_fallidos`, `bloqueado_hasta`.
- `medicamentos`, `ubicaciones`, `usuarios`: + campos de baja lógica.
- Todas: + campos de control.

### 3.2 Comentarios que se corrigen en el documento

> **Estado:** aplicados en `Proyecto_Integrado_Informe_3_base.docx` (versión base, no final), generado con
> `docs/informe/construir_informe.py`. Los diagramas están en `docs/diagramas/*.puml`.

| Comentario | Acción |
|---|---|
| Introducción y resumen ejecutivo en página aparte | Salto de página antes de cada Título 1 |
| Diagrama de clases: faltan métodos y claridad | Rehacer en notación UML con los métodos reales del código (`dar_de_baja`, `anular`, `ajustar`, `registrar_merma`, `verificar_cadena`…) y agrupado por módulo |
| Casos de uso: actores | Redibujar actores con la figura UML estándar |
| ¿A qué diagrama UML corresponden actividades y estados? | Redibujar con notación UML 2.5 estricta (marcos `act` y `stm`). Corregir la rama de controlados, que hoy salta el escaneo FEFO. Alinear los estados con el código: VIGENTE, ALERTA, NO_DISPENSABLE, RETIRO_OBLIGATORIO, AGOTADO, ALERTA_SANITARIA, MERMA, ANULADO |
| Paquetes mezclado con despliegue | Dejar solo paquetes y dependencias `«import»`, según la estructura real de `backend/app` |
| Red AWS: falta información | Agregar CIDR por subred, IGW, NAT, tablas de rutas y security groups con puertos |
| Tecnologías y herramientas sin fundamento | Agregar columna "alternativa considerada / por qué esta" |

## 4. Seguridad implementada en el código

| Patrón | Dónde | Amenaza que mitiga |
|---|---|---|
| Validación estricta de entrada (tipos, largos, rangos; campos desconocidos rechazados) | `api/schemas.py` | Inyección, asignación masiva |
| Consultas parametrizadas (ORM) | `repositories/`, `services/` | Inyección SQL |
| Hash de contraseñas y PIN con PBKDF2-SHA256 (600.000 iteraciones, sal aleatoria), comparación en tiempo constante | `security/claves.py` | Robo de credenciales, ataques de tiempo |
| JWT HS256 con expiración de 30 min; se rechazan tokens alterados, expirados y `alg=none` | `security/tokens.py` | Suplantación de sesión |
| Bloqueo tras 5 intentos fallidos (15 min) y mensaje genérico | `services/autenticacion.py` | Fuerza bruta, enumeración de usuarios |
| RBAC del lado servidor con mínimo privilegio; accesos denegados auditados | `security/rbac.py`, `api/deps.py` | Escalamiento de privilegios |
| Separación de funciones: el administrador no dispensa y solo el Q.F. firma | Matriz RBAC | Fraude interno |
| RUT de pacientes guardado como HMAC + versión enmascarada; búsqueda por POST (no en la URL) | `models.py`, `api/dispensacion.py` | Exposición de datos personales (Ley 19.628) |
| Libro de controlados con hash encadenado y triggers de solo inserción | `domain/libro.py`, `models.py` | Alteración de registros legales |
| Transacciones atómicas, `SELECT … FOR UPDATE` e idempotencia | `services/dispensacion.py` | Doble descuento, stock negativo |
| Cabeceras CSP, X-Frame-Options, nosniff, Referrer-Policy; sin scripts de terceros | `main.py` | XSS, clickjacking |
| Errores sin detalles internos (SQL, trazas) | `main.py` | Fuga de información |
| Secretos solo por variables de entorno; obligatorios en producción | `config.py`, `.gitignore` | Exposición de secretos |

**Análisis estático (Bandit 1.9.4):** 0 hallazgos. Un falso positivo (B105 sobre el
literal `"bearer"`, el tipo de token de OAuth 2.0) se documentó en el código con su
justificación.

## 5. Resultados de las pruebas ejecutadas

Ejecutadas el 17/11/2026 en Fedora Linux, Python 3.15.2.

| Nivel | Herramienta | Casos | Resultado |
|---|---|---|---|
| Unitarias (reglas de dominio y seguridad) | pytest | 68 | 68/68 ✅ · cobertura del dominio 99 % |
| Integración (API + base de datos, SQLite) | pytest + TestClient | 37 | 37/37 ✅ |
| Integración (API + **PostgreSQL 16**) | pytest + contenedor Podman | 38 | 38/38 ✅ (incluye concurrencia) |
| E2E (interfaz real) | Playwright + Brave | 11 | 11/11 ✅ |
| Seguridad estática | Bandit | — | 0 hallazgos |
| **Cobertura total del backend** | pytest-cov | — | **94 %** |

Casos destacados: el FEFO bloquea el lote más nuevo y el lote por vencer; una
dispensación con una línea inválida no descuenta ninguna (atomicidad); un reintento con la
misma clave no descuenta dos veces; un controlado sin PIN o con PIN incorrecto se rechaza;
el libro y el kardex rechazan `UPDATE`/`DELETE` incluso con SQL directo; **8
confirmaciones simultáneas de la misma receta producen una sola entrega** y el stock no
queda negativo; la vista PDA de 360 px no tiene desplazamiento horizontal.

### 5.1 Discrepancias encontradas (resultado esperado vs. obtenido)

| ID | Esperado | Obtenido | Causa | Corrección |
|---|---|---|---|---|
| D-01 | La dispensación bloquea la receta con `FOR UPDATE` en PostgreSQL | Error *"FOR UPDATE cannot be applied to the nullable side of an outer join"*. En SQLite pasaba. | SQLite ignora `FOR UPDATE`; el ORM usaba `LEFT JOIN` en relaciones obligatorias | `INNER JOIN` en relaciones con FK `NOT NULL` |
| D-02 | Modificar el libro de controlados devuelve error de integridad (409) | PostgreSQL devolvía un error genérico (`ProgrammingError`) | El trigger usaba el SQLSTATE por defecto (P0001) | `ERRCODE = integrity_constraint_violation` |
| D-03 | Escanear un lote de otro medicamento informa "es de otro medicamento" | Informaba "el lote no existe" | El servicio solo buscaba entre los lotes del medicamento | Búsqueda global del lote escaneado |
| D-04 | Reiniciar la base de demostración | Fallaba: el trigger de solo inserción bloqueaba el `DROP TABLE` | SQLite borra fila a fila al eliminar una tabla con FK | Rutina `borrar_esquema` solo para desarrollo |
| D-05 | Pruebas E2E estables | Error *"bad parameter or other API misuse"* | La base en memoria compartía una conexión entre hilos y la interfaz hace peticiones en paralelo | Servidor E2E como proceso aparte con base en archivo |
| D-06 | Interfaz sin textos extraños; Escape cierra diálogos | Aparecía "&nbsp;" literal; Escape no siempre cerraba | htm no interpreta entidades HTML; el evento se escuchaba solo en el formulario | Espaciador CSS; escucha a nivel de documento |
| D-07 | Estados del lote iguales en diagrama y código | El diagrama de estados y el enum `EstadosLote` del Informe 2 no coincidían | Se diseñaron por separado | El código unifica los 8 estados; falta actualizar el diagrama |

**Recomendaciones derivadas:**
1. Ejecutar las pruebas de integración contra PostgreSQL en el pipeline CI (D-01, D-02): SQLite no basta para validar bloqueos ni triggers.
2. Generar los diagramas de estados y de clases a partir del código para evitar diferencias (D-07).
3. Agregar una prueba E2E por cada mensaje de error visible al usuario (D-03, D-06).

## 6. Pendiente para la entrega final

1. Recepción CENABAST con guía de remesa y conciliación (HU-03, RN-05).
2. Rastreo lote → pacientes (HU-09) y auditoría de estantería con PDA (HU-08).
3. MFA con Amazon Cognito y despliegue en AWS (CloudFormation).
4. Publicador outbox → DynamoDB y documentos en S3.
5. Migraciones versionadas con Alembic (hoy el esquema se crea desde los modelos).
6. Prueba de carga con k6 (RNF-01: p95 ≤ 1,5 s con 30 usuarios).
7. Corregir los diagramas y el formato del informe según la sección 3.2.

## 7. Preguntas para el profesor

1. ¿La solución de baja lógica, anulación y kardex responde a lo que esperaba en el MER, o prefiere ver las anulaciones como entidades separadas (por ejemplo, una tabla `anulaciones`)?
2. ¿Es aceptable el frontend React sin compilación para esta etapa, o exige Vite + TypeScript desde ya?
3. Para la evaluación, ¿basta con demostrar en local con PostgreSQL en contenedor, o debe estar desplegado en AWS?
