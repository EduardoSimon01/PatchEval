"""
Eficacia: fiabilidad de la correccion.

Una correccion es fiable si resuelve la vulnerabilidad sin necesitar parches posteriores que la complementen. La forma de validar esto
son las confirmaciones de cambio posteriores que vuelven a modificar las mismas ubicaciones que habia tocado la correccion original.

Rastrear el archivo completo no sirve porque si es un proyecto activo cualquier archivo recibe
modificaciones constantes que no tienen nada que ver con la vulnerabilidad. 

Por eso el rastreo va sobre los rangos de lineas que la correccion dejo, apoyandose en el seguimiento de rangos de git, que sigue esas lineas aunque
se desplacen dentro del archivo.

Sobre ese conjunto se aplican dos filtros declarados:

1. Una ventana temporal porque un parche que vuelve a una correccion llega cerca de ella. Un cambio sobre las mismas lineas mucho tiempo despues es
   evolucion del sistema, no evidencia de que la correccion quedo incompleta.

2. Un vocabulario de incompletitud. No basta con que el mensaje diga fix, porque en estos proyectos la mayoria de los commits lo dice. Se buscan
   terminos que senalen que algo quedo pendiente o que se arregló.

Los dos filtros son decisiones del investigador y se declaran como tales. El conteo sin filtrar tambien se reporta, de modo que el lector pueda ver
cuanto depende o no el resultado de ese criterio.

Lo que esto hace es una salida es un candidato que hay que confirmar a mano, no un veredicto. El filtro lexico puede producir
falsos positivos cuando un cambio posterior sin relacion con la vulnerabilidad toca las mismas lineas y su mensaje usa una de las palabras buscadas.
"""

import re
from datetime import datetime, timezone


# Ventana en dias dentro de la cual un cambio posterior sobre las mismas lineas se considera candidato. 90 es decision del investigador y por eso
# viaja en la salida y quien no este de acuerdo puede cambiarla y volver a medir.
VENTANA_DIAS = 90

# Vocabulario de incompletitud. No incluye "fix" a secas porque en los proyectos evaluados ese termino aparece en la mayoria de los
# mensajes y no nos aporta nada. Lo que se busca son palabras que digan que algo quedo pendiente. Esta lista tambien es decision del investigador
# se puede cambiar si se considera necesario. 
PATRONES_INCOMPLETITUD = (
    r"incomplete",
    r"\bbypass",
    r"regression",
    r"\brevert",
    r"follow[\s-]?up",
    r"not (?:fully |completely )?(?:fixed|patched|addressed)",
    r"still (?:vulnerable|exploitable|possible|fails)",
    r"missed",
    r"insufficient",
    r"partial(?:ly)? fix",
    r"re-?fix",
    r"additional (?:fix|patch|check)",
)

_RE_INCOMPLETITUD = re.compile("|".join(PATRONES_INCOMPLETITUD), re.IGNORECASE)

# Un identificador de vulnerabilidad en el mensaje tambien es señal pero mas debil que las palabras de arriba, igual 
# sigue siendo relevante porque dice que ese commit posterior tambien trataba un tema de seguridad.
_RE_IDENTIFICADOR = re.compile(r"CVE-\d{4}-\d{4,7}|GHSA-[\w]{4}-[\w]{4}-[\w]{4}", re.IGNORECASE)

# Archivos donde rastrear linea por linea no nos dicen nada: dependencias declaradas, codigo generado y archivos de bloqueo. 
# Un cambio en go.sum por ejemplo no habla de la correccion sino de que alguien actualizo una biblioteca.
_RE_IGNORAR = re.compile(
    r"(go\.sum|go\.mod|package-lock\.json|yarn\.lock|Cargo\.lock|"
    r"\.pb\.go$|\.pb\.gw\.go$|_generated\.go$|zz_generated|"
    r"\.min\.(js|css)$|swagger\.json$)", re.IGNORECASE)


def _rastreable(ruta):
    return not _RE_IGNORAR.search(ruta)


def _senal(mensaje):
    """
    Clasifica la intencion del mensaje de un commit posterior.

    Devuelve 'incompletitud' si declara que algo quedo pendiente, 'identificador' si menciona una vulnerabilidad registrada, o None si no hay nada.
    """
    if _RE_INCOMPLETITUD.search(mensaje):
        return "incompletitud"
    if _RE_IDENTIFICADOR.search(mensaje):
        return "identificador"
    return None


def medir(repo, correccion, limite_archivos=25, ventana_dias=VENTANA_DIAS):
    """
    Busca parches complementarios sobre las lineas que dejo la correccion.

    Se ven dos conteos. El primero es cuantos cambios posteriores tocaron esas mismas lineas asi sin filtrar y el segundo es cuantos de esos
    declaran que la correccion original quedo incompleta es decir que la fiabilidad se juzga sobre el segundo, 
    pero el primero se publica para que se vea cuanto se esta filtrando.
    """
    rutas = [a.ruta for a in correccion.archivos if _rastreable(a.ruta)][:limite_archivos]

    fecha_base = datetime.fromisoformat(correccion.fecha)
    corte = fecha_base.timestamp()
    limite = corte + ventana_dias * 86400

    # Se indexa por sha porque un mismo comit posterior puede aparecer varias veces una vez por cada rango que toca sin esto se cuentan repetidos .
    sobre_las_mismas_lineas = {}

    for ruta in rutas:
        for inicio, fin in repo.rangos_modificados(correccion, ruta):
            for sha, marca, asunto in repo.commits_sobre_rango(ruta, inicio, fin):
                # marca <= corte descarta los anteriores comits a la correccion porque lo devuelve git log y el rastreo va hacia atras
                # en la historia entonces aqui lo que interesa es lo que vino despues.
                if marca <= corte or marca > limite:
                    continue
                if sha == correccion.sha:
                    continue

                registro = sobre_las_mismas_lineas.setdefault(sha, {
                    "sha": sha[:10],
                    "mensaje": asunto[:110],
                    "fecha": datetime.fromtimestamp(marca, tz=timezone.utc).isoformat(),
                    "dias_despues": int((marca - corte) // 86400),
                    "archivos_compartidos": [],
                    "senal": _senal(asunto),
                })
                if ruta not in registro["archivos_compartidos"]:
                    registro["archivos_compartidos"].append(ruta)

    todos = sorted(sobre_las_mismas_lineas.values(), key=lambda x: x["dias_despues"])
    complementarios = [c for c in todos if c["senal"] is not None]

    return {
        "archivos_rastreados": len(rutas),
        "cambios_sobre_las_mismas_lineas": len(todos),
        "parches_complementarios": len(complementarios),
        # es fiable recordar que es en el sentido de "no se encontraron indicios", no en el sentido de "esta probado que la correccion fue suficiente".
        "es_fiable": len(complementarios) == 0,
        "dias_hasta_el_primero": complementarios[0]["dias_despues"] if complementarios else None,
        "ventana_dias": ventana_dias,
        "candidatos": complementarios[:8],
        "contexto_sin_filtrar": todos[:5],
    }