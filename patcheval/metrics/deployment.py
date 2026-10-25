"""
Impacto de despliegue.

Lo que se mide aqui no es el estado de la configuracion sino los cambios que la correccion
produjo en ella, y se llevan dos conteos: las configuraciones inseguras que la correccion introdujo y las que resolvio.

Las ocho categorias salen del cruce entre la taxonomia de Rahman, la guia de endurecimiento de NSA y CISA y el CIS Kubernetes
Benchmark.
"""

import re
import yaml
from pathlib import PurePosixPath


# Severidad: 3 = alta, 2 = media, 1 = baja. 
CATEGORIAS = {
    "secretos_incrustados":  {"severidad": 3, "etiqueta": "Secretos incrustados"},
    "privilegios_excesivos": {"severidad": 3, "etiqueta": "Privilegios excesivos"},
    "permisos_amplios":      {"severidad": 3, "etiqueta": "Permisos amplios de acceso"},
    "sin_cifrado":           {"severidad": 2, "etiqueta": "Comunicacion sin cifrado"},
    "exposicion_puertos":    {"severidad": 2, "etiqueta": "Exposicion de puertos"},
    "raiz_escribible":       {"severidad": 2, "etiqueta": "Sistema de archivos escribible"},
    "sin_limites_recursos":  {"severidad": 1, "etiqueta": "Ausencia de limites de recursos"},
    "imagen_sin_version":    {"severidad": 1, "etiqueta": "Imagen sin version fija"},
}

# Un valor sensible escrito directamente en el manifiesto. 
# El {6,} del final evita marcar placeholders cortos como el "password: x" que aparece en las plantillas.
PATRON_SECRETO = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key)[ \t]*[:=][ \t]*[\"']?[\w/+=.-]{6,}", re.IGNORECASE)

# Nombres de variable que sugieren que lo que guardan es sensible se pueden añadir masm estas son genericas.
PATRON_NOMBRE_SENSIBLE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)", re.IGNORECASE)

# Dejamos afuera las direcciones locales porque un http hacia localhost no sale de la maquina y no sirve para la metrica.
PATRON_HTTP = re.compile(r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)", re.IGNORECASE)


def es_manifiesto(ruta):
    return PurePosixPath(ruta).suffix.lower() in {".yaml", ".yml"}


def _documentos(texto):
    """
    Carga los documentos YAML de un archivo.

    safe_load_all y no safe_load porque un solo archivo de Kubernetes suele traer varios documentos separados por ---. Con safe_load solo se leeria
    el primero y los demas se perderian.

    Si el archivo no parsea se devuelve vacio en vez de reventar en caso de que pasara.
    """
    try:
        return [d for d in yaml.safe_load_all(texto) if isinstance(d, dict)]
    except yaml.YAMLError:
        return []


def _secretos_en_variables(doc):
    """
    Detecta secretos declarados con el patron name/value de Kubernetes.

    Esto porque en un manifiesto el nombre de la variable y su valor viven en lineas distintas asi:

        env:
        - name: DB_PASSWORD
          value: superclave123

    Ninguna expresion regular sobre el texto agarra esto sin arriesgarse. Aquise recorre la estructura ya parseada y preguntamos por el par completo.

    La distincion clave es value vs valueFrom. Un value trae el dato escrito ahi mismo y un valueFrom apunta a un Secret y es la forma correcta
    """
    encontrados = 0

    def buscar(nodo):
        nonlocal encontrados
        if isinstance(nodo, dict):
            nombre = nodo.get("name")
            if (isinstance(nombre, str)
                    and PATRON_NOMBRE_SENSIBLE.search(nombre)
                    and "value" in nodo
                    and nodo.get("value") not in (None, "")):
                encontrados += 1
            for v in nodo.values():
                buscar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                buscar(v)

    buscar(doc)
    return encontrados


def _recorrer_contenedores(doc):
    """
    Encuentra las definiciones de contenedor dentro de un manifiesto.

    Buscamos en profundidad porque los contenedores no estan siempre al mismo nivel.
    """
    encontrados = []

    def buscar(nodo):
        if isinstance(nodo, dict):
            for clave in ("containers", "initContainers"):
                valor = nodo.get(clave)
                if isinstance(valor, list):
                    encontrados.extend(c for c in valor if isinstance(c, dict))
            for v in nodo.values():
                buscar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                buscar(v)

    buscar(doc)
    return encontrados


def detectar(texto):
    """
    Detecta configuraciones inseguras en el contenido de un manifiesto.

    Devuelve el conteo por categoria y se cuentan ocurrencias y no archivos, porque un mismo archivo se puede declarar varios contenedores y cada uno
    con su propio problema.
    """
    hallazgos = {k: 0 for k in CATEGORIAS}
    if not texto:
        return hallazgos

    # Las dos primeras reglas trabajan sobre el texto plano, sin parsear. Se hace a proposito porque un secreto 
    # puede estar en un comentario o en una seccion que el parser puede descartar, y alli igual esta expuesto.
    hallazgos["secretos_incrustados"] += len(PATRON_SECRETO.findall(texto))
    hallazgos["sin_cifrado"] += len(PATRON_HTTP.findall(texto))

    # El resto necesita entender la estructura, no alcanza con buscar palabras.
    for doc in _documentos(texto):
        hallazgos["secretos_incrustados"] += _secretos_en_variables(doc)

        # Damos permisos amplios en reglas de control de acceso. Usamos * en verbos o recursos porque significa "todo sobre todo", que es lo contrario del
        # principio de menor privilegio.
        if doc.get("kind") in ("Role", "ClusterRole"):
            for regla in doc.get("rules") or []:
                if not isinstance(regla, dict):
                    continue
                verbos = regla.get("verbs") or []
                recursos = regla.get("resources") or []
                if "*" in verbos or "*" in recursos:
                    hallazgos["permisos_amplios"] += 1

        # Servicios expuestos hacia afuera del cluster. ClusterIP queda adentro y no se marca y NodePort y LoadBalancer abren el servicio al exterior.
        if doc.get("kind") == "Service":
            tipo = (doc.get("spec") or {}).get("type")
            if tipo in ("NodePort", "LoadBalancer"):
                hallazgos["exposicion_puertos"] += 1

        for c in _recorrer_contenedores(doc):
            ctx = c.get("securityContext") or {}

            # Tres formas distintas de terminar con mas privilegios de los necesarios. Se cuentan por separado aunque caigan en la misma categoria 
            # porque un contenedor puede tener las tres y cada una la contamos como un problema.
            if ctx.get("privileged") is True:
                hallazgos["privilegios_excesivos"] += 1
            if ctx.get("runAsNonRoot") is False or ctx.get("runAsUser") == 0:
                hallazgos["privilegios_excesivos"] += 1
            if ctx.get("allowPrivilegeEscalation") is True:
                hallazgos["privilegios_excesivos"] += 1

            # El is not True es la ausencia del campo porque tambien cuenta. No es lo
            # mismo que preguntar "is False", que solo agarraria los que lo declaran explicitamente.
            if ctx.get("readOnlyRootFilesystem") is not True:
                hallazgos["raiz_escribible"] += 1

            recursos = c.get("resources") or {}
            if not recursos.get("limits"):
                hallazgos["sin_limites_recursos"] += 1

            imagen = c.get("image")
            if isinstance(imagen, str):
                # Una imagen fijada por el digest siempre apunta al mismo contenido y no se puede mover. Sin eso, la etiqueta latest o la
                # ausencia de etiqueta significan que despues se puede correr algo distinto de lo que se probo.
                if "@sha256:" not in imagen:
                    etiqueta = imagen.rsplit(":", 1)[-1] if ":" in imagen else "latest"
                    if etiqueta in ("latest", imagen):
                        hallazgos["imagen_sin_version"] += 1

    return hallazgos


def ponderar(hallazgos):
    """
    Suma los hallazgos multiplicados por la severidad de su categoria.
    """
    return sum(n * CATEGORIAS[k]["severidad"] for k, n in hallazgos.items())


def medir(repo, correccion):
    """
    Compara los manifiestos antes y despues de la correccion.

    Se reportan por separado las configuraciones introducidas y las resueltas, y no se restan entre si  una
    correccion puede meter dos problemas al repo mientras resuelve otros cuatro, y un saldo de "menos dos" esconderia que metio dos cosas nuevas. Los dos
    movimientos son distintos y el que lee tiene que verlos aparte y valorar.
    """
    manifiestos = [a.ruta for a in correccion.archivos if es_manifiesto(a.ruta)]

    antes_total = {k: 0 for k in CATEGORIAS}
    despues_total = {k: 0 for k in CATEGORIAS}

    detalle = []
    for ruta in manifiestos:
        antes = detectar(repo.contenido(correccion.sha_padre, ruta))
        despues = detectar(repo.contenido(correccion.sha, ruta))

        for k in CATEGORIAS:
            antes_total[k] += antes[k]
            despues_total[k] += despues[k]

        if antes != despues:
            detalle.append({"archivo": ruta, "antes": antes, "despues": despues})

    # El max es el que mantiene los dos conteos independientes y cada categoria aporta a introducidas o a resueltas.
    introducidas = {k: max(0, despues_total[k] - antes_total[k]) for k in CATEGORIAS}
    resueltas = {k: max(0, antes_total[k] - despues_total[k]) for k in CATEGORIAS}

    return {
        "manifiestos_analizados": len(manifiestos),
        # Se filtran las categorias en cero para que el reporte muestre solo lo que se movio.
        "introducidas": {k: v for k, v in introducidas.items() if v},
        "resueltas": {k: v for k, v in resueltas.items() if v},
        "total_introducidas": sum(introducidas.values()),
        "total_resueltas": sum(resueltas.values()),
        "ponderado_introducidas": ponderar(introducidas),
        "ponderado_resueltas": ponderar(resueltas),
        "detalle": detalle,
    }