"""Consulta pública de disponibilidad (sin inicio de sesión).

Solo informa "disponible / pocas unidades / sin stock" por medicamento: nunca
cantidades exactas, lotes ni datos de pacientes, y no incluye medicamentos
controlados. Al no tener autenticación, se limita el número de consultas por
dirección IP para evitar abusos (OWASP API4: consumo de recursos sin límite).
"""

import threading
import time
from collections import deque
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..services import inventario
from .deps import fecha_hoy, sesion

router = APIRouter(prefix="/api/publico", tags=["público"])


class LimiteDePeticiones:
    """Ventana deslizante en memoria: `maximo` peticiones por `segundos` y por cliente.

    Basta para una sola instancia; con varias instancias detrás de un balanceador
    el límite se aplica en el API Gateway o el WAF (ver el informe, red AWS).
    """

    def __init__(self, maximo: int, segundos: int):
        self.maximo, self.segundos = maximo, segundos
        self._historial: dict[str, deque] = {}
        self._candado = threading.Lock()

    def __call__(self, request: Request) -> None:
        cliente = request.client.host if request.client else "desconocido"
        ahora = time.monotonic()
        with self._candado:
            historial = self._historial.setdefault(cliente, deque())
            while historial and ahora - historial[0] > self.segundos:
                historial.popleft()
            if len(historial) >= self.maximo:
                espera = int(self.segundos - (ahora - historial[0])) + 1
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "Demasiadas consultas seguidas. Intente nuevamente en un momento.",
                                    headers={"Retry-After": str(espera)})
            historial.append(ahora)
            if len(self._historial) > 10_000:  # evita que la memoria crezca sin límite
                for clave in [c for c, h in self._historial.items() if not h or ahora - h[-1] > self.segundos]:
                    del self._historial[clave]


limite_publico = LimiteDePeticiones(maximo=60, segundos=60)


@router.get("/disponibilidad", dependencies=[Depends(limite_publico)])
def disponibilidad(q: str | None = Query(None, max_length=60), db: Session = Depends(sesion),
                   hoy: date = Depends(fecha_hoy)):
    return {"fecha": hoy.isoformat(), "medicamentos": inventario.disponibilidad_publica(db, hoy, q)}
