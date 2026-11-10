"""
Descubrimiento de las correcciones de seguridad de un repositorio.

El corpus no se arma a manoporque si yo escogiera los casos uno por uno, aunque fuera de buena fe, nadie podria distinguir una seleccion honesta de una
acomodada para que los resultados salgan como me conviene, y esa duda sola ya le quita valor a los resultados.

Entonces el criterio se escribe y la herramienta lo aplica una correccion entra al corpus si su mensaje menciona un aviso de seguridad publicado, si no es
una actualizacion automatica de dependencias, si no la firmo una herramienta y si toca por lo menos un archivo de codigo asi cualquiera con el repositorio
clonado corre esto y obtiene la misma lista.

Lo de mirar el mensaje en lugar de ir a buscar los avisos por fuera se hace ya que importa para la trabajo de investigacion y es que el criterio sigue siendo repetible
dentro de cinco años aunque la base de datos de avisos que yo hubiera consultado ya no exista o haya cambiado.

Cuando varios commits mencionan el mismo aviso se toma el mas antiguo porque es el que aplica la correccion y los posteriores no se descartan por ser
sospechosos sino que al contrario son justo lo que la metrica de fiabilidad tiene que encontrar por si sola y sacarlos de la historia seria esconderle a la
herramienta los casos que debe encontrar justamente.
"""

import re

from .repo import Repositorio
from . import baseline

# Esto es lo que se le pide a git que busque son deliberadamente amplios porque aqui conviene traer de mas y filtrar despues.
PATRONES_BUSQUEDA = ("CVE-20", "GHSA-")

# Un commit que menciona muchos avisos a la vez casi nunca es una correccion sino las notas de una version que enumeran todo lo que trae entonces dos es el
# limite porque una correccion si puede cerrar dos avisos emparentados pero siete ya es un inventario y no un arreglo.
MAXIMO_AVISOS = 2

# Esto es lo que corrige una vulnerabilidad de una biblioteca ajena subiendo su version porque aunque el mensaje traiga el CVE no es una correccion del proyecto y
# no hay decision de diseño que medirle sino solo un numero de version que cambio.
PATRONES_DEPENDENCIA = (
    r"upgrad\w*\s+(the\s+)?(indirect\s+)?dep",
    r"\bavoid\s+CVE", r"\bto\s+solve\s+CVE", r"\bfor\s+CVE",
    r"upgrad\w*\s+[\w./@-]+\s+to\s+v?\d",
    r"updat\w*\s+[\w./@-]+\s+to\s+v?\d",
)

_RE_DEPENDENCIA = re.compile("|".join(PATRONES_DEPENDENCIA), re.IGNORECASE)

# Dejamos el identificador ya bien formado para sacarlo del mensaje un GHSA son tres grupos de cuatro y un CVE es el año y un numero de cuatro a siete digitos.
_RE_AVISO = re.compile(
    r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}|CVE-\d{4}-\d{4,7}",
    re.IGNORECASE)


def avisos_en(mensaje):
    """
    Saca los identificadores de aviso que aparecen en un mensaje.

    Se normalizan a mayusculas porque en los mensajes aparecen de las dos formas y si no el mismo aviso contaria como dos.
    """
    return sorted({m.group(0).upper() for m in _RE_AVISO.finditer(mensaje or "")})

def es_dependencia(mensaje):
    """
    Dice si el commit corrige una vulnerabilidad de una biblioteca ajena.

    Va aparte del filtro de actualizaciones automaticas del baseline porque esto no lo escribio un bot sino una persona y el mensaje hasta trae el
    identificador correcto lo que no trae es una correccion del proyecto.
    """
    return bool(_RE_DEPENDENCIA.search(mensaje or ""))


def descubrir(repo):
    """
    Aplica el criterio y devuelve las correcciones elegidas y lo que se descarto.

    Lo descartado se devuelve con el motivo y no se tira porque poder mostrar que se reviso y lo que se quedo afuera es parte de sostener que la seleccion
    no fue a conveniencia.
    """
    candidatos = []
    descartados = []

    for sha, marca, autor, asunto, cuerpo in repo.commits_que_mencionan(PATRONES_BUSQUEDA):
        avisos = avisos_en(f"{asunto}\n{cuerpo}")

        if not avisos:
            # Cayo en la busqueda por algo parecido pero no trae un identificador bien formatedo.
            descartados.append((sha, asunto, "sin identificador de aviso"))
            continue

        if len(avisos) > MAXIMO_AVISOS:
            descartados.append((sha, asunto, f"menciona {len(avisos)} avisos, parecen notas de version"))
            continue

        if es_dependencia(asunto):
            descartados.append((sha, asunto, "corrige una dependencia ajena"))
            continue

        if baseline.es_automatico(asunto) or baseline.es_bot(autor):
            descartados.append((sha, asunto, "actualizacion automatica de dependencias"))
            continue

        if not baseline.toca_codigo(repo, sha):
            # Corrige una cosa de una biblioteca ajena subiendo su version o es documentacion en ninguno de los casos correccion del proyecto que medir y se descarta.
            descartados.append((sha, asunto, "no toca archivos de codigo"))
            continue

        candidatos.append({"sha": sha, "marca": marca, "asunto": asunto, "avisos": avisos})

    # Por cada aviso se guarda el commit mas antiguo que lo menciona.
    por_aviso = {}
    for c in candidatos:
        for aviso in c["avisos"]:
            previo = por_aviso.get(aviso)
            if previo is None or c["marca"] < previo["marca"]:
                por_aviso[aviso] = c

    # Un commit puede corregir dos avisos a la vez y no debe salir dos veces ahora se le anotan solo los avisos que le quedaron asignados y no todos los
    # que menciona por ejemplo si menciona uno que la regla del mas antiguo le dio a otro commit atribuirselo aqui seria contarlo dos veces.
    elegidos = {}
    for aviso, c in por_aviso.items():
        entrada = elegidos.setdefault(c["sha"], {
            "sha": c["sha"], "marca": c["marca"], "asunto": c["asunto"], "avisos": []})
        entrada["avisos"].append(aviso)

    for entrada in elegidos.values():
        entrada["avisos"].sort()

    ordenados = sorted(elegidos.values(), key=lambda c: c["marca"])
    return ordenados, descartados


def descubrir_archivo(ruta, proyecto=""):
    """
    Punto de entrada desde la linea de comandos. Devuelve el codigo de salida.}
    """
    try:
        repo = Repositorio(ruta)
    except Exception as exc:
        print(f"error: no se pudo abrir el repositorio: {exc}")
        return 1

    elegidos, descartados = descubrir(repo)

    print(f"DESCUBRIMIENTO sobre {ruta}")
    print(f"  {len(elegidos)} correcciones elegidas, {len(descartados)} descartadas")

    if descartados:
        print()
        print("  DESCARTADAS")
        for sha, asunto, motivo in descartados:
            print(f"    {sha[:10]} {asunto[:52]:<52} {motivo}")

    print()
    print("  Para pegar en corpus.yaml:")
    print()
    print(f"- proyecto: {proyecto or 'CAMBIAR'}")
    print(f"  ruta: {ruta}")
    print("  linea_base: 3")
    print("  correcciones:")
    for c in elegidos:
        print(f"    - sha: {c['sha']}")
        print(f"      fuente: {' '.join(c['avisos'])}")

    return 0