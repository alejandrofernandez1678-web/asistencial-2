"""Vocabulario controlado del catálogo farmacéutico y del paciente.

Se usa en la validación de entrada (API) y en la interfaz, para que una
misma forma farmacéutica no quede escrita de tres maneras distintas.
"""

FORMAS_FARMACEUTICAS = {
    "COMPRIMIDO": "Comprimido", "CAPSULA": "Cápsula", "JARABE": "Jarabe", "SUSPENSION": "Suspensión oral",
    "GOTAS": "Gotas", "INHALADOR": "Inhalador", "SOLUCION_INYECTABLE": "Solución inyectable",
    "CREMA": "Crema", "OTRO": "Otra",
}

# Unidad mínima en que se cuenta, descuenta y entrega el medicamento.
UNIDADES_DISPENSACION = {
    "COMPRIMIDO": "comprimido", "CAPSULA": "cápsula", "FRASCO": "frasco", "INHALADOR": "inhalador",
    "AMPOLLA": "ampolla", "POMO": "pomo", "UNIDAD": "unidad",
}

TIPOS_RECETA = ("AGUDA", "CRONICA", "RETENIDA")
TRAMOS_FONASA = ("A", "B", "C", "D")
PARENTESCOS = ("Hijo/a", "Cónyuge o pareja", "Padre/madre", "Hermano/a", "Cuidador/a", "Otro")
