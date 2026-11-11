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

def servicio_de(ruta, conocidos, raiz=""):
    """
    Dice a que servicio pertenece un archivo o None si no pertenece a ninguno.

    Sale aparte de medir para poder probarla sin repositorio que es donde estan los casos raros archivos sueltos en la raiz o  archivos fuera de la
    carpeta declarada o carpetas que no estan en la lista de servicios, etc.
    """
    partes = PurePosixPath(ruta).parts

    if raiz:
        tramos = PurePosixPath(raiz).parts
        # Lo que cae fuera de la carpeta declarada decimos que no pertenece a ningun servicio por ejemplo en Harbor la documentacion vive fuera de src.
        if partes[:len(tramos)] != tramos:
            return None
        partes = partes[len(tramos):]

    # Un archivo suelto sin carpeta propiano cuenta como servicio.
    if len(partes) > 1 and partes[0] in conocidos:
        return partes[0]

    return None


def medir(repo, correccion, raiz=""):
    """
    Calcula la proporcion de servicios que la correccion alcanzo.

    Los servicios se aproximan por los directorios de primer nivel de la carpeta declarada con todo lo que eso implica y que ya esta declarado como
    limitacion.
    """
    # El total se pide en el punto de la correccion y no en la HEAD porque si el proyecto gano servicios despues usar la HEAD inflaria el denominador
    # y haria que pareciera mas contenida de lo que fue una correccion vieja.
    todos = repo.servicios(correccion.sha, raiz)

    alcanzados = set()
    for a in correccion.archivos:
        s = servicio_de(a.ruta, todos, raiz)
        if s:
            alcanzados.add(s)

    total = len(todos)
    # El max(total, 1) evita dividir entre cero esto pasa con repos que tienen todo en la raiz es raro pero puede pasar.
    proporcion = round(len(alcanzados) / max(total, 1), 4)

    manifiestos = [a.ruta for a in correccion.archivos if es_manifiesto(a.ruta)]

    return {
        "servicios_totales": total,
        "servicios_afectados": len(alcanzados),
        "proporcion": proporcion,
        "cuales": sorted(alcanzados),
        "manifiestos_modificados": len(manifiestos),
        "raiz_servicios": raiz,
    }