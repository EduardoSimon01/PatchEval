"""
Acceso al repositorio.

Aqui es donde conseguimos: la correccion y el commit que la antecede. Este modulo es el unico que habla con git los demas modulos de metricas reciben 
ya resueltos los dos y no vuelven a tocar el repositorio.

Esa separacion no es decorativa. Si despues se cambia de GitPython a otra cosa, o si decido leer los repos desde un volcado en lugar de clonarlos, solo se
reescribe este archivo.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
import tempfile

import git


# Cabecera de fragmento del diff unificado: @@ -a,b +c,d @@
# El grupo 1 captura 'c' (linea donde arranca el fragmento en la version nueva) y el grupo 2 captura 'd' (cuantas lineas abarca).

# Solo interesa el lado derecho, o sea las lineas que quedaron DESPUES de la correccion. El lado izquierdo apunta a lineas que ya no existen, asi
# que no sirve para rastrear nada hacia adelante.
_CABECERA = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# Los directorios de primer nivel que no son servicios del sistema. Se usan para descontarlos al calcular la dispersion del cambio.
#
# La lista sale de mirar como organizan sus repos los proyectos del corpus si se agrega un proyecto nuevo conviene revisarla antes de confiar en la
# dispersion que reporte.
_NO_SON_SERVICIOS = {
    ".github", ".git", "docs", "doc", "hack", "vendor",
    "third_party", "test", "tests", "examples", "site",
}


@dataclass
class ArchivoTocado:
    """Un archivo que la correccion modifico, con su recuento de lineas."""
    ruta: str
    lineas_agregadas: int
    lineas_eliminadas: int
    tipo_cambio: str   # A = agregado, M = modificado, D = eliminado, R = renombrado


@dataclass
class Correccion:
    """
    Una correccion con el contexto minimo para poder medirla.

    Es el objeto que viaja a los modulos de metricas. Lleva los dos extremos de la comparacion (sha y sha padre) y la lista de archivos afectados,
    que es lo que cada metrica usa para decidir sobre cuales trabaja.
    """
    sha: str
    sha_padre: str
    mensaje: str
    fecha: str
    autor: str
    archivos: list = field(default_factory=list)
    # se usa field(default_factory=list) y no "= []" porque un valor mutable por defecto se comparte entre todas las instancias de la clase. Es un error  de Python 
    # y aqui significaria que dos correcciones distintas terminen apuntando a la misma lista de archivos.

    @property
    def total_agregadas(self):
        #Lineas agregadas en todos los archivos de la correccion.
        return sum(a.lineas_agregadas for a in self.archivos)

    @property
    def total_eliminadas(self):
        # Lineas eliminadas en todos los archivos de la correccion.
        return sum(a.lineas_eliminadas for a in self.archivos)


class Repositorio:
    # Envuelve un repositorio git y expone solo lo que el marco va a necesita leer.

    def __init__(self, ruta_o_url, directorio_trabajo=None):
        """
        Abre un repositorio existente o clona uno nuevo.

        Acepta las dos formas: durante el desarrollo del trabajo se trabaja sobre clones locales, que es mas rapido 
        y para se reproduzca la evaluacion con pasarle la URL basta.
        """
        self._temporal = None

        # El prefijo decide si hay que clonar o si ya esta en el disco.
        if str(ruta_o_url).startswith(("http://", "https://", "git@")):
            # Si no se indica donde dejarlo, se usa un directorio temporal del sistema. Queda vivo mientras dure el proceso.
            destino = directorio_trabajo or tempfile.mkdtemp(prefix="patcheval_")
            self._temporal = destino

            # filter="blob:none" baja la historia completa pero sin el contenido de los archivossino serpia mucho texto cada blob se trae cuando se pide.
            # El precio es que cada lectura de contenido necesita red, asi que para corridas grandes esmejor clonar a mano una sola vez.
            self.repo = git.Repo.clone_from(ruta_o_url, destino, filter="blob:none")
        else:
            # GitPython sube por el arbol de directorios hasta encontrar .git asi logra aceptar una ruta interna del repo y no solo la raiz. Si
            # algun dia se quiere evaluar un submodulo, ojo: devuelve el padre.
            self.repo = git.Repo(ruta_o_url)

        # working_dir es la raiz del repositorio ya resuelta por GitPython.
        self.ruta = Path(self.repo.working_dir)

    # ------------------------------------------------------------------
    def cargar_correccion(self, sha):
        """
        Resuelve la correccion y el detalle de los archivos que toco.

        Este es el mero punto de entrada: a partir de aqui se conoce el par de versiones contra el que trabajan las metricas.
        """
        # commit() resuelve cualquier referencia que git entienda: sha completo, sha abreviado, etiqueta, HEAD~3. La traduccion la hace git.
        commit = self.repo.commit(sha)

        if not commit.parents:
            # El commit raiz no tiene contra que compararse. No deberia aparecer en el corpus, pero si se introduce el sha inicial de un
            # repo se falla aqui y se evita devolver metricas sin sentido.
            raise ValueError("el commit no tiene padre, no hay diferencia que medir")

        # parents[0] es el primer padre. En un commit normal es el unico pero en una fusion es la rama principal, de modo que la diferencia abarca
        # todo el conjunto que la fusion incorporo. Eso es justo lo que s quiere cuando una correccion de seguridad entra por esa via pero hay que tener algo 
        # presente y es que la medicion incluye pruebas y ajustes de estilo que vinieron en el mismo paquete.
        padre = commit.parents[0]

        # Primera pasada: que archivos cambiaron. ---------------------------------------------------------------------------------------------------------------------
        archivos = []
        for d in padre.diff(commit, create_patch=False):
            # create_patch=False evita materializar el texto del parche. Aqui solo hace falta saber que archivos cambiaron el contenido se
            # pide despues y solo de los que cada metrica necesita.

            # b_path es la ruta en la version nueva y a_path la de la vieja.
            # Cuando un archivo se elimina, b_path viene en None, de ahi el respaldo con a_path.
            ruta = d.b_path or d.a_path

            archivos.append(ArchivoTocado(
                ruta=ruta,
                lineas_agregadas=0,     # se completan en la segunda pasada
                lineas_eliminadas=0,
                tipo_cambio=d.change_type,
            ))

        # Segunda pasada: cuantas lineas cambiaron en cada archivo.
        
        # El conteo se pide aparte porque el objeto diff no lo trae. commit.stats cuenta contra el primer padre, que es
        # la misma referencia que se uso arriba, asi que los dos recorridos hablan del mismo cambio.
        estadisticas = commit.stats.files
        for a in archivos:
            datos = estadisticas.get(a.ruta)
            if datos:
                # El get() puede no encontrar la ruta cuando git reporta un renombrado con una notacion distinta a la del diff. En ese
                # caso el archivo queda en cero y no se cae la corrida.
                a.lineas_agregadas = datos.get("insertions", 0)
                a.lineas_eliminadas = datos.get("deletions", 0)

        return Correccion(
            sha=commit.hexsha,
            sha_padre=padre.hexsha,
            # Solo la primera linea del mensaje: es el asunto del commit. El cuerpo no importa.
            mensaje=commit.message.strip().split("\n")[0],
            fecha=commit.committed_datetime.isoformat(),
            autor=str(commit.author),
            archivos=archivos,
        )

    # ------------------------------------------------------------------
    def contenido(self, sha, ruta):
        """
        Contenido de un archivo en un punto concreto de la historia.

        Lo usan las metricas para obtener las dos versiones del mismo archivo y compararlas y devuelve None cuando el archivo no existe en ese punto.
        """
        try:
            # El operador / navega dentro de el commit como si fuera una ruta.
            blob = self.repo.commit(sha).tree / ruta
        except (KeyError, ValueError):
            # KeyError: el archivo no existe en ese arbol (cuando la correccion creo el archivo y se pide la version anterior).
            # ValueError: la ruta apunta a un directorio.
            return None

        # errors="replace" porque hay repos con archivos malcodificados. Sin esto, un solo archivo mal codificado revienta la
        # corrida entera y se pierden las 25 correcciones que ya iban bien.
        return blob.data_stream.read().decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    def rangos_modificados(self, correccion, ruta, maximo=12):
        """
        Rangos de lineas que la correccion dejo en la version posterior.

        Salen de las cabeceras del diff. Son el punto de partida para preguntar despues si alguien volvio sobre esas mismas lineas, que es lo que mide la fiabilidad.

        El tope de 12 rangos por archivo evita que una correccion enorme aviente cientos de rastreos, cada uno con su propia llamada a git.
        """
        try:
            # unified=0 pide cero lineas de contexto. Con el contexto por defecto (3 lineas) los rangos salen con cosas innesesarias.
            salida = self.repo.git.diff(
                correccion.sha_padre, correccion.sha, "--unified=0", "--", ruta)
        except git.GitCommandError:
            # El archivo pudo haber sido eliminado o renombrado de una forma que git no resuelve en este contexto. Sin rangos que rastrear.
            return []

        rangos = []
        for linea in salida.splitlines():
            # El diff trae encabezados, lineas de contenido y cabeceras defragmento éro solo interesan las ultimas.
            if not linea.startswith("@@"):
                continue

            m = _CABECERA.match(linea)
            if not m:
                continue

            inicio = int(m.group(1))

            # Cuando el fragmento afecta una sola linea, git omite la coma y el largo. 
            largo = int(m.group(2)) if m.group(2) is not None else 1

            if largo == 0:
                # Fragmento que solo elimina. No deja lineas que rastrear.
                continue

            # El rango es inclusivo en los dos extremos, que es como lo espera git log -L.
            rangos.append((inicio, inicio + largo - 1))

            if len(rangos) >= maximo:
                break

        return rangos

    def commits_sobre_rango(self, ruta, inicio, fin, desde=None):
        """
        Commits que a lo largo de la historia tocaron ese rango de lineas.

        Se apoya en el rastreo de rangos de git (log -L), que sigue las lineas aunque se desplacen dentro del archivo o se muevan a otro. Es la pieza
        que hace que la metrica de fiabilidad mire ubicaciones y no archivos completos.

        El parametro desde acota la busqueda a partir de una fecha sin el, git recorre la historia completa del rango hacia atras, que puede ser de muchisimo tiempo
        cuando lo unico que interesa es lo que vino DESPUES de la correccion.

        Devuelve tuplas de (sha, marca de tiempo, asunto) de la mas reciente a la mas antigua.
        """
        try:
            # -s suprime el parche. Sin eso, log -L imprime el diff completo de cada commit y la salida se vuelve gradisima.
            # El separador \x1f es el de unidad de ASCII no aparece en mensajes de commit.
            # %H = sha completo, %ct = fecha como marca de tiempo, %s = asunto.
            args = [f"-L{inicio},{fin}:{ruta}", "--format=%H%x1f%ct%x1f%s", "-s"]
            if desde:
                args.insert(0, f"--since={desde}")
            salida = self.repo.git.log(*args)
        except git.GitCommandError:
            # Falla cuando el archivo no existe en la HEAD por ejemplo si se renombro despues de la correccion. 
            return []

        encontrados = []
        for linea in salida.splitlines():
            partes = linea.split("\x1f")
            # log -L intercala lineas propias del formato de rangos, asi que se filtra por forma tres campos y un sha de 40 caracteres.
            if len(partes) == 3 and len(partes[0]) == 40:
                encontrados.append((partes[0], int(partes[1]), partes[2]))

        return encontrados

    # ------------------------------------------------------------------
    def servicios(self, sha=None):
        """
        Aproximacion de los servicios del sistema.

        Se toman los directorios de primer nivel, descontando los que por convencion no contienen servicios. Es una aproximacion y esta
        declarada como limitacion: un proyecto que no organice asi sus servicios hace que la dispersion pierda precision.

        El parametro sha importa: se cuenta el sistema tal como estaba en el momento de la correccion, no como esta hoy. Un repositorio pudo haber
        ganado o perdido servicios desde entonces, y eso cambiaria el denominador de la dispersion.
        """
        ref = sha or self.repo.head.commit.hexsha
        arbol = self.repo.commit(ref).tree

        # .trees son los subdirectorios y .blobs serian los archivos sueltos de la raiz que no nos interesan.
        return [t.name for t in arbol.trees if t.name not in _NO_SON_SERVICIOS]