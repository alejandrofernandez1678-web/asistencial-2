"""Medición de rendimiento del planificador FEFO (no forma parte de la suite pytest).

Uso:  python -m tests.rendimiento.medir_fefo
Genera inventarios sintéticos de 1.000, 10.000 y 50.000 lotes (repartidos entre 50
medicamentos), mide 200 planificaciones por tamaño y repite la medición 3 veces.
Informa la mediana de las 3 ejecuciones para p50 y p95.
"""

import platform
import random
import statistics
import time
from datetime import date, timedelta

from app.domain.fefo import LoteFEFO, planificar

HOY = date(2026, 11, 17)
TAMANOS = (1_000, 10_000, 50_000)
REPETICIONES = 200
EJECUCIONES = 3
MEDICAMENTOS = 50


def inventario(n: int, semilla: int) -> list[LoteFEFO]:
    azar = random.Random(semilla)
    return [LoteFEFO(i, f"L-{i:06d}", azar.randint(1, MEDICAMENTOS),
                     HOY + timedelta(days=azar.randint(1, 900)), azar.randint(1, 500), f"C-{i % 300:03d}")
            for i in range(n)]


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p * (len(ordenados) - 1)))]


def medir(n: int, semilla: int) -> tuple[float, float]:
    lotes = inventario(n, semilla)
    tiempos = []
    for i in range(REPETICIONES):
        inicio = time.perf_counter()
        planificar(lotes, (i % MEDICAMENTOS) + 1, 30, HOY)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    return percentil(tiempos, 0.50), percentil(tiempos, 0.95)


def main() -> None:
    print(f"Python {platform.python_version()} · {platform.system()} {platform.machine()}")
    print(f"{'Lotes':>8} {'p50 (ms)':>10} {'p95 (ms)':>10}")
    for n in TAMANOS:
        resultados = [medir(n, semilla) for semilla in range(EJECUCIONES)]
        p50 = statistics.median(r[0] for r in resultados)
        p95 = statistics.median(r[1] for r in resultados)
        print(f"{n:>8} {p50:>10.2f} {p95:>10.2f}")


if __name__ == "__main__":
    main()
