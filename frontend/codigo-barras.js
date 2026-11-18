/* Codificación EAN-13 para dibujar el código de barras de cada medicamento.
 * Es la misma lógica de backend/app/domain/codigo_barras.py; una prueba E2E
 * compara ambos resultados para garantizar que lo impreso se puede escanear. */
(function () {
  "use strict";
  const L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"];
  const G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"];
  const R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"];
  const PARIDAD = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"];

  function digitoVerificador(doce) {
    let suma = 0;
    for (let i = 0; i < 12; i++) suma += Number(doce[i]) * (i % 2 ? 3 : 1);
    return String((10 - (suma % 10)) % 10);
  }

  function valido(codigo) {
    return /^\d{13}$/.test(codigo || "") && digitoVerificador(codigo) === codigo[12];
  }

  /** 95 módulos como texto de 0 y 1 (1 = barra), o null si el código no es válido. */
  function modulos(codigo) {
    if (!valido(codigo)) return null;
    const paridad = PARIDAD[Number(codigo[0])];
    let izquierda = "", derecha = "";
    for (let i = 0; i < 6; i++) izquierda += (paridad[i] === "L" ? L : G)[Number(codigo[i + 1])];
    for (let i = 7; i < 13; i++) derecha += R[Number(codigo[i])];
    return "101" + izquierda + "01010" + derecha + "101";
  }

  /** Barras agrupadas: [{ x, ancho, guarda }] en unidades de módulo, para dibujar en SVG. */
  function barras(codigo) {
    const m = modulos(codigo);
    if (!m) return [];
    const guardas = new Set([0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94]);
    const resultado = [];
    for (let i = 0; i < m.length; i++) {
      if (m[i] !== "1") continue;
      const guarda = guardas.has(i);
      const previa = resultado[resultado.length - 1];
      if (previa && previa.x + previa.ancho === i && previa.guarda === guarda) previa.ancho++;
      else resultado.push({ x: i, ancho: 1, guarda });
    }
    return resultado;
  }

  window.CodigoBarras = { digitoVerificador, valido, modulos, barras };
})();
