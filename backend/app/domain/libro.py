"""Libro digital de controlados con encadenamiento por hash (RF-05, RN-07).

Cada asiento guarda el hash del anterior; alterar cualquier asiento rompe
la cadena desde ese punto y verificar_cadena lo detecta.
"""

import hashlib
import json
from dataclasses import dataclass

HASH_GENESIS = "0" * 64


def calcular_hash(hash_previo: str, contenido: dict) -> str:
    canonico = json.dumps(contenido, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{hash_previo}|{canonico}".encode()).hexdigest()


@dataclass(frozen=True)
class AsientoVerificable:
    nro_asiento: int
    contenido: dict
    hash_previo: str
    hash_actual: str


def verificar_cadena(asientos: list[AsientoVerificable]) -> tuple[bool, int | None]:
    """Devuelve (True, None) si la cadena es íntegra o (False, nro_asiento) del primer asiento alterado."""
    esperado_previo = HASH_GENESIS
    for asiento in sorted(asientos, key=lambda a: a.nro_asiento):
        if asiento.hash_previo != esperado_previo:
            return False, asiento.nro_asiento
        if calcular_hash(asiento.hash_previo, asiento.contenido) != asiento.hash_actual:
            return False, asiento.nro_asiento
        esperado_previo = asiento.hash_actual
    return True, None
