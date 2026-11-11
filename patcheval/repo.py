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
from datetime import datetime

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
    "third_party", "test", "tests", "testing", "testdata",
    "examples", "site", "scripts", "script", "tools", "contrib",
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

        # El historial se pide una sola vez por repositorio y se guarda aqui.
        self._commits = None

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

    def commits_sobre_rango(self, ruta, inicio, fin):
        """
        Commits que a lo largo de la historia tocaron ese rango de lineas.

        Se apoya en el rastreo de rangos de git (log -L), que sigue las lineas aunque se desplacen dentro del archivo o se muevan a otro. Es la pieza
        que hace que la metrica de fiabilidad mire ubicaciones y no archivos completos.

        No se le pasa --since aunque acotar el recorrido seria mas rapido. Git no usa esa bandera para recortar la lista al final sino para dejar de
        recorrer la historia cuando cree que ya se paso de fecha, y esa decision depende de las fechas de los commits y de las caches que git
        regenera por su cuenta osea que puede dejar commits afuera, y puede dejar distintos de una corrida a otra esto lo comprobamos sobre la
        correccion 8b2f081ded el rastreo acotado perdia un commit del mismo dia que si era candidato y el resultado cambio entre dos corridas sin
        que cambiara ni el repositorio ni el codigo. El recorte por fecha se hace en el modulo de fiabilidad, donde se compara contra la marca de
        tiempo exacta.

        Devuelve tuplas de (sha, marca de tiempo, asunto) de la mas reciente a la mas antigua.
        """
        try:
            # -s suprime el parche. Sin eso, log -L imprime el diff completo de cada commit y la salida se vuelve gradisima.
            # El separador \x1f es el de unidad de ASCII no aparece en mensajes de commit.
            # %H = sha completo, %ct = fecha como marca de tiempo, %s = asunto.
            salida = self.repo.git.log(
                f"-L{inicio},{fin}:{ruta}", "--format=%H%x1f%ct%x1f%s", "-s")
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
    def servicios(self, sha=None, raiz=""):
        """
        Aproximacion de los servicios del sistema.

        Se toman los directorios de primer nivel descontando los que por convencion no contienen servicios con eso se tiene una aproximacion y esta
        declarada como limitacion porque si usa con un proyecto que no organice asi sus servicios hace que la dispersion pierda precision.

        El parametro raiz existe porque no todos los proyectos agrupan igual eb el caso de Argo CD pone sus servicios en la raiz del repositorio pero Harbor los
        mete todos bajo una carpeta llamada src y sin esto la dispersion de Harbor daria siempre uno sobre cuatro o algo asi lo cual no dice nada entonces la raiz 
        se declara por proyecto en el archivo del corpus y queda registrada con el resultado.

        El parametro sha importa ya que se cuenta el sistema tal como estaba en el momento de la correccion no como esta hoy porque un repositorio pudo haber
        ganado o perdido servicios desde entonces, y eso cambiaria el denominador de la dispersion.
        """
        ref = sha or self.sha_actual()
        arbol = self.repo.commit(ref).tree

        if raiz:
            try:
                arbol = arbol / raiz
            except KeyError:
                # La carpeta declarada no existia todavia en ese punto de la historia entonces es mejor devolver vacio que medir contra la raiz equivocada.
                return []

        # .trees son los subdirectorios y .blobs serian los archivos sueltos de la raiz que no nos interesan.
        # Los que empiezan con punto son configuracion o herramientas y nunca son servicios del sistema antes estaban uno por uno en la lista
        # pero cada proyecto trae los suyos y nombrarlos todos seria mucho trabajo de por gusto.
        return [t.name for t in arbol.trees if not t.name.startswith(".") and t.name not in _NO_SON_SERVICIOS]
    
    def sha_actual(self):
        """
        Identificador del estado del repositorio en este momento.

        Hace falta porque la fiabilidad mira hacia adelante entonces cuenta lo que vino despues de la correccion, y eso sigue creciendo mientras el proyecto
        viva por eso las tres metricas de costo comparan dos versiones fijas y van a dar lo mismo siempre pero la de fiabilidad medida hoy puede no coincidir
        con la medida el año entrante poe ejemplo entonces huardar contra que estado se midio es lo unico que vuelve reproducible ese numero.
        """
        return self.repo.head.commit.hexsha

    def todos_los_commits(self):
        """
        Todos los commits de la rama actual, sin fusiones.

        Se piden de una sola vez y se guardan porque el recorte por fecha se hace despues en Python antes se le pasaba --since y --until a git pero esas banderas 
        no recortan la lista al final sino que le dicen a git que deje de recorrer cuando cree que ya se paso de fecha y esa decision depende de las caches internas 
        que git regenera por su cuenta esto hacia que la linea base saliera distinta entre corridas sin que cambiara nada y como la linea base es la mitad 
        de cada par del contraste los valores de p se movian con ella

        Pedir la historia completa de un proyecto grande son unas decenas de miles de lineas entonces se hace una vez y se reusa.

        Devuelve tuplas de (sha, marca de tiempo, autor, asunto).
        """
        if self._commits is not None:
            return self._commits

        try:
            salida = self.repo.git.log("--no-merges", "--format=%H%x1f%ct%x1f%an%x1f%s")
        except git.GitCommandError:
            self._commits = []
            return self._commits

        encontrados = []
        for linea in salida.splitlines():
            partes = linea.split("\x1f")
            if len(partes) == 4 and len(partes[0]) == 40:
                encontrados.append((partes[0], int(partes[1]), partes[2], partes[3]))

        self._commits = encontrados
        return self._commits

    def commits_ordinarios(self, desde, hasta, maximo=800):
        """
        Commits de la rama actual entre dos fechas, sin fusiones.

        Es la materia prima de la linea base los cambios ordinarios contra los que se contrastan las correcciones de seguridad en este caso las fusiones se
        excluyen porque su diferencia abarca todo lo que la rama incorporo de modo que no son un cambio sino un paquete de cambios y medirlas como
        si fueran uno solo inflaria la linea base.

        El recorte por fecha se hace aqui y no en git.

        Devuelve tuplas de (sha, marca de tiempo, autor, asunto), de la mas reciente a la mas antigua.
        """
        ini = datetime.fromisoformat(desde).timestamp()
        fin = datetime.fromisoformat(hasta).timestamp()

        dentro = [c for c in self.todos_los_commits() if ini <= c[1] <= fin]
        return dentro[:maximo]

    def archivos_de(self, sha):
        """
        Rutas que toco un commit, sin medir nada mas.

        Usamos esto para descartar candidatos de la linea base antes de gastar en medirlos. Un commit que no toca codigo no sirve para contrastar y averiguarlo cargando la correccion entera seria pagar la medicion completa para despues tirarla.
        """
        try:
            salida = self.repo.git.show("--name-only", "--format=", sha)
        except git.GitCommandError:
            return []

        return [l.strip() for l in salida.splitlines() if l.strip()]

    def commits_que_mencionan(self, patrones, maximo=500):
        """
        Commits de la rama actual cuyo mensaje coincide con alguno de los patrones.

        A diferencia de commits_ordinarios aqui se devuelve tambien el cuerpo del mensaje y no solo el asunto porque los proyectos muchas veces ponen el
        identificador del aviso en el cuerpo y no en la primera linea.

        El cuerpo trae saltos de linea asi que los registros se separan con el caracter de separacion de registro de ASCII en lugar de confiar en
        las lineas que es lo que hice en el resto de los metodos.

        Devuelve tuplas de (sha, marca de tiempo, autor, asunto, cuerpo).
        """
        args = ["--no-merges", "-i", f"--max-count={maximo}",
                "--format=%H%x1f%ct%x1f%an%x1f%s%x1f%b%x1e"]
        for p in patrones:
            args.append(f"--grep={p}")

        try:
            salida = self.repo.git.log(*args)
        except git.GitCommandError:
            return []

        encontrados = []
        for registro in salida.split("\x1e"):
            partes = registro.strip("\n").split("\x1f")
            if len(partes) == 5 and len(partes[0]) == 40:
                encontrados.append((partes[0], int(partes[1]), partes[2], partes[3], partes[4]))

        return encontrados