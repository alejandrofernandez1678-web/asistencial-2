"""Errores del dominio.

Las reglas de negocio lanzan ReglaNegocioError con un código estable
(por ejemplo "FEFO" o "RECETA_VENCIDA") para que la API y las pruebas
puedan identificarlas sin depender del texto del mensaje.
"""


class ReglaNegocioError(Exception):
    def __init__(self, codigo: str, mensaje: str):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje
