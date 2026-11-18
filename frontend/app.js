/* SISGEF-Asistencial - interfaz web (React 18 + htm, sin paso de compilación).
 * La seguridad real está en el servidor: aquí los menús se ocultan según el rol,
 * pero cada acción vuelve a validarse en la API (RBAC, FEFO, firma del Q.F.). */
(function () {
  "use strict";
  const { useState, useEffect, useCallback, useRef } = React;
  const html = htm.bind(React.createElement);

  // ------------------------------------------------------------------ API
  let tokenActual = null;
  try { tokenActual = sessionStorage.getItem("sisgef_token"); } catch (_) { /* almacenamiento no disponible */ }
  let alExpirar = () => {};

  function guardarToken(token) {
    tokenActual = token;
    try { token ? sessionStorage.setItem("sisgef_token", token) : sessionStorage.removeItem("sisgef_token"); } catch (_) {}
  }

  async function api(metodo, ruta, cuerpo) {
    const opciones = { method: metodo, headers: {} };
    if (tokenActual) opciones.headers.Authorization = "Bearer " + tokenActual;
    if (cuerpo !== undefined) {
      opciones.headers["Content-Type"] = "application/json";
      opciones.body = JSON.stringify(cuerpo);
    }
    const respuesta = await fetch(ruta, opciones);
    const datos = await respuesta.json().catch(() => ({}));
    if (respuesta.status === 401 && ruta !== "/api/auth/login") { alExpirar(); }
    if (!respuesta.ok) {
      let mensaje = datos.detail;
      if (Array.isArray(mensaje)) mensaje = mensaje.map((d) => d.msg).join(" · ");
      const error = new Error(mensaje || "Error " + respuesta.status);
      error.codigo = datos.codigo; error.estado = respuesta.status;
      throw error;
    }
    return datos;
  }

  // -------------------------------------------------------------- utilidades
  function calcularDv(cuerpo) {
    let suma = 0, factor = 2;
    for (let i = cuerpo.length - 1; i >= 0; i--) { suma += Number(cuerpo[i]) * factor; factor = factor === 7 ? 2 : factor + 1; }
    const resto = 11 - (suma % 11);
    return resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  }
  function rutValido(rut) {
    const limpio = (rut || "").trim().replace(/\./g, "").toUpperCase();
    const m = /^(\d{7,8})-([\dK])$/.exec(limpio);
    return !!m && calcularDv(m[1]) === m[2];
  }
  const nuevaClave = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9-]/g, "");
  const fecha = (iso) => iso ? new Date(iso.length === 10 ? iso + "T12:00:00" : iso).toLocaleDateString("es-CL") : "-";
  const fechaHora = (iso) => iso ? new Date(iso).toLocaleString("es-CL") : "-";
  const pesos = (n) => n === null || n === undefined ? "-" : (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("es-CL");
  const porcentaje = (v) => v === null || v === undefined ? "s/d" : String(v).replace(".", ",") + " %";

  const ESTADOS = {
    VIGENTE: ["vigente", "✓", "Vigente"], ALERTA: ["alerta", "⚠", "En alerta"],
    NO_DISPENSABLE: ["bloqueado", "⛔", "No dispensable"], RETIRO_OBLIGATORIO: ["bloqueado", "⛔", "Retiro obligatorio"],
    AGOTADO: ["neutro", "○", "Agotado"], ALERTA_SANITARIA: ["bloqueado", "⚑", "Alerta sanitaria"],
    MERMA: ["neutro", "↓", "En merma"], ANULADO: ["neutro", "✕", "Anulado"],
    PENDIENTE: ["neutro", "○", "Pendiente"], PARCIAL: ["alerta", "◐", "Parcial"], DISPENSADA: ["vigente", "✓", "Dispensada"],
    ANULADA: ["neutro", "✕", "Anulada"], CONTROLADO: ["controlado", "◆", "Controlado"], ACTIVO: ["vigente", "✓", "Activo"],
    INACTIVO: ["neutro", "✕", "Dado de baja"], CRITICO: ["bloqueado", "▼", "Bajo umbral"],
    PREPARANDO: ["neutro", "", "Preparando"], EN_RUTA: ["alerta", "", "En ruta"], ENTREGADO: ["vigente", "", "Entregado"],
    FALLIDO: ["bloqueado", "", "No entregado"], DISPONIBLE: ["vigente", "", "Disponible"],
    POCAS_UNIDADES: ["alerta", "", "Pocas unidades"], SIN_STOCK: ["bloqueado", "", "Sin stock"],
    COMPLETA: ["vigente", "", "Completa"], RECHAZO: ["neutro", "", "Rechazo del paciente"], ABIERTO: ["alerta", "", "Abierto"],
    RESUELTO: ["vigente", "", "Resuelto"], NO_ATINGENTE: ["neutro", "", "No atingente"], ABIERTA: ["alerta", "", "Abierta"],
    CERRADA: ["neutro", "", "Cerrada"], DEVUELTO: ["vigente", "", "Devuelto"], OTORGADO: ["controlado", "", "Prestado"],
    RECIBIDO: ["alerta", "", "Recibido"],
  };
  function Estado({ valor, texto }) {
    const [clase, , etiqueta] = ESTADOS[valor] || ["neutro", "", valor];
    return html`<span className=${"estado " + clase}><span className="punto" aria-hidden="true"></span>${texto || etiqueta}</span>`;
  }

  // Íconos de línea (trazos de 24 px). Son decorativos: el texto del botón da el nombre accesible.
  const ICONOS = {
    logo: html`<path d="M12 5v14M5 12h14" />`,
    panel: html`<rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" />`,
    dispensar: html`<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z" /><path d="m8.5 8.5 7 7" />`,
    inventario: html`<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />`,
    medicamentos: html`<path d="M3 5v14M7 5v14M11 5v14M14 5v14M18 5v14M21 5v14" />`,
    dispensaciones: html`<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" /><path d="M12 7v5l4 2" />`,
    libro: html`<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" /><path d="M9 7h7M9 11h5" />`,
    usuarios: html`<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />`,
    auditoria: html`<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" />`,
    salir: html`<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5M21 12H9" />`,
    buscar: html`<circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />`,
    mas: html`<path d="M5 12h14M12 5v14" />`,
    imprimir: html`<path d="M6 9V2h12v7" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" rx="1" />`,
    alerta: html`<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><path d="M12 9v4M12 17h.01" />`,
    reloj: html`<circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />`,
    claro: html`<circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />`,
    oscuro: html`<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />`,
    sistema: html`<rect x="2" y="3" width="20" height="14" rx="2" /><path d="M8 21h8M12 17v4" />`,
    retiros: html`<rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />`,
    despachos: html`<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2" /><path d="M15 18H9" /><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14" /><circle cx="17" cy="18" r="2" /><circle cx="7" cy="18" r="2" />`,
    alertas: html`<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><path d="M12 9v4M12 17h.01" />`,
    reportes: html`<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M12 18v-6M9 15l3 3 3-3" />`,
    recetar: html`<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M9 12h6M9 16h4" />`,
    descargar: html`<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5M12 15V3" />`,
    pendientes: html`<rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v4M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" /><circle cx="16" cy="16" r="5" /><path d="M16 14v2l1.5 1" />`,
    tomas: html`<rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><path d="m9 14 2 2 4-4" />`,
    prestamos: html`<path d="M8 3 4 7l4 4" /><path d="M4 7h16" /><path d="m16 21 4-4-4-4" /><path d="M20 17H4" />`,
    actividades: html`<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" /><path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27" />`,
    indicadores: html`<path d="M3 3v16a2 2 0 0 0 2 2h16" /><path d="M18 17V9M13 17V5M8 17v-3" />`,
  };

  // Logo: cruz farmacéutica en dos tonos (el mismo dibujo de favicon.svg).
  function Logo() {
    return html`<svg className="logo" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="#0E7C86" />
      <path fill="#FFFFFF" d="M13.6 5.5h4.8a1.2 1.2 0 0 1 1.2 1.2v5.7h5.7a1.2 1.2 0 0 1 1.2 1.2v4.8a1.2 1.2 0 0 1-1.2 1.2h-5.7v5.7a1.2 1.2 0 0 1-1.2 1.2h-4.8a1.2 1.2 0 0 1-1.2-1.2v-5.7H6.7a1.2 1.2 0 0 1-1.2-1.2v-4.8a1.2 1.2 0 0 1 1.2-1.2h5.7V6.7a1.2 1.2 0 0 1 1.2-1.2Z" />
      <path fill="#9EE0E5" d="M19.6 12.4h5.7a1.2 1.2 0 0 1 1.2 1.2v4.8a1.2 1.2 0 0 1-1.2 1.2h-5.7Z" />
    </svg>`;
  }

  // Tema: "sistema" sigue al sistema operativo; "claro" y "oscuro" se guardan en este navegador.
  const TEMAS = [["claro", "Tema claro"], ["oscuro", "Tema oscuro"], ["sistema", "Tema del sistema"]];
  function leerTema() {
    try { const t = localStorage.getItem("sisgef_tema"); return t === "claro" || t === "oscuro" ? t : "sistema"; }
    catch (_) { return "sistema"; }
  }
  function aplicarTema(tema) {
    const raiz = document.documentElement;
    if (tema === "sistema") raiz.removeAttribute("data-theme");
    else raiz.setAttribute("data-theme", tema === "claro" ? "light" : "dark");
    try { tema === "sistema" ? localStorage.removeItem("sisgef_tema") : localStorage.setItem("sisgef_tema", tema); } catch (_) {}
  }
  function SelectorTema() {
    const [tema, setTema] = useState(leerTema);
    return html`<div className="selector-tema" role="group" aria-label="Tema de la interfaz">
      ${TEMAS.map(([valor, texto]) => html`<button type="button" key=${valor} aria-label=${texto} title=${texto}
          aria-pressed=${tema === valor} onClick=${() => { aplicarTema(valor); setTema(valor); }}><${Icono} nombre=${valor} /></button>`)}
    </div>`;
  }
  function Icono({ nombre }) {
    return html`<svg className="icono" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONOS[nombre]}</svg>`;
  }

  // Código de barras EAN-13 dibujado en SVG (codificación en codigo-barras.js).
  function CodigoBarras({ codigo, conTexto = true }) {
    const barras = window.CodigoBarras.barras(codigo);
    if (!barras.length) return html`<span className="ayuda">Sin código</span>`;
    const alto = conTexto ? 62 : 50;
    return html`<svg className="codigo-barras" viewBox=${`0 0 113 ${alto + (conTexto ? 10 : 0)}`} role="img"
        aria-label=${"Código de barras " + codigo} data-modulos=${window.CodigoBarras.modulos(codigo)}>
      <rect width="113" height=${alto + (conTexto ? 10 : 0)} fill="#fff" />
      ${barras.map((b) => html`<rect key=${b.x} x=${b.x + 11} y="4" width=${b.ancho}
          height=${conTexto ? (b.guarda ? alto - 2 : alto - 8) : alto - 8} fill="#000" />`)}
      ${conTexto && html`<g fontFamily="Consolas, Menlo, monospace" fontSize="8" fill="#000" textAnchor="middle">
        <text x="5" y=${alto + 4}>${codigo[0]}</text>
        <text x="35" y=${alto + 4} letterSpacing="2.2">${codigo.slice(1, 7)}</text>
        <text x="81" y=${alto + 4} letterSpacing="2.2">${codigo.slice(7)}</text>
      </g>`}
    </svg>`;
  }

  // ------------------------------------------------------- gráficos (SVG propio, sin librerías)
  // Guía de visualización: una sola escala, barras <= 24 px con extremo redondeado, líneas de 2 px,
  // grilla tenue, etiquetas selectivas, tooltip con mouse y teclado (flechas) y tabla de datos.
  // Colores validados para daltonismo y contraste: --serie-1 / --serie-2 en estilos.css.
  const numero = (v, decimales = 0) => Number(v).toLocaleString("es-CL", { maximumFractionDigits: decimales });
  const compacto = (v) => Math.abs(v) >= 1e6 ? numero(v / 1e6, 1) + " M" : Math.abs(v) >= 1e4 ? numero(v / 1e3) + " mil" : numero(v);
  const fechaCorta = (iso) => new Date(iso.length === 10 ? iso + "T12:00:00" : iso).toLocaleDateString("es-CL", { day: "numeric", month: "short" });

  function useAncho() {
    const ref = useRef(null);
    const [ancho, setAncho] = useState(600);
    useEffect(() => {
      if (!ref.current) return undefined;
      const medir = () => ref.current && setAncho(Math.max(260, Math.floor(ref.current.getBoundingClientRect().width)));
      medir();
      const observador = new ResizeObserver(medir);
      observador.observe(ref.current);
      return () => observador.disconnect();
    }, []);
    return [ref, ancho];
  }

  function ticksLimpios(maximo, cantidad = 4) {
    if (!(maximo > 0)) return [0, 1];
    const bruto = maximo / cantidad, base = Math.pow(10, Math.floor(Math.log10(bruto)));
    const paso = [1, 2, 2.5, 5, 10].map((f) => f * base).find((p) => p >= bruto);
    const ticks = [];
    for (let v = 0; v < maximo + paso * 0.999; v += paso) ticks.push(Number(v.toFixed(6)));
    return ticks;
  }

  function Grafico({ tipo = "columnas", titulo, descripcion, datos, formato = numero, formatoEje = compacto, maximo,
                     minimo = 0, referencia, columnas, alto = 210 }) {
    const [ref, ancho] = useAncho();
    const [activo, setActivo] = useState(null);
    const hay = (v) => v !== null && v !== undefined;
    const m = { izq: 52, der: tipo === "linea" ? 60 : 14, sup: 18, inf: 26 };
    const w = Math.max(ancho - m.izq - m.der, 60), h = alto - m.sup - m.inf;
    const valores = datos.map((d) => d.valor).filter(hay);
    // Las columnas parten siempre en cero; una línea puede acotar su piso (minimo) para que se lea la variación.
    const piso = tipo === "linea" ? Math.min(minimo, ...valores) : 0;
    const ticks = ticksLimpios((maximo ?? Math.max(0, ...valores, referencia ? referencia.valor : 0)) - piso).map((t) => t + piso);
    const tope = ticks[ticks.length - 1] - piso || 1;
    const y = (v) => m.sup + h - ((Math.min(Math.max(v, piso), piso + tope) - piso) / tope) * h;
    const banda = w / Math.max(datos.length, 1);
    const x = (i) => m.izq + banda * i + banda / 2;
    const grosor = Math.max(2, Math.min(24, banda - 2));   // 2 px de superficie entre barras vecinas
    const largoEtiqueta = Math.max(...datos.map((d) => String(d.etiqueta).length), 1) * 6.5 + 14;
    const salto = Math.max(1, Math.ceil(datos.length / Math.max(1, Math.floor(w / largoEtiqueta))));
    const barra = (cx, v) => {
      const x0 = cx - grosor / 2, y0 = y(v), yb = y(0), r = Math.min(4, grosor / 2, yb - y0);
      return `M${x0},${yb}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + grosor - r}Q${x0 + grosor},${y0} ${x0 + grosor},${y0 + r}V${yb}Z`;
    };
    const segmentos = [];
    let tramo = [];
    datos.forEach((d, i) => { if (hay(d.valor)) tramo.push([x(i), y(d.valor), i]); else { if (tramo.length) segmentos.push(tramo); tramo = []; } });
    if (tramo.length) segmentos.push(tramo);
    const ultimo = datos.map((d, i) => (hay(d.valor) ? i : -1)).filter((i) => i >= 0).pop();
    const mover = (paso) => setActivo((a) => Math.min(datos.length - 1, Math.max(0, a === null ? (paso > 0 ? 0 : datos.length - 1) : a + paso)));
    const d = activo !== null ? datos[activo] : null;
    // el tooltip va al lado de la marca (a la derecha si cabe), sin taparla
    const izquierda = activo === null ? 0 : x(activo) + grosor / 2 + 192 <= ancho ? x(activo) + Math.max(grosor / 2, 6) + 6
      : Math.max(x(activo) - Math.max(grosor / 2, 6) - 186, 0);
    const resumen = `${titulo}. ${datos.length} períodos` + (hay(ultimo) ? `; último ${datos[ultimo].etiquetaLarga || datos[ultimo].etiqueta}: ${formato(datos[ultimo].valor)}` : "")
      + ". Use las flechas para recorrer los valores.";
    return html`<figure className="grafico" ref=${ref}>
      <figcaption><strong>${titulo}</strong>${descripcion && html`<span className="ayuda">${descripcion}</span>`}</figcaption>
      <div className="grafico-lienzo">
        <svg width=${ancho} height=${alto} role="img" aria-label=${resumen} tabIndex="0" onMouseLeave=${() => setActivo(null)}
             onBlur=${() => setActivo(null)} onKeyDown=${(e) => {
               if (e.key === "ArrowRight") { e.preventDefault(); mover(1); }
               else if (e.key === "ArrowLeft") { e.preventDefault(); mover(-1); }
               else if (e.key === "Escape") setActivo(null); }}>
          ${ticks.map((t) => html`<g key=${"t" + t}>
            ${t > piso && html`<line className="grafico-grilla" x1=${m.izq} x2=${m.izq + w} y1=${y(t)} y2=${y(t)} />`}
            <text className="grafico-eje" x=${m.izq - 8} y=${y(t)} dy="0.32em" textAnchor="end">${formatoEje(t)}</text></g>`)}
          ${datos.map((dd, i) => i % salto === 0 && html`<text key=${"x" + i} className="grafico-eje" x=${x(i)} y=${alto - 7} textAnchor="middle">${dd.etiqueta}</text>`)}
          ${tipo === "columnas" && datos.map((dd, i) => hay(dd.valor) && dd.valor > 0
            && html`<path key=${"b" + i} className=${"grafico-barra" + (activo === i ? " activa" : "")} d=${barra(x(i), dd.valor)} />`)}
          ${tipo === "linea" && activo !== null && html`<line className="grafico-cruz" x1=${x(activo)} x2=${x(activo)} y1=${m.sup} y2=${y(piso)} />`}
          ${tipo === "linea" && segmentos.map((s, k) => s.length > 1
            ? html`<path key=${"l" + k} className="grafico-linea" d=${"M" + s.map(([px, py]) => px + "," + py).join("L")} />`
            : html`<circle key=${"l" + k} className="grafico-punto" cx=${s[0][0]} cy=${s[0][1]} r="4" />`)}
          <line className="grafico-base" x1=${m.izq} x2=${m.izq + w} y1=${y(piso)} y2=${y(piso)} />
          ${referencia && html`<g>
            <line className="grafico-referencia" x1=${m.izq} x2=${m.izq + w} y1=${y(referencia.valor)} y2=${y(referencia.valor)} />
            <text className="grafico-eje" x=${m.izq + 4} y=${y(referencia.valor) - 6}>${referencia.etiqueta}</text></g>`}
          ${tipo === "linea" && hay(ultimo) && html`<g>
            <circle className="grafico-punto" cx=${x(ultimo)} cy=${y(datos[ultimo].valor)} r="4" />
            <text className="grafico-valor" x=${x(ultimo) + 9} y=${y(datos[ultimo].valor)} dy="0.32em">${formato(datos[ultimo].valor)}</text></g>`}
          ${tipo === "linea" && d && hay(d.valor) && html`<circle className="grafico-punto" cx=${x(activo)} cy=${y(d.valor)} r="5" />`}
          ${datos.map((dd, i) => html`<rect key=${"z" + i} className="grafico-zona" x=${m.izq + banda * i} y=${m.sup} width=${banda} height=${h}
              onMouseEnter=${() => setActivo(i)} />`)}
        </svg>
        ${d && html`<div className="grafico-tooltip" style=${{ left: izquierda + "px" }} aria-live="polite">
          <strong>${hay(d.valor) ? formato(d.valor) : "Sin datos"}</strong>
          <span>${d.etiquetaLarga || d.etiqueta}</span>
          ${d.detalle && html`<span className="ayuda">${d.detalle}</span>`}</div>`}
      </div>
      <details className="grafico-tabla"><summary>Ver los datos en una tabla</summary>
        <div className="tabla-envoltura"><table>
          <thead><tr>${columnas.map(([t, , num]) => html`<th key=${t} className=${num ? "num" : ""}>${t}</th>`)}</tr></thead>
          <tbody>${datos.map((dd, i) => html`<tr key=${i}>${columnas.map(([t, f, num]) => html`<td key=${t} className=${num ? "num" : ""}>${f(dd)}</td>`)}</tr>`)}</tbody>
        </table></div></details>
    </figure>`;
  }

  function imprimirEtiqueta() {
    document.documentElement.classList.add("modo-etiqueta");
    const limpiar = () => { document.documentElement.classList.remove("modo-etiqueta"); window.removeEventListener("afterprint", limpiar); };
    window.addEventListener("afterprint", limpiar);
    window.print();
    setTimeout(limpiar, 1000);
  }

  const NOMBRES_ROL = { QF: "Químico farmacéutico", TECNICO: "TENS de farmacia", BODEGUERO: "Bodeguero",
                        MEDICO: "Médico", ADMIN: "Administrador" };
  const TIPOS_RECETA = { AGUDA: "Aguda", CRONICA: "Crónica", RETENIDA: "Retenida" };
  const iniciales = (nombre) => nombre.replace(/^(Q\.F\.|Téc\.|Bod\.)\s*/, "").split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

  function Aviso({ tipo, children }) {
    if (!children) return null;
    return html`<div className=${"aviso " + tipo} role=${tipo === "error" ? "alert" : "status"}>${children}</div>`;
  }

  function useCarga(funcion, dependencias) {
    const [estado, setEstado] = useState({ datos: null, error: null, cargando: true });
    const recargar = useCallback(() => {
      setEstado((e) => ({ ...e, cargando: true }));
      funcion().then((datos) => setEstado({ datos, error: null, cargando: false }))
        .catch((error) => setEstado({ datos: null, error: error.message, cargando: false }));
    }, dependencias); // eslint-disable-line
    useEffect(recargar, [recargar]);
    return [estado, recargar];
  }

  // Diálogo genérico para acciones que exigen motivo o datos (baja, anulación, merma...)
  function Dialogo({ titulo, descripcion, campos, textoAceptar, peligro, onAceptar, onCerrar }) {
    const [valores, setValores] = useState(() => Object.fromEntries(campos.map((c) => [c.nombre, c.inicial ?? ""])));
    const [error, setError] = useState(null);
    const [enviando, setEnviando] = useState(false);
    const primero = useRef(null);
    useEffect(() => { primero.current && primero.current.focus(); }, []);
    useEffect(() => {
      const alPresionar = (e) => { if (e.key === "Escape") onCerrar(); };
      document.addEventListener("keydown", alPresionar);
      return () => document.removeEventListener("keydown", alPresionar);
    }, [onCerrar]);
    async function enviar(e) {
      e.preventDefault(); setEnviando(true); setError(null);
      try { await onAceptar(valores); onCerrar(); } catch (err) { setError(err.message); } finally { setEnviando(false); }
    }
    return html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && onCerrar()}>
      <form className="dialogo" role="dialog" aria-modal="true" aria-label=${titulo} onSubmit=${enviar}>
        <h2>${titulo}</h2>
        ${descripcion && html`<p className="ayuda">${descripcion}</p>`}
        <${Aviso} tipo="error">${error}<//>
        ${campos.map((c, i) => c.multiple
          ? html`<fieldset className="campo grupo-casillas" key=${c.nombre}>
              <legend>${c.etiqueta}${c.ayuda && html` <span className="ayuda">${c.ayuda}</span>`}</legend>
              ${c.opciones.map(([v, t]) => html`<label key=${v} className="casilla">
                <input type="checkbox" checked=${valores[c.nombre].includes(v)}
                       onChange=${(e) => setValores({ ...valores, [c.nombre]: e.target.checked
                         ? [...valores[c.nombre], v] : valores[c.nombre].filter((x) => x !== v) })} /> ${t}</label>`)}
            </fieldset>`
          : html`<div className="campo" key=${c.nombre}>
          <label htmlFor=${"d-" + c.nombre}>${c.etiqueta}${c.ayuda && html` <span className="ayuda">${c.ayuda}</span>`}</label>
          ${c.opciones
            ? html`<select id=${"d-" + c.nombre} ref=${i === 0 ? primero : null} value=${valores[c.nombre]}
                     onChange=${(e) => setValores({ ...valores, [c.nombre]: e.target.value })}>
                     ${c.opciones.map(([v, t]) => html`<option key=${v} value=${v}>${t}</option>`)}</select>`
            : html`<input id=${"d-" + c.nombre} ref=${i === 0 ? primero : null} type=${c.tipo || "text"} required=${c.requerido !== false}
                     minLength=${c.minimo} min=${c.min} max=${c.max} value=${valores[c.nombre]}
                     onChange=${(e) => setValores({ ...valores, [c.nombre]: e.target.value })} />`}
        </div>`)}
        <div className="acciones">
          <button className=${"boton " + (peligro ? "peligro" : "")} disabled=${enviando}>${textoAceptar || "Aceptar"}</button>
          <button type="button" className="boton secundario" onClick=${onCerrar}>Cancelar</button>
        </div>
      </form>
    </div>`;
  }

  // ------------------------------------------------------------------ ingreso
  const DEMO = [["Q.F.", "15555555-6"], ["TENS", "17777777-3"], ["Bodeguero", "18888888-7"], ["Médico", "13579246-2"],
                ["Admin", "11111111-1"]];

  function Ingreso({ onIngreso }) {
    const [rut, setRut] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState(null);
    const [enviando, setEnviando] = useState(false);
    const rutMal = rut.length > 8 && !rutValido(rut);
    async function enviar(e) {
      e.preventDefault(); setError(null);
      if (!rutValido(rut)) { setError("El RUT no es válido. Revise el dígito verificador."); return; }
      setEnviando(true);
      try {
        const r = await api("POST", "/api/auth/login", { rut, password });
        guardarToken(r.access_token); onIngreso();
      } catch (err) { setError(err.message); } finally { setEnviando(false); }
    }
    return html`<main className="ingreso">
      <section className="ingreso-panel" aria-hidden="true">
        <div className="marca"><${Logo} />
          <div><strong>SISGEF</strong><small>Farmacia asistencial · CESFAM</small></div></div>
        <div>
          <h2>Gestión de la farmacia asistencial</h2>
          <p>Dispensación con verificación de lote, control de vencimientos y libro digital de medicamentos controlados.</p>
        </div>
        <div className="pie">Proyecto Integrado · INACAP · v0.4</div>
      </section>
      <div className="ingreso-formulario"><${SelectorTema} /><form onSubmit=${enviar}>
      <h1>Iniciar sesión</h1>
      <span className="ayuda">Ingrese con su RUT y la contraseña asignada por el administrador.</span>
      <${Aviso} tipo="error">${error}<//>
      <div className="campo">
        <label htmlFor="rut">RUT</label>
        <input id="rut" autoComplete="username" placeholder="12345678-5" value=${rut} aria-invalid=${rutMal}
               aria-describedby="rut-ayuda" onChange=${(e) => setRut(e.target.value)} />
        <div id="rut-ayuda" className="ayuda" aria-live="polite">${rutMal ? "Dígito verificador incorrecto." : "Sin puntos, con guion."}</div>
      </div>
      <div className="campo">
        <label htmlFor="clave">Contraseña</label>
        <input id="clave" type="password" autoComplete="current-password" value=${password}
               onChange=${(e) => setPassword(e.target.value)} />
      </div>
      <button type="submit" className="boton" disabled=${enviando}>${enviando ? "Ingresando…" : "Ingresar"}</button>
      <div className="demo"><strong>Entorno de demostración</strong>
        Contraseña común <code>Farmacia2026!</code>. Seleccione un perfil para completar los datos:
        <div className="opciones">${DEMO.map(([n, r]) => html`<button type="button" key=${r}
          onClick=${() => { setRut(r); setPassword("Farmacia2026!"); }}>${n}</button>`)}</div>
      </div>
      <p className="enlace-publico"><a href="#/disponibilidad">Consultar disponibilidad de medicamentos (sin iniciar sesión)</a></p>
    </form></div></main>`;
  }

  // -------------------------------------------------------------------- panel
  function Panel() {
    const [{ datos, error }] = useCarga(() => api("GET", "/api/stock"), []);
    const [{ datos: entregas }] = useCarga(() => api("GET", "/api/panel/entregas?dias=30"), []);
    if (error) return html`<${Aviso} tipo="error">${error}<//>`;
    if (!datos) return html`<p>Cargando…</p>`;
    const criticos = datos.filter((d) => d.critico).length;
    const enRetiro = datos.reduce((s, d) => s + (d.unidades_por_estado.RETIRO_OBLIGATORIO || 0) + (d.unidades_por_estado.NO_DISPENSABLE || 0), 0);
    const enAlerta = datos.reduce((s, d) => s + (d.unidades_por_estado.ALERTA || 0), 0);
    return html`<div>
      <div className="rejilla k4">
        ${[["Medicamentos activos", datos.length, "", "medicamentos"],
           ["Bajo umbral crítico", criticos, criticos ? "bloqueado" : "", "alerta"],
           ["Unidades en alerta (≤ 60 días)", enAlerta, enAlerta ? "alerta" : "", "reloj"],
           ["Unidades no dispensables", enRetiro, enRetiro ? "bloqueado" : "", "inventario"]].map(([etiqueta, valor, tono, icono]) =>
          html`<div className=${"tarjeta kpi " + tono} key=${etiqueta}>
            <div><div className="etiqueta">${etiqueta}</div><div className="valor">${valor}</div></div>
            <span className="indicador"><${Icono} nombre=${icono} /></span></div>`)}
      </div>
      ${entregas && html`<div className="tarjeta"><${Grafico} titulo="Entregas por día"
          descripcion=${`Últimos 30 días · ${numero(entregas.reduce((s, e) => s + e.entregas, 0))} entregas, ${numero(entregas.reduce((s, e) => s + e.unidades, 0))} unidades`}
          datos=${entregas.map((e) => ({ etiqueta: fechaCorta(e.fecha), etiquetaLarga: fecha(e.fecha), valor: e.entregas,
                                         detalle: `${numero(e.unidades)} unidades entregadas` }))}
          formato=${(v) => `${numero(v)} entrega${v === 1 ? "" : "s"}`}
          columnas=${[["Día", (e) => e.etiquetaLarga], ["Entregas", (e) => numero(e.valor), true], ["Detalle", (e) => e.detalle]]} /></div>`}
      <div className="tarjeta"><h2>Stock dispensable por programa</h2>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Medicamento</th><th>Programa</th><th className="num">Dispensable</th><th className="num">Umbral</th><th>Estado</th></tr></thead>
          <tbody>${datos.map((d) => html`<tr key=${d.id_medicamento}>
            <td>${d.nombre} ${d.es_controlado && html`<${Estado} valor="CONTROLADO" />`}</td>
            <td>${d.programa || "-"}</td>
            <td className="num">${d.stock_dispensable}</td><td className="num">${d.umbral_critico}</td>
            <td>${d.critico ? html`<${Estado} valor="CRITICO" />` : html`<${Estado} valor="VIGENTE" texto="Suficiente" />`}</td>
          </tr>`)}</tbody>
        </table></div>
      </div>
    </div>`;
  }

  // ---------------------------------------------------------------- dispensar
  function LineaReceta({ detalle, linea, onCambio }) {
    const [plan, setPlan] = useState(null);
    const [lotes, setLotes] = useState([]);
    const [error, setError] = useState(null);
    const [lectura, setLectura] = useState("");
    const entradaEscaneo = useRef(null);

    async function verPlan() {
      setError(null); setPlan(null);
      try {
        const [p, l] = await Promise.all([
          api("GET", `/api/dispensaciones/plan?id_detalle_receta=${detalle.id_detalle_receta}&cantidad=${linea.cantidad}`),
          api("GET", `/api/lotes?id_medicamento=${detalle.id_medicamento}`),
        ]);
        setPlan(p); setLotes(l); onCambio({ ...linea, lotes_escaneados: [] });
        setTimeout(() => entradaEscaneo.current && entradaEscaneo.current.focus(), 0);
      } catch (err) { setError(err.message); }
    }
    function escanear(e) {
      e.preventDefault();
      const codigo = lectura.trim();
      if (!codigo) return;
      if (plan && !plan.some((p) => p.codigo_lote === codigo)) {
        const esperado = plan[0];
        setError(`El lote ${codigo} no corresponde al plan FEFO. Entregue ${esperado.codigo_lote} del casillero ${esperado.ubicacion}.`);
      } else {
        setError(null);
        if (!linea.lotes_escaneados.includes(codigo)) onCambio({ ...linea, lotes_escaneados: [...linea.lotes_escaneados, codigo] });
      }
      setLectura("");
    }
    const enPlan = new Set((plan || []).map((p) => p.codigo_lote));
    return html`<div className="tarjeta">
      <div className="acciones" style=${{ justifyContent: "space-between" }}>
        <h3>${detalle.medicamento} ${detalle.es_controlado && html`<${Estado} valor="CONTROLADO" />`}</h3>
        <span className="ayuda">Prescrito ${detalle.cant_prescrita} · entregado ${detalle.cant_entregada} · corresponde ahora <strong>${detalle.saldo_entrega}</strong></span>
      </div>
      <p className="ayuda">Posología: ${detalle.posologia}</p>
      <div className="fila-campos">
        <div className="campo"><label htmlFor=${"c" + detalle.id_detalle_receta}>Cantidad a entregar (unidades)</label>
          <input id=${"c" + detalle.id_detalle_receta} type="number" min="0" max=${detalle.saldo_entrega} value=${linea.cantidad}
                 onChange=${(e) => { setPlan(null); onCambio({ ...linea, cantidad: Number(e.target.value), lotes_escaneados: [] }); }} /></div>
        <div className="campo"><span className="etiqueta-vacia" aria-hidden="true"></span>
          <button type="button" className="boton secundario" disabled=${!(linea.cantidad > 0)} onClick=${verPlan}>Calcular plan FEFO</button></div>
        ${linea.cantidad < detalle.saldo_entrega && html`<div className="campo">
          <label htmlFor=${"m" + detalle.id_detalle_receta}>Motivo de lo no entregado (${detalle.saldo_entrega - linea.cantidad} u.)</label>
          <select id=${"m" + detalle.id_detalle_receta} value=${linea.motivo || ""} onChange=${(e) => onCambio({ ...linea, motivo: e.target.value })}>
            <option value="">Automático (según el stock)</option>
            <option value="SIN_STOCK">Sin stock: compromiso de 24 h hábiles</option>
            <option value="RECHAZO_PACIENTE">El paciente no lo quiere llevar</option>
          </select></div>`}
      </div>
      <${Aviso} tipo="error">${error}<//>
      ${plan && html`<div>
        <div className="tira-fefo" aria-label="Lotes del medicamento en orden de vencimiento">
          ${lotes.filter((l) => l.unidades_disp > 0).map((l) => html`<div key=${l.id_lote}
               className=${"lote " + (enPlan.has(l.codigo_lote) ? "elegido" : l.dispensable ? "" : "bloqueado")}>
            <div className="codigo">${l.codigo_lote} ${linea.lotes_escaneados.includes(l.codigo_lote) && "✓"}</div>
            <div>Casillero ${l.ubicacion} · ${l.unidades_disp} u.</div>
            <div>Vence ${fecha(l.fecha_vencimiento)} (${l.dias_para_vencer} d)</div>
            <${Estado} valor=${l.estado} />
            ${enPlan.has(l.codigo_lote) && html`<div><strong>Tomar ${plan.find((p) => p.codigo_lote === l.codigo_lote).cantidad} u.</strong></div>`}
          </div>`)}
        </div>
        <form className="fila-campos" onSubmit=${escanear}>
          <div className="campo"><label htmlFor=${"e" + detalle.id_detalle_receta}>Escanear lote <span className="ayuda">(lector o teclado + Enter)</span></label>
            <input id=${"e" + detalle.id_detalle_receta} ref=${entradaEscaneo} value=${lectura} autoComplete="off"
                   onChange=${(e) => setLectura(e.target.value)} placeholder="L-0000" /></div>
          <div className="campo"><span className="etiqueta-vacia" aria-hidden="true"></span><button className="boton ancho-movil">Registrar escaneo</button></div>
        </form>
        <p className="ayuda" aria-live="polite">Escaneados: ${linea.lotes_escaneados.join(", ") || "ninguno"} de ${plan.length} lote(s) del plan.</p>
      </div>`}
    </div>`;
  }

  // Receta: asigna medicamentos al paciente para que luego se dispensen con FEFO.
  const lineaVacia = () => ({ id_medicamento: "", cant_por_entrega: "", posologia: "" });
  const fechaLocal = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  function NuevaReceta({ paciente, puedeControlados, onCreada, onCerrar }) {
    const [{ datos: meds, error: errorMeds }] = useCarga(() => api("GET", "/api/medicamentos"), []);
    const hoyIso = fechaLocal(new Date());
    const minimo = fechaLocal(new Date(Date.now() - 30 * 86400000));
    const [folio, setFolio] = useState("");
    const [fechaEmision, setFechaEmision] = useState(hoyIso);
    const [retenidaManual, setRetenidaManual] = useState(false);
    const [tipo, setTipo] = useState("AGUDA");
    const [entregas, setEntregas] = useState(3);
    const [intervalo, setIntervalo] = useState(30);
    const [lineas, setLineas] = useState([lineaVacia()]);
    const [libro, setLibro] = useState({ prescriptor_nombre: "", prescriptor_rut: "", domicilio_paciente: "", numero_receta_cheque: "" });
    const [error, setError] = useState(null);
    const [enviando, setEnviando] = useState(false);
    const primero = useRef(null);
    useEffect(() => { primero.current && primero.current.focus(); }, []);
    useEffect(() => {
      const alPresionar = (e) => { if (e.key === "Escape") onCerrar(); };
      document.addEventListener("keydown", alPresionar);
      return () => document.removeEventListener("keydown", alPresionar);
    }, [onCerrar]);

    const porId = Object.fromEntries((meds || []).map((m) => [String(m.id_medicamento), m]));
    const hayControlado = lineas.some((l) => porId[l.id_medicamento]?.es_controlado);
    const exigeCheque = lineas.some((l) => porId[l.id_medicamento]?.requiere_receta_cheque);
    const retenida = hayControlado || retenidaManual;
    const cronica = tipo === "CRONICA" && !retenida;
    const cambiar = (i, campo, valor) => setLineas(lineas.map((l, j) => (j === i ? { ...l, [campo]: valor } : l)));
    const [escaneo, setEscaneo] = useState("");
    function agregarPorCodigo(e) {
      if (e.key !== "Enter") return;
      e.preventDefault();  // dentro del formulario, Enter no debe guardar la receta
      const codigo = escaneo.trim();
      const med = (meds || []).find((m) => m.codigo_barras === codigo);
      setEscaneo("");
      if (!med) { setError(`No hay un medicamento activo con el código de barras ${codigo}.`); return; }
      if (med.es_controlado && !puedeControlados) { setError(`${med.nombre} es controlado: solo un Q.F. puede recetarlo.`); return; }
      const id = String(med.id_medicamento);
      if (lineas.some((l) => l.id_medicamento === id)) { setError(`${med.nombre} ya está en la receta.`); return; }
      setError(null);
      const vacia = lineas.findIndex((l) => !l.id_medicamento);
      setLineas(vacia >= 0 ? lineas.map((l, j) => (j === vacia ? { ...l, id_medicamento: id } : l))
                           : [...lineas, { ...lineaVacia(), id_medicamento: id }]);
    }

    async function enviar(e) {
      e.preventDefault(); setError(null);
      const elegidos = lineas.map((l) => l.id_medicamento);
      if (new Set(elegidos).size !== elegidos.length) { setError("Un medicamento aparece dos veces en la receta."); return; }
      if (hayControlado && !rutValido(libro.prescriptor_rut)) { setError("RUT del prescriptor inválido: revise el dígito verificador."); return; }
      setEnviando(true);
      try {
        const r = await api("POST", "/api/recetas", { id_paciente: paciente.id_paciente, folio: folio.trim(),
          fecha_emision: fechaEmision, es_retenida: retenida, tipo_receta: retenida ? "RETENIDA" : tipo,
          total_entregas: cronica ? Number(entregas) : 1, intervalo_dias: cronica ? Number(intervalo) : 30,
          lineas: lineas.map((l) => ({ id_medicamento: Number(l.id_medicamento), cant_por_entrega: Number(l.cant_por_entrega),
                                       posologia: l.posologia.trim() })),
          ...(hayControlado ? { prescriptor_nombre: libro.prescriptor_nombre.trim(), prescriptor_rut: libro.prescriptor_rut.trim(),
                                domicilio_paciente: libro.domicilio_paciente.trim(),
                                numero_receta_cheque: exigeCheque ? libro.numero_receta_cheque.trim() : null } : {}) });
        onCreada(r); onCerrar();
      } catch (err) { setError(err.message); } finally { setEnviando(false); }
    }

    return html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && onCerrar()}>
      <form className="dialogo dialogo-ancho" role="dialog" aria-modal="true" aria-label="Nueva receta" onSubmit=${enviar}>
        <h2>Nueva receta</h2>
        <p className="ayuda">Paciente: <strong>${paciente.nombre}</strong> (${paciente.rut}). Transcriba la receta emitida por el médico.</p>
        <${Aviso} tipo="error">${error || errorMeds}<//>
        <div className="fila-campos">
          <div className="campo"><label htmlFor="r-folio">Folio <span className="ayuda">(letras, números y guion)</span></label>
            <input id="r-folio" ref=${primero} required minLength="2" maxLength="30" pattern="[A-Za-z0-9\\-]+"
                   placeholder="RX-2001" value=${folio} onChange=${(e) => setFolio(e.target.value)} /></div>
          <div className="campo"><label htmlFor="r-fecha">Fecha de emisión <span className="ayuda">(máx. 30 días)</span></label>
            <input id="r-fecha" type="date" required min=${minimo} max=${hoyIso} value=${fechaEmision}
                   onChange=${(e) => setFechaEmision(e.target.value)} /></div>
        </div>
        <label className="casilla"><input type="checkbox" checked=${retenida} disabled=${hayControlado}
          onChange=${(e) => setRetenidaManual(e.target.checked)} /> Receta retenida (el original queda en farmacia)
          ${hayControlado && html`<span className="ayuda"> obligatoria por incluir un controlado</span>`}</label>
        ${hayControlado && html`<fieldset className="linea-receta"><legend>Datos para el libro de controlados (D.S. 404/405)</legend>
          <div className="fila-campos">
            <div className="campo"><label htmlFor="r-presc">Médico prescriptor</label>
              <input id="r-presc" required minLength="3" maxLength="120" value=${libro.prescriptor_nombre}
                     onChange=${(e) => setLibro({ ...libro, prescriptor_nombre: e.target.value })} /></div>
            <div className="campo"><label htmlFor="r-presc-rut">RUT del prescriptor</label>
              <input id="r-presc-rut" required maxLength="12" placeholder="10203040-0" value=${libro.prescriptor_rut}
                     aria-invalid=${libro.prescriptor_rut.length > 8 && !rutValido(libro.prescriptor_rut)}
                     onChange=${(e) => setLibro({ ...libro, prescriptor_rut: e.target.value })} /></div>
          </div>
          <div className="fila-campos">
            <div className="campo"><label htmlFor="r-dom">Domicilio del paciente <span className="ayuda">(el de la receta)</span></label>
              <input id="r-dom" required minLength="5" maxLength="200" value=${libro.domicilio_paciente}
                     onChange=${(e) => setLibro({ ...libro, domicilio_paciente: e.target.value })} /></div>
            ${exigeCheque && html`<div className="campo"><label htmlFor="r-cheque">N.º de receta cheque</label>
              <input id="r-cheque" required maxLength="20" pattern="[A-Za-z0-9\\-]+" value=${libro.numero_receta_cheque}
                     onChange=${(e) => setLibro({ ...libro, numero_receta_cheque: e.target.value })} /></div>`}
          </div></fieldset>`}
        <div className="fila-campos">
          <div className="campo"><label htmlFor="r-tipo">Tipo de receta</label>
            <select id="r-tipo" value=${retenida ? "RETENIDA" : tipo} disabled=${retenida} onChange=${(e) => setTipo(e.target.value)}>
              ${retenida ? html`<option value="RETENIDA">Retenida (una entrega)</option>` : html`
              <option value="AGUDA">Aguda (una entrega)</option>
              <option value="CRONICA">Crónica (entregas periódicas)</option>`}
            </select></div>
          ${cronica && html`
            <div className="campo"><label htmlFor="r-entregas">Número de entregas</label>
              <input id="r-entregas" type="number" required min="2" max="6" value=${entregas}
                     onChange=${(e) => setEntregas(e.target.value)} /></div>
            <div className="campo"><label htmlFor="r-intervalo">Días entre entregas</label>
              <input id="r-intervalo" type="number" required min="7" max="90" value=${intervalo}
                     onChange=${(e) => setIntervalo(e.target.value)} /></div>`}
        </div>

        <h3>Medicamentos</h3>
        <div className="escaneo-receta"><div className="campo">
          <label htmlFor="r-escaneo">Agregar por código de barras <span className="ayuda">(lector o teclado + Enter)</span></label>
          <input id="r-escaneo" inputMode="numeric" autoComplete="off" placeholder="13 dígitos del envase o etiqueta"
                 value=${escaneo} onChange=${(e) => setEscaneo(e.target.value)} onKeyDown=${agregarPorCodigo} /></div></div>
        ${lineas.map((l, i) => html`<fieldset className="linea-receta" key=${i}>
          <legend>Medicamento ${i + 1}</legend>
          <div className="fila-campos">
            <div className="campo"><label htmlFor=${"r-med-" + i}>Medicamento</label>
              <select id=${"r-med-" + i} required value=${l.id_medicamento} onChange=${(e) => cambiar(i, "id_medicamento", e.target.value)}>
                <option value="">Seleccione…</option>
                ${(meds || []).map((m) => html`<option key=${m.id_medicamento} value=${m.id_medicamento}
                    disabled=${m.es_controlado && !puedeControlados}>${m.nombre}${m.es_controlado ? " (controlado" + (puedeControlados ? ")" : ": solo Q.F.)") : ""}</option>`)}
              </select></div>
            <div className="campo"><label htmlFor=${"r-cant-" + i}>${cronica ? "Cantidad por entrega" : "Cantidad"} (unidades)</label>
              <input id=${"r-cant-" + i} type="number" required min="1" max="10000" value=${l.cant_por_entrega}
                     onChange=${(e) => cambiar(i, "cant_por_entrega", e.target.value)} />
              ${cronica && l.cant_por_entrega > 0 && html`<span className="ayuda">Total: ${l.cant_por_entrega * entregas} en ${entregas} entregas</span>`}</div>
          </div>
          <div className="campo"><label htmlFor=${"r-pos-" + i}>Posología</label>
            <input id=${"r-pos-" + i} required minLength="3" maxLength="200" placeholder="1 comprimido cada 12 h"
                   value=${l.posologia} onChange=${(e) => cambiar(i, "posologia", e.target.value)} /></div>
          ${lineas.length > 1 && html`<button type="button" className="boton chico secundario"
              onClick=${() => setLineas(lineas.filter((_, j) => j !== i))}>Quitar medicamento ${i + 1}</button>`}
        </fieldset>`)}
        <button type="button" className="boton secundario chico" style=${{ marginBottom: "1rem" }} disabled=${lineas.length >= 30}
                onClick=${() => setLineas([...lineas, lineaVacia()])}>+ Agregar otro medicamento</button>

        <div className="acciones">
          <button className="boton" disabled=${enviando || !meds}>${enviando ? "Guardando…" : "Guardar receta"}</button>
          <button type="button" className="boton secundario" onClick=${onCerrar}>Cancelar</button>
        </div>
      </form>
    </div>`;
  }

  function Dispensar({ permisos, contexto }) {
    const [rut, setRut] = useState("");
    const [noEncontrado, setNoEncontrado] = useState(false);
    const [dialogo, setDialogo] = useState(null);
    const puedeRegistrar = permisos.includes("registrar_paciente");
    const puedeRecetar = permisos.includes("registrar_receta");
    const puedeDispensar = permisos.includes("dispensar");
    const [nuevaReceta, setNuevaReceta] = useState(false);
    const [resultado, setResultado] = useState(null);
    const [receta, setReceta] = useState(null);
    const [lineas, setLineas] = useState({});
    const RETIRO_INICIAL = { tipo: "", id_apoderado: "", rut_retira: "", relacion: "", rut_qf: "", pin_qf: "",
                             confirma_alergias: false, a_domicilio: false };
    const [retiro, setRetiro] = useState(RETIRO_INICIAL);
    const [clave, setClave] = useState(nuevaClave());
    const [mensaje, setMensaje] = useState(null);
    const [error, setError] = useState(null);
    const [entrega, setEntrega] = useState(null);
    const recargarFicha = async (id) => setResultado(await api("GET", `/api/pacientes/${id}/ficha`));
    useEffect(() => {  // llegada desde "Retiros del día": se abre la ficha sin volver a escribir el RUT
      if (contexto && contexto.id_paciente) recargarFicha(contexto.id_paciente).catch((err) => setError(err.message));
    }, [contexto]); // eslint-disable-line
    function agregarApoderado() {
      setDialogo({ titulo: "Agregar apoderado", textoAceptar: "Registrar",
        descripcion: "Persona autorizada a retirar en nombre del paciente. Su RUT se guarda protegido.",
        campos: [
          { nombre: "rut", etiqueta: "RUT del apoderado", ayuda: "(sin puntos, con guion)" },
          { nombre: "nombre", etiqueta: "Nombre completo", minimo: 3 },
          { nombre: "parentesco", etiqueta: "Parentesco", inicial: "Hijo/a",
            opciones: ["Hijo/a", "Cónyuge o pareja", "Padre/madre", "Hermano/a", "Cuidador/a", "Otro"].map((x) => [x, x]) },
          { nombre: "telefono", etiqueta: "Teléfono", requerido: false },
          { nombre: "vigente_hasta", etiqueta: "Autorizado hasta", tipo: "date", requerido: false, ayuda: "(vacío: sin vencimiento)" },
        ],
        onAceptar: async (v) => {
          if (!rutValido(v.rut)) throw new Error("RUT inválido: revise el dígito verificador.");
          await api("POST", `/api/pacientes/${resultado.paciente.id_paciente}/apoderados`, { ...v,
            telefono: v.telefono.trim() || null, vigente_hasta: v.vigente_hasta || null });
          await recargarFicha(resultado.paciente.id_paciente); setMensaje(`Apoderado ${v.nombre} registrado.`);
        } });
    }
    function bajaApoderado(a) {
      setDialogo({ titulo: `Dar de baja a ${a.nombre}`, peligro: true, textoAceptar: "Dar de baja",
        descripcion: "Deja de estar autorizado para retirar; sus retiros anteriores se conservan.",
        campos: [{ nombre: "motivo", etiqueta: "Motivo", minimo: 10, ayuda: "(mínimo 10 caracteres)" }],
        onAceptar: async (v) => { await api("POST", `/api/apoderados/${a.id_apoderado}/baja`, v);
          await recargarFicha(resultado.paciente.id_paciente); setMensaje(`${a.nombre} dado de baja como apoderado.`); } });
    }

    async function buscar(e, rutBuscado = rut) {
      e && e.preventDefault(); setError(null); setResultado(null); setReceta(null); setEntrega(null); setNoEncontrado(false);
      if (!rutValido(rutBuscado)) { setError("RUT inválido: revise el dígito verificador."); return; }
      try { setResultado(await api("POST", "/api/pacientes/buscar", { rut: rutBuscado })); }
      catch (err) { setError(err.message); setNoEncontrado(err.codigo === "NO_ENCONTRADO"); }
    }
    async function registrarPaciente() {
      let programas = [], sectores = [];
      try { ({ programas, sectores } = await api("GET", "/api/catalogos")); } catch (_) { /* se registra sin catálogos */ }
      setDialogo({ titulo: "Registrar paciente", textoAceptar: "Registrar",
        descripcion: "El RUT se guarda protegido: solo se muestra enmascarado.",
        campos: [
          { nombre: "rut", etiqueta: "RUT", ayuda: "(sin puntos, con guion)", inicial: rutValido(rut) ? rut : "" },
          { nombre: "nombre", etiqueta: "Nombre completo", minimo: 3 },
          { nombre: "fecha_nacimiento", etiqueta: "Fecha de nacimiento", tipo: "date", requerido: false,
            max: new Date().toISOString().slice(0, 10) },
          { nombre: "tramo_fonasa", etiqueta: "Tramo FONASA", inicial: "",
            opciones: [["", "Sin información"], ["A", "A"], ["B", "B"], ["C", "C"], ["D", "D"]] },
          { nombre: "es_prais", etiqueta: "Beneficiario PRAIS", inicial: "no", opciones: [["no", "No"], ["si", "Sí"]] },
          ...(sectores.length ? [{ nombre: "id_sector", etiqueta: "Sector", inicial: "",
            opciones: [["", "Sin asignar"], ...sectores.map((x) => [String(x.id_sector), x.nombre])] }] : []),
          { nombre: "alergias", etiqueta: "Alergias", requerido: false, ayuda: "(se muestran como alerta al dispensar)" },
          { nombre: "es_postrado", etiqueta: "Paciente postrado", inicial: "no",
            opciones: [["no", "No"], ["si", "Sí (despacho a domicilio)"]] },
          { nombre: "direccion", etiqueta: "Dirección", requerido: false, ayuda: "(solo pacientes postrados)" },
          ...(programas.length ? [{ nombre: "programas", etiqueta: "Programas de salud", multiple: true, inicial: [],
            opciones: programas.map((p) => [p.id_programa, p.nombre]) }] : []),
        ],
        onAceptar: async (v) => {
          if (!rutValido(v.rut)) throw new Error("RUT inválido: revise el dígito verificador.");
          const p = await api("POST", "/api/pacientes", { rut: v.rut, nombre: v.nombre,
            fecha_nacimiento: v.fecha_nacimiento || null, tramo_fonasa: v.tramo_fonasa || null, programas: v.programas || [],
            id_sector: v.id_sector ? Number(v.id_sector) : null, es_prais: v.es_prais === "si",
            es_postrado: v.es_postrado === "si", alergias: v.alergias.trim() || null, direccion: v.direccion.trim() || null });
          setRut(v.rut); await buscar(null, v.rut); setMensaje(`Paciente ${p.nombre} registrado.`);
        } });
    }
    function elegir(r) {
      setReceta(r); setEntrega(null); setMensaje(null); setError(null); setClave(nuevaClave()); setRetiro(RETIRO_INICIAL);
      setLineas(Object.fromEntries(r.detalles.filter((d) => d.saldo_entrega > 0)
        .map((d) => [d.id_detalle_receta, { id_detalle_receta: d.id_detalle_receta, cantidad: d.saldo_entrega,
          lotes_escaneados: [], motivo: "" }])));
    }
    const hayControlados = receta && receta.detalles.some((d) => d.es_controlado && lineas[d.id_detalle_receta]?.cantidad > 0);
    const apoderadosVigentes = (resultado?.apoderados || []).filter((a) => a.vigente);
    const tipoRetiro = retiro.tipo || (hayControlados ? "TERCERO" : "PACIENTE");
    const hoyTexto = fechaLocal(new Date());
    async function sinStock(r) {
      setError(null); setMensaje(null);
      try {
        const s = await api("POST", `/api/recetas/${r.id_receta}/sin-stock`);
        setMensaje(`Receta ${s.folio}: quedó registrada la solicitud sin stock.` + (s.faltantes.length
          ? ` Compromiso de entrega hasta ${fechaHora(s.faltantes[0].plazo)}.` : " Ya tenía un compromiso de entrega abierto."));
        await recargarFicha(resultado.paciente.id_paciente);
      } catch (err) { setError(err.message); }
    }
    async function confirmar() {
      setError(null); setMensaje(null);
      const todas = Object.values(lineas);
      const cuerpo = { id_receta: receta.id_receta, clave_idempotencia: clave,
        lineas: todas.filter((l) => l.cantidad > 0).map(({ id_detalle_receta, cantidad, lotes_escaneados }) =>
          ({ id_detalle_receta, cantidad, lotes_escaneados })) };
      const motivos = Object.fromEntries(todas.filter((l) => l.motivo).map((l) => [l.id_detalle_receta, l.motivo]));
      if (Object.keys(motivos).length) cuerpo.motivos_incompletos = motivos;
      cuerpo.retira_tipo = tipoRetiro;
      if (tipoRetiro === "APODERADO") cuerpo.id_apoderado = Number(retiro.id_apoderado) || null;
      if (tipoRetiro === "TERCERO") Object.assign(cuerpo, { rut_retira: retiro.rut_retira, relacion: retiro.relacion });
      if (tipoRetiro === "PACIENTE" && hayControlados) cuerpo.rut_retira = retiro.rut_retira;
      if (resultado.paciente.alergias) cuerpo.confirma_alergias = retiro.confirma_alergias;
      if (retiro.a_domicilio && !hayControlados) cuerpo.a_domicilio = true;
      if (hayControlados) cuerpo.firma_qf = { rut: retiro.rut_qf, pin: retiro.pin_qf };
      try {
        const r = await api("POST", "/api/dispensaciones", cuerpo);
        setEntrega(r);
        setMensaje(`Entrega ${r.numero_entrega} de ${r.total_entregas} registrada (receta ${r.folio}: ${ESTADOS[r.estado_receta][2].toLowerCase()}).`
          + (r.id_despacho ? " Despacho a domicilio en preparación." : "")
          + (r.total_entregas > 1 && r.proxima_fecha_retiro ? ` Próximo retiro: ${fecha(r.proxima_fecha_retiro)}.` : "")
          + r.faltantes.map((f) => f.motivo === "SIN_STOCK"
            ? ` Pendiente por quiebre: ${f.medicamento} (${f.cantidad} u.), compromiso hasta ${fechaHora(f.plazo)}.`
            : ` No llevó ${f.medicamento} (${f.cantidad} u.): rechazo del paciente.`).join(""));
        setReceta(null); setRetiro(RETIRO_INICIAL);
        await recargarFicha(resultado.paciente.id_paciente);
      } catch (err) { setError(err.message); }
    }

    return html`<div>
      <form className="tarjeta fila-campos" onSubmit=${buscar}>
        <div className="campo"><label htmlFor="rut-paciente">RUT del paciente</label>
          <input id="rut-paciente" value=${rut} placeholder="12345678-5" aria-invalid=${rut.length > 8 && !rutValido(rut)}
                 onChange=${(e) => setRut(e.target.value)} /></div>
        <div className="campo"><span className="etiqueta-vacia" aria-hidden="true"></span><button className="boton ancho-movil">Buscar recetas</button></div>
        ${puedeRegistrar && html`<div className="campo"><span className="etiqueta-vacia" aria-hidden="true"></span>
          <button type="button" className="boton secundario ancho-movil" onClick=${registrarPaciente}>Registrar paciente</button></div>`}
      </form>
      <${Aviso} tipo="error">${error}<//>
      ${noEncontrado && puedeRegistrar && html`<div className="acciones" style=${{ marginBottom: "1rem" }}>
        <button type="button" className="boton" onClick=${registrarPaciente}>Registrar este paciente</button></div>`}
      <${Aviso} tipo="ok">${mensaje}<//>
      ${entrega && entrega.rotulos.length > 0 && html`<div className="tarjeta imprimible"><h2 className="no-imprimir">Rótulos de unidosis</h2>
        <div className="rejilla k2">${entrega.rotulos.map((r, i) => html`<div className="rotulo" key=${i}>
          <strong>${r.medicamento}</strong>
          <div>Paciente: ${r.paciente} · Programa: ${r.programa}${r.entrega ? ` · Entrega ${r.entrega}` : ""}</div>
          <div className="tabular">Lote ${r.lote} · Vence ${fecha(r.vencimiento)} · ${r.cantidad} u.</div>
          <div>${r.posologia}</div></div>`)}</div>
        <button className="boton secundario no-imprimir" onClick=${imprimirEtiqueta}><${Icono} nombre="imprimir" />Imprimir rótulos</button>
      </div>`}
      ${resultado && html`<div className="tarjeta">
        <h2>${resultado.paciente.nombre} <span className="ayuda">${resultado.paciente.rut}</span></h2>
        <div className="ficha-paciente">
          <span>${resultado.paciente.sector || "Sin sector"}</span>
          <span>FONASA ${resultado.paciente.tramo_fonasa || "s/i"}</span>
          ${resultado.paciente.es_prais && html`<${Estado} valor="CONTROLADO" texto="PRAIS" />`}
          ${resultado.paciente.es_postrado && html`<${Estado} valor="ALERTA" texto="Postrado · despacho a domicilio" />`}
        </div>
        <p className="ayuda">Programas: ${resultado.paciente.programas.join(", ") || "-"}</p>
        ${resultado.paciente.alergias && html`<div className="aviso error" role="note"><strong>Alergias:</strong> ${resultado.paciente.alergias}</div>`}
        <div className="apoderados">
          <div className="acciones" style=${{ justifyContent: "space-between" }}>
            <h3 style=${{ margin: 0 }}>Apoderados</h3>
            ${puedeRegistrar && html`<button className="boton chico secundario" onClick=${agregarApoderado}><${Icono} nombre="mas" />Agregar apoderado</button>`}
          </div>
          ${(resultado.apoderados || []).length === 0
            ? html`<p className="ayuda">Sin apoderados registrados.</p>`
            : html`<ul className="lista-apoderados">${resultado.apoderados.map((a) => html`<li key=${a.id_apoderado}>
                <span><strong>${a.nombre}</strong> · ${a.parentesco} · <span className="mono">${a.rut}</span>${a.telefono ? " · " + a.telefono : ""}
                  ${!a.vigente && html` <${Estado} valor="INACTIVO" texto="Autorización vencida" />`}</span>
                ${puedeRegistrar && html`<button className="boton chico peligro" onClick=${() => bajaApoderado(a)}>Dar de baja</button>`}</li>`)}</ul>`}
        </div>
        ${puedeRecetar && html`<div className="acciones" style=${{ marginBottom: ".75rem" }}>
          <button className="boton secundario" onClick=${() => setNuevaReceta(true)}><${Icono} nombre="mas" />Nueva receta</button></div>`}
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Folio</th><th>Tipo</th><th>Emisión</th><th>Entregas</th><th>Próximo retiro</th><th>Vigencia</th><th>Estado</th><th></th></tr></thead>
          <tbody>${resultado.recetas.length === 0 && html`<tr><td colSpan="8">El paciente no tiene recetas registradas.</td></tr>`}
          ${resultado.recetas.map((r) => html`<tr key=${r.id_receta}>
            <td>${r.folio}</td>
            <td>${r.es_retenida ? html`<${Estado} valor="CONTROLADO" texto="Retenida" />` : TIPOS_RECETA[r.tipo_receta]}</td>
            <td>${fecha(r.fecha_emision)}</td>
            <td className="tabular">${r.entregas_realizadas} de ${r.total_entregas}</td>
            <td className="tabular">${r.proxima_fecha_retiro ? fecha(r.proxima_fecha_retiro) : "-"}
              ${r.retiro_desde && r.retiro_desde > hoyTexto && html`<div className="ayuda">Se retira desde ${fecha(r.retiro_desde)}</div>`}</td>
            <td>${r.vigente ? html`<${Estado} valor="VIGENTE" />` : html`<${Estado} valor="NO_DISPENSABLE" texto="Vencida" />`}</td>
            <td><${Estado} valor=${r.estado} /></td>
            <td>${puedeDispensar && html`<button className="boton chico" disabled=${!r.vigente || r.estado === "DISPENSADA" || r.estado === "ANULADA"
                          || (r.retiro_desde && r.retiro_desde > hoyTexto)}
                        onClick=${() => elegir(r)}>Atender receta</button>`}
              ${puedeDispensar && r.vigente && r.estado !== "DISPENSADA" && r.estado !== "ANULADA" && !(r.retiro_desde && r.retiro_desde > hoyTexto)
                && html`<button className="boton chico secundario" title="No hay stock de nada de lo que corresponde: queda el compromiso de 24 h hábiles"
                        onClick=${() => sinStock(r)}>Sin stock</button>`}</td></tr>`)}</tbody>
        </table></div>
      </div>`}
      ${receta && html`<div>
        <h2>Receta ${receta.folio}</h2>
        ${receta.detalles.filter((d) => lineas[d.id_detalle_receta]).map((d) => html`<${LineaReceta} key=${d.id_detalle_receta}
            detalle=${d} linea=${lineas[d.id_detalle_receta]} onCambio=${(l) => setLineas({ ...lineas, [d.id_detalle_receta]: l })} />`)}
        <div className="tarjeta"><h3>Retiro${receta.total_entregas > 1 ? ` · entrega ${receta.entrega_actual} de ${receta.total_entregas}` : ""}</h3>
          <div className="fila-campos">
            <div className="campo"><label htmlFor="quien">Quién retira</label>
              <select id="quien" value=${tipoRetiro} disabled=${retiro.a_domicilio}
                      onChange=${(e) => setRetiro({ ...retiro, tipo: e.target.value })}>
                <option value="PACIENTE">El paciente</option>
                ${apoderadosVigentes.length > 0 && html`<option value="APODERADO">Apoderado registrado</option>`}
                <option value="TERCERO">Otra persona</option>
              </select></div>
            ${tipoRetiro === "APODERADO" && html`<div className="campo"><label htmlFor="apo">Apoderado</label>
              <select id="apo" value=${retiro.id_apoderado} onChange=${(e) => setRetiro({ ...retiro, id_apoderado: e.target.value })}>
                <option value="">Seleccione…</option>
                ${apoderadosVigentes.map((a) => html`<option key=${a.id_apoderado} value=${a.id_apoderado}>${a.nombre} (${a.parentesco}, ${a.rut})</option>`)}
              </select></div>`}
            ${(tipoRetiro === "TERCERO" || (tipoRetiro === "PACIENTE" && hayControlados)) && html`<div className="campo">
              <label htmlFor="rr">RUT de quien retira</label><input id="rr" value=${retiro.rut_retira}
              aria-invalid=${retiro.rut_retira.length > 8 && !rutValido(retiro.rut_retira)} onChange=${(e) => setRetiro({ ...retiro, rut_retira: e.target.value })} /></div>`}
            ${tipoRetiro === "TERCERO" && html`<div className="campo"><label htmlFor="rel">Relación con el paciente</label><input id="rel" placeholder="Hija, vecino, cuidador…"
              value=${retiro.relacion} onChange=${(e) => setRetiro({ ...retiro, relacion: e.target.value })} /></div>`}
          </div>
          ${resultado.paciente.es_postrado && resultado.paciente.tiene_direccion && !hayControlados && html`
            <label className="casilla-linea"><input type="checkbox" checked=${retiro.a_domicilio}
              onChange=${(e) => setRetiro({ ...retiro, a_domicilio: e.target.checked, tipo: e.target.checked ? "PACIENTE" : retiro.tipo })} />
              Despachar a domicilio (paciente postrado)</label>`}
          ${resultado.paciente.alergias && html`<div className="aviso error" role="note" style=${{ marginTop: ".75rem" }}>
            <label className="casilla-linea" style=${{ color: "inherit" }}><input type="checkbox" checked=${retiro.confirma_alergias}
              onChange=${(e) => setRetiro({ ...retiro, confirma_alergias: e.target.checked })} />
              Revisé las alergias del paciente (${resultado.paciente.alergias}) y la entrega es compatible.</label></div>`}
        </div>
        ${hayControlados && html`<div className="tarjeta"><h3><${Estado} valor="CONTROLADO" /> Firma del Q.F.</h3>
          <p className="ayuda">Controlado: receta retenida, identificación de quien retira y firma del Q.F. con su PIN.</p>
          <div className="fila-campos">
            <div className="campo"><label htmlFor="rqf">RUT del Q.F.</label><input id="rqf" value=${retiro.rut_qf}
              onChange=${(e) => setRetiro({ ...retiro, rut_qf: e.target.value })} /></div>
            <div className="campo"><label htmlFor="pqf">PIN de firma del Q.F.</label><input id="pqf" type="password" inputMode="numeric"
              autoComplete="off" value=${retiro.pin_qf} onChange=${(e) => setRetiro({ ...retiro, pin_qf: e.target.value })} /></div>
          </div></div>`}
        <div className="acciones">
          <button className="boton ancho-movil" onClick=${confirmar}>Confirmar entrega</button>
          <button className="boton secundario" onClick=${() => setReceta(null)}>Cancelar</button>
        </div>
      </div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${nuevaReceta && resultado && html`<${NuevaReceta} paciente=${resultado.paciente}
          puedeControlados=${permisos.includes("firmar_controlados")} onCerrar=${() => setNuevaReceta(false)}
          onCreada=${async (r) => { await recargarFicha(resultado.paciente.id_paciente); setMensaje(`Receta ${r.folio} registrada con ${r.detalles.length} medicamento(s)`
            + (r.total_entregas > 1 ? `, crónica de ${r.total_entregas} entregas.` : ".")); }} />`}
    </div>`;
  }

  // -------------------------------------------------------------- inventario
  function Inventario({ permisos }) {
    const [verCerrados, setVerCerrados] = useState(false);
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/lotes?incluir_cerrados=" + verCerrados), [verCerrados]);
    const [catalogo] = useCarga(() => Promise.all([api("GET", "/api/medicamentos"), api("GET", "/api/catalogos")]), []);
    const [dialogo, setDialogo] = useState(null);
    const [kardex, setKardex] = useState(null);
    const [aviso, setAviso] = useState(null);
    const puede = (p) => permisos.includes(p);

    async function abrirKardex(lote) {
      setKardex({ lote, filas: await api("GET", `/api/lotes/${lote.id_lote}/kardex`) });
    }
    function accion(tipo, lote) {
      const configuraciones = {
        ajuste: { titulo: `Ajustar cantidad del lote ${lote.codigo_lote}`, textoAceptar: "Registrar ajuste",
          descripcion: "Para corregir una cantidad mal ingresada. Queda un movimiento AJUSTE en el kardex.",
          campos: [{ nombre: "unidades_correctas", etiqueta: "Unidades correctas", tipo: "number", min: 0, inicial: lote.unidades_disp },
                   { nombre: "motivo", etiqueta: "Motivo", minimo: 10, ayuda: "(mínimo 10 caracteres)" }],
          enviar: (v) => api("POST", `/api/lotes/${lote.id_lote}/ajuste`, { unidades_correctas: Number(v.unidades_correctas), motivo: v.motivo }) },
        anular: { titulo: `Anular lote ${lote.codigo_lote}`, textoAceptar: "Anular lote", peligro: true,
          descripcion: "Da de baja un lote mal ingresado. No se borra: queda en el historial con su motivo. Solo es posible si nunca se dispensó.",
          campos: [{ nombre: "motivo", etiqueta: "Motivo de la anulación", minimo: 10, ayuda: "(mínimo 10 caracteres)" }],
          enviar: (v) => api("POST", `/api/lotes/${lote.id_lote}/anular`, v) },
        merma: { titulo: `Retirar a merma: ${lote.codigo_lote}`, textoAceptar: "Registrar merma",
          campos: [{ nombre: "cantidad", etiqueta: "Cantidad", tipo: "number", min: 1, max: lote.unidades_disp, inicial: lote.unidades_disp },
                   { nombre: "motivo", etiqueta: "Motivo", opciones: [["VENCIMIENTO", "Vencimiento"], ["DANO", "Daño"], ["ALERTA_SANITARIA", "Alerta sanitaria (ISP)"]], inicial: "VENCIMIENTO" }],
          enviar: (v) => api("POST", `/api/lotes/${lote.id_lote}/merma`, { cantidad: Number(v.cantidad), motivo: v.motivo }) },
      };
      const c = configuraciones[tipo];
      setDialogo({ ...c, onAceptar: async (v) => { await c.enviar(v); setAviso(`${c.textoAceptar}: listo.`); recargar(); } });
    }
    function ingresar() {
      const [meds, cat] = catalogo.datos;
      setDialogo({ titulo: "Ingresar lote (recepción)", textoAceptar: "Ingresar",
        campos: [
          { nombre: "id_medicamento", etiqueta: "Medicamento", opciones: meds.map((m) => [m.id_medicamento, m.nombre]), inicial: meds[0]?.id_medicamento },
          { nombre: "codigo_lote", etiqueta: "Código de lote" },
          { nombre: "fecha_vencimiento", etiqueta: "Fecha de vencimiento", tipo: "date" },
          { nombre: "unidades", etiqueta: "Unidades", tipo: "number", min: 1 },
          { nombre: "id_ubicacion", etiqueta: "Ubicación", opciones: cat.ubicaciones.map((u) => [u.id_ubicacion, `${u.codigo} (${u.tipo})`]), inicial: cat.ubicaciones[0]?.id_ubicacion },
          { nombre: "proveedor", etiqueta: "Proveedor", inicial: "CENABAST", requerido: false },
          { nombre: "tipo_documento", etiqueta: "Documento de recepción", inicial: "FACTURA",
            opciones: [["FACTURA", "Factura"], ["GUIA", "Guía de despacho"], ["DONACION", "Donación"], ["", "Sin documento"]] },
          { nombre: "numero_documento", etiqueta: "N.º de documento", requerido: false },
          { nombre: "fecha_documento", etiqueta: "Fecha del documento", tipo: "date", requerido: false, max: fechaLocal(new Date()) },
          { nombre: "costo_total", etiqueta: "Costo total neto ($)", tipo: "number", min: 0, requerido: false, ayuda: "(valoriza el inventario: FOFAR)" },
        ],
        descripcion: "En un controlado solo el Q.F. recibe y el libro exige proveedor, documento y fecha (D.S. 404/405 art. 18).",
        onAceptar: async (v) => {
          const r = await api("POST", "/api/lotes", { ...v, id_medicamento: Number(v.id_medicamento), unidades: Number(v.unidades), id_ubicacion: Number(v.id_ubicacion),
            proveedor: v.proveedor.trim() || null, tipo_documento: v.tipo_documento || null, numero_documento: v.numero_documento.trim() || null,
            fecha_documento: v.fecha_documento || null, costo_total: v.costo_total === "" ? null : Number(v.costo_total) });
          setAviso(`Lote ${r.lote.codigo_lote} ingresado.` + (r.alertas.length ? " Alertas: " + r.alertas.join(" ") : "")); recargar();
        } });
    }

    return html`<div>
      <div className="acciones" style=${{ marginBottom: "1rem" }}>
        ${puede("gestionar_lotes") && catalogo.datos && html`<button className="boton" onClick=${ingresar}><${Icono} nombre="mas" />Ingresar lote</button>`}
        <label className="casilla-linea"><input type="checkbox"
          checked=${verCerrados} onChange=${(e) => setVerCerrados(e.target.checked)} /> Mostrar lotes anulados y en merma</label>
      </div>
      <${Aviso} tipo="ok">${aviso}<//>
      <${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Lote</th><th>Medicamento</th><th>Ubicación</th><th>Vence</th><th className="num">Días</th><th className="num">Stock</th><th className="num">Costo u.</th><th>Estado</th><th>Acciones</th></tr></thead>
        <tbody>${datos.map((l) => html`<tr key=${l.id_lote} className=${l.estado === "ANULADO" || l.estado === "MERMA" ? "inactivo" : ""}>
          <td className="tabular"><strong>${l.codigo_lote}</strong></td><td>${l.medicamento}</td><td>${l.ubicacion}</td>
          <td className="tabular">${fecha(l.fecha_vencimiento)}</td><td className="num">${l.dias_para_vencer}</td><td className="num">${l.unidades_disp}</td>
          <td className="num" title=${l.numero_documento ? `${l.proveedor || ""} · ${l.tipo_documento} ${l.numero_documento}` : "Sin documento"}>${l.costo_unitario === null ? "-" : "$" + l.costo_unitario.toLocaleString("es-CL")}</td>
          <td><${Estado} valor=${l.estado} />${l.motivo_anulacion && html`<div className="ayuda">${l.motivo_anulacion}</div>`}</td>
          <td><div className="acciones">
            <button className="boton chico secundario" onClick=${() => abrirKardex(l)}>Kardex</button>
            ${l.estado !== "ANULADO" && l.estado !== "MERMA" && html`
              ${puede("gestionar_lotes") && html`<button className="boton chico secundario" onClick=${() => accion("ajuste", l)}>Ajustar</button>`}
              ${puede("registrar_merma") && l.unidades_disp > 0 && html`<button className="boton chico secundario" onClick=${() => accion("merma", l)}>Merma</button>`}
              ${puede("anular_lote") && html`<button className="boton chico peligro" onClick=${() => accion("anular", l)}>Anular</button>`}`}
          </div></td></tr>`)}</tbody>
      </table></div></div>`}
      ${kardex && html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && setKardex(null)}>
        <div className="dialogo dialogo-ancho" role="dialog" aria-modal="true" aria-label="Kardex"><h2>Kardex del lote ${kardex.lote.codigo_lote}</h2>
          ${kardex.filas.length > 1 && html`<${Grafico} tipo="linea" titulo="Saldo del lote" alto=${170}
              descripcion=${`${kardex.filas.length < 100 ? "Todos los" : "Últimos"} ${kardex.filas.length} movimientos, uno por punto`}
              datos=${kardex.filas.map((f) => ({ etiqueta: fechaCorta(f.fecha_hora), etiquetaLarga: fechaHora(f.fecha_hora), valor: f.saldo_resultante,
                                                 detalle: `${f.tipo.replace(/_/g, " ").toLowerCase()} ${f.cantidad > 0 ? "+" : ""}${f.cantidad}` }))}
              formato=${(v) => `${numero(v)} u.`}
              columnas=${[["Fecha", (f) => f.etiquetaLarga], ["Saldo", (f) => numero(f.valor), true], ["Movimiento", (f) => f.detalle]]} />`}
          <div className="tabla-envoltura"><table><thead><tr><th>Fecha</th><th>Tipo</th><th className="num">Cant.</th><th className="num">Saldo</th><th>Motivo</th></tr></thead>
          <tbody>${kardex.filas.map((m) => html`<tr key=${m.id_movimiento}><td>${fechaHora(m.fecha_hora)}</td><td>${m.tipo}</td>
            <td className="num">${m.cantidad > 0 ? "+" : ""}${m.cantidad}</td><td className="num">${m.saldo_resultante}</td><td>${m.motivo || m.referencia || ""}</td></tr>`)}</tbody></table></div>
          <button className="boton secundario" onClick=${() => setKardex(null)}>Cerrar</button></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------------ medicamentos
  function MedicamentosVista({ permisos }) {
    const [inactivos, setInactivos] = useState(true);
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/medicamentos?incluir_inactivos=" + inactivos), [inactivos]);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [filtro, setFiltro] = useState("");
    const [etiqueta, setEtiqueta] = useState(null);
    const [{ datos: catalogo }] = useCarga(() => api("GET", "/api/catalogos"), []);
    const editable = permisos.includes("gestionar_medicamentos");
    useEffect(() => {
      if (!etiqueta) return undefined;
      const alPresionar = (e) => { if (e.key === "Escape") setEtiqueta(null); };
      document.addEventListener("keydown", alPresionar);
      return () => document.removeEventListener("keydown", alPresionar);
    }, [etiqueta]);

    const texto = filtro.trim().toLowerCase();
    const visibles = (datos || []).filter((m) => !texto || m.codigo_barras === texto
      || m.nombre.toLowerCase().includes(texto) || m.codigo.toLowerCase().includes(texto));
    function alEscanear(e) {  // un lector de código de barras escribe los 13 dígitos y envía Enter
      if (e.key !== "Enter") return;
      const exacto = (datos || []).find((m) => m.codigo_barras === filtro.trim());
      if (exacto) setEtiqueta(exacto);
    }

    function crear() {
      setDialogo({ titulo: "Nuevo medicamento", textoAceptar: "Crear", campos: [
        { nombre: "codigo", etiqueta: "Código", ayuda: "(mayúsculas y números)" }, { nombre: "nombre", etiqueta: "Nombre" },
        { nombre: "principio_activo", etiqueta: "Principio activo" },
        { nombre: "concentracion", etiqueta: "Concentración", requerido: false, ayuda: "(p. ej. 50 mg)" },
        { nombre: "forma_farmaceutica", etiqueta: "Forma farmacéutica", inicial: "COMPRIMIDO",
          opciones: (catalogo?.formas_farmaceuticas || [{ codigo: "OTRO", nombre: "Otra" }]).map((f) => [f.codigo, f.nombre]) },
        { nombre: "unidad_dispensacion", etiqueta: "Unidad de dispensación", inicial: "COMPRIMIDO",
          opciones: (catalogo?.unidades_dispensacion || [{ codigo: "UNIDAD", nombre: "unidad" }]).map((u) => [u.codigo, u.nombre]) },
        { nombre: "codigo_barras", etiqueta: "Código de barras EAN-13", requerido: false,
          ayuda: "(opcional: el de la caja; si se deja vacío se genera uno interno)" },
        { nombre: "unidades_envase", etiqueta: "Unidades por envase", tipo: "number", min: 1 },
        { nombre: "umbral_critico", etiqueta: "Umbral crítico", tipo: "number", min: 0, inicial: 0 }],
        onAceptar: async (v) => {
          if (v.codigo_barras && !window.CodigoBarras.valido(v.codigo_barras.trim()))
            throw new Error("El código de barras debe tener 13 dígitos y un dígito verificador válido.");
          const m = await api("POST", "/api/medicamentos", { ...v, codigo_barras: v.codigo_barras.trim() || null,
            concentracion: v.concentracion.trim() || null,
            unidades_envase: Number(v.unidades_envase), umbral_critico: Number(v.umbral_critico) });
          setAviso(`Medicamento ${m.nombre} creado con código de barras ${m.codigo_barras}.`); recargar(); setEtiqueta(m);
        } });
    }
    function baja(m) {
      setDialogo({ titulo: `Dar de baja: ${m.nombre}`, peligro: true, textoAceptar: "Dar de baja",
        descripcion: "La baja es lógica: el medicamento deja de usarse, pero se conserva para las recetas y dispensaciones históricas. Solo se permite sin stock dispensable.",
        campos: [{ nombre: "motivo", etiqueta: "Motivo", minimo: 10, ayuda: "(mínimo 10 caracteres)" }],
        onAceptar: async (v) => { await api("POST", `/api/medicamentos/${m.id_medicamento}/baja`, v); setAviso(`${m.nombre} dado de baja.`); recargar(); } });
    }
    async function reactivar(m) {
      try { await api("POST", `/api/medicamentos/${m.id_medicamento}/reactivar`); setAviso(`${m.nombre} reactivado.`); recargar(); }
      catch (err) { setAviso(null); alert(err.message); }
    }
    return html`<div>
      <div className="barra-herramientas">
        <div className="acciones" style=${{ flex: 1 }}>
          <div className="buscador"><${Icono} nombre="buscar" />
            <label htmlFor="buscar-med" className="sr-only">Buscar medicamento</label>
            <input id="buscar-med" type="search" placeholder="Buscar por nombre, código o código de barras" value=${filtro}
                   onChange=${(e) => setFiltro(e.target.value)} onKeyDown=${alEscanear} /></div>
          <label className="casilla-linea"><input type="checkbox" checked=${inactivos}
            onChange=${(e) => setInactivos(e.target.checked)} /> Incluir dados de baja</label>
        </div>
        ${editable && html`<button className="boton" onClick=${crear}><${Icono} nombre="mas" />Nuevo medicamento</button>`}
      </div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Código</th><th>Nombre</th><th>Código de barras</th><th>Programa</th><th className="num">Envase</th><th>Estado</th><th>Acciones</th></tr></thead>
        <tbody>${visibles.length === 0 && html`<tr><td colSpan="7">No hay medicamentos que coincidan con la búsqueda.</td></tr>`}
        ${visibles.map((m) => html`<tr key=${m.id_medicamento} className=${m.activo ? "" : "inactivo"}>
          <td className="mono">${m.codigo}</td><td>${m.nombre} ${m.es_controlado && html`<${Estado} valor="CONTROLADO" />`} ${m.es_ges && html`<${Estado} valor="VIGENTE" texto="GES" />`}
            <div className="ayuda">${m.principio_activo}${m.concentracion ? " · " + m.concentracion : ""} · se entrega por ${(m.unidad_dispensacion || "").toLowerCase()}</div></td>
          <td><div className="celda-barras"><${CodigoBarras} codigo=${m.codigo_barras} conTexto=${false} />
            <span className="mono">${m.codigo_barras}</span></div></td>
          <td>${m.programa || "-"}</td><td className="num">${m.unidades_envase}</td>
          <td><${Estado} valor=${m.activo ? "ACTIVO" : "INACTIVO"} />${!m.activo && html`<div className="ayuda">${fecha(m.fecha_baja)} · ${m.motivo_baja}</div>`}</td>
          <td><div className="acciones">
            <button className="boton chico secundario" onClick=${() => setEtiqueta(m)}>Etiqueta</button>
            ${editable && (m.activo
              ? html`<button className="boton chico peligro" onClick=${() => baja(m)}>Dar de baja</button>`
              : html`<button className="boton chico secundario" onClick=${() => reactivar(m)}>Reactivar</button>`)}</div></td>
        </tr>`)}</tbody></table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${etiqueta && html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && setEtiqueta(null)}>
        <div className="dialogo" role="dialog" aria-modal="true" aria-label=${"Etiqueta de " + etiqueta.nombre}
>
          <h2>Etiqueta de código de barras</h2>
          <p className="ayuda">${etiqueta.codigo_barras.startsWith("200")
            ? "Código interno del CESFAM (prefijo 200, reservado por GS1 para uso interno)."
            : "Código del fabricante (EAN-13 impreso en el envase)."}</p>
          <div className="etiqueta-medicamento imprimible">
            <div className="nombre">${etiqueta.nombre}</div>
            <div className="detalle">${etiqueta.codigo} · ${etiqueta.unidades_envase} u. por envase${etiqueta.es_controlado ? " · Controlado" : ""}</div>
            <${CodigoBarras} codigo=${etiqueta.codigo_barras} />
          </div>
          <div className="acciones">
            <button className="boton" onClick=${imprimirEtiqueta}><${Icono} nombre="imprimir" />Imprimir etiqueta</button>
            <button className="boton secundario" onClick=${() => setEtiqueta(null)}>Cerrar</button>
          </div>
        </div></div>`}
    </div>`;
  }

  // ---------------------------------------------------------- dispensaciones
  function Dispensaciones({ permisos }) {
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/dispensaciones"), []);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [rotulos, setRotulos] = useState(null);
    const puedeDevolver = permisos.includes("registrar_devolucion");
    function devolver(d, l) {
      setDialogo({ titulo: `Devolución: ${l.medicamento}`, textoAceptar: "Registrar devolución",
        descripcion: `Entrega #${d.id_dispensacion} (${d.folio}), lote ${l.lote}, ${l.cantidad} u. entregadas. `
          + "La receta sigue contando lo entregado." + (l.es_controlado ? " Por ser controlado, queda además en el libro." : ""),
        campos: [
          { nombre: "cantidad", etiqueta: "Unidades devueltas", tipo: "number", min: 1, max: l.cantidad, inicial: 1 },
          { nombre: "destino", etiqueta: "Destino", inicial: "REINGRESO", opciones: [
            ["REINGRESO", "Reingresa al lote (envase íntegro, aprobado por el Q.F.)"], ["DESCARTE", "Descartar (no vuelve al stock)"]] },
          { nombre: "motivo", etiqueta: "Motivo", minimo: 10, ayuda: "(mínimo 10 caracteres)" },
        ],
        onAceptar: async (v) => {
          const r = await api("POST", "/api/devoluciones", { id_detalle_disp: l.id_detalle_disp, cantidad: Number(v.cantidad),
            destino: v.destino, motivo: v.motivo });
          setAviso(`Devolución registrada: ${r.cantidad} u. de ${r.medicamento} (${r.destino === "REINGRESO" ? "reingresan al lote " + r.lote : "descartadas"}).`);
          recargar();
        } });
    }
    async function verRotulos(d) {
      try { setRotulos(await api("GET", `/api/dispensaciones/${d.id_dispensacion}/rotulos`)); }
      catch (err) { setAviso(null); setRotulos(null); alert(err.message); }
    }
    function anular(d) {
      setDialogo({ titulo: `Anular dispensación #${d.id_dispensacion} (${d.folio})`, peligro: true, textoAceptar: "Anular",
        descripcion: "Repone el stock a cada lote, libera la receta y, si hay controlados, agrega un asiento de rectificación al libro (el libro no se modifica).",
        campos: [{ nombre: "motivo", etiqueta: "Motivo de la anulación", minimo: 10, ayuda: "(mínimo 10 caracteres)" }],
        onAceptar: async (v) => { await api("POST", `/api/dispensaciones/${d.id_dispensacion}/anular`, v); setAviso(`Dispensación #${d.id_dispensacion} anulada.`); recargar(); } });
    }
    return html`<div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>#</th><th>Fecha</th><th>Folio</th><th>Paciente</th><th>Detalle</th><th>Estado</th><th></th></tr></thead>
        <tbody>${datos.length === 0 && html`<tr><td colSpan="7">Aún no hay dispensaciones.</td></tr>`}
        ${datos.map((d) => html`<tr key=${d.id_dispensacion} className=${d.estado === "ANULADA" ? "inactivo" : ""}>
          <td className="num">${d.id_dispensacion}</td><td>${fechaHora(d.fecha_hora)}</td><td>${d.folio}</td><td>${d.paciente}</td>
          <td>${d.lineas.map((l, i) => html`<div key=${i} className="linea-entrega"><span className="tabular">${l.medicamento} · ${l.lote} · ${l.cantidad} u.</span>
            ${puedeDevolver && d.estado !== "ANULADA" && html`<button className="boton chico secundario" onClick=${() => devolver(d, l)}>Devolver</button>`}</div>`)}
            <div className="ayuda">Entrega ${d.numero_entrega} de ${d.total_entregas}${d.retira_tipo !== "PACIENTE" ? ` · retira ${d.retira_tipo === "APODERADO" ? "apoderado" : "tercero"} (${d.relacion})` : ""}</div></td>
          <td><${Estado} valor=${d.estado === "ANULADA" ? "ANULADA" : "VIGENTE"} />${d.motivo_anulacion && html`<div className="ayuda">${d.motivo_anulacion}</div>`}</td>
          <td><div className="acciones"><button className="boton chico secundario" onClick=${() => verRotulos(d)}>Rótulos</button>
            ${d.estado !== "ANULADA" && html`<button className="boton chico peligro" onClick=${() => anular(d)}>Anular</button>`}</div></td>
        </tr>`)}</tbody></table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${rotulos && html`<${VentanaRotulos} datos=${rotulos} onCerrar=${() => setRotulos(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------------------- libro
  const TIPOS_ASIENTO = { SALIDA: ["CONTROLADO", "Salida"], INGRESO: ["VIGENTE", "Ingreso"], RECTIFICACION: ["ALERTA", "Rectificación"],
                          DEVOLUCION: ["ALERTA", "Devolución"], MERMA: ["NO_DISPENSABLE", "Merma"], AJUSTE: ["ALERTA", "Ajuste"] };
  function detalleAsiento(a) {
    const c = a.contenido;
    const nombre = c.nombre || c.medicamento;
    if (a.tipo === "SALIDA") return `${c.folio}${c.receta_cheque ? " · receta cheque " + c.receta_cheque : ""} · ${nombre} · lote ${c.lote} · ${c.cantidad} u. · retira ${c.rut_retira} (${c.relacion})`
      + (c.prescriptor ? ` · prescribe ${c.prescriptor}` : "") + (c.paciente ? ` · paciente ${c.paciente}` : "");
    if (a.tipo === "INGRESO") return `${nombre} · lote ${c.lote} · ${c.cantidad} u. · ${c.proveedor}, ${c.documento}`;
    if (a.tipo === "RECTIFICACION") return `Anula asiento ${c.anula_asiento}: ${c.motivo}`;
    if (a.tipo === "DEVOLUCION") return `${c.folio} · ${nombre} · lote ${c.lote} · ${c.cantidad} u. ${c.destino === "REINGRESO" ? "reingresan" : "descartadas"} · ${c.motivo}`;
    return `${nombre} · lote ${c.lote} · ${a.tipo === "AJUSTE" && c.cantidad > 0 ? "+" : ""}${a.tipo === "MERMA" ? -c.cantidad : c.cantidad} u. · ${c.motivo || ""}`;
  }

  function Libro() {
    const [{ datos, error }] = useCarga(() => api("GET", "/api/controlados/libro"), []);
    const [verificacion, setVerificacion] = useState(null);
    return html`<div>
      <div className="acciones" style=${{ marginBottom: "1rem" }}>
        <button className="boton" onClick=${async () => setVerificacion(await api("GET", "/api/controlados/verificar"))}>Verificar integridad</button>
      </div>
      ${verificacion && (verificacion.integra
        ? html`<${Aviso} tipo="ok">Cadena íntegra: ${verificacion.asientos_verificados} asiento(s) verificado(s).<//>`
        : html`<${Aviso} tipo="error">Cadena alterada a partir del asiento ${verificacion.primer_asiento_alterado}.<//>`)}
      <${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th className="num">N°</th><th>Fecha</th><th>Tipo</th><th>Detalle</th><th className="num">Saldo</th><th>Hash</th></tr></thead>
        <tbody>${datos.length === 0 && html`<tr><td colSpan="6">El libro aún no tiene asientos.</td></tr>`}
        ${datos.map((a) => html`<tr key=${a.nro_asiento}><td className="num">${a.nro_asiento}</td><td>${fechaHora(a.fecha_hora)}</td>
          <td><${Estado} valor=${(TIPOS_ASIENTO[a.tipo] || ["NEUTRO"])[0]} texto=${(TIPOS_ASIENTO[a.tipo] || [, a.tipo])[1]} /></td>
          <td>${detalleAsiento(a)}</td>
          <td className="num">${a.saldo ?? "-"}</td>
          <td className="hash">${a.hash_actual.slice(0, 16)}…</td></tr>`)}</tbody></table></div></div>`}
    </div>`;
  }

  // ----------------------------------------------------- usuarios y auditoría
  function Usuarios() {
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/usuarios"), []);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    function crear() {
      setDialogo({ titulo: "Nuevo usuario", textoAceptar: "Crear", campos: [
        { nombre: "rut", etiqueta: "RUT" }, { nombre: "nombre", etiqueta: "Nombre" },
        { nombre: "rol", etiqueta: "Rol", opciones: [["TECNICO", "TENS de farmacia"], ["BODEGUERO", "Bodeguero"], ["QF", "Q.F."], ["MEDICO", "Médico"], ["ADMIN", "Administrador"]], inicial: "TECNICO" },
        { nombre: "password", etiqueta: "Contraseña inicial", tipo: "password", minimo: 12, ayuda: "(mínimo 12 caracteres)" },
        { nombre: "pin", etiqueta: "PIN de firma", ayuda: "(solo Q.F.)", requerido: false }],
        onAceptar: async (v) => { await api("POST", "/api/usuarios", { ...v, pin: v.pin || null }); setAviso("Usuario creado."); recargar(); } });
    }
    function baja(u) {
      setDialogo({ titulo: `Dar de baja a ${u.nombre}`, peligro: true, textoAceptar: "Dar de baja",
        descripcion: "El usuario pierde el acceso de inmediato; sus registros históricos se conservan.",
        campos: [{ nombre: "motivo", etiqueta: "Motivo", minimo: 10 }],
        onAceptar: async (v) => { await api("POST", `/api/usuarios/${u.id_usuario}/baja`, v); setAviso(`${u.nombre} dado de baja.`); recargar(); } });
    }
    return html`<div>
      <div className="acciones" style=${{ marginBottom: "1rem" }}><button className="boton" onClick=${crear}><${Icono} nombre="mas" />Nuevo usuario</button></div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>RUT</th><th>Nombre</th><th>Rol</th><th>Último acceso</th><th>Estado</th><th></th></tr></thead>
        <tbody>${datos.map((u) => html`<tr key=${u.id_usuario} className=${u.activo ? "" : "inactivo"}>
          <td className="mono">${u.rut}</td><td>${u.nombre}</td><td>${NOMBRES_ROL[u.rol] || u.rol}</td><td>${fechaHora(u.ultimo_acceso)}</td>
          <td><${Estado} valor=${u.activo ? "ACTIVO" : "INACTIVO"} /></td>
          <td>${u.activo && html`<button className="boton chico peligro" onClick=${() => baja(u)}>Dar de baja</button>`}</td></tr>`)}</tbody>
      </table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
    </div>`;
  }

  function Auditoria() {
    const [{ datos, error }] = useCarga(() => api("GET", "/api/auditoria?limite=100"), []);
    return html`<div><${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Fecha</th><th>Evento</th><th>Entidad</th><th>Usuario</th><th>Detalle</th></tr></thead>
        <tbody>${datos.map((e) => html`<tr key=${e.id_evento}><td>${fechaHora(e.creado_en)}</td>
          <td><${Estado} valor=${e.tipo_evento.includes("DENEGADO") || e.tipo_evento.includes("FALLIDO") ? "NO_DISPENSABLE" : "PENDIENTE"} texto=${e.tipo_evento} /></td>
          <td>${e.entidad}${e.id_entidad ? " #" + e.id_entidad : ""}</td><td className="num">${e.id_usuario ?? "-"}</td>
          <td className="hash">${JSON.stringify(e.payload)}</td></tr>`)}</tbody></table></div></div>`}</div>`;
  }


  // ----------------------------------------------------- rótulos (reimpresión)
  function VentanaRotulos({ datos, onCerrar }) {
    useEffect(() => {
      const alPresionar = (e) => { if (e.key === "Escape") onCerrar(); };
      document.addEventListener("keydown", alPresionar);
      return () => document.removeEventListener("keydown", alPresionar);
    }, [onCerrar]);
    return html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && onCerrar()}>
      <div className="dialogo dialogo-ancho" role="dialog" aria-modal="true" aria-label=${"Rótulos de la receta " + datos.folio}>
        <h2>Rótulos · receta ${datos.folio}</h2>
        ${datos.estado === "ANULADA" && html`<${Aviso} tipo="info">Esta entrega fue anulada.<//>`}
        <div className="rejilla k2 imprimible">${datos.rotulos.map((r, i) => html`<div className="rotulo" key=${i}>
          <strong>${r.medicamento}</strong>
          <div>Paciente: ${r.paciente} · Programa: ${r.programa}${r.entrega ? ` · Entrega ${r.entrega}` : ""}</div>
          <div className="tabular">Lote ${r.lote} · Vence ${fecha(r.vencimiento)} · ${r.cantidad} u.</div>
          <div>${r.posologia}</div></div>`)}</div>
        <div className="acciones">
          <button className="boton" onClick=${imprimirEtiqueta}><${Icono} nombre="imprimir" />Imprimir rótulos</button>
          <button className="boton secundario" onClick=${onCerrar}>Cerrar</button>
        </div>
      </div></div>`;
  }

  // ---------------------------------------------------------- retiros del día
  function Retiros({ abrir }) {
    const [dias, setDias] = useState("0");
    const [{ datos, error }] = useCarga(() => api("GET", "/api/recetas/retiros?dias=" + dias), [dias]);
    const hoyTexto = fechaLocal(new Date());
    return html`<div>
      <div className="barra-herramientas">
        <div className="acciones"><label htmlFor="ret-dias" className="casilla-linea">Mostrar</label>
          <select id="ret-dias" style=${{ width: "auto" }} value=${dias} onChange=${(e) => setDias(e.target.value)}>
            <option value="0">Hoy y atrasados</option><option value="7">Próximos 7 días</option><option value="30">Próximos 30 días</option>
          </select></div>
        ${datos && html`<span className="ayuda">${datos.length} receta(s) por retirar</span>`}
      </div>
      <${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Retiro</th><th>Paciente</th><th>Sector</th><th>Receta</th><th>Medicamentos</th><th></th></tr></thead>
        <tbody>${datos.length === 0 && html`<tr><td colSpan="6">No hay retiros pendientes para este período.</td></tr>`}
        ${datos.map((r) => html`<tr key=${r.id_receta}>
          <td className="tabular">${fecha(r.proxima_fecha_retiro)}
            <div>${r.dias_atraso > 0 ? html`<${Estado} valor="NO_DISPENSABLE" texto=${`Atrasado ${r.dias_atraso} d`} />`
              : r.proxima_fecha_retiro <= hoyTexto ? html`<${Estado} valor="VIGENTE" texto="Hoy" />` : ""}</div></td>
          <td>${r.paciente.nombre}<div className="ayuda mono">${r.paciente.rut}</div>
            ${r.paciente.es_postrado && html`<${Estado} valor="ALERTA" texto="Postrado" />`}</td>
          <td>${r.paciente.sector || "-"}</td>
          <td>${r.folio}<div className="ayuda">${TIPOS_RECETA[r.tipo_receta]} · entrega ${r.entrega_actual} de ${r.total_entregas}</div></td>
          <td>${r.medicamentos.join(", ")}</td>
          <td><button className="boton chico" onClick=${() => abrir("dispensar", { id_paciente: r.paciente.id_paciente })}>Atender</button></td>
        </tr>`)}</tbody></table></div></div>`}
    </div>`;
  }

  // ------------------------------------------------------ despachos a domicilio
  const COLUMNAS_DESPACHO = [["PREPARANDO", "Preparando"], ["EN_RUTA", "En ruta"], ["FALLIDO", "No entregados"], ["ENTREGADO", "Entregados"]];

  function Despachos() {
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/despachos"), []);
    const [dialogo, setDialogo] = useState(null);
    const [acta, setActa] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [fallo, setFallo] = useState(null);
    async function cambiar(d, estado, extra = {}) {
      await api("POST", `/api/despachos/${d.id_despacho}/estado`, { estado, ...extra });
      setAviso(`Despacho de ${d.paciente}: ${ESTADOS[estado][2].toLowerCase()}.`); setFallo(null); recargar();
    }
    function accion(d, estado) {
      if (estado === "ENTREGADO") {
        setDialogo({ titulo: `Entrega en domicilio: ${d.paciente}`, textoAceptar: "Registrar entrega",
          campos: [{ nombre: "recibe_nombre", etiqueta: "Nombre de quien recibe" },
                   { nombre: "observacion", etiqueta: "Observación", requerido: false }],
          onAceptar: (v) => cambiar(d, "ENTREGADO", { recibe_nombre: v.recibe_nombre, observacion: v.observacion || null }) });
      } else if (estado === "FALLIDO") {
        setDialogo({ titulo: `No se pudo entregar: ${d.paciente}`, textoAceptar: "Registrar", peligro: true,
          campos: [{ nombre: "observacion", etiqueta: "Motivo", minimo: 5, ayuda: "(p. ej. nadie en el domicilio)" }],
          onAceptar: (v) => cambiar(d, "FALLIDO", v) });
      } else {
        cambiar(d, estado).catch((err) => { setAviso(null); setFallo(err.message); });
      }
    }
    const grupos = Object.fromEntries(COLUMNAS_DESPACHO.map(([e]) => [e, (datos || []).filter((d) => d.estado === e)]));
    return html`<div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error || fallo}<//>
      ${datos && html`<div className="tablero">${COLUMNAS_DESPACHO.map(([estado, titulo]) => html`<section className="columna-tablero" key=${estado}
          aria-label=${titulo}>
        <h2>${titulo} <span className="ayuda">${grupos[estado].length}</span></h2>
        ${grupos[estado].length === 0 && html`<p className="ayuda">Sin despachos.</p>`}
        ${grupos[estado].slice(0, estado === "ENTREGADO" ? 10 : 50).map((d) => html`<article className="tarjeta despacho" key=${d.id_despacho}>
          <div className="acciones" style=${{ justifyContent: "space-between" }}><strong>${d.paciente}</strong><${Estado} valor=${d.estado} /></div>
          <div className="ayuda mono">${d.rut} · ${d.sector || "sin sector"}</div>
          <div className="direccion">${d.direccion || "Sin dirección registrada"}</div>
          <div className="ayuda">${d.folio} · entrega ${d.numero_entrega} de ${d.total_entregas}</div>
          <ul className="lineas-despacho">${d.lineas.map((l, i) => html`<li key=${i}>${l.medicamento} · ${l.cantidad} u. <span className="ayuda">(${l.lote})</span></li>`)}</ul>
          ${d.fecha_salida && html`<div className="ayuda">Salió: ${fechaHora(d.fecha_salida)}</div>`}
          ${d.fecha_entrega && html`<div className="ayuda">Recibió ${d.recibe_nombre} · ${fechaHora(d.fecha_entrega)}</div>`}
          ${d.observacion && html`<div className="ayuda">Obs.: ${d.observacion}</div>`}
          <div className="acciones">
            ${estado === "PREPARANDO" && html`<button className="boton chico" onClick=${() => accion(d, "EN_RUTA")}>Salir a ruta</button>`}
            ${estado === "EN_RUTA" && html`<button className="boton chico" onClick=${() => accion(d, "ENTREGADO")}>Entregado</button>
              <button className="boton chico peligro" onClick=${() => accion(d, "FALLIDO")}>No se pudo entregar</button>`}
            ${estado === "FALLIDO" && d.estado_dispensacion !== "ANULADA" && html`<button className="boton chico" onClick=${() => accion(d, "EN_RUTA")}>Reintentar</button>`}
            ${estado === "ENTREGADO" && html`<button className="boton chico secundario" onClick=${() => setActa(d)}><${Icono} nombre="imprimir" />Acta</button>`}
          </div>
        </article>`)}
      </section>`)}</div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${acta && html`<${VentanaDocumento} titulo="Acta de recepción de medicamentos en domicilio"
          subtitulo=${`Programa Fondo de Farmacia · Anexo 2 · Despacho N.º ${acta.id_despacho}`}
          filas=${[["Paciente", acta.paciente], ["RUT", acta.rut], ["Domicilio", acta.direccion || "-"], ["Receta", `${acta.folio} · entrega ${acta.numero_entrega} de ${acta.total_entregas}`],
                   ["Medicamentos", acta.lineas.map((l) => `${l.medicamento} (${l.cantidad} u., lote ${l.lote})`).join("; ")],
                   ["Recibió", acta.recibe_nombre || "-"], ["Fecha de entrega", fechaHora(acta.fecha_entrega)]]}
          firmas=${["Recibe conforme (nombre, RUT y firma)", "Entrega (funcionario CESFAM)"]} onCerrar=${() => setActa(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------- alertas de inventario
  const ACCION_SUGERIDA = { RETIRO_OBLIGATORIO: "Retirar a merma", NO_DISPENSABLE: "No entregar; preparar merma",
                            ALERTA: "Entregar primero (FEFO)", ALERTA_SANITARIA: "Bloqueado por el ISP" };

  function Alertas() {
    const [{ datos, error }] = useCarga(() => api("GET", "/api/inventario/alertas"), []);
    const [{ datos: porMes }] = useCarga(() => api("GET", "/api/inventario/vencimientos-por-mes?meses=6"), []);
    if (error) return html`<${Aviso} tipo="error">${error}<//>`;
    if (!datos) return html`<p className="ayuda">Cargando…</p>`;
    const r = datos.resumen;
    return html`<div>
      <div className="rejilla k4">
        ${[["Retiro obligatorio (≤ 14 días)", r.RETIRO_OBLIGATORIO, "bloqueado"], ["No dispensables (≤ 30 días)", r.NO_DISPENSABLE, "bloqueado"],
           ["En alerta (≤ 60 días)", r.ALERTA, "alerta"], ["Bajo umbral crítico", r.STOCK_CRITICO, "bloqueado"]].map(([etiqueta, valor, tono]) =>
          html`<div className=${"tarjeta kpi " + (valor ? tono : "")} key=${etiqueta}>
            <div><div className="etiqueta">${etiqueta}</div><div className="valor">${valor}</div></div>
            <span className="indicador"><${Icono} nombre="alertas" /></span></div>`)}
      </div>
      ${porMes && html`<div className="tarjeta"><${Grafico} titulo="Valor del stock que vence, por mes"
          descripcion=${`Próximos 6 meses · ${pesos(porMes.reduce((s, v) => s + v.valor, 0))} en ${numero(porMes.reduce((s, v) => s + v.unidades, 0))} unidades. Lo que vence antes se mueve a merma.`}
          datos=${porMes.map((v) => ({ etiqueta: v.etiqueta.split(" ")[0], etiquetaLarga: v.etiqueta, valor: v.valor,
                                       detalle: `${numero(v.unidades)} unidades en ${v.lotes} lote(s)` + (v.sin_costo ? ` · ${v.sin_costo} sin costo registrado` : "") }))}
          formato=${pesos} formatoEje=${(v) => "$" + compacto(v)}
          columnas=${[["Mes", (v) => v.etiquetaLarga], ["Valor", (v) => pesos(v.valor), true], ["Detalle", (v) => v.detalle]]} /></div>`}
      <div className="tarjeta"><h2>Vencimientos próximos</h2>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Estado</th><th>Lote</th><th>Medicamento</th><th>Ubicación</th><th>Vence</th><th className="num">Días</th><th className="num">Unidades</th><th>Acción sugerida</th></tr></thead>
          <tbody>${datos.vencimientos.length === 0 && html`<tr><td colSpan="8">No hay lotes con alerta de vencimiento.</td></tr>`}
          ${datos.vencimientos.map((l) => html`<tr key=${l.id_lote}><td><${Estado} valor=${l.estado} /></td>
            <td className="mono">${l.codigo_lote}</td><td>${l.medicamento}</td><td>${l.ubicacion}</td>
            <td className="tabular">${fecha(l.fecha_vencimiento)}</td><td className="num">${l.dias_para_vencer}</td>
            <td className="num">${l.unidades_disp}</td><td>${ACCION_SUGERIDA[l.estado] || ""}</td></tr>`)}</tbody>
        </table></div></div>
      <div className="tarjeta"><h2>Stock bajo el umbral crítico</h2>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Medicamento</th><th>Programa</th><th className="num">Dispensable</th><th className="num">Umbral</th><th className="num">Faltan</th></tr></thead>
          <tbody>${datos.stock_critico.length === 0 && html`<tr><td colSpan="5">Ningún medicamento bajo su umbral.</td></tr>`}
          ${datos.stock_critico.map((m) => html`<tr key=${m.id_medicamento}><td>${m.nombre}</td><td>${m.programa || "-"}</td>
            <td className="num">${m.stock_dispensable}</td><td className="num">${m.umbral_critico}</td>
            <td className="num"><strong>${m.deficit}</strong></td></tr>`)}</tbody>
        </table></div></div>
    </div>`;
  }

  // ------------------------------------------------------------------ reportes
  async function descargarArchivo(ruta, nombre) {
    const respuesta = await fetch(ruta, { headers: { Authorization: "Bearer " + tokenActual } });
    if (respuesta.status === 401) { alExpirar(); throw new Error("Sesión expirada."); }
    if (!respuesta.ok) {
      const datos = await respuesta.json().catch(() => ({}));
      throw new Error(Array.isArray(datos.detail) ? datos.detail.map((d) => d.msg).join(" · ") : datos.detail || "Error " + respuesta.status);
    }
    const url = URL.createObjectURL(await respuesta.blob());
    const enlace = document.createElement("a");
    enlace.href = url; enlace.download = nombre;
    document.body.appendChild(enlace); enlace.click(); enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function Reportes({ permisos }) {
    const hoyIso = fechaLocal(new Date());
    const [desde, setDesde] = useState(hoyIso.slice(0, 8) + "01");
    const [hasta, setHasta] = useState(hoyIso);
    const [dias, setDias] = useState(90);
    const [aviso, setAviso] = useState(null);
    const [error, setError] = useState(null);
    async function bajar(ruta, nombre) {
      setAviso(null); setError(null);
      try { await descargarArchivo(ruta, nombre); setAviso(`Descargado ${nombre}. Queda registrado en la auditoría.`); }
      catch (err) { setError(err.message); }
    }
    const rango = `desde=${desde}&hasta=${hasta}`;
    return html`<div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      <div className="tarjeta"><h2>Período</h2>
        <div className="fila-campos">
          <div className="campo"><label htmlFor="rep-desde">Desde</label><input id="rep-desde" type="date" value=${desde} max=${hasta} onChange=${(e) => setDesde(e.target.value)} /></div>
          <div className="campo"><label htmlFor="rep-hasta">Hasta</label><input id="rep-hasta" type="date" value=${hasta} min=${desde} onChange=${(e) => setHasta(e.target.value)} /></div>
        </div>
        <p className="ayuda">Los archivos son CSV separados por punto y coma; se abren directo en Excel. No incluyen datos de pacientes, salvo el libro de controlados (RUT enmascarado).</p>
      </div>
      <div className="rejilla k2">
        <div className="tarjeta"><h2>Kardex</h2><p className="ayuda">Cada movimiento de stock del período: ingresos, entregas, mermas, ajustes y devoluciones, con stock anterior y posterior.</p>
          <button className="boton" onClick=${() => bajar(`/api/reportes/kardex.csv?${rango}`, `kardex_${desde}_${hasta}.csv`)}><${Icono} nombre="descargar" />Descargar kardex</button></div>
        <div className="tarjeta"><h2>Entregas por programa</h2><p className="ayuda">Unidades entregadas por programa y medicamento: base para el pedido mensual.</p>
          <button className="boton" onClick=${() => bajar(`/api/reportes/entregas.csv?${rango}`, `entregas_${desde}_${hasta}.csv`)}><${Icono} nombre="descargar" />Descargar entregas</button></div>
        <div className="tarjeta"><h2>Vencimientos próximos</h2>
          <div className="campo"><label htmlFor="rep-dias">Lotes que vencen en los próximos (días)</label>
            <input id="rep-dias" type="number" min="1" max="365" value=${dias} onChange=${(e) => setDias(e.target.value)} /></div>
          <button className="boton" onClick=${() => bajar(`/api/reportes/vencimientos.csv?dias=${dias}`, `vencimientos_${dias}d.csv`)}><${Icono} nombre="descargar" />Descargar vencimientos</button></div>
        <div className="tarjeta"><h2>REM A04 · sección J</h2><p className="ayuda">Recetas cardiovasculares por medicamento: despacho total y oportuno, brechas por oportunidad y completitud, y días de demora (FOFAR).</p>
          <button className="boton" onClick=${() => bajar(`/api/reportes/rem-a04-j.csv?${rango}`, `rem_a04_j_${desde}_${hasta}.csv`)}><${Icono} nombre="descargar" />Descargar REM A04 J</button></div>
        ${permisos.includes("ver_libro") && html`<div className="tarjeta"><h2>Libro de controlados</h2><p className="ayuda">Ingresos, egresos y saldos con su hash (D.S. 404/405 art. 18), para fiscalización.</p>
          <button className="boton" onClick=${() => bajar("/api/reportes/libro.csv", `libro_controlados_${hoyIso}.csv`)}><${Icono} nombre="descargar" />Descargar libro</button></div>`}
      </div>
    </div>`;
  }

  // ------------------------------------------------- consulta pública (sin login)
  function DisponibilidadPublica() {
    const [texto, setTexto] = useState("");
    const [busqueda, setBusqueda] = useState("");
    const [{ datos, error }] = useCarga(() => fetch("/api/publico/disponibilidad" + (busqueda ? "?q=" + encodeURIComponent(busqueda) : ""))
      .then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || "Error " + r.status); return d; }), [busqueda]);
    return html`<div className="publica">
      <header className="publica-cabecera">
        <div className="marca"><${Logo} /><div><strong>SISGEF</strong><small>Farmacia asistencial · CESFAM</small></div></div>
        <${SelectorTema} />
      </header>
      <main className="publica-contenido">
        <h1>Disponibilidad de medicamentos</h1>
        <p className="ayuda">Consulte si un medicamento está disponible en la farmacia antes de venir a retirarlo.</p>
        <form className="buscador-publico" onSubmit=${(e) => { e.preventDefault(); setBusqueda(texto.trim()); }}>
          <div className="buscador"><${Icono} nombre="buscar" />
            <label htmlFor="pub-q" className="sr-only">Buscar medicamento</label>
            <input id="pub-q" type="search" maxLength="60" placeholder="Nombre o principio activo, p. ej. losartán"
                   value=${texto} onChange=${(e) => setTexto(e.target.value)} /></div>
          <button className="boton">Buscar</button>
        </form>
        <${Aviso} tipo="error">${error}<//>
        ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
          <thead><tr><th>Medicamento</th><th>Programa</th><th>Disponibilidad</th></tr></thead>
          <tbody>${datos.medicamentos.length === 0 && html`<tr><td colSpan="3">No se encontraron medicamentos.</td></tr>`}
          ${datos.medicamentos.map((m) => html`<tr key=${m.nombre}>
            <td><strong>${m.nombre}</strong><div className="ayuda">${m.principio_activo}${m.concentracion ? " · " + m.concentracion : ""}</div></td>
            <td>${m.programa || "-"} ${m.es_ges && html`<${Estado} valor="VIGENTE" texto="GES" />`}</td>
            <td><${Estado} valor=${m.disponibilidad} /></td></tr>`)}</tbody>
        </table></div></div>
        <p className="ayuda">Información referencial al ${fecha(datos.fecha)}. Para retirar necesita una receta vigente. Los medicamentos controlados no se publican; consulte en la farmacia.</p>`}
        <p><a href="#">Ingreso de funcionarios</a></p>
      </main>
    </div>`;
  }

  // ------------------------------------------------- documento imprimible (actas y fichas)
  function VentanaDocumento({ titulo, subtitulo, filas, texto, firmas, onCerrar }) {
    useEffect(() => {
      const alPresionar = (e) => { if (e.key === "Escape") onCerrar(); };
      document.addEventListener("keydown", alPresionar);
      return () => document.removeEventListener("keydown", alPresionar);
    }, [onCerrar]);
    return html`<div className="dialogo-fondo" onClick=${(e) => e.target === e.currentTarget && onCerrar()}>
      <div className="dialogo dialogo-ancho" role="dialog" aria-modal="true" aria-label=${titulo}>
        <div className="documento imprimible">
          <div className="documento-cabecera"><${Logo} /><div><strong>CESFAM · Farmacia asistencial</strong><small>${subtitulo}</small></div></div>
          <h2>${titulo}</h2>
          <dl>${filas.map(([etiqueta, valor]) => html`<${React.Fragment} key=${etiqueta}><dt>${etiqueta}</dt><dd>${valor}</dd><//>`)}</dl>
          ${texto && html`<p>${texto}</p>`}
          ${firmas && html`<div className="firmas">${firmas.map((f) => html`<div key=${f}>${f}</div>`)}</div>`}
          <p className="pie-documento">Emitido por SISGEF el ${new Date().toLocaleString("es-CL")}</p>
        </div>
        <div className="acciones">
          <button className="boton" onClick=${imprimirEtiqueta}><${Icono} nombre="imprimir" />Imprimir</button>
          <button className="boton secundario" onClick=${onCerrar}>Cerrar</button>
        </div>
      </div></div>`;
  }

  // -------------------------------------------- pendientes FOFAR: faltantes y reclamos
  const CANALES_RECLAMO = [["OIRS", "OIRS"], ["SALUD_RESPONDE", "Salud Responde"], ["PRESENCIAL", "Presencial en farmacia"]];

  function Plazo({ item }) {
    if (item.estado === "ENTREGADO" || item.estado === "RESUELTO") {
      const aTiempo = item.estado === "ENTREGADO" ? item.a_tiempo : item.dentro_de_plazo;
      return html`<${Estado} valor=${aTiempo ? "VIGENTE" : "NO_DISPENSABLE"} texto=${aTiempo ? "En plazo" : "Fuera de plazo"} />`;
    }
    if (item.estado !== "PENDIENTE" && item.estado !== "ABIERTO") return html`<span className="ayuda">-</span>`;
    if (item.vencido) return html`<${Estado} valor="NO_DISPENSABLE" texto="Plazo vencido" />`;
    const horas = item.horas_habiles_restantes;
    return html`<${Estado} valor=${horas <= 6 ? "ALERTA" : "VIGENTE"} texto=${`Quedan ${String(horas).replace(".", ",")} h hábiles`} />`;
  }

  function Pendientes({ abrir }) {
    const [verCerrados, setVerCerrados] = useState(false);
    const [{ datos, error }, recargar] = useCarga(() => Promise.all([
      api("GET", "/api/faltantes" + (verCerrados ? "" : "?estado=PENDIENTE")),
      api("GET", "/api/reclamos" + (verCerrados ? "" : "?estado=ABIERTO"))]), [verCerrados]);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [fallo, setFallo] = useState(null);
    const [acta, setActa] = useState(null);
    const camposReclamo = [
      { nombre: "canal", etiqueta: "Canal", opciones: CANALES_RECLAMO, inicial: "OIRS" },
      { nombre: "folio_externo", etiqueta: "Folio OIRS o Salud Responde", requerido: false },
      { nombre: "descripcion", etiqueta: "Descripción del reclamo", minimo: 10, ayuda: "(mínimo 10 caracteres)" }];
    function reclamar(f) {
      setDialogo({ titulo: f ? `Reclamo por ${f.medicamento}` : "Registrar reclamo", textoAceptar: "Registrar reclamo",
        descripcion: "FOFAR: la solución (entrega del medicamento) se da dentro de 24 horas hábiles y se cierra con acta.",
        campos: f ? camposReclamo : [{ nombre: "rut", etiqueta: "RUT del paciente", ayuda: "(sin puntos, con guion)" }, ...camposReclamo],
        onAceptar: async (v) => {
          if (!f && !rutValido(v.rut)) throw new Error("RUT inválido: revise el dígito verificador.");
          const r = await api("POST", "/api/reclamos", { canal: v.canal, descripcion: v.descripcion,
            folio_externo: v.folio_externo.trim() || null, ...(f ? { id_faltante: f.id_faltante } : { rut: v.rut }) });
          setAviso(`Reclamo de ${r.paciente.nombre} registrado. Plazo: ${fechaHora(r.plazo)}.`); recargar();
        } });
    }
    function cerrar(r) {
      setDialogo({ titulo: `Cerrar reclamo de ${r.paciente.nombre}`, textoAceptar: "Cerrar y emitir acta",
        descripcion: r.faltante ? `Compromiso: ${r.faltante.medicamento} (${r.faltante.cantidad} u.), receta ${r.faltante.folio}. Debe estar entregado.`
          : "Registre la solución entregada al paciente.",
        campos: [{ nombre: "solucion", etiqueta: "Solución", minimo: 10, inicial: r.faltante ? `Se entregó ${r.faltante.medicamento}` : "" },
                 { nombre: "recibe_nombre", etiqueta: "Quién recibe y firma el acta", minimo: 3, inicial: r.paciente.nombre }],
        onAceptar: async (v) => {
          const c = await api("POST", `/api/reclamos/${r.id_reclamo}/cerrar`, v);
          setAviso(`Reclamo cerrado ${c.dentro_de_plazo ? "dentro" : "fuera"} del plazo de 24 horas hábiles.`); setActa(c); recargar();
        } });
    }
    function noAtingente(r) {
      setDialogo({ titulo: `Reclamo no atingente: ${r.paciente.nombre}`, textoAceptar: "Marcar no atingente",
        descripcion: "Para reclamos que no son por entrega de medicamentos del programa: salen del indicador con su motivo.",
        campos: [{ nombre: "motivo", etiqueta: "Motivo", minimo: 10 }],
        onAceptar: async (v) => { await api("POST", `/api/reclamos/${r.id_reclamo}/no-atingente`, v); setAviso("Reclamo marcado como no atingente."); recargar(); } });
    }
    async function verActa(r) {
      try { setFallo(null); setActa(await api("GET", `/api/reclamos/${r.id_reclamo}/acta`)); } catch (err) { setFallo(err.message); }
    }
    const [faltantes, reclamos] = datos || [[], []];
    const conReclamo = new Set(reclamos.filter((r) => r.faltante).map((r) => r.faltante.id_faltante));
    return html`<div>
      <div className="barra-herramientas">
        <label className="casilla-linea"><input type="checkbox" checked=${verCerrados} onChange=${(e) => setVerCerrados(e.target.checked)} />
          Mostrar también los resueltos</label>
        <button className="boton" onClick=${() => reclamar(null)}><${Icono} nombre="mas" />Registrar reclamo</button>
      </div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error || fallo}<//>
      ${datos && html`<div className="tarjeta"><h2>Compromisos de entrega <span className="ayuda">· quiebres de stock, 24 horas hábiles</span></h2>
        <p className="ayuda">Al entregar el medicamento desde Dispensar, el compromiso se cumple solo.</p>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Paciente</th><th>Receta</th><th>Medicamento</th><th className="num">Unid.</th><th>Registrado</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
          <tbody>${faltantes.length === 0 && html`<tr><td colSpan="8">No hay compromisos ${verCerrados ? "registrados" : "pendientes"}.</td></tr>`}
          ${faltantes.map((f) => html`<tr key=${f.id_faltante}>
            <td>${f.paciente.nombre}<div className="ayuda mono">${f.paciente.rut}</div></td>
            <td>${f.folio}<div className="ayuda">entrega ${f.numero_entrega} de ${f.total_entregas}</div></td>
            <td>${f.medicamento}</td><td className="num">${f.cantidad}</td>
            <td className="tabular">${fechaHora(f.fecha_registro)}</td><td className="tabular">${fechaHora(f.plazo)}</td>
            <td><${Plazo} item=${f} /></td>
            <td><div className="acciones">${f.estado === "PENDIENTE" && html`
              <button className="boton chico" onClick=${() => abrir("dispensar", { id_paciente: f.paciente.id_paciente })}>Atender</button>
              ${!conReclamo.has(f.id_faltante) && html`<button className="boton chico secundario" onClick=${() => reclamar(f)}>Reclamo</button>`}`}</div></td>
          </tr>`)}</tbody></table></div></div>
      <div className="tarjeta"><h2>Reclamos</h2>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Fecha</th><th>Paciente</th><th>Canal</th><th>Detalle</th><th>Plazo</th><th>Estado</th><th></th></tr></thead>
          <tbody>${reclamos.length === 0 && html`<tr><td colSpan="7">No hay reclamos ${verCerrados ? "registrados" : "abiertos"}.</td></tr>`}
          ${reclamos.map((r) => html`<tr key=${r.id_reclamo}>
            <td className="tabular">${fechaHora(r.fecha_reclamo)}</td>
            <td>${r.paciente.nombre}<div className="ayuda mono">${r.paciente.rut}</div></td>
            <td>${r.canal_texto}${r.folio_externo && html`<div className="ayuda">${r.folio_externo}</div>`}</td>
            <td className="col-detalle">${r.descripcion}${r.faltante && html`<div className="ayuda">${r.faltante.medicamento} · ${r.faltante.folio} · compromiso ${ESTADOS[r.faltante.estado] ? ESTADOS[r.faltante.estado][2].toLowerCase() : r.faltante.estado}</div>`}</td>
            <td><${Plazo} item=${r} /></td><td><${Estado} valor=${r.estado} /></td>
            <td><div className="acciones">
              ${r.estado === "ABIERTO" && html`<button className="boton chico" onClick=${() => cerrar(r)}>Cerrar con acta</button>
                <button className="boton chico secundario" onClick=${() => noAtingente(r)}>No atingente</button>`}
              ${r.estado === "RESUELTO" && html`<button className="boton chico secundario" onClick=${() => verActa(r)}><${Icono} nombre="imprimir" />Acta</button>`}
            </div></td></tr>`)}</tbody></table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${acta && html`<${VentanaDocumento} titulo="Acta de recepción de medicamentos"
          subtitulo=${`Programa Fondo de Farmacia · reclamo N.º ${acta.id_reclamo} (${acta.canal_texto}${acta.folio_externo ? " " + acta.folio_externo : ""})`}
          filas=${[["Paciente", acta.paciente.nombre], ["RUT", acta.paciente.rut],
                   ...(acta.faltante ? [["Receta", `${acta.faltante.folio} · entrega ${acta.faltante.numero_entrega} de ${acta.faltante.total_entregas}`],
                                        ["Medicamento", `${acta.faltante.medicamento} · ${acta.faltante.cantidad} unidades`]] : []),
                   ["Reclamo", `${fechaHora(acta.fecha_reclamo)} · ${acta.descripcion}`], ["Plazo (24 h hábiles)", fechaHora(acta.plazo)],
                   ["Entrega", fechaHora(acta.fecha_solucion)], ["Resultado", acta.dentro_de_plazo ? "Dentro del plazo" : "Fuera del plazo"],
                   ["Solución", acta.solucion]]}
          firmas=${[`Recibe conforme: ${acta.recibe_nombre}`, "Entrega (Q.F. o TENS de farmacia)"]} onCerrar=${() => setActa(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------- toma de inventario físico
  function TomasInventario({ permisos }) {
    const aprueba = permisos.includes("aprobar_inventario");
    const [{ datos: tomas, error }, recargar] = useCarga(() => api("GET", "/api/inventario/tomas"), []);
    const [{ datos: catalogo }] = useCarga(() => api("GET", "/api/catalogos"), []);
    const [toma, setToma] = useState(null);
    const [conteos, setConteos] = useState({});
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [fallo, setFallo] = useState(null);
    async function ver(id) {
      const t = await api("GET", `/api/inventario/tomas/${id}`);
      setToma(t); setConteos(Object.fromEntries(t.conteos.map((c) => [c.id_conteo, c.cantidad_contada ?? ""])));
    }
    useEffect(() => {
      const abierta = (tomas || []).find((t) => t.estado === "ABIERTA");
      if (abierta && !toma) ver(abierta.id_toma).catch((err) => setFallo(err.message));
    }, [tomas]); // eslint-disable-line
    function abrirToma() {
      setDialogo({ titulo: "Abrir toma de inventario", textoAceptar: "Abrir toma",
        descripcion: "Se listan los lotes con stock. El equipo cuenta a ciegas; usted revisa las diferencias y cierra la toma.",
        campos: [{ nombre: "id_ubicacion", etiqueta: "Alcance", inicial: "",
                   opciones: [["", "Toda la farmacia"], ...catalogo.ubicaciones.map((u) => [String(u.id_ubicacion), `${u.codigo} (${u.tipo})`])] },
                 { nombre: "observacion", etiqueta: "Observación", requerido: false }],
        onAceptar: async (v) => {
          const t = await api("POST", "/api/inventario/tomas", { id_ubicacion: v.id_ubicacion ? Number(v.id_ubicacion) : null,
            observacion: v.observacion.trim() || null });
          setAviso(`Toma N.º ${t.id_toma} abierta con ${t.resumen.lotes} lote(s).`); recargar(); await ver(t.id_toma);
        } });
    }
    async function guardar(e, c) {
      e.preventDefault(); setFallo(null);
      if (conteos[c.id_conteo] === "") return;
      try {
        await api("POST", `/api/inventario/tomas/${toma.id_toma}/conteos`, { id_conteo: c.id_conteo, cantidad: Number(conteos[c.id_conteo]) });
        await ver(toma.id_toma); recargar();
      } catch (err) { setFallo(err.message); }
    }
    function cerrarToma() {
      setDialogo({ titulo: `Cerrar toma N.º ${toma.id_toma}`, textoAceptar: "Cerrar y aplicar diferencias",
        descripcion: `${toma.resumen.con_diferencia} lote(s) con diferencia (${pesos(toma.resumen.valor_diferencias)}). Cada diferencia queda como AJUSTE en el kardex y, en controlados, en el libro.`,
        campos: [{ nombre: "observacion", etiqueta: "Observación", requerido: false }],
        onAceptar: async (v) => {
          const t = await api("POST", `/api/inventario/tomas/${toma.id_toma}/cerrar`, { observacion: v.observacion.trim() || null });
          setToma(t); setAviso(`Toma N.º ${t.id_toma} cerrada: diferencias aplicadas.`); recargar();
        } });
    }
    const hayAbierta = (tomas || []).some((t) => t.estado === "ABIERTA");
    const avance = toma ? Math.round(toma.resumen.contados * 100 / toma.resumen.lotes) : 0;
    return html`<div>
      <div className="barra-herramientas">
        ${aprueba && catalogo && !hayAbierta ? html`<button className="boton" onClick=${abrirToma}><${Icono} nombre="mas" />Abrir toma de inventario</button>`
          : html`<span className="ayuda">${hayAbierta ? "Hay una toma abierta: registre los conteos." : "El Q.F. abre las tomas de inventario."}</span>`}
      </div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error || fallo}<//>
      ${toma && html`<div className="tarjeta">
        <div className="acciones" style=${{ justifyContent: "space-between" }}>
          <h2>Toma N.º ${toma.id_toma} · ${toma.ubicacion} <${Estado} valor=${toma.estado} /></h2>
          ${aprueba && toma.estado === "ABIERTA" && html`<button className="boton" disabled=${toma.resumen.contados < toma.resumen.lotes} onClick=${cerrarToma}>Cerrar toma</button>`}
        </div>
        <div className="progreso" role="progressbar" aria-valuenow=${avance} aria-valuemin="0" aria-valuemax="100" aria-label="Avance del conteo"><span style=${{ width: avance + "%" }}></span></div>
        <p className="ayuda">${toma.resumen.contados} de ${toma.resumen.lotes} lotes contados.${aprueba ? "" : " Conteo a ciegas: cuente las unidades físicas sin mirar el sistema."}
          ${aprueba && toma.resumen.con_diferencia !== undefined && ` Diferencias: ${toma.resumen.con_diferencia} lote(s), ${pesos(toma.resumen.valor_diferencias)}.`}</p>
        <div className="tabla-envoltura"><table>
          <thead><tr><th>Ubicación</th><th>Lote</th><th>Medicamento</th><th>Vence</th><th>Contado</th>
            ${aprueba && html`<th className="num">Sistema</th><th className="num">Diferencia</th><th className="num">Valor</th>`}</tr></thead>
          <tbody>${toma.conteos.map((c) => html`<tr key=${c.id_conteo}>
            <td>${c.ubicacion}</td><td className="mono">${c.codigo_lote}</td>
            <td>${c.medicamento} ${c.es_controlado && html`<${Estado} valor="CONTROLADO" />`}</td>
            <td className="tabular">${fecha(c.fecha_vencimiento)}</td>
            <td>${toma.estado === "ABIERTA" ? html`<form className="conteo-fila" onSubmit=${(e) => guardar(e, c)}>
                <label htmlFor=${"cnt" + c.id_conteo} className="sr-only">Unidades contadas del lote ${c.codigo_lote}</label>
                <input id=${"cnt" + c.id_conteo} type="number" min="0" value=${conteos[c.id_conteo]}
                       onChange=${(e) => setConteos({ ...conteos, [c.id_conteo]: e.target.value })} />
                <button className="boton chico secundario">${c.contado ? "Corregir" : "Guardar"}</button>
                ${c.contado && html`<span aria-label="contado">✓</span>`}</form>`
              : html`<span className="tabular">${c.cantidad_contada}</span>`}</td>
            ${aprueba && html`<td className="num">${c.stock_al_contar ?? "-"}</td>
              <td className="num">${c.diferencia === null || c.diferencia === undefined ? "-" : html`<strong>${c.diferencia > 0 ? "+" : ""}${c.diferencia}</strong>`}</td>
              <td className="num">${c.valor_diferencia === null ? "-" : pesos(c.valor_diferencia)}</td>`}
          </tr>`)}</tbody></table></div></div>`}
      ${tomas && html`<div className="tarjeta"><h2>Historial de tomas</h2><div className="tabla-envoltura"><table>
        <thead><tr><th className="num">N.º</th><th>Alcance</th><th>Apertura</th><th>Cierre</th><th>Avance</th><th>Estado</th><th></th></tr></thead>
        <tbody>${tomas.length === 0 && html`<tr><td colSpan="7">Aún no hay tomas de inventario.</td></tr>`}
        ${tomas.map((t) => html`<tr key=${t.id_toma}><td className="num">${t.id_toma}</td><td>${t.ubicacion}</td>
          <td className="tabular">${fechaHora(t.fecha_apertura)}</td><td className="tabular">${fechaHora(t.fecha_cierre)}</td>
          <td className="tabular">${t.contados} de ${t.lotes}</td><td><${Estado} valor=${t.estado} /></td>
          <td><button className="boton chico secundario" onClick=${() => ver(t.id_toma).catch((err) => setFallo(err.message))}>Ver</button></td></tr>`)}</tbody>
      </table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
    </div>`;
  }

  // ------------------------------------------------- préstamos entre establecimientos
  function Prestamos() {
    const [{ datos, error }, recargar] = useCarga(() => api("GET", "/api/prestamos"), []);
    const [{ datos: catalogo }] = useCarga(() => Promise.all([api("GET", "/api/medicamentos"), api("GET", "/api/catalogos")]), []);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const hoyIso = fechaLocal(new Date());
    const camposLote = (cat) => [
      { nombre: "codigo_lote", etiqueta: "Código de lote" },
      { nombre: "fecha_vencimiento", etiqueta: "Vencimiento del lote", tipo: "date", min: hoyIso },
      { nombre: "id_ubicacion", etiqueta: "Ubicación", opciones: cat.ubicaciones.map((u) => [String(u.id_ubicacion), `${u.codigo} (${u.tipo})`]),
        inicial: String(cat.ubicaciones[0]?.id_ubicacion) }];
    const datosLote = (v) => ({ codigo_lote: v.codigo_lote.trim(), fecha_vencimiento: v.fecha_vencimiento, id_ubicacion: Number(v.id_ubicacion) });
    function nuevo(tipo) {
      const [meds, cat] = catalogo;
      const prestables = meds.filter((m) => !m.es_controlado);
      setDialogo({ titulo: tipo === "OTORGADO" ? "Prestar a otro establecimiento" : "Recibir un préstamo", textoAceptar: "Registrar préstamo",
        descripcion: tipo === "OTORGADO" ? "Sale de nuestros lotes en orden FEFO (movimiento PRESTAMO_SALIDA)."
          : "Entra como lote (PRESTAMO_ENTRADA). Los controlados no se prestan.",
        campos: [{ nombre: "establecimiento", etiqueta: "Establecimiento", minimo: 3 },
          { nombre: "id_medicamento", etiqueta: "Medicamento", opciones: prestables.map((m) => [String(m.id_medicamento), m.nombre]),
            inicial: String(prestables[0]?.id_medicamento) },
          { nombre: "cantidad", etiqueta: "Unidades", tipo: "number", min: 1 },
          { nombre: "fecha_compromiso", etiqueta: "Fecha comprometida de devolución", tipo: "date", min: hoyIso },
          { nombre: "documento", etiqueta: "N.º de formulario de préstamo", requerido: false },
          ...(tipo === "RECIBIDO" ? camposLote(cat) : [])],
        onAceptar: async (v) => {
          await api("POST", "/api/prestamos", { tipo, establecimiento: v.establecimiento, id_medicamento: Number(v.id_medicamento),
            cantidad: Number(v.cantidad), fecha_compromiso: v.fecha_compromiso, documento: v.documento.trim() || null,
            ...(tipo === "RECIBIDO" ? datosLote(v) : {}) });
          setAviso("Préstamo registrado."); recargar();
        } });
    }
    function devolver(p) {
      setDialogo({ titulo: `Devolución: ${p.medicamento} (${p.cantidad} u.)`, textoAceptar: "Registrar devolución",
        descripcion: p.tipo === "OTORGADO" ? `${p.establecimiento} nos devuelve las unidades: indique el lote recibido.`
          : `Devolvemos las unidades a ${p.establecimiento}: salen de nuestros lotes en orden FEFO.`,
        campos: p.tipo === "OTORGADO" ? camposLote(catalogo[1]) : [],
        onAceptar: async (v) => {
          await api("POST", `/api/prestamos/${p.id_prestamo}/devolver`, p.tipo === "OTORGADO" ? datosLote(v) : {});
          setAviso(`Préstamo con ${p.establecimiento} devuelto.`); recargar();
        } });
    }
    return html`<div>
      <div className="acciones" style=${{ marginBottom: "1rem" }}>
        ${catalogo && html`<button className="boton" onClick=${() => nuevo("OTORGADO")}><${Icono} nombre="prestamos" />Prestar</button>
          <button className="boton secundario" onClick=${() => nuevo("RECIBIDO")}><${Icono} nombre="mas" />Recibir préstamo</button>`}
      </div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Tipo</th><th>Establecimiento</th><th>Medicamento</th><th className="num">Unid.</th><th>Fecha</th><th>Devolver el</th><th>Estado</th><th></th></tr></thead>
        <tbody>${datos.length === 0 && html`<tr><td colSpan="8">No hay préstamos registrados.</td></tr>`}
        ${datos.map((p) => html`<tr key=${p.id_prestamo} className=${p.estado === "DEVUELTO" ? "inactivo" : ""}>
          <td><${Estado} valor=${p.tipo} /></td><td>${p.establecimiento}${p.documento && html`<div className="ayuda">${p.documento}</div>`}</td>
          <td>${p.medicamento}</td><td className="num">${p.cantidad}</td><td className="tabular">${fecha(p.fecha)}</td>
          <td className="tabular">${fecha(p.fecha_compromiso)}${p.vencido && html`<div><${Estado} valor="NO_DISPENSABLE" texto="Atrasado" /></div>`}</td>
          <td><${Estado} valor=${p.estado} />${p.fecha_devolucion && html`<div className="ayuda">${fecha(p.fecha_devolucion)}</div>`}</td>
          <td>${p.estado === "PENDIENTE" && catalogo && html`<button className="boton chico" onClick=${() => devolver(p)}>Registrar devolución</button>`}</td>
        </tr>`)}</tbody></table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------- actividades farmacéuticas
  const TIPOS_ACTIVIDAD = [["SEGUIMIENTO_FT", "Seguimiento farmacoterapéutico"], ["REVISION_MEDICACION", "Revisión de la medicación"],
    ["CONCILIACION", "Conciliación farmacéutica"], ["EDUCACION", "Educación farmacéutica"], ["RAM", "Sospecha de reacción adversa (RAM)"],
    ["EVENTO_ADVERSO", "Evento adverso asociado a medicamentos"], ["FALLA_CALIDAD", "Falla de calidad"], ["TALLER", "Taller de educación grupal"]];
  const GRAVEDADES = { LEVE: "Leve", MODERADA: "Moderada", GRAVE: "Grave" };

  function Actividades() {
    const anio = new Date().getFullYear();
    const hoyIso = fechaLocal(new Date());
    const [{ datos, error }, recargar] = useCarga(() => Promise.all([api("GET", "/api/actividades"),
      api("GET", `/api/actividades/programacion/${anio}`)]), []);
    const [{ datos: meds }] = useCarga(() => api("GET", "/api/medicamentos"), []);
    const [dialogo, setDialogo] = useState(null);
    const [aviso, setAviso] = useState(null);
    const [ficha, setFicha] = useState(null);
    function registrar() {
      setDialogo({ titulo: "Registrar actividad farmacéutica", textoAceptar: "Registrar",
        descripcion: "La atención farmacéutica, la RAM y el evento adverso van a nombre de un paciente; la RAM y la falla de calidad indican el medicamento.",
        campos: [
          { nombre: "tipo", etiqueta: "Tipo de actividad", opciones: TIPOS_ACTIVIDAD, inicial: "SEGUIMIENTO_FT" },
          { nombre: "fecha", etiqueta: "Fecha", tipo: "date", inicial: hoyIso, max: hoyIso },
          { nombre: "rut_paciente", etiqueta: "RUT del paciente", requerido: false, ayuda: "(no aplica a falla de calidad ni a talleres)" },
          { nombre: "id_medicamento", etiqueta: "Medicamento", inicial: "", opciones: [["", "No aplica"], ...(meds || []).map((m) => [String(m.id_medicamento), m.nombre])] },
          { nombre: "gravedad", etiqueta: "Gravedad (solo RAM)", inicial: "", opciones: [["", "No aplica"], ...Object.entries(GRAVEDADES)] },
          { nombre: "participantes", etiqueta: "Asistentes (solo talleres)", tipo: "number", min: 1, requerido: false },
          { nombre: "descripcion", etiqueta: "Descripción", minimo: 10, ayuda: "(mínimo 10 caracteres)" },
          { nombre: "resultado", etiqueta: "Intervención o resultado", requerido: false }],
        onAceptar: async (v) => {
          if (v.rut_paciente.trim() && !rutValido(v.rut_paciente)) throw new Error("RUT inválido: revise el dígito verificador.");
          const a = await api("POST", "/api/actividades", { tipo: v.tipo, fecha: v.fecha, descripcion: v.descripcion,
            rut_paciente: v.rut_paciente.trim() || null, id_medicamento: v.id_medicamento ? Number(v.id_medicamento) : null,
            gravedad: v.gravedad || null, participantes: v.participantes ? Number(v.participantes) : null,
            resultado: v.resultado.trim() || null });
          setAviso(`${a.tipo_texto} registrada.` + (a.pendiente_notificar ? " Recuerde notificarla al ISP (SVI)." : "")); recargar();
        } });
    }
    function programar(p) {
      setDialogo({ titulo: `Programación ${anio}`, textoAceptar: "Guardar", descripcion: "Actividades farmacéuticas comprometidas para el año (FOFAR: 50 % a junio y 100 % a diciembre).",
        campos: [{ nombre: "cantidad", etiqueta: "Actividades programadas", tipo: "number", min: 1, inicial: p.programadas || "" }],
        onAceptar: async (v) => { await api("PUT", `/api/actividades/programacion/${anio}`, { cantidad: Number(v.cantidad) }); setAviso("Programación guardada."); recargar(); } });
    }
    function notificar(a) {
      setDialogo({ titulo: `Notificación al ISP: ${a.tipo_texto}`, textoAceptar: "Registrar notificación",
        descripcion: "Ingrese la notificación en el Sistema de Vigilancia Integrado (SVI) del ISP y registre aquí el folio recibido.",
        campos: [{ nombre: "fecha_notificacion", etiqueta: "Fecha de notificación", tipo: "date", inicial: hoyIso, min: a.fecha, max: hoyIso },
                 { nombre: "folio_isp", etiqueta: "Folio del ISP", minimo: 3 }],
        onAceptar: async (v) => { await api("POST", `/api/actividades/${a.id_actividad}/notificacion`, v); setAviso("Notificación registrada."); recargar(); } });
    }
    function anular(a) {
      setDialogo({ titulo: `Anular: ${a.tipo_texto}`, peligro: true, textoAceptar: "Anular", descripcion: "No se borra: queda anulada con su motivo y deja de sumar al indicador.",
        campos: [{ nombre: "motivo", etiqueta: "Motivo", minimo: 10 }],
        onAceptar: async (v) => { await api("POST", `/api/actividades/${a.id_actividad}/anular`, v); setAviso("Actividad anulada."); recargar(); } });
    }
    const [lista, avance] = datos || [[], null];
    const porNotificar = lista.filter((a) => a.pendiente_notificar).length;
    return html`<div>
      <div className="acciones" style=${{ marginBottom: "1rem" }}>
        <button className="boton" disabled=${!meds} onClick=${registrar}><${Icono} nombre="mas" />Registrar actividad</button>
        ${avance && html`<button className="boton secundario" onClick=${() => programar(avance)}>Programación ${anio}</button>`}
      </div>
      <${Aviso} tipo="ok">${aviso}<//><${Aviso} tipo="error">${error}<//>
      ${avance && html`<div className="rejilla k4">
        ${[["Realizadas en " + anio, avance.realizadas, ""], ["Programadas", avance.programadas ?? "Sin programar", avance.programadas ? "" : "alerta"],
           ["Cumplimiento (meta " + avance.meta + " %)", porcentaje(avance.porcentaje), avance.cumple ? "cumple" : "alerta"],
           ["RAM por notificar al ISP", porNotificar, porNotificar ? "bloqueado" : ""]].map(([etiqueta, valor, tono]) => html`
          <div className=${"tarjeta kpi " + tono} key=${etiqueta}><div><div className="etiqueta">${etiqueta}</div><div className="valor">${valor}</div></div>
            <span className="indicador"><${Icono} nombre="actividades" /></span></div>`)}
      </div>`}
      ${datos && html`<div className="tarjeta"><div className="tabla-envoltura"><table>
        <thead><tr><th>Fecha</th><th>Actividad</th><th>Paciente</th><th>Medicamento</th><th>Detalle</th><th>Estado</th><th></th></tr></thead>
        <tbody>${lista.length === 0 && html`<tr><td colSpan="7">Aún no hay actividades este año.</td></tr>`}
        ${lista.map((a) => html`<tr key=${a.id_actividad} className=${a.estado === "ANULADA" ? "inactivo" : ""}>
          <td className="tabular">${fecha(a.fecha)}</td>
          <td>${a.tipo_texto}${a.gravedad && html`<div className="ayuda">Gravedad ${GRAVEDADES[a.gravedad].toLowerCase()}</div>`}${a.participantes && html`<div className="ayuda">${a.participantes} asistentes</div>`}</td>
          <td>${a.paciente ? html`${a.paciente.nombre}<div className="ayuda mono">${a.paciente.rut}</div>` : "-"}</td>
          <td>${a.medicamento || "-"}${a.lote && html`<div className="ayuda">lote ${a.lote}</div>`}</td>
          <td className="col-detalle">${a.descripcion}${a.resultado && html`<div className="ayuda">${a.resultado}</div>`}</td>
          <td>${a.estado === "ANULADA" ? html`<${Estado} valor="ANULADA" />` : a.pendiente_notificar ? html`<${Estado} valor="ALERTA" texto="Por notificar al ISP" />`
            : a.folio_isp ? html`<${Estado} valor="VIGENTE" texto=${"ISP " + a.folio_isp} />` : html`<${Estado} valor="VIGENTE" texto="Registrada" />`}</td>
          <td><div className="acciones">
            ${a.categoria === "FARMACOVIGILANCIA" && html`<button className="boton chico secundario" onClick=${() => setFicha(a)}><${Icono} nombre="imprimir" />Ficha</button>`}
            ${a.pendiente_notificar && html`<button className="boton chico" onClick=${() => notificar(a)}>Notificar</button>`}
            ${a.estado === "VIGENTE" && html`<button className="boton chico peligro" onClick=${() => anular(a)}>Anular</button>`}
          </div></td></tr>`)}</tbody></table></div></div>`}
      ${dialogo && html`<${Dialogo} ...${dialogo} onCerrar=${() => setDialogo(null)} />`}
      ${ficha && html`<${VentanaDocumento} titulo=${"Ficha de notificación · " + ficha.tipo_texto}
          subtitulo="Farmacovigilancia · para ingresar al Sistema de Vigilancia Integrado (SVI) del ISP"
          filas=${[["Fecha de detección", fecha(ficha.fecha)],
                   ...(ficha.paciente ? [["Paciente", ficha.paciente.nombre], ["RUT", ficha.paciente.rut], ["Edad", ficha.paciente.edad ?? "Sin fecha de nacimiento"]] : []),
                   ["Medicamento sospechoso", ficha.medicamento ? `${ficha.medicamento} (${ficha.principio_activo})` : "-"],
                   ["Lote", ficha.lote ? `${ficha.lote} · vence ${fecha(ficha.vencimiento_lote)}` : "No registrado"],
                   ...(ficha.gravedad ? [["Gravedad", GRAVEDADES[ficha.gravedad]]] : []),
                   ["Descripción", ficha.descripcion], ["Intervención", ficha.resultado || "-"],
                   ["Notificación ISP", ficha.folio_isp ? `${ficha.folio_isp} · ${fecha(ficha.fecha_notificacion)}` : "Pendiente"]]}
          firmas=${["Químico farmacéutico notificador"]} onCerrar=${() => setFicha(null)} />`}
    </div>`;
  }

  // ------------------------------------------------------------- indicadores FOFAR
  function Indicadores() {
    const hoyIso = fechaLocal(new Date());
    const inicioMes = (atras) => { const f = new Date(); f.setDate(1); f.setMonth(f.getMonth() - atras); return fechaLocal(f); };
    const PERIODOS = [["Este mes", inicioMes(0)], ["Últimos 3 meses", inicioMes(2)], ["Últimos 6 meses", inicioMes(5)],
                      ["Este año", hoyIso.slice(0, 4) + "-01-01"]];
    const [desde, setDesde] = useState(inicioMes(5));
    const [hasta, setHasta] = useState(hoyIso);
    const [{ datos: carga, error, cargando }] = useCarga(() => Promise.all([
      api("GET", `/api/indicadores/fofar?desde=${desde}&hasta=${hasta}`),
      api("GET", `/api/indicadores/fofar/mensual?desde=${desde}&hasta=${hasta}`)]), [desde, hasta]);
    const [datos, mensual] = carga || [null, null];
    const [fallo, setFallo] = useState(null);
    async function bajarRem() {
      setFallo(null);
      try { await descargarArchivo(`/api/reportes/rem-a04-j.csv?desde=${desde}&hasta=${hasta}`, `rem_a04_j_${desde}_${hasta}.csv`); }
      catch (err) { setFallo(err.message); }
    }
    const d = datos;
    // "en curso": reclamos aún dentro de su plazo, o actividades antes del corte (30 de junio y 31 de diciembre)
    const corte = /-(06-30|12-31)$/.test(hasta);
    const tarjetas = d ? [
      ["1 · Despacho total y oportuno", porcentaje(d.despacho.porcentaje), "Meta 100 %", d.despacho.solicitudes ? d.despacho.cumple : null,
       `${d.despacho.cumplidas} de ${d.despacho.solicitudes} solicitudes cardiovasculares`],
      ["2 · Reclamos resueltos en 24 h hábiles", porcentaje(d.reclamos.porcentaje), "Meta 100 %",
       !d.reclamos.reclamos ? null : d.reclamos.fuera_de_plazo === 0 && d.reclamos.en_curso > 0 ? "curso" : d.reclamos.cumple,
       `${d.reclamos.resueltos_en_plazo} de ${d.reclamos.reclamos} reclamos` + (d.reclamos.en_curso ? `, ${d.reclamos.en_curso} en plazo aún` : "")],
      ["3 · Merma valorizada", porcentaje(d.merma.porcentaje), "Meta ≤ 0,99 %", d.merma.porcentaje === null ? null : d.merma.cumple,
       `${pesos(d.merma.merma_valorizada)} de ${pesos(d.merma.inventario_valorizado)}`],
      ["4 · Actividades farmacéuticas", porcentaje(d.actividades.porcentaje), `Meta ${d.actividades.meta} % al corte`,
       !d.actividades.programadas ? null : d.actividades.cumple ? true : corte ? false : "curso",
       `${d.actividades.realizadas} de ${d.actividades.programadas ?? "sin programar"} (${d.actividades.anio})`]] : [];
    const tono = (cumple) => cumple === null ? "" : cumple === "curso" ? "alerta" : cumple ? "cumple" : "bloqueado";
    const estadoMeta = (cumple) => cumple === null ? html`<${Estado} valor="PENDIENTE" texto="Sin datos" />`
      : cumple === "curso" ? html`<${Estado} valor="ALERTA" texto="En curso" />`
      : cumple ? html`<${Estado} valor="VIGENTE" texto="Cumple" />` : html`<${Estado} valor="NO_DISPENSABLE" texto="No cumple" />`;
    return html`<div className=${cargando && datos ? "recargando" : ""}>
      <div className="periodos" role="group" aria-label="Período">${PERIODOS.map(([texto, inicio]) => html`<button key=${texto} type="button"
          className="boton chico secundario" aria-pressed=${desde === inicio && hasta === hoyIso}
          onClick=${() => { setDesde(inicio); setHasta(hoyIso); }}>${texto}</button>`)}</div>
      <div className="tarjeta fila-campos">
        <div className="campo"><label htmlFor="ind-desde">Desde</label><input id="ind-desde" type="date" value=${desde} max=${hasta} onChange=${(e) => setDesde(e.target.value)} /></div>
        <div className="campo"><label htmlFor="ind-hasta">Hasta</label><input id="ind-hasta" type="date" value=${hasta} min=${desde} onChange=${(e) => setHasta(e.target.value)} /></div>
        <div className="campo"><span className="etiqueta-vacia" aria-hidden="true"></span>
          <button className="boton secundario" onClick=${bajarRem}><${Icono} nombre="descargar" />REM A04 sección J</button></div>
      </div>
      <${Aviso} tipo="error">${error || fallo}<//>
      ${d && html`<div className="rejilla k4">${tarjetas.map(([titulo, valor, meta, cumple, detalle]) => html`
        <div className=${"tarjeta kpi " + tono(cumple)} key=${titulo}>
          <div><div className="etiqueta">${titulo}</div><div className="valor">${valor}</div>
            <div className="meta">${meta} · ${detalle}</div>
            <div style=${{ marginTop: ".4rem" }}>${estadoMeta(cumple)}</div></div>
          <span className="indicador"><${Icono} nombre="indicadores" /></span></div>`)}</div>
      ${mensual && html`<div className="rejilla k2">
        <div className="tarjeta"><${Grafico} tipo="linea" titulo="1 · Despacho total y oportuno, por mes" maximo=${100} minimo=${80}
            descripcion="Recetas cardiovasculares entregadas completas en el momento"
            referencia=${{ valor: 100, etiqueta: "Meta 100 %" }}
            datos=${mensual.meses.map((x) => ({ etiqueta: x.etiqueta.split(" ")[0], etiquetaLarga: x.etiqueta, valor: x.despacho,
                                               detalle: `${numero(x.solicitudes)} solicitudes · ${x.sin_stock} con quiebre de stock` }))}
            formato=${porcentaje} formatoEje=${(v) => numero(v) + " %"}
            columnas=${[["Mes", (x) => x.etiquetaLarga], ["Despacho oportuno", (x) => porcentaje(x.valor), true], ["Detalle", (x) => x.detalle]]} /></div>
        <div className="tarjeta"><${Grafico} titulo="3 · Merma valorizada, por mes"
            descripcion="Porcentaje del inventario valorizado al cierre del mes (sin insulinas)"
            referencia=${{ valor: 0.99, etiqueta: "Meta ≤ 0,99 %" }}
            datos=${mensual.meses.map((x) => ({ etiqueta: x.etiqueta.split(" ")[0], etiquetaLarga: x.etiqueta, valor: x.merma,
                                               detalle: `${pesos(x.merma_valorizada)} mermados` }))}
            formato=${(v) => numero(v, 2) + " %"} formatoEje=${(v) => numero(v, 2) + " %"}
            columnas=${[["Mes", (x) => x.etiquetaLarga], ["Merma", (x) => x.valor === null ? "s/d" : numero(x.valor, 2) + " %", true], ["Detalle", (x) => x.detalle]]} /></div>
      </div>
      <div className="tarjeta"><${Grafico} tipo="linea" titulo=${`4 · Actividades farmacéuticas acumuladas en ${hasta.slice(0, 4)}`}
          descripcion=${mensual.programadas ? `Programadas para el año: ${mensual.programadas} (meta: 50 % a junio y 100 % a diciembre)` : "Aún no hay programación para el año"}
          referencia=${mensual.programadas ? { valor: mensual.programadas, etiqueta: `Programadas ${mensual.programadas}` } : null}
          datos=${mensual.actividades.map((x) => ({ etiqueta: x.etiqueta.split(" ")[0], etiquetaLarga: x.etiqueta, valor: x.acumuladas,
                                                   detalle: `${x.realizadas} en el mes` }))}
          formato=${(v) => `${numero(v)} actividades`} formatoEje=${numero}
          columnas=${[["Mes", (x) => x.etiquetaLarga], ["Acumuladas", (x) => numero(x.valor), true], ["Detalle", (x) => x.detalle]]} /></div>`}
      <div>
        <div className="tarjeta"><h2>Brechas de despacho por medicamento</h2>
          <p className="ayuda">Solicitudes: ${d.despacho.completas} completas, ${d.despacho.sin_stock} con quiebre de stock y ${d.despacho.rechazo_paciente} con rechazo del paciente (no cuenta como incumplimiento).</p>
          <div className="tabla-envoltura"><table>
            <thead><tr><th>Medicamento</th><th className="num">Faltantes</th><th className="num">Entregados después</th><th className="num">Pendientes</th><th className="num">Días de demora</th></tr></thead>
            <tbody>${d.despacho.brechas.length === 0 && html`<tr><td colSpan="5">Sin quiebres de stock en el período.</td></tr>`}
            ${d.despacho.brechas.map((b) => html`<tr key=${b.medicamento}><td>${b.medicamento}</td><td className="num">${b.faltantes}</td>
              <td className="num">${b.entregados_despues}</td><td className="num">${b.pendientes}</td>
              <td className="num">${b.dias_promedio === null ? "-" : String(b.dias_promedio).replace(".", ",")}</td></tr>`)}</tbody></table></div></div>
        <div className="tarjeta"><h2>Detalle</h2>
          <dl className="lista-datos">
            <dt>Reclamos</dt><dd>${d.reclamos.resueltos_en_plazo} en plazo · ${d.reclamos.fuera_de_plazo} fuera de plazo · ${d.reclamos.en_curso} en curso</dd>
            <dt>Merma</dt><dd>${pesos(d.merma.merma_valorizada)} mermados sobre ${pesos(d.merma.inventario_valorizado)} de inventario al cierre (sin insulinas)
              ${(d.merma.lotes_sin_costo || d.merma.mermas_sin_costo) ? html`<div className="ayuda">Sin costo registrado: ${d.merma.lotes_sin_costo} lote(s) y ${d.merma.mermas_sin_costo} merma(s) no se valorizan.</div>` : ""}</dd>
            <dt>Actividades</dt><dd>${Object.entries(d.actividades.por_tipo).map(([t, n]) => `${(TIPOS_ACTIVIDAD.find(([c]) => c === t) || [t, t])[1]}: ${n}`).join(" · ") || "Sin actividades"}</dd>
          </dl></div>
      </div>`}
    </div>`;
  }

  // -------------------------------------------------------------- aplicación
  const PANTALLAS = [
    { id: "panel", titulo: "Panel", seccion: "Atención", permiso: "ver_stock", descripcion: "Stock dispensable por programa, quiebres y vencimientos próximos.", Vista: Panel },
    { id: "dispensar", titulo: "Dispensar", seccion: "Atención", permiso: "dispensar", descripcion: "Búsqueda del paciente, recetas, plan FEFO, verificación del lote y rótulo de unidosis.", Vista: Dispensar },
    { id: "recetar", titulo: "Recetar", seccion: "Atención", permiso: "registrar_receta", excluye: "dispensar", descripcion: "Búsqueda del paciente, recetas vigentes y emisión de recetas agudas o crónicas.", Vista: Dispensar },
    { id: "retiros", titulo: "Retiros", seccion: "Atención", permiso: "dispensar", descripcion: "Entregas que corresponden hoy o están atrasadas, para prepararlas con anticipación.", Vista: Retiros },
    { id: "despachos", titulo: "Despachos", seccion: "Atención", permiso: "gestionar_despachos", descripcion: "Despacho a domicilio de pacientes postrados: preparación, ruta y entrega.", Vista: Despachos },
    { id: "pendientes", titulo: "Pendientes", seccion: "Atención", permiso: "gestionar_reclamos", descripcion: "Compromisos de entrega por quiebre de stock y reclamos: se resuelven dentro de 24 horas hábiles (FOFAR).", Vista: Pendientes },
    { id: "dispensaciones", titulo: "Entregas", seccion: "Atención", permiso: "anular_dispensacion", descripcion: "Entregas recientes: rótulos, devoluciones y anulación con motivo.", Vista: Dispensaciones },
    { id: "inventario", titulo: "Lotes", seccion: "Inventario", permiso: "ver_stock", descripcion: "Recepción, vencimientos, ajustes, mermas y anulación de lotes.", Vista: Inventario },
    { id: "medicamentos", titulo: "Medicamentos", seccion: "Inventario", permiso: "ver_stock", descripcion: "Catálogo con código de barras EAN-13 y baja lógica: nada se borra, todo queda trazable.", Vista: MedicamentosVista },
    { id: "alertas", titulo: "Alertas", seccion: "Inventario", permiso: "ver_stock", descripcion: "Lotes por vencer o bloqueados y medicamentos bajo su umbral crítico.", Vista: Alertas },
    { id: "tomas", titulo: "Inventario físico", seccion: "Inventario", permiso: "contar_inventario", descripcion: "Toma de inventario a ciegas; el Q.F. revisa las diferencias y las aplica como ajuste.", Vista: TomasInventario },
    { id: "prestamos", titulo: "Préstamos", seccion: "Inventario", permiso: "gestionar_prestamos", descripcion: "Préstamos de medicamentos con otros establecimientos ante quiebres de stock (Anexo 1 FOFAR).", Vista: Prestamos },
    { id: "libro", titulo: "Libro", seccion: "Control", permiso: "ver_libro", descripcion: "Libro de control de estupefacientes y psicotrópicos: ingresos, egresos y saldos, encadenado por hash.", Vista: Libro },
    { id: "actividades", titulo: "Atención farmacéutica", seccion: "Control", permiso: "registrar_actividad", descripcion: "Seguimiento, conciliación, educación, farmacovigilancia y talleres del Q.F.", Vista: Actividades },
    { id: "indicadores", titulo: "Indicadores FOFAR", seccion: "Control", permiso: "ver_reportes", descripcion: "Los cuatro indicadores del Programa Fondo de Farmacia, con sus metas.", Vista: Indicadores },
    { id: "reportes", titulo: "Reportes", seccion: "Control", permiso: "ver_reportes", descripcion: "Exportación a CSV: kardex, entregas por programa, vencimientos, REM A04 sección J y libro de controlados.", Vista: Reportes },
    { id: "auditoria", titulo: "Auditoría", seccion: "Control", permiso: "ver_auditoria", descripcion: "Eventos registrados en la bandeja de salida (outbox).", Vista: Auditoria },
    { id: "usuarios", titulo: "Usuarios", seccion: "Sistema", permiso: "gestionar_usuarios", descripcion: "Alta y baja de funcionarios y asignación de roles.", Vista: Usuarios },
  ];
  const HOY_TEXTO = new Date().toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const HOY_TITULO = HOY_TEXTO.charAt(0).toUpperCase() + HOY_TEXTO.slice(1);

  function App() {
    const [yo, setYo] = useState(null);
    const [cargando, setCargando] = useState(!!tokenActual);
    const [pantalla, setPantalla] = useState("panel");
    const [contexto, setContexto] = useState(null);
    const [ruta, setRuta] = useState(window.location.hash);
    useEffect(() => {
      const alCambiar = () => setRuta(window.location.hash);
      window.addEventListener("hashchange", alCambiar);
      return () => window.removeEventListener("hashchange", alCambiar);
    }, []);
    const abrir = useCallback((id, datos = null) => { setContexto(datos); setPantalla(id); }, []);

    const salir = useCallback(() => { guardarToken(null); setYo(null); setCargando(false); }, []);
    alExpirar = salir;
    const cargarYo = useCallback(() => {
      setCargando(true);
      api("GET", "/api/auth/yo").then((u) => { setYo(u); setPantalla(u.permisos.includes("dispensar") ? "dispensar"
        : u.permisos.includes("registrar_receta") ? "recetar" : "panel"); })
        .catch(salir).finally(() => setCargando(false));
    }, [salir]);
    useEffect(() => { if (tokenActual) cargarYo(); }, [cargarYo]);

    if (ruta === "#/disponibilidad") return html`<${DisponibilidadPublica} />`;
    if (cargando) return html`<main className="ingreso-formulario" style=${{ minHeight: "100vh" }}><p className="ayuda">Cargando…</p></main>`;
    if (!yo) return html`<${Ingreso} onIngreso=${cargarYo} />`;

    const visibles = PANTALLAS.filter((p) => yo.permisos.includes(p.permiso) && !(p.excluye && yo.permisos.includes(p.excluye)));
    const actual = visibles.find((p) => p.id === pantalla) || visibles[0];
    const secciones = [...new Set(visibles.map((p) => p.seccion))];
    const rol = NOMBRES_ROL[yo.rol] || yo.rol;
    return html`<div className="app">
      <nav className="lateral" aria-label="Menú principal">
        <div className="marca"><${Logo} />
          <div><strong>SISGEF</strong><small>Farmacia asistencial · CESFAM</small></div></div>
        <div className="menu">${secciones.map((s) => html`<${React.Fragment} key=${s}>
          <div className="menu-seccion" aria-hidden="true">${s}</div>
          ${visibles.filter((p) => p.seccion === s).map((p) => html`<button key=${p.id} aria-current=${p.id === actual.id ? "page" : undefined}
             onClick=${() => abrir(p.id)}><${Icono} nombre=${p.id} />${p.titulo}</button>`)}
        <//>`)}</div>
        <div className="sesion">
          <div className="usuario"><span className="avatar" aria-hidden="true">${iniciales(yo.nombre)}</span>
            <div style=${{ minWidth: 0 }}><div className="nombre">${yo.nombre}</div><div className="rol">${rol}</div></div></div>
          <button className="boton secundario chico" onClick=${salir}><${Icono} nombre="salir" />Cerrar sesión</button>
        </div>
      </nav>
      <div className="principal">
        <header className="barra-superior">
          <div className="miga"><span>${actual.seccion}</span><span className="separador" aria-hidden="true">/</span><strong>${actual.titulo}</strong></div>
          <div className="contexto"><span className="fecha-hoy">${HOY_TITULO}</span><span className="chip">${rol}</span><${SelectorTema} /></div>
        </header>
        <main className="contenido">
          <div className="barra-movil"><strong>${yo.nombre}</strong><div className="acciones"><${SelectorTema} /><button className="boton secundario chico" onClick=${salir}>Salir</button></div></div>
          <div className="encabezado"><div><h1>${actual.titulo}</h1><p>${actual.descripcion}</p></div></div>
          <${actual.Vista} key=${actual.id + (contexto ? JSON.stringify(contexto) : "")} permisos=${yo.permisos}
              contexto=${contexto} abrir=${abrir} />
        </main>
      </div>
    </div>`;
  }

  ReactDOM.createRoot(document.getElementById("raiz")).render(html`<${App} />`);
})();
