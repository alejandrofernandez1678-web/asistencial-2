"""Genera el Informe 3 (versión base) a partir del Informe 2, aplicando la retroalimentación.

Uso (desde la raíz del repositorio):
    python docs/informe/construir_informe.py

Entrada : Proyecto_Integrado_Informe_2_3.docx            (no se modifica)
Salida  : Proyecto_Integrado_Informe_3_base.docx
Requiere: python-docx y los PNG de docs/diagramas/png (docs/diagramas/renderizar.sh).
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).parent))
from herramientas_docx import (NS, Cuerpo, codigo, figura, filas_de, fuente, leyenda, parrafo,  # noqa: E402
                               reemplazar_imagen, renumerar, tabla, texto, titulo, vineta)

RAIZ = Path(__file__).resolve().parents[2]
ENTRADA = RAIZ / "Proyecto_Integrado_Informe_2_3.docx"
SALIDA = RAIZ / "Proyecto_Integrado_Informe_3_base.docx"
DIAGRAMAS = RAIZ / "docs" / "diagramas" / "png"
IMAGENES = RAIZ / "docs" / "informe" / "imagenes"
EVIDENCIA = RAIZ / "docs" / "informe" / "evidencia" / "salida_pruebas.txt"

doc = Document(ENTRADA)
c = Cuerpo(doc)
P, T = c.parrafo, c.poner_texto


def leyenda_existente(prefijo):
    return c.parrafo(prefijo)


# =============================================================== 1. Formato
# Cada capítulo (Título 1) comienza en una página nueva (retroalimentación: introducción
# y resumen ejecutivo deben ir en una plana diferente).
for el in c.hijos():
    if el.tag != qn("w:p"):
        continue
    ppr = el.find(qn("w:pPr"))
    estilo = ppr.find(qn("w:pStyle")) if ppr is not None else None
    tiene_toc = any(b.get(qn("w:name"), "").startswith("_Toc") for b in el.iter(qn("w:bookmarkStart")))
    if estilo is not None and estilo.get(qn("w:val")) == "Ttulo1" and texto(el).strip() and tiene_toc:
        if ppr.find(qn("w:pageBreakBefore")) is None:
            ppr.insert(1, parse_xml(f"<w:pageBreakBefore {NS}/>"))

# ================================================================ 2. Portada
for t in doc.element.body.iter(qn("w:t")):
    if t.text and t.text.startswith("Informe 2: Planificación"):
        t.text = "Informe 3 (versión base): arquitectura corregida, implementación y pruebas"
    elif t.text and "06/10/2026" in t.text:
        t.text = t.text.replace("06/10/2026", "17/11/2026 (versión base, no final)")

# ============================================================ 3. Introducción
T(P("El objetivo del Informe 2"),
  "Esta versión base del Informe 3 corrige el Informe 2 según la retroalimentación del profesor "
  "(formato, diagramas UML, modelo de datos y justificación de tecnologías) e incorpora la primera "
  "implementación funcional del sistema (versión 0.3.0), con la configuración del entorno paso a paso y "
  "los resultados reales de las pruebas ejecutadas.")

objetivos = [
    "Planificar el proyecto con Scrum, identificando fases, responsables, dependencias y ruta crítica.",
    "Describir la arquitectura con las cinco vistas del modelo 4+1 en notación UML 2.5 estricta y justificar "
    "cada tecnología frente a sus alternativas.",
    "Desarrollar un prototipo interactivo funcional, consistente y adaptable, e integrar la retroalimentación de usuarios.",
    "Diseñar el modelo de datos con campos de control y eliminación lógica, combinando bases estructuradas y no estructuradas.",
    "Definir políticas de autenticación y autorización, amenazas y mitigaciones, y estándares de codificación segura.",
    "Implementar una primera versión funcional del sistema y documentar la configuración del entorno paso a paso.",
    "Ejecutar el plan de pruebas (unitarias, integración, E2E, rendimiento y seguridad) y comparar los resultados "
    "esperados con los obtenidos.",
]
primer_obj = P("Planificar el proyecto con Scrum")
items = [primer_obj]
el = primer_obj
while True:
    el = el.getnext()
    if el is None or texto(el).strip() == "" or "Prrafodelista" not in el.xml:
        break
    items.append(el)
for el, nuevo in zip(items, objetivos):
    T(el, nuevo)
ancla = items[-1]
from copy import deepcopy  # noqa: E402
for nuevo in objetivos[len(items):]:
    copia = deepcopy(items[-1])
    T(copia, nuevo)
    ancla.addnext(copia)
    ancla = copia

T(P("Declaración de transparencia."),
  "**Declaración de transparencia.** Todos los resultados marcados como ejecutados se obtuvieron el 17/11/2026 "
  "sobre el código real del repositorio (versión 0.3.0), con la salida de consola en el Anexo B. La validación "
  "con usuarios del capítulo de prototipo sigue siendo simulada y así se indica. La prueba de carga con k6 y el "
  "despliegue en AWS quedan planificados para los Sprints 5 y 6; para ellos solo se informan metas, nunca resultados.")

# ======================================================== 4. Resumen ejecutivo
T(P("El prototipo v1.1 cubre"),
  "La versión 0.3.0 del sistema implementa completas 6 de las 9 historias de usuario y una séptima en forma "
  "parcial. Los resultados ejecutados son los siguientes:")
T(P("La Tabla 1 resume"),
  "La Tabla 1 resume la evidencia ejecutada por el equipo durante el Sprint 3: cada fila indica el tipo de "
  "verificación y su resultado medido.")
cap = leyenda_existente("Tabla 1.")
c.poner_texto_leyenda(cap, "Resultados ejecutados del Sprint 3")
c.reemplazar_tabla(cap, tabla(["Evidencia ejecutada", "Resultado"], [
    ["Pruebas unitarias de reglas de negocio y seguridad (pytest)", "68 de 68 aprobadas · cobertura del dominio 99 %"],
    ["Pruebas de integración de la API", "37 de 37 en SQLite y 38 de 38 en PostgreSQL 16 (incluye concurrencia)"],
    ["Pruebas E2E sobre la aplicación real (Playwright)", "11 de 11 aprobadas"],
    ["Cobertura total del backend (pytest-cov)", "94 %"],
    ["Análisis estático de seguridad (Bandit 1.9.4)", "0 hallazgos en 1.719 líneas"],
    ["Rendimiento del algoritmo FEFO con 50.000 lotes", "p95 = 1,51 ms, mediana de 3 ejecuciones (meta de la operación completa: 1,5 s)"],
], [5113, 4382]))

# ============================================================ 5. Arquitectura
T(P("El modelo 4+1 de Kruchten"),
  "El modelo 4+1 de Kruchten (1995) describe la arquitectura desde cinco vistas, cada una dirigida a un "
  "interesado distinto. Cada vista se representa con el tipo de diagrama UML que le corresponde. Para que el tipo "
  "de cada diagrama sea inequívoco, todos se dibujaron con PlantUML en notación UML 2.5 y llevan el marco UML con "
  "su tipo en la esquina superior izquierda: **uc** (casos de uso), **class** (clases), **stm** (máquina de "
  "estados), **act** (actividades), **sd** (secuencia), **cmp** (componentes), **pkg** (paquetes) y **dep** "
  "(despliegue). La vista de escenarios (+1) une a las otras cuatro, porque cada caso de uso recorre la lógica, "
  "los procesos, el desarrollo y la infraestructura.")
c.reemplazar_tabla(leyenda_existente("Tabla 7."), tabla(
    ["Vista", "Pregunta que responde", "Interesado principal", "Diagramas UML utilizados", "Figuras"], [
        ["Escenarios (+1)", "¿Qué hacen los usuarios con el sistema?", "Q.F., técnicos, bodeguero",
         "Diagrama de casos de uso (uc) y especificación de caso de uso", "Figura 2, Tabla 8"],
        ["Lógica", "¿Qué conceptos y responsabilidades tiene el sistema?", "Equipo de desarrollo",
         "Diagrama de clases (class) y diagrama de máquina de estados (stm)", "Figura 3, Figura 4"],
        ["Procesos", "¿Cómo se comporta el sistema en ejecución y en concurrencia?", "Desarrollo e integración",
         "Diagrama de actividades (act) y diagrama de secuencia (sd)", "Figura 5, Figura 6"],
        ["Desarrollo", "¿Cómo se organiza el software en módulos?", "Desarrolladores, DevSecOps",
         "Diagrama de componentes (cmp) y diagrama de paquetes (pkg)", "Figura 7, Figura 8"],
        ["Física", "¿En qué nodos se ejecuta y cómo se comunican?", "Infraestructura y seguridad",
         "Diagrama de despliegue (dep)", "Figura 10, Figura 11"],
    ], [14, 26, 18, 28, 14]))

T(P("La Figura 2 muestra los cuatro actores"),
  "La Figura 2 muestra los cuatro actores con la figura de actor de UML, ubicados fuera del límite del sistema, "
  "y los doce casos de uso que realizan. El Químico farmacéutico hereda los casos del Técnico de farmacia "
  "(generalización de actores); E1 incluye a E2 («include») y E3 extiende a E1 cuando la receta trae un "
  "controlado («extend»). Los casos E10 a E12 se agregaron para modelar la anulación y la baja lógica que pidió "
  "la revisión del modelo de datos.")
reemplazar_imagen(doc, c.imagen_tras(leyenda_existente("Figura 2.")), DIAGRAMAS / "01_casos_uso.png", 15.5, 14)

T(P("La Figura 3 presenta las clases"),
  "La Figura 3 presenta el modelo de dominio: 19 clases y 2 enumeraciones agrupadas en cuatro paquetes "
  "(pacientes y recetas, inventario, dispensación y controlados, seguridad y auditoría). Todas las clases "
  "muestran sus atributos y los métodos que implementa el código; las líneas indican asociaciones con su "
  "multiplicidad, el rombo relleno indica composición y las flechas punteadas, dependencias «use». Las clases "
  "con estereotipo «planificada» (remesas) se implementan en el Sprint 4.")
cap = leyenda_existente("Figura 3.")
reemplazar_imagen(doc, c.imagen_tras(cap), DIAGRAMAS / "02_clases.png", 16.5, 19.5)
c.reemplazar_tabla(leyenda_existente("Tabla 10."), tabla(["Clase", "Responsabilidad", "Regla que implementa"], [
    ["Lotes", "Conoce su vencimiento y su stock; calcula su estado, descuenta y repone unidades, y se ajusta o "
              "anula si fue mal ingresado.", "RN-01 a RN-03"],
    ["PlanificadorFEFO «service»", "Ordena los lotes dispensables y valida el lote escaneado.", "RN-02, RN-06"],
    ["MovimientosStock", "Kardex de solo inserción: registra cada entrada, salida, ajuste, merma o anulación con su "
                         "saldo.", "Trazabilidad (retroalimentación MER)"],
    ["Medicamentos / Ubicaciones", "Catálogos con baja lógica: darDeBaja() y reactivar() conservan la historia.",
     "Retroalimentación MER"],
    ["Recetas / DetallesReceta", "Controla la vigencia, las cantidades prescritas y entregadas; el detalle no existe "
                                 "sin su receta (composición).", "RN-04"],
    ["Dispensaciones / DetallesDispensacion", "Registra quién entrega, a quién y desde qué lote; genera el rótulo; "
                                              "se anula con motivo y repone el stock.", "RF-01, RF-06"],
    ["LibrosControlados / AsientosControlados", "Asienta cada salida de controlado, la rectifica sin modificarla y "
                                                "verifica la cadena de hashes.", "RN-07, RF-05"],
    ["Mermas", "Registra los retiros por vencimiento, daño o alerta sanitaria.", "RF-03"],
    ["Remesas / DetallesRemesa «planificada»", "Concilia lo recibido contra la orden de compra y origina los lotes.",
     "RN-05, RF-07"],
    ["Usuarios / Roles", "Determinan los permisos de cada funcionario; el usuario se bloquea por intentos fallidos "
                         "y se da de baja sin borrarse.", "RF-11, RNF-04"],
    ["EventosPendientes", "Guarda cada evento de auditoría en la misma transacción hasta su publicación (outbox).",
     "RNF-05"],
], [30, 50, 20]))

T(P("La Figura 4 muestra los estados"),
  "La Figura 4 es un diagrama de máquina de estados UML (stm) de la clase Lotes. Un pseudoestado de elección "
  "decide el estado inicial según los días que faltan para el vencimiento; Vigente y En alerta forman el estado "
  "compuesto Dispensable, y cada transición indica su evento y su guarda entre corchetes. Los ocho estados "
  "coinciden con la enumeración EstadosLote del diagrama de clases y del código.")
cap = leyenda_existente("Figura 4.")
c.poner_texto_leyenda(cap, "Diagrama de máquina de estados (stm) de la clase Lotes (vista lógica)")
reemplazar_imagen(doc, c.imagen_tras(cap), DIAGRAMAS / "03_estados_lote.png", 16, 13)

T(P("La Figura 5 representa el proceso"),
  "La Figura 5 es un diagrama de actividades UML (act) con tres particiones: técnico, sistema y Q.F. Los nodos de "
  "decisión no llevan texto y cada salida indica su guarda entre corchetes; los bucles devuelven el flujo cuando el "
  "RUT o el lote escaneado no son válidos. La rama de controlados se evalúa después del escaneo FEFO, de modo que "
  "un controlado también se valida por lote. La bifurcación final genera el rótulo y publica el evento en paralelo.")
cap = leyenda_existente("Figura 5.")
c.poner_texto_leyenda(cap, "Diagrama de actividades (act) de la dispensación con particiones por actor (vista de procesos)")
reemplazar_imagen(doc, c.imagen_tras(cap), DIAGRAMAS / "04_actividades_dispensacion.png", 13, 19.5)

T(P("La Figura 6 muestra, en orden temporal"),
  "La Figura 6 es el diagrama de secuencia UML (sd) de una dispensación. Muestra en orden los mensajes entre el "
  "técnico, la interfaz, la API, el servicio de dispensación, el planificador FEFO y PostgreSQL, con el fragmento "
  "alt (lote correcto o incorrecto), el fragmento opt (receta con controlado) y el proceso asíncrono que publica la "
  "auditoría en DynamoDB.")
reemplazar_imagen(doc, c.imagen_tras(leyenda_existente("Figura 6.")), DIAGRAMAS / "05_secuencia_dispensacion.png", 16, 15)
for t in doc.element.body.iter(qn("w:t")):
    if t.text and "(pasos 17 a 20)" in t.text:
        t.text = t.text.replace("(pasos 17 a 20)", "(pasos 27 a 29)")

reemplazar_imagen(doc, c.imagen_tras(leyenda_existente("Figura 7.")), DIAGRAMAS / "06_componentes.png", 13, 17.5)
T(P("Las interfaces (círculos) desacoplan"),
  "Las interfaces (círculos) desacoplan los componentes: Dispensación, Inventario y Catálogo usan IReglas e "
  "IRepositorio sin conocer su implementación, por lo que la regla FEFO vive en un solo lugar, el dominio. El "
  "Publicador de auditoría, aún planificado, leerá los eventos pendientes a través de los repositorios y los "
  "enviará a DynamoDB.")

T(P("La Figura 8 muestra los paquetes"),
  "La Figura 8 es un diagrama de paquetes UML (pkg): muestra solo los paquetes reales del código y sus "
  "dependencias «import». A diferencia de la versión anterior, ya no incluye protocolos de red ni elementos de "
  "infraestructura, que pertenecen al diagrama de despliegue de la vista física (Figura 10).")
reemplazar_imagen(doc, c.imagen_tras(leyenda_existente("Figura 8.")), DIAGRAMAS / "07_paquetes.png", 15.5, 14)
T(P("La regla de dependencias es estricta"),
  "La regla de dependencias es estricta: el paquete domain no importa ningún otro, por lo que las reglas de negocio "
  "se prueban sin base de datos ni nube. Por eso las 68 pruebas unitarias se ejecutan en menos de un segundo.")

T(P("La Figura 11 muestra la arquitectura de red"),
  "La Figura 11 detalla la red en AWS: la VPC 10.0.0.0/16 con seis subredes repartidas en dos zonas de "
  "disponibilidad, el Internet Gateway, un NAT Gateway por zona, la tabla de rutas de cada subred, los grupos de "
  "seguridad con sus puertos y los VPC Endpoints. La ⟦Tabla:red⟧ resume esa configuración.")
reemplazar_imagen(doc, c.imagen_tras(leyenda_existente("Figura 11.")), DIAGRAMAS / "08_red_aws.png", 16.5, 14)

fuente_t11 = c.parrafo("Fuente:", despues_de=leyenda_existente("Tabla 11."))
c.insertar_despues(
    fuente_t11,
    parrafo("La ⟦Tabla:red⟧ detalla cada subred: su zona, su bloque CIDR, su tabla de rutas, los recursos que aloja "
            "y el grupo de seguridad que controla el tráfico de entrada.", mantener=True),
    leyenda("Tabla", "red", "Subredes, tablas de rutas y grupos de seguridad de la VPC"),
    tabla(["Subred", "Zona", "CIDR", "Tabla de rutas", "Recursos", "Grupo de seguridad (entrada)"], [
        ["Pública a", "us-east-1a", "10.0.0.0/24", "0.0.0.0/0 → Internet Gateway", "ALB, NAT Gateway a",
         "sg-alb: TCP 443 solo desde CloudFront"],
        ["Pública b", "us-east-1b", "10.0.1.0/24", "0.0.0.0/0 → Internet Gateway", "ALB, NAT Gateway b", "sg-alb"],
        ["Privada app a", "us-east-1a", "10.0.10.0/24", "0.0.0.0/0 → NAT a; S3 y DynamoDB → VPC Endpoint",
         "EC2 API a", "sg-app: TCP 8000 solo desde sg-alb"],
        ["Privada app b", "us-east-1b", "10.0.11.0/24", "0.0.0.0/0 → NAT b; S3 y DynamoDB → VPC Endpoint",
         "EC2 API b", "sg-app"],
        ["Privada datos a", "us-east-1a", "10.0.20.0/24", "Solo local (sin salida a internet)", "RDS primaria",
         "sg-db: TCP 5432 solo desde sg-app"],
        ["Privada datos b", "us-east-1b", "10.0.21.0/24", "Solo local (sin salida a internet)", "RDS standby", "sg-db"],
    ], [14, 12, 13, 25, 15, 21]),
    fuente(),
    parrafo("Las reglas de salida de sg-app solo permiten TCP 5432 hacia sg-db y HTTPS 443 hacia los VPC Endpoints y "
            "el NAT Gateway; las subredes de datos no tienen ruta a internet. Las ACL de red mantienen la "
            "configuración por defecto, porque el control fino se hace con los grupos de seguridad, que tienen estado."),
)

# =========================================================== 6. Tecnologías
T(P("La Tabla 13 presenta las tecnologías"),
  "La Tabla 13 presenta las tecnologías seleccionadas por capa: por qué se eligió cada una, qué alternativa se "
  "evaluó y por qué se descartó, y la necesidad futura que permite cubrir.")
alternativas = [
    "Angular: más pesado y con mayor curva de aprendizaje; Vue: menos experiencia del equipo. En el avance se usa "
    "React sin compilación porque el equipo aún no instala Node.js.",
    "Django: incluye ORM y plantillas que una API no necesita; Node/Express: el equipo domina Python y pytest.",
    "SQL escrito a mano: mayor riesgo de inyección y sin migraciones versionadas.",
    "MySQL: CHECK y triggers más limitados y sin pgcrypto; una base NoSQL no garantiza la integridad del stock.",
    "Guardar la auditoría en PostgreSQL: compite con la operación transaccional; MongoDB Atlas: servicio fuera de AWS.",
    "Guardar archivos en la base: la hace crecer y encarece los respaldos.",
    "Autenticación propia: obliga a almacenar credenciales y construir MFA; Auth0: servicio externo con costo.",
    "AWS Lambda: arranque en frío y conexiones a PostgreSQL más complejas; ECS Fargate: mayor costo en AWS Academy.",
    "Terraform: requiere estado remoto y no siempre se permite en Learner Lab; consola manual: no es reproducible.",
    "Prometheus y Grafana: más infraestructura que mantener para un equipo de dos personas.",
    "GitLab CI o Jenkins: el repositorio ya está en GitHub y Jenkins exige un servidor propio.",
    "Lector con SDK propietario: requiere drivers e integración por modelo.",
]
cap = leyenda_existente("Tabla 13.")
c.poner_texto_leyenda(cap, "Tecnologías: justificación, alternativa evaluada y necesidad futura")
viejas = filas_de(c.siguiente(cap))
c.reemplazar_tabla(cap, tabla(["Capa", "Tecnología", "Por qué se eligió", "Alternativa evaluada y por qué se descartó",
                               "Necesidad futura que cubre"],
                              [[f[0], f[1], f[2], alt, f[3]] for f, alt in zip(viejas, alternativas)],
                              [12, 17, 25, 28, 18]))

T(P("La Tabla 14 lista las herramientas"),
  "La Tabla 14 lista las herramientas que usa el equipo para gestionar, versionar, diagramar, probar y documentar "
  "el proyecto, y la razón de cada elección.")
c.poner_texto_leyenda(leyenda_existente("Tabla 14."), "Herramientas de soporte del proyecto y razón de su elección")
c.reemplazar_tabla(leyenda_existente("Tabla 14."), tabla(["Propósito", "Herramienta", "Por qué la elegimos"], [
    ["Gestión del backlog y sprints", "GitHub Projects (tablero Kanban por sprint)",
     "Integrado al repositorio: cada tarjeta se enlaza con su issue y su pull request; Trello o Jira separarían el "
     "tablero del código."],
    ["Control de versiones y revisión", "Git + GitHub (pull requests y protección de rama principal)",
     "Estándar de la industria: historial auditable, una rama por historia y revisión obligatoria antes de integrar."],
    ["Diseño de diagramas", "PlantUML con Graphviz",
     "Diagramas como texto: se versionan junto al código, respetan la notación UML y se regeneran con un comando."],
    ["Pruebas", "pytest, pytest-cov, Playwright, k6",
     "pytest es el estándar de Python y comparte lenguaje con el backend; Playwright prueba en un navegador real; "
     "k6 define los umbrales de carga como código."],
    ["Seguridad", "Bandit, Semgrep, Gitleaks, pip-audit, Trivy, OWASP ZAP",
     "Cubren el código propio, los secretos, las dependencias, las imágenes y la aplicación en ejecución; son "
     "gratuitas y se integran en CI."],
    ["Entorno local", "Podman (PostgreSQL 16 en contenedor)",
     "Reproduce la base de producción sin instalarla en el equipo; funciona sin privilegios de administrador y es "
     "compatible con Docker Compose."],
    ["Documentación", "Markdown (README, ADR) y OpenAPI generado por FastAPI",
     "Se versiona con el código; la documentación de la API se genera desde el código y no se desactualiza."],
], [22, 30, 48]))

# ========================================================= 7. Modelo de datos
T(P("La Figura 20 presenta el modelo"),
  "La Figura 20 presenta el modelo entidad-relación de la base PostgreSQL. Respecto del Informe 2 incorpora los "
  "campos de control (⚙) en todas las tablas de negocio, los campos de baja lógica (⌫) en los catálogos, los "
  "estados de anulación de lotes y dispensaciones, y la nueva tabla movimientos_stock (kardex). Las tablas en rojo "
  "son de solo inserción y las de color ámbar se implementan en el Sprint 4.")
cap = leyenda_existente("Figura 20.")
c.poner_texto_leyenda(cap, "Modelo entidad-relación (notación pata de gallo): 18 tablas con claves, campos de "
                           "control y eliminación lógica")
reemplazar_imagen(doc, c.imagen_tras(cap), DIAGRAMAS / "09_mer.png", 16, 20.5)

c.reemplazar_tabla(leyenda_existente("Tabla 21."), tabla(["Tabla", "Descripción", "Claves y restricciones relevantes"], [
    ["usuarios / roles", "Funcionarios y perfiles de acceso.",
     "UQ rut; FK id_rol; hash de contraseña y de PIN; bloqueo por intentos; baja lógica."],
    ["pacientes", "Beneficiarios de la dispensación.", "UQ rut_hmac (HMAC-SHA256); el RUT solo se muestra enmascarado."],
    ["programas_salud / pacientes_programas", "Programas GES y crónicos; relación N:M con los pacientes.",
     "PK compuesta (id_paciente, id_programa)."],
    ["medicamentos", "Productos con unidades por envase y tipo de control.",
     "UQ codigo; FK id_programa; CHECK unidades_envase > 0; baja lógica."],
    ["ubicaciones", "Casilleros, estantes y caja de seguridad.",
     "UQ codigo; baja lógica; los controlados solo se guardan en CAJA_SEGURIDAD."],
    ["lotes", "Existencias por lote, vencimiento y casillero.",
     "UQ (id_medicamento, codigo_lote); CHECK unidades_disp ≥ 0; estado DISPONIBLE, ALERTA_SANITARIA, MERMA o "
     "ANULADO (con fecha, responsable y motivo)."],
    ["movimientos_stock (nueva)", "Kardex: cada entrada, salida, ajuste, merma o anulación con su saldo.",
     "CHECK cantidad ≠ 0 y saldo_resultante ≥ 0; solo inserción (trigger)."],
    ["remesas / detalles_remesa", "Ingresos desde CENABAST y sus líneas (Sprint 4).",
     "UQ nro_guia; estado ABIERTA, CONCILIADA o ANULADA."],
    ["recetas / detalles_receta", "Prescripciones y sus líneas.",
     "UQ folio; CHECK cant_prescrita > 0 y cant_entregada ≤ cant_prescrita; estado PENDIENTE, PARCIAL, DISPENSADA o ANULADA."],
    ["dispensaciones / detalles_dispensacion", "Entregas, quién retira y lote usado en cada línea.",
     "UQ clave_idempotencia; estado VIGENTE o ANULADA (con fecha, responsable y motivo); FK id_lote (lote → paciente)."],
    ["asientos_controlados", "Asientos del libro digital de controlados.",
     "Solo inserción; tipo SALIDA o RECTIFICACION; id_asiento_origen apunta al asiento corregido; UQ hash_actual."],
    ["mermas", "Retiros de lotes vencidos, dañados o con alerta sanitaria.", "FK id_lote e id_usuario; CHECK cantidad > 0."],
    ["eventos_pendientes", "Bandeja de salida de eventos de auditoría (patrón outbox).",
     "Se escribe en la misma transacción; publicado_en marca su envío a DynamoDB."],
], [26, 32, 42]))

ultimo_integridad = P("Auditoría sin pérdida (outbox)")
copia = deepcopy(ultimo_integridad)
T(copia, "**Sin eliminación física:** ninguna operación del sistema ejecuta DELETE sobre datos de negocio. Los "
         "catálogos se dan de baja con activo = false, las dispensaciones y los lotes se anulan con motivo, y toda "
         "corrección de stock queda en el kardex (sección 7.7).")
ultimo_integridad.addnext(copia)

T(P("El Código 1 muestra la creación"),
  "El Código 1 muestra la creación de tres tablas clave: lotes, con sus campos de control y de anulación; "
  "movimientos_stock (kardex); y la protección de solo inserción que comparten el kardex y el libro de controlados.")
cap = leyenda_existente("Código 1.")
c.poner_texto_leyenda(cap, "Extracto del DDL: lotes, movimientos_stock (kardex) y protección de solo inserción")
fin = P("El Código 2 muestra")
c.eliminar_entre(cap, fin)
c.insertar_despues(cap, codigo([
    "CREATE TABLE lotes (",
    "  id_lote             BIGSERIAL PRIMARY KEY,",
    "  id_medicamento      BIGINT NOT NULL REFERENCES medicamentos ON DELETE RESTRICT,",
    "  codigo_lote         VARCHAR(40) NOT NULL,",
    "  fecha_vencimiento   DATE NOT NULL,",
    "  unidades_ingresadas INTEGER NOT NULL CHECK (unidades_ingresadas > 0),",
    "  unidades_disp       INTEGER NOT NULL CHECK (unidades_disp >= 0),",
    "  id_ubicacion        BIGINT NOT NULL REFERENCES ubicaciones ON DELETE RESTRICT,",
    "  estado              VARCHAR(20) NOT NULL DEFAULT 'DISPONIBLE'",
    "                      CHECK (estado IN ('DISPONIBLE','ALERTA_SANITARIA','MERMA','ANULADO')),",
    "  fecha_anulacion     TIMESTAMPTZ,",
    "  anulado_por         BIGINT REFERENCES usuarios,",
    "  motivo_anulacion    VARCHAR(250),",
    "  creado_en           TIMESTAMPTZ NOT NULL DEFAULT now(),   -- campos de control",
    "  creado_por          BIGINT REFERENCES usuarios,",
    "  actualizado_en      TIMESTAMPTZ,",
    "  actualizado_por     BIGINT REFERENCES usuarios,",
    "  UNIQUE (id_medicamento, codigo_lote)",
    ");",
    "CREATE INDEX ix_lotes_fefo ON lotes (id_medicamento, fecha_vencimiento) WHERE unidades_disp > 0;",
    "",
    "CREATE TABLE movimientos_stock (                          -- kardex",
    "  id_movimiento    BIGSERIAL PRIMARY KEY,",
    "  id_lote          BIGINT NOT NULL REFERENCES lotes ON DELETE RESTRICT,",
    "  tipo             VARCHAR(30) NOT NULL CHECK (tipo IN ('INGRESO','DISPENSACION',",
    "                   'ANULACION_DISPENSACION','MERMA','AJUSTE','ANULACION_LOTE')),",
    "  cantidad         INTEGER NOT NULL CHECK (cantidad <> 0),",
    "  saldo_resultante INTEGER NOT NULL CHECK (saldo_resultante >= 0),",
    "  motivo           VARCHAR(250),",
    "  id_usuario       BIGINT NOT NULL REFERENCES usuarios,",
    "  fecha_hora       TIMESTAMPTZ NOT NULL DEFAULT now()",
    ");",
    "",
    "CREATE FUNCTION fn_solo_insercion() RETURNS trigger AS $$",
    "BEGIN RAISE EXCEPTION '% es de solo insercion', TG_TABLE_NAME",
    "  USING ERRCODE = 'integrity_constraint_violation'; END; $$ LANGUAGE plpgsql;",
    "CREATE TRIGGER tg_movimientos_inmutable BEFORE UPDATE OR DELETE ON movimientos_stock",
    "  FOR EACH ROW EXECUTE FUNCTION fn_solo_insercion();",
    "CREATE TRIGGER tg_asientos_inmutable BEFORE UPDATE OR DELETE ON asientos_controlados",
    "  FOR EACH ROW EXECUTE FUNCTION fn_solo_insercion();",
    "REVOKE UPDATE, DELETE ON movimientos_stock, asientos_controlados FROM app_sisgef;",
]))

# Nueva sección al final del capítulo de datos (no altera la numeración 7.1 a 7.6)
tabla_criterio = c.siguiente(leyenda_existente("Tabla 22."))
fuente_criterio = c.parrafo("Fuente:", despues_de=tabla_criterio)
c.insertar_despues(
    fuente_criterio,
    titulo("Campos de control y eliminación lógica", 2),
    parrafo("En una farmacia asistencial ningún registro puede desaparecer: la normativa exige reconstruir quién "
            "entregó qué lote a qué paciente, y un medicamento descontinuado sigue apareciendo en recetas antiguas. "
            "Por eso el modelo no elimina filas: cada corrección deja rastro con fecha, responsable y motivo."),
    parrafo("La ⟦Tabla:bajas⟧ responde cómo se da de baja cada tipo de registro, qué campos lo registran y qué "
            "prueba automatizada lo verifica.", mantener=True),
    leyenda("Tabla", "bajas", "Cómo se da de baja, se anula o se corrige cada registro"),
    tabla(["Situación", "Cómo se resuelve", "Campos que lo registran", "Prueba"], [
        ["Trazabilidad de cada fila", "Toda tabla de negocio registra quién y cuándo la creó y la modificó.",
         "creado_en, creado_por, actualizado_en, actualizado_por", "Todas"],
        ["Dar de baja un producto (medicamento)", "Baja lógica con motivo; no se permite si tiene stock "
         "dispensable; se puede reactivar.", "activo, fecha_baja, baja_por, motivo_baja", "IT-37, IT-38, E2E-11"],
        ["Anular una entrega (equivalente a la «venta»)", "Estado ANULADA con motivo; el stock vuelve a cada lote "
         "y la receta queda pendiente otra vez.", "estado, fecha_anulacion, anulada_por, motivo_anulacion; "
         "movimiento ANULACION_DISPENSACION", "IT-22, IT-23, E2E-12"],
        ["Lote con cantidad mal ingresada", "Ajuste con motivo; el kardex muestra la diferencia.",
         "movimientos_stock (tipo AJUSTE, motivo)", "IT-33"],
        ["Lote mal ingresado (lote equivocado)", "Anulación con motivo, solo si nunca se dispensó; si ya se usó, "
         "se corrige con ajuste o merma.", "estado ANULADO, fecha_anulacion, anulado_por, motivo_anulacion",
         "IT-34, IT-35"],
        ["Funcionario que deja el servicio", "Baja lógica; su sesión deja de funcionar de inmediato.",
         "activo, fecha_baja, baja_por, motivo_baja", "IT-06"],
        ["Error en el libro de controlados", "Asiento de RECTIFICACION encadenado; el asiento original no se toca.",
         "tipo, id_asiento_origen", "IT-24"],
    ], [24, 32, 30, 14]),
    fuente(),
)

# ======================================================== 8. Seguridad (RBAC)
cap = leyenda_existente("Tabla 24.")
tbl24 = c.siguiente(cap)
filas24 = filas_de(tbl24, con_encabezado=True)
filas24[1:] += [
    ["Anular dispensaciones (con motivo)", "—", "Sí", "—", "—"],
    ["Ajustar un lote mal ingresado", "—", "Sí", "Sí", "—"],
    ["Anular un lote mal ingresado", "—", "Sí", "—", "—"],
    ["Dar de baja o reactivar medicamentos", "—", "Sí", "—", "Sí"],
]
c.reemplazar_tabla(cap, tabla(filas24[0], filas24[1:], [36, 16, 16, 16, 16]))

# ================================================= 9. Nuevo capítulo: Implementación
plan_pruebas = P("Plan de pruebas")
comandos = [
    "# 1. Requisitos (Fedora; en Ubuntu usar apt)",
    "sudo dnf install -y python3-pip git podman",
    "",
    "# 2. Código y entorno virtual",
    "git clone https://github.com/alejandrofernandez1678-web/Proyecto-farmacia-asistencial.git",
    "cd Proyecto-farmacia-asistencial/backend",
    "python3 -m venv .venv && source .venv/bin/activate",
    "pip install -r requirements-dev.txt",
    "",
    "# 3. Variables de entorno (dos secretos distintos)",
    "cp .env.ejemplo .env",
    "python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
    "",
    "# 4. (Opcional) PostgreSQL 16 en contenedor",
    "podman compose -f ../compose.yaml up -d",
    "",
    "# 5. Datos de demostración y servidor",
    "python -m app.seed --reiniciar",
    "uvicorn app.main:app --reload            # http://127.0.0.1:8000",
    "",
    "# 6. Pruebas",
    "pytest --cov                             # unitarias + integración + E2E",
    "bandit -c pyproject.toml -r app          # análisis estático de seguridad",
]
c.insertar_despues(
    plan_pruebas.getprevious(),
    titulo("Implementación del sistema", 1),
    parrafo("Este capítulo documenta la primera versión funcional de SISGEF-Asistencial (0.3.0): qué historias "
            "cubre, cómo se organiza el código, cómo se configura el entorno paso a paso y qué patrones de seguridad "
            "implementa. El código está en el repositorio GitHub del equipo, en la rama trabajo-con-claude, con la "
            "etiqueta v0.3.0-avance."),
    titulo("Alcance implementado", 2),
    parrafo("La ⟦Tabla:alcance⟧ muestra el estado de cada historia de usuario en esta versión.", mantener=True),
    leyenda("Tabla", "alcance", "Historias de usuario implementadas en la versión 0.3.0"),
    tabla(["HU", "Caso de uso", "Estado", "Qué se puede hacer hoy"], [
        ["HU-01", "E1 Dispensar receta con unidosis", "Completa",
         "Buscar paciente por RUT, validar la vigencia de 30 días, entregar por unidad y emitir el rótulo."],
        ["HU-04", "E2 Validar lote según FEFO", "Completa",
         "Plan FEFO con lote y casillero; el escaneo de otro lote se bloquea e indica el correcto."],
        ["HU-02", "E3 Despachar controlado y asentar libro", "Completa",
         "Receta retenida, RUT y relación de quien retira, firma del Q.F. con PIN y asiento encadenado por hash."],
        ["HU-05", "E7 Panel por programa", "Completa", "Stock dispensable por programa, unidades por estado y umbral crítico."],
        ["HU-07", "E6 Retirar lote a merma", "Completa", "Estados por vencimiento (60, 30 y 14 días) y merma con motivo."],
        ["HU-06", "E9 Gestionar usuarios y roles", "Completa (sin MFA)",
         "Alta y baja de usuarios, matriz RBAC y bloqueo por intentos fallidos."],
        ["HU-03", "E4 Recepcionar remesa CENABAST", "Parcial",
         "Ingreso de lote con alerta de vencimiento menor a 6 meses; falta la guía de remesa y la conciliación."],
        ["HU-09", "E8 Rastrear lote → pacientes", "Pendiente",
         "El modelo ya lo permite (detalles_dispensacion.id_lote); falta la pantalla."],
        ["HU-08", "E5 Auditar estantería con PDA", "Pendiente", "La vista móvil está lista; falta el flujo de conteo."],
    ], [10, 30, 16, 44]),
    fuente(),
    titulo("Estructura del código", 2),
    parrafo("El repositorio sigue el diagrama de paquetes (Figura 8). Cada capa tiene una responsabilidad única:"),
    vineta("`backend/app/domain`: reglas de negocio puras (RUT, estados de lote, FEFO, recetas y libro con hash), sin "
           "dependencias externas."),
    vineta("`backend/app/services`: casos de uso (dispensar, anular, ingresar, ajustar y anular lotes, mermas y bajas); "
           "cada uno es una transacción atómica."),
    vineta("`backend/app/repositories` y `models.py`: acceso a PostgreSQL con SQLAlchemy, restricciones CHECK y "
           "triggers de solo inserción."),
    vineta("`backend/app/security` y `api`: hash de credenciales, tokens JWT, matriz RBAC, validación de entrada con "
           "Pydantic y routers FastAPI."),
    vineta("`frontend`: interfaz web en React 18 que sigue la guía de estilo del prototipo (Tabla 16)."),
    vineta("`backend/tests`: pruebas unitarias, de integración y E2E; `docs/diagramas`: fuentes PlantUML de todas las figuras."),
    titulo("Configuración del entorno de trabajo", 2),
    parrafo("El entorno se configura en seis pasos y no requiere instalar PostgreSQL ni Docker: por defecto usa SQLite, "
            "y para probar contra PostgreSQL 16 basta un contenedor de Podman. Los secretos nunca se escriben en el "
            "código: se leen de variables de entorno (archivo .env, excluido del repositorio). El ⟦Código:entorno⟧ "
            "resume los comandos y la ⟦Tabla:variables⟧ describe cada variable.", mantener=True),
    leyenda("Código", "entorno", "Configuración del entorno paso a paso (README del repositorio)"),
    codigo(comandos),
    parrafo(""),
    leyenda("Tabla", "variables", "Variables de entorno del sistema"),
    tabla(["Variable", "Uso", "Valor por defecto"], [
        ["SISGEF_ENTORNO", "desarrollo, pruebas o produccion; en producción se desactiva la documentación interactiva.",
         "desarrollo"],
        ["SISGEF_DATABASE_URL", "Conexión a la base de datos (SQLite o PostgreSQL).", "sqlite:///./sisgef.db"],
        ["SISGEF_JWT_SECRETO", "Firma de los tokens de sesión.", "Obligatoria en producción"],
        ["SISGEF_HMAC_SECRETO", "Huella del RUT para buscar pacientes sin guardarlo en claro.", "Obligatoria en producción"],
        ["SISGEF_JWT_MINUTOS", "Duración de la sesión.", "30"],
        ["SISGEF_PBKDF2_ITERACIONES", "Costo del hash de contraseñas y PIN.", "600000"],
    ], [30, 50, 20]),
    fuente(),
    titulo("Seguridad implementada en el código", 2),
    parrafo("La ⟦Tabla:patrones⟧ relaciona cada patrón de seguridad implementado con el lugar del código donde vive y "
            "la amenaza que mitiga (capítulo de seguridad del software).", mantener=True),
    leyenda("Tabla", "patrones", "Patrones de seguridad implementados"),
    tabla(["Patrón", "Dónde", "Amenaza que mitiga"], [
        ["Validación estricta de entrada (tipos, largos, rangos; campos desconocidos rechazados)", "api/schemas.py",
         "Inyección, asignación masiva"],
        ["Consultas parametrizadas con el ORM", "repositories, services", "Inyección SQL"],
        ["Hash PBKDF2-SHA256 con 600.000 iteraciones y sal aleatoria; comparación en tiempo constante",
         "security/claves.py", "Robo de credenciales, ataques de tiempo"],
        ["JWT HS256 de 30 minutos; se rechazan tokens alterados, expirados y alg=none", "security/tokens.py",
         "Suplantación de sesión"],
        ["Bloqueo tras 5 intentos fallidos y mensaje genérico", "services/autenticacion.py",
         "Fuerza bruta, enumeración de usuarios"],
        ["RBAC del lado del servidor con mínimo privilegio y auditoría de accesos denegados", "security/rbac.py, api/deps.py",
         "Escalamiento de privilegios"],
        ["RUT del paciente como HMAC más versión enmascarada; búsqueda por POST", "models.py, api", "Exposición de datos "
         "personales (Ley 19.628)"],
        ["Libro de controlados y kardex con hash encadenado y triggers de solo inserción", "domain/libro.py, models.py",
         "Alteración de registros legales"],
        ["Transacciones atómicas, SELECT … FOR UPDATE e idempotencia", "services/dispensacion.py",
         "Doble descuento, stock negativo"],
        ["Cabeceras CSP, X-Frame-Options y nosniff; sin scripts de terceros", "main.py", "XSS, clickjacking"],
        ["Errores sin detalles internos y secretos solo en variables de entorno", "main.py, config.py",
         "Fuga de información y de secretos"],
    ], [46, 24, 30]),
    fuente(),
    titulo("Interfaz implementada", 2),
    parrafo("Las figuras siguientes son capturas de la aplicación real (no del prototipo). La ⟦Figura:ui_fefo⟧ "
            "muestra el bloqueo FEFO: el técnico escaneó un lote más nuevo y el sistema indica el lote y el casillero "
            "correctos.", mantener=True),
    leyenda("Figura", "ui_fefo", "Dispensación: la tira FEFO marca el lote a entregar y bloquea un lote más nuevo"),
    figura(doc, str(IMAGENES / "ui_fefo_bloqueo.png"), 14.5, 17),
    fuente("aplicación SISGEF-Asistencial v0.3.0."),
    parrafo("La ⟦Figura:ui_lotes⟧ muestra la gestión de lotes con sus estados por vencimiento y las acciones de "
            "kardex, ajuste, merma y anulación, y la ⟦Figura:ui_baja⟧ muestra cómo el sistema impide dar de baja un "
            "medicamento que todavía tiene stock dispensable.", mantener=True),
    leyenda("Figura", "ui_lotes", "Lotes: estados por vencimiento y acciones de corrección sin eliminar registros"),
    figura(doc, str(IMAGENES / "ui_lotes.png"), 15, 17),
    fuente("aplicación SISGEF-Asistencial v0.3.0."),
    leyenda("Figura", "ui_baja", "Baja lógica de un medicamento: se exige motivo y se rechaza si tiene stock"),
    figura(doc, str(IMAGENES / "ui_baja_logica.png"), 14.5, 12),
    fuente("aplicación SISGEF-Asistencial v0.3.0."),
)

# ========================================================= 10. Plan de pruebas
c.reemplazar_tabla(leyenda_existente("Tabla 28."), tabla(
    ["Nivel", "Objetivo", "Herramientas", "Criterio de salida", "Estado"], [
        ["Unitarias", "Verificar cada regla de negocio de forma aislada.", "pytest, pytest-cov",
         "100 % aprobadas; cobertura ≥ 80 % en dominio", "Ejecutada: 68/68, cobertura del dominio 99 %"],
        ["Integración", "Verificar API y base de datos juntas, incluida la concurrencia.",
         "pytest + TestClient; PostgreSQL 16 en Podman", "100 % aprobadas; sin stock negativo en concurrencia",
         "Ejecutada: 37/37 en SQLite y 38/38 en PostgreSQL"],
        ["E2E", "Verificar flujos completos desde la interfaz.", "Playwright", "Flujos críticos aprobados",
         "Ejecutada sobre la aplicación real: 11/11"],
        ["Rendimiento", "Verificar RNF-01 (p95 ≤ 1,5 s con 30 usuarios).", "Benchmark en Python; k6",
         "p95 ≤ 1,5 s; error < 1 %", "Parcial: FEFO medido; carga con k6 planificada (Sprint 6)"],
        ["Seguridad", "Detectar vulnerabilidades en código, dependencias y aplicación.",
         "Bandit, pytest; Semgrep, Gitleaks, Trivy, OWASP ZAP", "0 hallazgos altos o críticos",
         "Parcial: Bandit y pruebas de seguridad ejecutadas; el resto en CI"],
        ["Aceptación (UAT)", "Confirmar que se cumplen los criterios de las HU con usuarios reales.",
         "Guion de UAT, pruebas exploratorias", "Acta firmada por el Q.F.", "Planificada (Sprint 6)"],
    ], [13, 24, 21, 21, 21]))

for el in c.hijos():
    if el.tag == qn("w:p") and texto(el) == "Pruebas unitarias (ejecutadas)":
        intro_ut = el.getnext()
        break
T(intro_ut, "Las reglas de negocio viven en el paquete domain del backend y se prueban con pytest, sin base de datos. "
            "Las pruebas cubren los valores límite de cada regla (por ejemplo, 30 y 31 días o 14 y 15 días), que es "
            "donde suelen aparecer los errores. Se agregaron pruebas unitarias de seguridad para el hash de "
            "credenciales, los tokens y la matriz RBAC.")
cap = leyenda_existente("Tabla 29.")
c.poner_texto_leyenda(cap, "Resultados de las pruebas unitarias (ejecutadas el 17/11/2026)")
c.reemplazar_tabla(cap, tabla(["Grupo", "Casos", "Qué verifica", "HU / RF", "Resultado"], [
    ["Validación de RUT", "UT-01, UT-02 (10)", "RUT válidos con K y con puntos, dígito incorrecto, formato inválido, "
                                               "inyección, texto excesivo y enmascarado.", "RF-04", "10/10 ✓"],
    ["Estados de vencimiento", "UT-03 (10)", "Límites de 14, 30 y 60 días, agotado y estados registrados "
                                             "(alerta sanitaria, merma, anulado).", "RF-03", "10/10 ✓"],
    ["Algoritmo FEFO", "UT-04 a UT-07 (6)", "Omite lotes no dispensables, reparte entre lotes, stock insuficiente, "
                                            "cantidad inválida y desempate.", "RF-02", "6/6 ✓"],
    ["Validación del escaneo", "UT-08 a UT-11 (5)", "Lote más nuevo, lote por vencer, lote de otro medicamento, lote "
                                                    "inexistente y lote correcto.", "RF-02", "5/5 ✓"],
    ["Unidosis y rótulo", "UT-12, UT-13 (4)", "Detección de fraccionamiento y datos obligatorios del rótulo.", "RF-01", "4/4 ✓"],
    ["Receta y recepción", "UT-14, UT-15 (10)", "Vigencia de 30 días, fecha futura, pendiente y alerta de 6 meses "
                                               "en sus límites.", "RF-06, RF-07", "10/10 ✓"],
    ["Libro de controlados", "UT-16 a UT-18 (4)", "Cadena íntegra, alteración y eliminación de asientos detectadas.",
     "RF-05", "4/4 ✓"],
    ["Seguridad", "UT-S (19)", "Hash con sal, hashes malformados, tokens alterados, expirados y alg=none, y matriz RBAC.",
     "RNF-03, RNF-04", "19/19 ✓"],
    ["Total", "68", "Cobertura del paquete domain: 99 %", "", "68/68 ✓"],
], [20, 16, 40, 12, 12]))
T(P("El Código 6 muestra dos de las pruebas"),
  "El Código 6 muestra dos de las pruebas unitarias ejecutadas: el bloqueo por FEFO y la detección de una "
  "alteración en el libro de controlados.")
cap = leyenda_existente("Código 6.")
c.eliminar_entre(cap, P("Pruebas E2E sobre el prototipo"))
c.insertar_despues(cap, codigo([
    "def test_ut08_escaneo_lote_mas_nuevo_bloqueado():",
    "    with pytest.raises(ReglaNegocioError, match=\"FEFO\") as error:",
    "        _validar(\"L-2507\")",
    "    assert \"L-2502\" in error.value.mensaje and \"B-03\" in error.value.mensaje",
    "",
    "def test_ut17_libro_detecta_alteracion_de_un_asiento():",
    "    asientos = _cadena()",
    "    alterado = AsientoVerificable(2, {**asientos[1].contenido, \"cantidad\": 2},",
    "                                  asientos[1].hash_previo, asientos[1].hash_actual)",
    "    assert verificar_cadena([asientos[0], alterado, asientos[2]]) == (False, 2)",
]))

titulo_e2e = P("Pruebas E2E sobre el prototipo")
T(titulo_e2e, "Pruebas E2E sobre la aplicación (ejecutadas)")
T(titulo_e2e.getnext(), "La Tabla 30 muestra los casos de prueba E2E ejecutados con Playwright sobre la aplicación real "
                        "(servidor FastAPI, base de datos y navegador), su resultado y la evidencia observada.")
cap = leyenda_existente("Tabla 30.")
c.poner_texto_leyenda(cap, "Resultados de las pruebas E2E con Playwright (ejecutadas el 17/11/2026)")
c.reemplazar_tabla(cap, tabla(["ID", "Caso de prueba", "Resultado", "Evidencia"], [
    ["E2E-01", "El ingreso rechaza un RUT con dígito verificador incorrecto.", "Aprobado", "Alerta: dígito verificador; no se muestra el menú."],
    ["E2E-02", "El técnico no ve Libro, Usuarios, Entregas ni Auditoría (RBAC).", "Aprobado", "Menú: Panel, Dispensar, Lotes, Medicamentos."],
    ["E2E-03/04", "Escanear un lote más nuevo se bloquea por FEFO; el lote a 9 días aparece como retiro obligatorio.",
     "Aprobado", "«Entregue L-2502 del casillero B-03»."],
    ["E2E-05", "Los lotes correctos se entregan y generan los rótulos.", "Aprobado", "2 rótulos con lote y paciente."],
    ["E2E-06", "El controlado rechaza un PIN incorrecto y con el PIN correcto crea un asiento íntegro.", "Aprobado",
     "«Cadena íntegra: 1 asiento verificado»."],
    ["E2E-07", "La recepción alerta un vencimiento menor a 6 meses.", "Aprobado", "Alerta: vence en 132 días."],
    ["E2E-08", "El acceso fuera de rol se deniega y queda en auditoría.", "Aprobado", "HTTP 403 y evento ACCESO_DENEGADO."],
    ["E2E-09", "La vista PDA de 360 px no tiene desplazamiento horizontal.", "Aprobado", "Ancho del documento: 360 px."],
    ["E2E-10", "Se respeta la preferencia de tema oscuro.", "Aprobado", "Fondo rgb(15, 28, 32)."],
    ["E2E-11", "No se puede dar de baja un medicamento con stock dispensable.", "Aprobado", "«Retírelos a merma antes de darlo de baja»."],
    ["E2E-12", "Una entrega se anula desde la pantalla de entregas.", "Aprobado", "Estado «Anulada» con motivo."],
], [12, 44, 12, 32]))

titulo_it = P("Pruebas de integración (simuladas)")
T(titulo_it, "Pruebas de integración (ejecutadas)")
T(titulo_it.getnext(), "Las pruebas de integración ejercitan la API completa contra una base real, con sus restricciones "
                       "y triggers. Se ejecutan sobre SQLite en cada cambio y sobre PostgreSQL 16 en un contenedor "
                       "Podman, que es el motor de producción; solo en PostgreSQL se puede probar el bloqueo por filas.")
T(titulo_it.getnext().getnext(), "La Tabla 31 resume los casos de integración más relevantes, con el resultado esperado "
                                 "y el obtenido.")
cap = leyenda_existente("Tabla 31.")
c.poner_texto_leyenda(cap, "Casos de prueba de integración (ejecutados sobre PostgreSQL 16)")
c.reemplazar_tabla(cap, tabla(["ID", "Caso de prueba", "Resultado esperado", "Resultado obtenido"], [
    ["IT-40", "8 técnicos confirman la misma receta al mismo tiempo.", "Una sola entrega; el stock nunca queda negativo.",
     "Conforme: 1 × 201 y 7 × 422; stock final 30"],
    ["IT-20", "UPDATE o DELETE directo sobre asientos_controlados y movimientos_stock.", "Rechazo del trigger.",
     "Conforme: error de integridad (SQLSTATE 23000)"],
    ["IT-21", "Forzar unidades_disp = -1 en un lote.", "Rechazo por CHECK.", "Conforme"],
    ["IT-04", "Token ausente o falsificado.", "401 sin datos.", "Conforme"],
    ["IT-03", "Cinco intentos de ingreso fallidos.", "Cuenta bloqueada (423) aunque luego la clave sea correcta.", "Conforme"],
    ["IT-05", "Accesos fuera de rol.", "403 y evento ACCESO_DENEGADO.", "Conforme"],
    ["IT-16", "Dispensación con una línea válida y otra inválida.", "No se descuenta ninguna (atomicidad).", "Conforme"],
    ["IT-17", "Repetir una dispensación con la misma clave de idempotencia.", "Misma respuesta, sin doble descuento.",
     "Conforme"],
    ["IT-22", "Anular una dispensación.", "Stock repuesto, receta pendiente y kardex con ANULACION_DISPENSACION.", "Conforme"],
    ["IT-24", "Anular la entrega de un controlado.", "Asiento de RECTIFICACION y cadena íntegra.", "Conforme"],
    ["IT-34/35", "Anular un lote mal ingresado y uno ya dispensado.", "El primero queda ANULADO; el segundo se rechaza.",
     "Conforme"],
    ["IT-38", "Dar de baja y reactivar un medicamento.", "Deja de listarse, no admite lotes y se conserva en el historial.",
     "Conforme"],
    ["IT-pend-1", "Pedir una receta de otro establecimiento (IDOR).", "404 y evento de auditoría.",
     "Pendiente: multi-establecimiento en Sprint 5"],
    ["IT-pend-2", "Caída de DynamoDB durante una dispensación.", "El evento queda pendiente y se reintenta.",
     "Pendiente: publicador outbox en Sprint 5"],
], [11, 33, 30, 26]))

T(P("Medición ejecutada del algoritmo FEFO"),
  "Medición ejecutada del algoritmo FEFO con el script tests/rendimiento/medir_fefo.py: inventarios sintéticos de "
  "1.000, 10.000 y 50.000 lotes repartidos entre 50 medicamentos, 200 planificaciones por tamaño y 3 ejecuciones "
  "completas (Python 3.15, Fedora Linux); se informa la mediana de las 3 ejecuciones. Incluso con 50.000 lotes el "
  "cálculo usa menos del 0,2 % de la meta de 1,5 s de la operación completa.")
c.reemplazar_tabla(leyenda_existente("Tabla 32."), tabla(["Lotes en inventario", "p50", "p95"], [
    ["1.000", "0,02 ms", "0,03 ms"], ["10.000", "0,23 ms", "0,26 ms"], ["50.000", "1,34 ms", "1,51 ms"]], [40, 30, 30]))
T(P("La Tabla 33 compara las métricas"),
  "La prueba de carga todavía no se ejecuta. La Tabla 33 deja definidas sus métricas, la meta de cada una y su estado.")
cap = leyenda_existente("Tabla 33.")
c.poner_texto_leyenda(cap, "Métricas de la prueba de carga (planificada)")
c.reemplazar_tabla(cap, tabla(["Métrica", "Meta", "Estado"], [
    ["p95 búsqueda de paciente", "≤ 1,5 s", "Pendiente (Sprint 6)"],
    ["p95 dispensación", "≤ 1,5 s", "Pendiente (Sprint 6)"],
    ["Tasa de error", "< 1 %", "Pendiente (Sprint 6)"],
    ["CPU EC2 promedio", "< 70 %", "Pendiente (Sprint 6)"],
], [45, 25, 30]))

c.reemplazar_tabla(leyenda_existente("Tabla 34."), tabla(["Prueba", "Herramienta", "Tipo", "Resultado"], [
    ["Análisis estático de todo el backend", "Bandit 1.9.4", "Automatizada",
     "Ejecutada: 0 hallazgos en 1.719 líneas (1 falso positivo justificado en el código)"],
    ["Entradas maliciosas (inyección, texto excesivo, campos extra)", "pytest (UT-02, IT-07)", "Automatizada", "Ejecutada: rechazadas"],
    ["Autenticación: tokens alterados, expirados y alg=none; bloqueo por intentos", "pytest", "Automatizada",
     "Ejecutada: todos rechazados"],
    ["Autorización por rol y auditoría de accesos denegados", "pytest (IT-05), Playwright (E2E-08)", "Automatizada",
     "Ejecutada: 403 y evento registrado"],
    ["Inmutabilidad del libro y del kardex", "pytest sobre PostgreSQL (IT-20)", "Automatizada", "Ejecutada: trigger rechaza cambios"],
    ["Cabeceras de seguridad (CSP, X-Frame-Options, nosniff)", "pytest (IT-08)", "Automatizada", "Ejecutada"],
    ["Secretos en el repositorio", "Gitleaks", "Automatizada", "Planificada en CI (.env excluido por .gitignore)"],
    ["Vulnerabilidades en dependencias e imagen", "pip-audit, Trivy", "Automatizada", "Planificada en CI"],
    ["Escaneo dinámico de la aplicación", "OWASP ZAP (baseline)", "Automatizada", "Planificada Sprint 6"],
], [36, 24, 14, 26]))

cap = leyenda_existente("Tabla 35.")
filas35 = filas_de(c.siguiente(cap))
for fila in filas35:
    if fila[0].startswith("Vitest"):
        fila[3] = "Al migrar el frontend a Vite + TypeScript"
    if fila[0].startswith("Testcontainers"):
        fila[0], fila[3] = "PostgreSQL 16 en Podman", "Ejecutada en el Sprint 3; en CI en cada pull request"
c.reemplazar_tabla(cap, tabla(["Herramienta / técnica", "Tipo", "Nivel", "Cuándo se usa"], filas35, [30, 16, 24, 30]))

titulo_def = P("Registro de defectos")
T(titulo_def, "Comparación de resultados esperados y obtenidos")
T(titulo_def.getnext(), "Durante la implementación y las pruebas se compararon los resultados esperados con los "
                        "obtenidos. Las discrepancias encontradas fueron reales y todas se corrigieron; las dos primeras "
                        "solo aparecieron al ejecutar las pruebas sobre PostgreSQL, lo que confirma el valor de probar "
                        "sobre el motor de producción.")
T(titulo_def.getnext().getnext(), "La Tabla 36 registra cada discrepancia, su causa y la corrección aplicada.")
cap = leyenda_existente("Tabla 36.")
c.poner_texto_leyenda(cap, "Discrepancias entre resultados esperados y obtenidos")
tbl36 = c.siguiente(cap)
c.reemplazar_tabla(cap, tabla(["ID", "Esperado", "Obtenido", "Causa", "Corrección"], [
    ["D-01", "La dispensación bloquea la receta con FOR UPDATE en PostgreSQL.",
     "Error «FOR UPDATE cannot be applied to the nullable side of an outer join». En SQLite pasaba.",
     "SQLite ignora FOR UPDATE; el ORM usaba LEFT JOIN en relaciones obligatorias.", "INNER JOIN en relaciones con FK NOT NULL."],
    ["D-02", "Modificar el libro devuelve error de integridad (409).", "PostgreSQL devolvía un error genérico.",
     "El trigger usaba el SQLSTATE por defecto (P0001).", "ERRCODE integrity_constraint_violation."],
    ["D-03", "Un lote de otro medicamento se informa como tal.", "Se informaba «el lote no existe».",
     "El servicio solo buscaba entre los lotes del medicamento.", "Búsqueda global del lote escaneado."],
    ["D-04", "La base de demostración se reinicia.", "El trigger de solo inserción bloqueaba el DROP TABLE.",
     "SQLite borra fila a fila al eliminar una tabla con FK.", "Rutina de reinicio solo para desarrollo."],
    ["D-05", "Las pruebas E2E son estables.", "Error «bad parameter or other API misuse».",
     "La base en memoria compartía una conexión entre hilos.", "Servidor E2E en un proceso aparte con base en archivo."],
    ["D-06", "La interfaz no muestra textos extraños y Escape cierra los diálogos.", "Aparecía «&nbsp;» literal y "
     "Escape no siempre cerraba.", "htm no interpreta entidades HTML; el evento se escuchaba solo en el formulario.",
     "Espaciador CSS y evento a nivel de documento."],
    ["D-07", "Los estados del lote coinciden en diagrama y código.", "El diagrama de estados y la enumeración del "
     "Informe 2 no coincidían.", "Se diseñaron por separado.", "Ocho estados únicos en código y diagramas."],
], [8, 22, 24, 24, 22]))
fuente36 = c.parrafo("Fuente:", despues_de=cap)
c.insertar_despues(
    fuente36,
    parrafo("**Recomendaciones derivadas de la comparación:**"),
    vineta("Ejecutar las pruebas de integración contra PostgreSQL en el pipeline de CI en cada pull request (D-01, D-02): "
           "SQLite no basta para validar bloqueos ni triggers."),
    vineta("Mantener los diagramas como código PlantUML junto al código fuente y revisarlos en cada pull request que "
           "cambie el modelo (D-07)."),
    vineta("Agregar una prueba E2E por cada mensaje de error visible para el usuario (D-03, D-06)."),
    vineta("Definir una alarma de CloudWatch por eventos de auditoría sin publicar cuando exista el publicador outbox."),
)

# ============================================================== 11. Conclusión
conclusiones = [
    "Esta versión base del Informe 3 responde a cada observación del Informe 2. Los capítulos empiezan en una página "
    "nueva; los nueve diagramas de arquitectura se rehicieron en notación UML 2.5 con el marco que declara su tipo; el "
    "diagrama de clases muestra los métodos de todas las clases; el diagrama de paquetes quedó separado del de "
    "despliegue; y la red en AWS detalla subredes, rutas y grupos de seguridad. Cada tecnología y herramienta se "
    "justifica frente a una alternativa concreta.",
    "El modelo de datos incorpora campos de control en todas las tablas y resuelve la eliminación sin borrar nada: "
    "baja lógica de catálogos, anulación con motivo de lotes y dispensaciones, y un kardex de solo inserción que "
    "registra cada corrección. Estas decisiones ya están implementadas y verificadas por pruebas automatizadas.",
    "La versión 0.3.0 implementa seis historias de usuario completas y una parcial, con 116 pruebas aprobadas sobre "
    "SQLite y 106 sobre PostgreSQL 16, 94 % de cobertura y cero hallazgos de Bandit. Las siete discrepancias "
    "encontradas se corrigieron y dejaron recomendaciones concretas. Quedan para los Sprints 4 a 6 la recepción "
    "CENABAST, el rastreo de lotes, la auditoría con PDA, el MFA con Cognito, el despliegue en AWS y la prueba de carga.",
]
conc = P("Conclusión")
parrafos_conc = []
el = conc.getnext()
while el is not None and texto(el).strip() and "Ttulo1" not in el.xml:
    parrafos_conc.append(el)
    el = el.getnext()
for el, nuevo in zip(parrafos_conc, conclusiones):
    T(el, nuevo)

# =============================================================== 12. Anexo B
anexo = P("Anexo B. Evidencia")
T(anexo.getnext(), "El Código 8 reproduce la salida de consola real de las pruebas ejecutadas el 17/11/2026: la suite "
                   "completa con cobertura, la ejecución sobre PostgreSQL 16, el análisis de Bandit y la medición de "
                   "rendimiento del algoritmo FEFO.")
cap = leyenda_existente("Código 8.")
c.poner_texto_leyenda(cap, "Salida de consola de las pruebas ejecutadas (17/11/2026)")
siguientes = []
el = cap.getnext()
while el is not None and el.find(qn("w:pPr")) is not None and el.find(".//" + qn("w:pBdr")) is not None:
    siguientes.append(el)
    el = el.getnext()
c.eliminar(*siguientes)
lineas = [l for l in EVIDENCIA.read_text(encoding="utf-8").splitlines()
          if not re.match(r"^app/.*\s100%$", l)]  # se omiten los módulos con 100 % para acortar
c.insertar_despues(cap, codigo(lineas))

# ============================================================== 13. Glosario
cap = leyenda_existente("Tabla 37.")
tbl37 = c.siguiente(cap)
encabezado37 = filas_de(tbl37, con_encabezado=True)[0]
encabezado37[-1] = "Por qué se usa en el proyecto"
filas37 = filas_de(tbl37) + [
    ["Baja lógica", "Desactivar un registro con fecha, responsable y motivo en lugar de borrarlo.",
     "Conserva la trazabilidad de recetas y dispensaciones antiguas (7.7)."],
    ["Kardex", "Registro cronológico de entradas y salidas de un producto con su saldo.",
     "Cada cambio de stock queda en movimientos_stock (7.7)."],
    ["Marco UML (frame)", "Rectángulo con la etiqueta del tipo de diagrama (uc, class, stm, act, sd, cmp, pkg, dep).",
     "Hace inequívoco a qué diagrama UML corresponde cada figura (4)."],
    ["PlantUML", "Herramienta que genera diagramas UML a partir de texto.",
     "Los diagramas se versionan junto al código y se regeneran con un comando (5.2)."],
    ["Podman", "Motor de contenedores compatible con Docker que funciona sin privilegios de administrador.",
     "Levanta PostgreSQL 16 local para las pruebas de integración (9.4)."],
]
filas37.sort(key=lambda f: f[0].lower())
c.poner_texto_leyenda(cap, f"Glosario técnico ({len(filas37)} términos)")
c.reemplazar_tabla(cap, tabla(encabezado37, filas37, [24, 42, 34]))

# Pie de página y símbolos que la fuente del documento no tiene
for seccion in doc.sections:
    for t in seccion.footer._element.iter(qn("w:t")):
        if t.text and "Informe 2" in t.text:
            t.text = t.text.replace("Informe 2", "Informe 3 (versión base)")
for t in doc.element.body.iter(qn("w:t")):
    if t.text and ("(⚙)" in t.text or "(⌫)" in t.text):
        t.text = t.text.replace(" (⚙)", "").replace(" (⌫)", "")

# ==================================================== 14. Numeración y cierre
# El nuevo capítulo de implementación desplaza el plan de pruebas del capítulo 9 al 10.
for t in doc.element.body.iter(qn("w:t")):
    if t.text:
        t.text = re.sub(r"\(9\.(\d)\)", r"(10.\1)", t.text)

mapa, totales, partidas = renumerar(c)

# Pedir a Word que actualice el índice y los campos al abrir el documento
ajustes = doc.settings.element
if ajustes.find(qn("w:updateFields")) is None:
    ajustes.append(parse_xml(f'<w:updateFields {NS} w:val="true"/>'))

doc.save(SALIDA)
print(f"Generado: {SALIDA}")
print(f"Totales: {totales}")
if partidas:
    print("Revisar referencias partidas entre runs:")
    for p in partidas:
        print("  -", p)
