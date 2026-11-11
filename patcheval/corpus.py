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
import csv

import yaml

from .repo import Repositorio
from . import classify
from . import profile
from . import baseline


def cargar(ruta):
    """Lee el archivo del corpus y devuelve la lista de entradas."""
    with open(ruta, encoding="utf-8") as f:
        datos = yaml.safe_load(f)

    if not isinstance(datos, list):
        raise ValueError("el corpus debe ser una lista de proyectos")

    return datos


def normalizar(correcciones):
    """
    Acepta las dos formas de declarar una correccion en el archivo del corpus.

    La corta es solo el identificador y la larga agrega de donde salio osea el aviso publicado que la respalda. La larga es la que realmente conviene sin el
    aviso nadie puede comprobar que ese commit corrige de verdad una vulnerabilidad y no es un cambio cualquiera que alguien metio.
    """
    salida = []
    for c in correcciones or []:
        if isinstance(c, dict):
            salida.append((str(c.get("sha", "")), str(c.get("fuente", ""))))
        else:
            salida.append((str(c), ""))
    return salida

def evaluar(entradas):
    """
    Construye el perfil de cada correccion declarada.

    Devuelve los perfiles que salieron bien y la lista de los que no, con el motivo. El repositorio se abre una sola vez por proyecto porque abrirlo por cada
    correccion seria pagar el mismo costo varias veces sin razon.
    """
    perfiles = []
    fallas = []

    for entrada in entradas:
        nombre = entrada.get("proyecto", "")
        ruta = entrada.get("ruta", "")
        raiz = str(entrada.get("raiz_servicios", "") or "")

        try:
            repo = Repositorio(ruta)
        except Exception as exc:
            fallas.append((nombre, ruta, f"no se pudo abrir el repositorio: {exc}"))
            continue

        for sha, fuente in normalizar(entrada.get("correcciones")):
            try:
                c = repo.cargar_correccion(sha)
                perfiles.append(profile.construir(repo, c, proyecto=nombre, fuente=fuente, raiz_servicios=raiz))
                print(f"  medido  {nombre} {sha}")
            except Exception as exc:
                fallas.append((nombre, sha, str(exc)))
                print(f"  FALLO   {nombre} {sha}: {exc}")

        # La linea base se arma despues de medir las correcciones del proyecto porque la ventana de busqueda se define alrededor de sus fechas.
        cantidad = int(entrada.get("linea_base", 0) or 0)
        if cantidad:
            de_seguridad = [p for p in perfiles
                            if p.proyecto == nombre and p.tipo == "seguridad"]
            for sha, asunto, pareja in baseline.seleccionar(repo, de_seguridad, cantidad):
                try:
                    c = repo.cargar_correccion(sha)
                    perfiles.append(profile.construir(repo, c, proyecto=nombre, tipo="ordinaria", pareja=pareja, raiz_servicios=raiz))
                    print(f"  base    {nombre} {sha[:10]} {asunto[:45]}")
                except Exception as exc:
                    fallas.append((nombre, sha, str(exc)))
                    print(f"  FALLO   {nombre} {sha[:10]}: {exc}")

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

# Las columnas de la exportacion. Se declaran en orden fijo para que dos corridas produzcan archivos comparables y para que agregar un campo al perfil
# no cambie en silencio la forma de la tabla.
CAMPOS_CSV = (
    "proyecto", "tipo", "sha", "fecha", "fuente", "pareja", "raiz_servicios",
    "archivos", "lineas_agregadas", "lineas_eliminadas",
    "archivos_codigo", "ccn_antes", "ccn_despues", "delta_ccn", "densidad_decision",
    "servicios_afectados", "servicios_totales", "proporcion_servicios",
    "manifiestos_analizados", "introducidas", "ponderado_introducidas",
    "resueltas", "ponderado_resueltas",
    "cambios_sobre_las_mismas_lineas", "parches_complementarios",
    "dias_hasta_el_primero", "ventana_dias",
    "head", "evaluado_en",
)


def exportar_csv(perfiles, ruta):
    """
    Escribe los perfiles como tabla.

    El contraste contra la linea base se hace sobre esto si un valor que falta, como la densidad cuando la correccion no agrega lineas, se deja vacio y no
    en cero la herramienta de analisis tiene que poder distinguir un dato ausente de un dato que vale cero.
    """
    destino = Path(ruta)
    os.makedirs(destino.parent, exist_ok=True)

    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CAMPOS_CSV)
        for p in perfiles:
            w.writerow(["" if getattr(p, campo) is None else getattr(p, campo)
                        for campo in CAMPOS_CSV])

    return destino

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

    # Los niveles salen del conjunto de correcciones de seguridad y la linea base no entra porque esta para contrastar, no para definir los cortes.
    de_seguridad = [p for p in perfiles if p.tipo == "seguridad"]
    if len(de_seguridad) >= classify.MINIMO:
        classify.informe(classify.clasificar(de_seguridad))
    else:
        print()
        print(f"  la clasificacion por cuartiles necesita {classify.MINIMO} correcciones "
              f"de seguridad, hay {len(de_seguridad)}")

    destino = guardar(perfiles, ruta_salida)
    # El csv lo dejamos a la par del json con el mismo nombre asi uno conserva el detalle completo y el otro es el que entra al analisis.
    destino_csv = exportar_csv(perfiles, Path(ruta_salida).with_suffix(".csv"))
    print()
    print(f"  {len(perfiles)} perfiles guardados en {destino} y {destino_csv}")

    if fallas:
        print()
        print(f"  {len(fallas)} correcciones no se pudieron medir:")
        for nombre, sha, motivo in fallas:
            print(f"    {nombre} {sha}: {motivo}")

    return 0