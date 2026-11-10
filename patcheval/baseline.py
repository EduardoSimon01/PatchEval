"""
Seleccion de la linea base.

El costo arquitectonico de una correccion no significa nada por si solo por ejemplo que agregue 166 de complejidad solo cobra sentido al compararlo con lo que cuesta
un cambio cualquiera del mismo proyecto es decir que si los cambios ordinarios agregan tanto como las correcciones, entonces corregir vulnerabilidades no sale mas
caro que programar, y esa es una conclusion legitima que hay que poder alcanzar.

La seleccion la hace el prototipo y no yo a mano porque escoger los cambios ordinarios uno por uno podria hacer que sin querer se incline la comparacion
hacia el lado que convenga. El criterio ya esta escrito aqui y cualquiera puede repetirlo sobre el mismo repositorio y obtener los mismos commits.
"""

import re
from datetime import datetime, timedelta

# Esto es cuanto tiempo alrededor de la correccion se buscan los cambios ordinarios la idea es que vengan de la misma epoca del proyecto por si un cambio de hace
# cinco anos pertenece a otro sistema aunque el repositorio sea el mismo.
VENTANA_DIAS = 180

# Un cambio ordinario no puede ser una correccion de seguridad disfrazada si se nos pasa una la linea base dejaria de ser la base y la comparacion se
# estaria haciendo contra si misma osea que se compararian correcciones con correcciones.
PALABRAS_SEGURIDAD = (
    r"CVE-\d{4}", r"GHSA-", r"\bsecurity\b", r"vulnerab", r"exploit",
    r"\bXSS\b", r"\bCSRF\b", r"\bSSRF\b", r"\bRCE\b", r"injection",
    r"sanitiz", r"escalat", r"\bauth(?:z|n)?\s+bypass",
)

_RE_SEGURIDAD = re.compile("|".join(PALABRAS_SEGURIDAD), re.IGNORECASE)


def es_seguridad(mensaje):
    """
    Dice si el mensaje de un commit sugiere que trata una vulnerabilidad.
    """
    return bool(_RE_SEGURIDAD.search(mensaje))


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

    Por cada correccion en el cropus se busca en la ventana a su alrededor se descartan las propias correcciones del corpus y lo que parezca de seguridad y de lo que
    queda se toman N repartidos.

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
            for sha, _, asunto in repo.commits_ordinarios(desde, hasta)
            if sha not in excluidos and not es_seguridad(asunto)
        ]

        for sha, asunto in muestrear(candidatos, cantidad):
            if sha not in elegidos:
                elegidos[sha] = asunto
                excluidos.add(sha)

    return list(elegidos.items())