"""
Seleccion de la linea base.

El costo arquitectonico de una correccion no significa nada por si solo por ejemplo que agregue 166 de complejidad solo cobra sentido al compararlo con lo que cuesta
un cambio cualquiera del mismo proyecto es decir que si los cambios ordinarios agregan tanto como las correcciones, entonces corregir vulnerabilidades no sale mas
caro que programar, y esa es una conclusion legitima que hay que poder alcanzar.

La seleccion la hace el prototipo y no yo a mano porque escoger los cambios ordinarios uno por uno podria hacer que sin querer se incline la comparacion
hacia el lado que convenga. El criterio ya esta escrito aqui y cualquiera puede repetirlo sobre el mismo repositorio y obtener los mismos commits.

Un cambio ordinario tiene que ser codigo escrito por una persona la primera version de esto no lo exigia y al correrlo devolvio tres actualizaciones automaticas
de dependencias con una linea cada una, cero archivos de codigo y cero variacion de complejidad, o sea que contra eso cualquier correccion sale cara pero no porque
corregir cueste sino porque en lo que habiamos agarrado no habia nada que medir por eso salieron los dos filtros nuevos.
"""

import re
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from .metrics import complexity

# Esto es cuanto tiempo alrededor de la correccion se buscan los cambios ordinarios la idea es que vengan de la misma epoca del proyecto por si un cambio de hace
# cinco anos pertenece a otro sistema aunque el repositorio sea el mismo.
VENTANA_DIAS = 180

# Esto es cuantos candidatos se revisan por cada uno que hace falta porque el filtro que mira si el commit toca codigo cuesta una llamada a git por candidato asi que no se le
# pasan todos, se reparten sobre el conjunto ya limpio y se van validando en ese orden hasta juntar los que se necesitan.
HOLGURA = 6

# Un cambio ordinario no puede ser una correccion de seguridad disfrazada si se nos pasa una la linea base dejaria de ser la base y la comparacion se
# estaria haciendo contra si misma osea que se compararian correcciones con correcciones.
PALABRAS_SEGURIDAD = (
    r"CVE-\d{4}", r"GHSA-", r"\bsecurity\b", r"vulnerab", r"exploit",
    r"\bXSS\b", r"\bCSRF\b", r"\bSSRF\b", r"\bRCE\b", r"injection",
    r"sanitiz", r"escalat", r"\bauth(?:z|n)?\s+bypass",
)

# Las actualizaciones automaticas de dependencias tampoco sirven porque no las escribio nadie, las genera una herramienta que solo sube un numero de version
# entonces su costo arquitectonico es cero por construccion y no porque el cambio sea simple.
PATRONES_AUTOMATICO = (
    r"^chore\(deps", r"^build\(deps", r"^chore: update dependency",
    r"\bbump\b", r"\bdependabot\b", r"\brenovate\b",
)

# Por el mensaje igual se escapan algunas asi que tambien se mira quien firma el commit.
PATRONES_BOT = (r"\[bot\]", r"\bbot\b", r"dependabot", r"renovate", r"github-actions")

_RE_SEGURIDAD = re.compile("|".join(PALABRAS_SEGURIDAD), re.IGNORECASE)
_RE_AUTOMATICO = re.compile("|".join(PATRONES_AUTOMATICO), re.IGNORECASE)
_RE_BOT = re.compile("|".join(PATRONES_BOT), re.IGNORECASE)


def es_seguridad(mensaje):
    """
    Dice si el mensaje de un commit sugiere que trata una vulnerabilidad.
    """
    return bool(_RE_SEGURIDAD.search(mensaje))


def es_automatico(mensaje):
    """
    Dice si el mensaje es de una actualizacion automatica de dependencias.
    """
    return bool(_RE_AUTOMATICO.search(mensaje))


def es_bot(autor):
    """
    Dice si el que firma el commit es una herramienta y no una persona.
    """
    return bool(_RE_BOT.search(autor or ""))


def toca_codigo(repo, sha):
    """
    Dice si el commit modifico aunque sea un archivo de codigo.

    Este es el filtro que de verdad importa porque un commit que solo mueve documentacion o configuracion de la integracion continua o archivos de bloqueo
    tiene variacion de complejidad cero pero no porque sea simple sino porque no habia codigo que medirle, y meter ese cero a la comparacion la ensucia.

    Se reusa la lista de extensiones del modulo de complejidad para que las dos partes entiendan lo mismo por codigo.
    """
    return any(PurePosixPath(ruta).suffix.lower() in complexity.EXTENSIONES
               for ruta in repo.archivos_de(sha))


def muestrear(candidatos, cantidad):
    """
    Toma N elementos repartidos de forma pareja a lo largo de la lista.

    Se reparte en lugar de tomar los primeros porque los candidatos vienen ordenados por fecha y si agarramos los primeros daria los mas recientes y todos
    de la misma semana mejor repartidos asi cubren la ventana completa.

    No se usa azar a proposito porque un muestreo aleatorio exigiria declarar la semilla para que otro pueda repetirlo y aun asi dependeria de la
    implementacion del generador aleatorio mejor repartir porque es mas deterministico.
    """
    if cantidad <= 0 or not candidatos:
        return []
    if cantidad >= len(candidatos):
        return list(candidatos)
    if cantidad == 1:
        return [candidatos[len(candidatos) // 2]]

    paso = (len(candidatos) - 1) / (cantidad - 1)
    return [candidatos[round(i * paso)] for i in range(cantidad)]


def seleccionar(repo, perfiles, cantidad):
    """
    Escoge cambios ordinarios para contrastar con las correcciones dadas.

    Por cada correccion en el cropus se busca en la ventana a su alrededor se descartan las propias correcciones del corpus, lo que parezca de seguridad, lo
    automatico y lo que firmo una herramienta y de lo que queda se reparten candidatos y se van aceptando los que tocan codigo hasta juntar N.

    Un mismo commit no se toma dos veces aunque caiga en la ventana de dos correcciones distintas sino contaria doble en el analisis y el contraste
    quedaria pesado hacia esa epoca del proyecto.
    """
    excluidos = {p.sha for p in perfiles}
    elegidos = {}

    for p in perfiles:
        base = datetime.fromisoformat(p.fecha)
        desde = (base - timedelta(days=VENTANA_DIAS)).date().isoformat()
        hasta = (base + timedelta(days=VENTANA_DIAS)).date().isoformat()

        candidatos = [
            (sha, asunto)
            for sha, _, autor, asunto in repo.commits_ordinarios(desde, hasta)
            if sha not in excluidos
            and not es_seguridad(asunto)
            and not es_automatico(asunto)
            and not es_bot(autor)
        ]

        faltan = cantidad
        for sha, asunto in muestrear(candidatos, min(len(candidatos), cantidad * HOLGURA)):
            if faltan == 0:
                break
            if sha in elegidos or not toca_codigo(repo, sha):
                continue

            elegidos[sha] = asunto
            excluidos.add(sha)
            faltan -= 1

    return list(elegidos.items())