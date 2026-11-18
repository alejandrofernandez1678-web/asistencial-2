#!/usr/bin/env bash
# Genera las imágenes PNG de todos los diagramas PlantUML en docs/diagramas/png/.
# Requiere Java. Descarga PlantUML la primera vez. Usa Graphviz si está instalado
# (sudo dnf install graphviz); si no, el motor interno de PlantUML.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="1.2025.4"
JAR="herramientas/plantuml.jar"
if [[ ! -f "$JAR" ]]; then
  mkdir -p herramientas
  curl -sSfL -o "$JAR" "https://github.com/plantuml/plantuml/releases/download/v${VERSION}/plantuml-${VERSION}.jar"
fi

if command -v dot >/dev/null 2>&1; then
  export SISGEF_SMETANA=0
else
  echo "Graphviz no está instalado: se usa el motor interno (smetana)."
  export SISGEF_SMETANA=1
fi

mkdir -p png
java -Djava.awt.headless=true -jar "$JAR" -charset UTF-8 -tpng -o png ./*.puml
ls -1 png
