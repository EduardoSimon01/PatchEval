"""
La complejidad ciclomatica.

La complejidad se mide sobre las funciones que la correccion toco, en la version anterior y en la de prueba, y se reporta la diferencia.
Un valor con mas dice que la correccion dejo el codigo con mas caminos de los que tenia antes.
"""

import os
import tempfile
from pathlib import PurePosixPath

import lizard


# Lenguajes que lizard sabe analizar y que aparecen en los proyectos del corpus. Si se agrega un proyecto en otro lenguaje hay que revisar que lizard lo soporte,
# porque si no lo soporta el archivo simplemente no jala y la medicion no avisa.
EXTENSIONES = {".py", ".go", ".java", ".js", ".ts", ".c", ".cc", ".cpp",".h", ".hpp", ".rb", ".php", ".cs", ".rs", ".swift", ".kt"}


def es_codigo(ruta):
    # PurePosixPath y no Path porque las rutas vienen de git, que siempre usa / aunque estemos en Windows
    return PurePosixPath(ruta).suffix.lower() in EXTENSIONES


def _analizar(texto, nombre):
    """
    Corre lizard sobre un contenido que esta en memoria.

    lizard solo sabe leer archivos del disco, no cadenas, asi que hay que escribir el contenido a un temporal o tener la carpeta en disco. 
     lizard decide queHay que dejar el sufijo porque lizard sabe el lenguaje por la extension, de modo que si se pierde el .algo lo tratamos 
     como texto plano y devuelve cero funciones sin quejarse.
    """
    if texto is None:
        return None

    sufijo = PurePosixPath(nombre).suffix or ".txt"
    tmp = tempfile.NamedTemporaryFile("w", suffix=sufijo, delete=False, encoding="utf-8", errors="replace")
    try:
        tmp.write(texto)
        tmp.close()   # hay que cerrarlo antes de que lizard lo abra, sino en da error de archivo en uso
        return lizard.analyze_file(tmp.name)
    finally:
        # El finally se asegura de borrar el temporal aunque lizard pete. Sin esto se van acumulando archivo en el disco, uno por cada
        # archivo de cada correccion.
        os.unlink(tmp.name)

def medir(repo, correccion):
    """
    Compara la complejidad de los archivos de codigo antes y despues de la correccion.

    Solo se miran los archivos que la correccion toco. El resto no entra porque lo que queremos saber es que dejo este cambio, no que tan complejo
    es el repo.
    """
    archivos = [a.ruta for a in correccion.archivos if es_codigo(a.ruta)]

    ccn_antes = 0
    ccn_despues = 0
    funciones_antes = 0
    funciones_despues = 0
    por_archivo = []

    for ruta in archivos:
        a = _analizar(repo.contenido(correccion.sha_padre, ruta), ruta)
        d = _analizar(repo.contenido(correccion.sha, ruta), ruta)

        # Si el archivo no existe en uno de los dos lados, analizar devuelve none y ese lado cuenta cero. asi un archivo nuevo tenia
        # cero complejidad antes porque no existía, y uno borrado tiene cero despues porque ya no existe.
        ca = sum(f.cyclomatic_complexity for f in a.function_list) if a else 0
        cd = sum(f.cyclomatic_complexity for f in d.function_list) if d else 0
        na = len(a.function_list) if a else 0
        nd = len(d.function_list) if d else 0

        ccn_antes += ca
        ccn_despues += cd
        funciones_antes += na
        funciones_despues += nd

        # Solo se guarda el detalle de los archivos donde algo importante cambio. Los que la correccion toco pero sin alterar la complejidad (un comentario por ejemplo)
        # no aportan nada al reporte y lo unico que harian es alargarlo.
        if cd != ca:
            por_archivo.append({"archivo": ruta, "ccn_antes": ca, "ccn_despues": cd, "delta": cd - ca})

    # Se ordena por magnitud del cambio sin importar el signo, para que arriba queden los archivos donde mas se movio la cosa.
    por_archivo.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "archivos_codigo": len(archivos),
        "ccn_antes": ccn_antes,
        "ccn_despues": ccn_despues,
        "delta_ccn": ccn_despues - ccn_antes,
        "funciones_antes": funciones_antes,
        "funciones_despues": funciones_despues,
        "delta_funciones": funciones_despues - funciones_antes,
        "detalle": por_archivo[:10],   # se corta en 10 porque una correccion grande puede tocar 50 archivos y el reporte se vuelve ilegible
    }