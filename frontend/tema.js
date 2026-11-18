/* Aplica el tema elegido (claro u oscuro) antes de dibujar la página, para
 * que no aparezca un destello con el tema equivocado. Sin elección guardada,
 * se usa el del sistema operativo. Va en un archivo aparte porque la CSP
 * (script-src 'self') no permite scripts en línea. */
(function () {
  "use strict";
  try {
    var tema = localStorage.getItem("sisgef_tema");
    if (tema === "claro") document.documentElement.setAttribute("data-theme", "light");
    else if (tema === "oscuro") document.documentElement.setAttribute("data-theme", "dark");
  } catch (_) { /* almacenamiento no disponible: se usa el tema del sistema */ }
})();
