"""
Evaluacion de varias correcciones de una sola pasada.

Hasta el H5-1 el prototipo evaluaba una correccion por corrida. Eso sirve para
mirar un caso, pero la clasificacion por cuartiles necesita un conjunto: sin
varias correcciones no hay contra que comparar y los niveles no significan
nada.

Una correccion que falla no detiene la corrida. Sobre un corpus de decenas de
casos siempre va a haber alguno con un sha mal copiado o un repositorio
desactualizado, y perder una hora de medicion por eso no tiene sentido. Las
fallas se juntan y se reportan al final.
"""

import json
import os
from pathlib import Path

import yaml

from .repo import Repositorio
from . import classify
from . import profile


def cargar(ruta):
    """Lee el archivo del corpus y devuelve la lista de entradas."""
    with open(ruta, encoding="utf-8") as f:
        datos = yaml.safe_load(f)

    if not isinstance(datos, list):
        raise ValueError("el corpus debe ser una lista de proyectos")

    return datos


def evaluar(entradas):
    """
    Construye el perfil de cada correccion declarada.

    Devuelve los perfiles que salieron bien y la lista de los que no, con el
    motivo. El repositorio se abre una sola vez por proyecto: abrirlo por cada
    correccion seria pagar el mismo costo varias veces sin razon.
    """
    perfiles = []
    fallas = []

    for entrada in entradas:
        nombre = entrada.get("proyecto", "")
        ruta = entrada.get("ruta", "")

        try:
            repo = Repositorio(ruta)
        except Exception as exc:
            fallas.append((nombre, ruta, f"no se pudo abrir el repositorio: {exc}"))
            continue

        for sha in entrada.get("correcciones", []):
            try:
                c = repo.cargar_correccion(sha)
                perfiles.append(profile.construir(repo, c, proyecto=nombre))
                print(f"  medido  {nombre} {sha}")
            except Exception as exc:
                fallas.append((nombre, sha, str(exc)))
                print(f"  FALLO   {nombre} {sha}: {exc}")

    return perfiles, fallas


def guardar(perfiles, ruta):
    """Escribe los perfiles a disco para que el analisis no dependa de volver a medir."""
    destino = Path(ruta)
    os.makedirs(destino.parent, exist_ok=True)

    with open(destino, "w", encoding="utf-8") as f:
        json.dump([p.como_diccionario() for p in perfiles], f,
                  indent=2, ensure_ascii=False)

    return destino


def tabla(perfiles):
    """Resumen en una linea por correccion, para mirar el conjunto de un vistazo."""
    print()
    print(f"  {'proyecto':<12} {'sha':<10} {'dCCN':>6} {'dens':>7} {'disp':>6} {'desp':>6} {'cand':>5}")
    print("  " + "-" * 60)
    for p in perfiles:
        dens = "-" if p.densidad_decision is None else f"{p.densidad_decision:.2f}"
        print(f"  {p.proyecto[:12]:<12} {p.sha[:10]:<10} {p.delta_ccn:>+6d} "
              f"{dens:>7} {p.proporcion_servicios:>6} "
              f"{p.ponderado_introducidas:>6} {p.parches_complementarios:>5}")


def evaluar_archivo(ruta_corpus, ruta_salida):
    """Punto de entrada desde la linea de comandos. Devuelve el codigo de salida."""
    try:
        entradas = cargar(ruta_corpus)
    except Exception as exc:
        print(f"error: no se pudo leer el corpus: {exc}")
        return 1

    print(f"CORPUS {ruta_corpus}")
    perfiles, fallas = evaluar(entradas)

    if not perfiles:
        print()
        print("  no se pudo medir ninguna correccion")
        return 1

    tabla(perfiles)

    # La clasificacion solo entra si el conjunto da para calcularla y cuando no da, se dice cuantas faltan y que no aparezca que algo se rompio.
    if len(perfiles) >= classify.MINIMO:
        classify.informe(classify.clasificar(perfiles))
    else:
        print()
        print(f"  la clasificacion por cuartiles necesita {classify.MINIMO} correcciones, "
              f"hay {len(perfiles)}")

    destino = guardar(perfiles, ruta_salida)
    print()
    print(f"  {len(perfiles)} perfiles guardados en {destino}")

    if fallas:
        print()
        print(f"  {len(fallas)} correcciones no se pudieron medir:")
        for nombre, sha, motivo in fallas:
            print(f"    {nombre} {sha}: {motivo}")

    return 0