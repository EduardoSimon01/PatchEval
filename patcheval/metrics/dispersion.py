"""
Dispersion del cambio.

Responde que tan repartida quedo la correccion entre los servicios del sistema. Una correccion que toca un solo servicio es contenida, una que toca
la mitad del sistema ya hablamos de un problema que estaba en todos lados o de una solucion que se metio en todos lados que pueda que no debía.

Es la subdimension mas barata de calcular de todas, porque no hace falta leer el contenido de ningun archivo nomas con mirar en que carpeta cae cada uno
"""

from pathlib import PurePosixPath


def es_manifiesto(ruta):
    # No agarra archivos de codigo porque queremos ver un cambio que solo toca manifiestos.
    return PurePosixPath(ruta).suffix.lower() in {".yaml", ".yml"}


def medir(repo, correccion):
    """
    Calcula la proporcion de servicios que la correccion alcanzo.

    Los servicios se aproximan por los directorios de primer nivel, con todo lo que eso implica y que ya esta declarado como limitacion.
    """
    # El total se pide en el punto de la correccion y no en la HEAD porque si el proyecto gano servicios despues, usar la HEAD inflaria el denominador 
    # y haria que pareciera mas contenida de lo que fue una correccion vieja.
    todos = repo.servicios(correccion.sha)

    alcanzados = set()
    for a in correccion.archivos:
        # Primer tramo de la ruta tal como git la reporta los archivos que solo estan en la raiz no tiene carpeta, asi que no cuenta como servicio.
        partes = PurePosixPath(a.ruta).parts
        if len(partes) > 1 and partes[0] in todos:
            alcanzados.add(partes[0])

    total = len(todos)
    # El max(total, 1) evita dividir entre cero. Pasa con repos que tienen todo en la raiz, que es raro pero puede pasar.
    proporcion = round(len(alcanzados) / max(total, 1), 4)

    manifiestos = [a.ruta for a in correccion.archivos if es_manifiesto(a.ruta)]

    return {
        "servicios_totales": total,
        "servicios_afectados": len(alcanzados),
        "proporcion": proporcion,
        "cuales": sorted(alcanzados),
        "manifiestos_modificados": len(manifiestos),
    }