# CLAUDE.md – Proyecto Integrado SISGEF-Asistencial

Contexto para sesiones futuras de Claude Code. Responder siempre en español.

## Qué es
Proyecto académico INACAP (equipo: Joaquín Figueroa y Alejandro Fernández): sistema web para la
farmacia asistencial de un CESFAM. Dispensación con FEFO y unidosis, libro digital de controlados
encadenado por hash, vencimientos y mermas, y permisos por rol.

## Documentos
- `Proyecto Farmacias.pdf`: enunciado del proyecto.
- `Proyecto_Integrado_Informe_2_3.docx`: Informe 2 entregado (plantilla INACAP). No modificarlo; las versiones nuevas van en archivos aparte.
- `RubricaEva3.txt`: rúbrica de la evaluación final (implementación, pruebas, informe).
- `Proyecto_Integrado_Informe_3_base.docx` / `.pdf`: Informe 3 versión base con la retroalimentación aplicada. **No editarlo a mano**: se regenera con `python docs/informe/construir_informe.py` (python-docx) y el PDF con `python3 docs/informe/exportar_pdf.py` (python del sistema, usa LibreOffice/UNO). Los diagramas son PlantUML en `docs/diagramas/` (`./renderizar.sh`, requiere Java y Graphviz).
- `docs/AVANCE.md`: avance v0.3.0, retroalimentación del profesor, discrepancias y pendientes. **Leerlo primero.**

## Código (creado el 17/11/2026, v0.3.0)
- `backend/app`: capas `domain` → `repositories` / `services` → `api`, más `security`. El dominio no importa nada externo.
- `frontend/`: React 18 + htm sin compilación (no hay Node.js en la máquina). Las librerías están en `frontend/vendor/`.
- Instalación y comandos: `README.md`.

## Reglas del proyecto
- Nunca se hace `DELETE` sobre datos de negocio: se usa baja lógica, anulación con motivo y kardex (`movimientos_stock`).
- `asientos_controlados` y `movimientos_stock` son de solo inserción (triggers).
- Todo cambio de stock pasa por `services/inventario.mover_stock`.
- Antes de dar algo por terminado, ejecutar las pruebas también contra PostgreSQL (Podman). SQLite oculta errores de `FOR UPDATE` y de triggers.

## Entorno de la máquina
Fedora, Python 3.15. Sin Node, sin Docker y sin `gh`. Hay Podman, Graphviz, Java, LibreOffice y Brave (`/usr/bin/brave-browser`, que usa Playwright).
