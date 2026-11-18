# Propuesta v0.6 – Mejoras a partir de normativa y buenas prácticas

Investigación del 17-11-2026. Cada mejora indica de dónde sale (norma, programa o estándar),
qué falta hoy en SISGEF v0.5 y cómo se implementaría respetando las reglas del proyecto
(sin `DELETE`, kardex vía `mover_stock`, tablas de solo inserción).

## Hallazgo principal: el FOFAR evalúa a la farmacia con 4 indicadores

La Orientación Técnica del **Programa Fondo de Farmacia (FOFAR)** de la DIVAP-MINSAL fija
cómo se mide (y se paga) la gestión de la farmacia de un CESFAM. Hoy SISGEF no puede calcular
ninguno de los cuatro:

| N.º | Indicador FOFAR | Fórmula | Meta |
|---|---|---|---|
| 1 | Recetas con despacho **total y oportuno** | recetas despachadas completas el mismo día de la solicitud / recetas solicitadas | 100 % (mensual, REM A04 sección J) |
| 2 | Reclamos con **solución en 24 h hábiles** | reclamos resueltos (entrega del fármaco) en < 24 h hábiles / total de reclamos | 100 % |
| 3 | **Merma valorizada** | valor mermado del período / inventario valorizado semestral (sin insulinas) | ≤ 0,99 % |
| 4 | **Actividades farmacéuticas** | actividades realizadas / programadas (semestre) | 50 % a junio, 100 % a diciembre |

Además, la OT pide: préstamo de medicamentos entre establecimientos ante quiebre de stock
(Anexo 1), acta de recepción en domicilio (Anexo 2), registro de "rechazo del paciente" y
11 h semanales del Q.F. en atención farmacéutica, farmacovigilancia y talleres.

---

## Bloque 1 – FOFAR (lo que el MINSAL mide) · prioridad alta

### 1.1 Faltantes, compromisos de entrega y reclamos (indicadores 1 y 2)
- **Falta hoy:** si no hay stock, la entrega queda parcial sin registrar qué se le debe al paciente.
- **Propuesta:**
  - Al dispensar, cada línea queda **COMPLETA** u **INCOMPLETA** (motivo: sin stock / rechazo del paciente / otro). Una línea incompleta genera un **compromiso de entrega** con plazo de 24 h hábiles (se excluyen sábados, domingos y feriados de una tabla).
  - **Reclamo** con canal (OIRS, Salud Responde, presencial), vínculo al compromiso, reloj de horas hábiles, cierre con la entrega y **acta de recepción** imprimible.
  - Pantalla "Pendientes" con semáforo (a tiempo / por vencer / fuera de plazo).
  - Reporte mensual **"REM A04 sección J"**: recetas cardiovasculares solicitadas, despachadas total y oportunamente, incumplidas por oportunidad o por completitud, y los días de demora por fármaco.

### 1.2 Inventario valorizado, toma de inventario y merma % (indicador 3)
- **Falta hoy:** los lotes no tienen precio, por lo que la merma no se puede valorizar ni contrastar con un conteo físico.
- **Propuesta:**
  - **Precio unitario** en el ingreso del lote (factura o CENABAST), junto con el N.º y la fecha de factura y el proveedor (esto también lo exige el libro, ver 3.1).
  - **Toma de inventario**: se abre un conteo (total o por ubicación), se registra lo contado ciego por lote, la diferencia la aprueba el Q.F. y se aplica con `mover_stock` como ajuste con motivo. El conteo cerrado queda inmutable.
  - Indicador de merma valorizada semestral (excluye insulinas) en Alertas y en Reportes.

### 1.3 Registro de actividades farmacéuticas (indicador 4)
- **Tipos de actividad:**
  - Atención farmacéutica: revisión de la medicación, conciliación, educación y seguimiento farmacoterapéutico.
  - Farmacovigilancia: RAM, falla de calidad y evento adverso.
  - Talleres grupales.
- **Registro:** cada actividad se asocia a un paciente cuando corresponde, con el resultado y la intervención realizada. La meta semestral se configura y se muestra en un tablero de cumplimiento.
- **Farmacovigilancia:** genera una ficha imprimible con los datos que pide el formulario del ISP, para ingresarla al Sistema de Vigilancia Integrado (SVI). No se integra en línea porque el ISP no ofrece una API pública.

### 1.4 Préstamos y traspasos entre establecimientos (Anexo 1 FOFAR)
- Solicitud de préstamo (entrega o recepción), con su establecimiento de contraparte y la fecha comprometida de devolución.
- Movimientos `TRASPASO_SALIDA` / `TRASPASO_ENTRADA` registrados en el kardex.
- Alerta cuando un préstamo no se ha devuelto.

---

## Bloque 2 – Seguridad del paciente en la dispensación · prioridad alta

### 2.1 Alergias estructuradas por principio activo
Hoy la alergia es texto libre y solo se pide confirmarla. Propuesta: la ficha registra la lista
de principios activos alérgenos. Si se intenta dispensar uno de ellos, el sistema **bloquea**
la entrega y solo el Q.F. puede autorizarla, dejando el motivo en la auditoría.

### 2.2 Alertas de dispensación
- **Duplicidad terapéutica:** el mismo principio activo en dos recetas vigentes del paciente.
- **Medicamentos de alto riesgo**, según la lista ISMP para atención ambulatoria (insulinas, sulfonilureas, anticoagulantes orales, opioides, metotrexato): marca en el catálogo, doble verificación y un rótulo destacado.
- **Medicamentos con nombre o aspecto parecido** (LASA, por ejemplo hidroxizina / hidralazina): se muestran con *tall man lettering* en la búsqueda y en el rótulo. Siguiendo la advertencia de ISMP, la lista se mantiene corta para no diluir el efecto.
- **Interacciones:** tabla curada y pequeña de interacciones relevantes en APS. No es una base de datos comercial y el informe debe decirlo explícitamente.

### 2.3 Adherencia (PDC) en crónicos
- **Cálculo:** la *Proportion of Days Covered* se obtiene de las propias entregas: días con medicamento disponible en el período, sin sumar dos veces los días en que dos entregas se superponen.
- **Uso:** se considera adherente a quien alcanza un **PDC ≥ 80 %**, el umbral estándar en enfermedades crónicas. Esto alimenta una lista de pacientes con baja adherencia para la atención farmacéutica.
- **Límite:** el PDC mide si el paciente retiró el medicamento, no si lo tomó, y la pantalla debe advertirlo.

### 2.4 Lectura de GS1 DataMatrix
- **Qué contiene:** el código 2D de las cajas incluye el GTIN (01), el vencimiento (17, en formato AAMMDD), el lote (10) y la serie (21).
- **Al ingresar un lote:** se escanea la caja y el sistema completa el medicamento, el lote y el vencimiento sin tipeo.
- **Al dispensar:** se valida que el lote escaneado sea el que indica FEFO.
- **Implementación:** el parser va en `domain/`, maneja el separador FNC1/GS (ASCII 29) y las variantes con paréntesis, y se prueba con ejemplos de GS1.

### 2.5 Cadena de frío (NT 208 del ISP, complemento de la NT 147)
- **Registro:** temperatura mínima y máxima del refrigerador dos veces al día, en un rango de 2 a 8 °C.
- **Excursión fuera de rango:** pone en cuarentena los lotes de esa ubicación hasta que el Q.F. decida si se liberan o se mandan a merma.
- **Seguimiento:** alerta de registro faltante y reporte mensual.

---

## Bloque 3 – Cumplimiento normativo de controlados · prioridad alta

### 3.1 Libro de control completo según DS 404/405, art. 18
Hoy el libro registra solo salidas, anulaciones y devoluciones. El reglamento exige además:
- **Ingresos:** fecha, cantidad, proveedor, N.º y fecha de la factura o guía, y la resolución si corresponde. Hoy el ingreso de un lote controlado no genera asiento.
- **Egresos:** N.º de **receta cheque** (listas II y III de psicotrópicos y estupefacientes), nombre y RUT del médico, y nombre y domicilio del paciente.
- **Saldos:** el saldo por producto después de cada asiento.

### 3.2 Arqueo de controlados
Conteo físico periódico de los controlados contra el saldo del libro, firmado con el PIN del Q.F.
Si hay diferencias, se registra un asiento de ajuste con motivo y queda abierta una investigación.

---

## Bloque 4 – Abastecimiento · prioridad media
- **Indicadores por medicamento:**
  - **CPM** (consumo promedio mensual de los últimos 3 a 6 meses).
  - **Meses de cobertura** (stock / CPM).
  - **Punto de reorden** (consumo diario × demora del proveedor + stock de seguridad).
- **Pedido sugerido** mensual para CENABAST, exportable a CSV.
- Clasificación **ABC** (por valor consumido) y **VEN** (vital, esencial, no esencial) para priorizar.
- El umbral crítico fijo de hoy pasa a calcularse con estos indicadores, y se puede corregir a mano.

## Bloque 5 – Datos personales, seguridad e interoperabilidad · prioridad media
- **Ley 21.719 de datos personales:**
  - Entra en vigor el **1-12-2026**. El Congreso tramita postergarla al 1-12-2027.
  - Los datos de salud son sensibles. Propuesta:
    - Registro de **quién consultó cada ficha** (hoy se auditan acciones, no lecturas).
    - Exportación de los datos de un paciente cuando ejerce su derecho de acceso.
    - Política de retención documentada.
- **MFA (TOTP)** para Q.F. y Administrador, implementado con la biblioteca estándar (RFC 6238). El Informe 2 ya lo comprometía vía Cognito.
- **Receta electrónica (FHIR):**
  - El MINSAL publica la guía *Sistema Nacional de Receta Electrónica* (FHIR R4, perfil `PrescripcionRecetaCL`), pero aún es **borrador v0.9.6**.
  - **Propuesta:** exportar las dispensaciones como `MedicationDispense` y aceptar la importación de una receta en `MedicationRequest`, documentado como prototipo de interoperabilidad.

---

## Recomendación de orden

1. **Bloque 1 (FOFAR)** y **3.1 (libro completo)**: son lo que mide el MINSAL y lo que exige el reglamento, y los dos se defienden muy bien en el informe.
2. **Bloque 2**: seguridad del paciente, con un impacto visible en la ventanilla.
3. Bloques 4 y 5.

Cada bloque lleva su migración Alembic, sus pruebas (unitarias, de integración y E2E) y la
actualización de `PLAN`/README, igual que en la v0.5.

## Fuentes
- MINSAL-DIVAP, [Orientación Técnica Programa Fondo de Farmacia (FOFAR) 2023](https://saludresponde.minsal.cl/wp-content/uploads/2025/08/ORIENTACION-TECNICA-FOFAR-2023-Final-21-08-2023.pdf): indicadores 1 a 4, reclamos en 24 h hábiles, Anexos 1 y 2, actividades farmacéuticas.
- [Servicio de Salud Arica – Fondo de Farmacia](https://portal.saludarica.cl/programas-de-salud/fondo-de-farmacia/) · [Chile Seguridades y Oportunidades – FOFAR](https://www.chileseguridadesyoportunidades.gob.cl/servicio-farmacia-enfermedades-cronicas)
- [DS 405, art. 18 (libro de control de psicotrópicos)](https://iura.cl/dto-405-minsal/18) · [DS 404, art. 18](https://iura.cl/dto-404-minsal/18) · [DS 405, art. 23 (receta cheque)](https://iura.cl/dto-405-minsal/23)
- [NT 208, medicamentos refrigerados (Diario Oficial 2019)](https://www.diariooficial.interior.gob.cl/publicaciones/2019/09/30/42465/01/1660165.pdf) · [NT 147 en BCN](https://www.bcn.cl/leychile/navegar?idNorma=1049227)
- Farmacovigilancia ISP y SVI: [Salud y Fármacos](https://www.saludyfarmacos.org/boletin-farmacos/boletines/feb202301/54_ch/) · [procedimiento RAM en APS (Arica)](https://transparencia.municipalidaddearica.cl/uploads/file/LEY20285/2013/OCTUBRE/Reglam/14927_procedimiento-1.PDF)
- [MINSAL – Criterios técnicos para la programación de actividades del Q.F.](https://www.minsal.cl/wp-content/uploads/2026/09/20-RPE-Criterios-Tecnicos-para-programacion-de-Actividades-de-Quimicos-Farmaceuticos-en-Atencion-Primaria-Secundaria-y-Terciaria.pdf)
- [MINSAL – IG FHIR Sistema Nacional de Receta Electrónica (borrador)](https://build.fhir.org/ig/Minsal-CL/IG_snre/StructureDefinition-RecetaPrescripcionCl.html)
- GS1 DataMatrix: [GS1 – 2D barcodes in healthcare](https://gs1.org/industries/retail/2d-barcodes/explorer/2d-barcodes-healthcare) · [AEMPS – dispositivos de seguridad](https://www.aemps.gob.es/industria-farmaceutica/dispositivos-de-seguridad-de-medicamentos-de-uso-humano/recomendaciones-y-aclaraciones-para-la-aplicacion-de-los-dispositivos-de-seguridad-de-medicamentos-de-uso-humano/) · [EAHP – pruebas de lectura](https://eahp.eu/wp-content/uploads/2024/03/fiche-technique-jeu_de_test_dm-ndeg5_v05gb4.pdf)
- ISMP: [List of Confused Drug Names](https://home.ecri.org/blogs/ismp-resources/list-of-confused-drug-names) · [ISMP Canada – Tall Man Lettering](https://www.ismp-canada.org/download/TALLman/TALLmanLettering-ProjectReport.pdf)
- Adherencia PDC: [PMC9546055 (umbral 80 %)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9546055) · [PMC10397888](https://pmc.ncbi.nlm.nih.gov/articles/PMC10397888)
- Abastecimiento: [Salud Mesoamérica – niveles máx./mín.](https://www.saludmesoamerica.org/sites/default/files/toolkits/documents/3.%20Guia%20de%20gestion%20para%20niveles%20inventarios%20max%20min_0.pdf) · [MSP Uruguay – estimación de necesidades](https://www.gub.uy/ministerio-salud-publica/sites/ministerio-salud-publica/files/documentos/publicaciones/Gu%C3%ADa%20estimacion%20necesidades%20y%20compras%20insumos%20%20SSYSR%20-%202013.pdf.pdf)
- Ley 21.719: [Diario Constitucional](https://www.diarioconstitucional.cl/2026/06/12/la-ley-21-719-entra-en-vigor-el-1-de-diciembre-y-expone-vacios-en-regulacion-de-pequenas-empresas/) · [Emol – proyecto de postergación](https://www.emol.com/noticias/Economia/2026/09/01/1210206/gobierno-aplazar-vigencia-proteccion-datos.html) · [Guía de implementación (Gobierno Digital)](https://wikiguias.digital.gob.cl/datos-personales/guia-practica-implementacion-nueva-ley-datos-personales)

---

## Implementación (17-11-2026): Bloque 1 (FOFAR) y 3.1 (libro completo)

Migración Alembic `0004_fofar_y_libro_completo` (reversible; la bajada se niega si hay datos que
la versión 0003 no puede representar). Pruebas: 279 aprobadas (21 de integración y unitarias
nuevas en `test_api_fofar.py` y `test_horas_habiles.py`, 7 E2E nuevas), bandit sin hallazgos.
**Pendiente:** correr la suite y las migraciones contra PostgreSQL.

| Mejora | Dónde | Regla clave |
|---|---|---|
| Libro D.S. 404/405 art. 18 | `services/libro.py`, `models.AsientosControlados` | Asientos INGRESO (proveedor y documento), MERMA y AJUSTE ligados al lote; cada asiento guarda el saldo. Solo el Q.F. recibe, mermea o ajusta controlados. |
| Datos de la receta retenida | `services/recetas.py` | Prescriptor (nombre y RUT) y domicilio del paciente obligatorios con controlados; N.º de receta cheque si el medicamento la exige (`requiere_receta_cheque`). |
| Despacho total y oportuno | `services/faltantes.py` | Cada atención es una solicitud: COMPLETA, SIN_STOCK o RECHAZO. Lo que falta por quiebre genera un compromiso de 24 horas hábiles (`domain/horas_habiles.py`, sin fines de semana ni feriados 2026-2027). |
| Reclamos | `services/faltantes.py`, pantalla Pendientes | Canal OIRS, Salud Responde o presencial; se cierran con acta de recepción y solo después de entregar el compromiso. No atingentes salen del indicador. |
| Inventario valorizado | `Lotes.costo_total`, `services/toma_inventario.py` | Toma a ciegas (quien cuenta no ve el sistema); el Q.F. cierra y las diferencias se aplican como AJUSTE (kardex y libro). |
| Actividades farmacéuticas | `services/actividades.py` | Atención farmacéutica, farmacovigilancia (ficha para el SVI del ISP y folio de notificación) y talleres; programación anual. |
| Préstamos (Anexo 1) | `services/prestamos.py` | PRESTAMO_SALIDA por FEFO y PRESTAMO_ENTRADA como lote; los controlados no se prestan. |
| Indicadores y REM A04 J | `services/indicadores.py`, pantalla Indicadores FOFAR | Los 4 indicadores con su meta; REM A04 sección J por medicamento (oportunidad, completitud, días de demora). |

Decisiones tomadas al implementar:
- **Rechazo del paciente** no cuenta como incumplimiento del indicador 1; se informa aparte, como lo
  pide la OT FOFAR.
- **Inventario del indicador 3**: se valoriza al cierre del período reconstruyendo el saldo de cada
  lote desde el kardex (no hay una toma semestral obligatoria en el sistema).
- **Indicador 4**: la meta se evalúa en los cortes (30 de junio y 31 de diciembre); antes se muestra
  como "en curso".
- **RUT de quien retira en el libro**: se mantiene enmascarado (HMAC); el D.S. pide la cédula del
  adquirente, que queda en la receta en papel archivada por folio. Conviene validarlo con el docente.
- **Fechas**: las respuestas de la API ahora incluyen la zona horaria (`reloj.iso_utc`); antes SQLite
  devolvía fechas sin zona y algunas pantallas mostraban 3 horas de más.

### Gráficos (18-11-2026)

Componente `Grafico` propio en `frontend/app.js` (SVG, sin librerías por la CSP): columnas y líneas, una
sola escala, tooltip con mouse y con flechas del teclado, y la tabla de datos debajo de cada gráfico.
Colores: serie azul de la paleta de referencia, validada con el script de la guía de visualización
(daltonismo y contraste >= 3:1) sobre las superficies clara y oscura de la app; el turquesa de la marca
no pasó (poco croma en claro, demasiado claro en oscuro).

| Pantalla | Gráfico | Fuente |
|---|---|---|
| Panel | Entregas por día, últimos 30 días | `GET /api/panel/entregas` |
| Indicadores FOFAR | Despacho oportuno por mes (con meta), merma por mes (con meta), actividades acumuladas vs. programadas | `GET /api/indicadores/fofar/mensual` (sigue el período elegido) |
| Alertas | Valor del stock que vence, por mes (próximos 6) | `GET /api/inventario/vencimientos-por-mes` |
| Kardex de un lote | Saldo del lote, movimiento a movimiento | `GET /api/lotes/{id}/kardex` (ahora devuelve los últimos movimientos) |
