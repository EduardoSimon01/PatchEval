"""
Pruebas de la metrica de fiabilidad.

La parte lexica se prueba sola llamando a la funcion que clasifica el mensaje. La parte que de verdad importa, que es el rastreo de lineas, no se
puede probar sin un repositorio entonces hay que armar uno.

Estas pruebas lo que hacen es que construyen un repositorio de git en miniatura, con commits hechos a proposito, y comprueban que el rastreo distingue entre un
cambio posterior sobre las mismas lineas y uno sobre otras lineas del mismo archivo. 
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from patcheval import Repositorio
from patcheval.metrics import reliability


class PruebaVocabulario(unittest.TestCase):
    """
    La clasificacion del mensaje es una funcion pura, no necesita repositorio.
    """

    def test_palabras_de_incompletitud(self):
        for mensaje in ("fix: incomplete validation",
                        "fix: auth bypass still possible",
                        "revert the previous patch",
                        "follow-up to the security fix",
                        "fix: partial fix for the path check"):
            self.assertEqual(reliability._senal(mensaje), "incompletitud", mensaje)

    def test_identificador_de_vulnerabilidad(self):
        self.assertEqual(reliability._senal("bump dep for CVE-2024-21538"), "identificador")
        self.assertEqual(reliability._senal("merge from GHSA-m3vr-7329-44ww"), "identificador")

    def test_fix_a_secas_no_alcanza(self):
        # En estos proyectos la mayoria de los commits empieza con fix entonces aceptarlo como señal es como no filtrar nada.
        self.assertIsNone(reliability._senal("fix: update the client timeout"))
        self.assertIsNone(reliability._senal("fix(ui): align the buttons"))

    def test_mensaje_corriente(self):
        self.assertIsNone(reliability._senal("feat: add support for custom headers"))
        self.assertIsNone(reliability._senal("chore: bump go to 1.22"))


class PruebaRastreoDeLineas(unittest.TestCase):
    """
    Esta clase arma un repositorio de verdad y comprueba el rastreo sobre el.

    Para hacerlo corto hacemos una version inicial, una correccion que toca unas lineas, y despues un cambio que toca esas mismas lineas o uno
    que toca otras. Lo que se verifica es que el modulo sepa distinguirlos.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="patcheval_prueba_")
        self._git("init", "-q")
        # El repositorio tiene que tener autor configurado sino git no deja hacer commits y ponemos local para no tocar la configuracion de la maquina.
        self._git("config", "user.email", "prueba@local")
        self._git("config", "user.name", "prueba")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _git(self, *args, fecha=None):
        # Las fechas se fijan a mano porque los commits de la prueba se crean en milisegundos y git guarda la fecha con resolucion igual entonces
        # sin esto todos quedan con la misma marca, el modulo los descarta por no ser posteriores a la correccion y falla.
        entorno = dict(os.environ)
        if fecha:
            entorno["GIT_AUTHOR_DATE"] = fecha
            entorno["GIT_COMMITTER_DATE"] = fecha
        subprocess.run(["git", "-C", self.dir, *args], check=True, env=entorno,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _escribir(self, lineas):
        with open(os.path.join(self.dir, "m.py"), "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")

    def _commit(self, mensaje, fecha):
        self._git("add", ".")
        self._git("commit", "-q", "-m", mensaje, fecha=fecha)

    def _preparar_correccion(self):
        """
        Deja el repositorio con una version inicial y una correccion encima, y devuelve el sha de la correccion.
        """
        self._escribir(["def a():", "    return 1", "", "def b():", "    return 2"])
        self._commit("version inicial", "2026-01-01T10:00:00")

        # La correccion toca la primera funcion
        self._escribir(["def a():", "    if True:", "        return 1", "", "def b():", "    return 2"])
        self._commit("fix: valida la entrada", "2026-01-02T10:00:00")

        repo = Repositorio(self.dir)
        return repo, repo.cargar_correccion("HEAD")

    def test_cambio_sobre_las_mismas_lineas_se_detecta(self):
        repo, correccion = self._preparar_correccion()

        # Alguien vuelve sobre la misma funcion y declara que la correccion quedo corta.
        self._escribir(["def a():", "    if True and False:", "        return 1", "", "def b():", "    return 2"])
        self._commit("fix: incomplete validation in a()", "2026-01-20T10:00:00")

        e = reliability.medir(repo, correccion)
        self.assertEqual(e["parches_complementarios"], 1)
        self.assertFalse(e["es_fiable"])

    def test_cambio_sobre_otras_lineas_no_se_detecta(self):
        repo, correccion = self._preparar_correccion()

        # Mismo archivo, mismo tipo de mensaje, pero la que cambia es la otra funcion entonces no deberia detectarla 
        #porque la correccion se hizo en la primera funcion a
        self._escribir(["def a():", "    if True:", "        return 1", "", "def b():", "    return 99"])
        self._commit("fix: incomplete validation in b()", "2026-01-20T10:00:00")

        e = reliability.medir(repo, correccion)
        self.assertEqual(e["parches_complementarios"], 0)
        self.assertTrue(e["es_fiable"])

    def test_el_conteo_sin_filtrar_si_ve_el_cambio(self):
        repo, correccion = self._preparar_correccion()
        self._escribir(["def a():", "    if True and False:", "        return 1", "", "def b():", "    return 2"])
        self._commit("chore: renombra una variable", "2026-01-20T10:00:00")

        e = reliability.medir(repo, correccion)
        # El cambio toca las mismas lineas, asi que aparece en el conteo general, pero su mensaje no declara incompletitud y por eso no cuenta como
        # candidato porque tienen que tener las dos cosas y miramos los dos numeros porque es lo que deja ver cuanto esta filtrando el criterio.
        self.assertEqual(e["cambios_sobre_las_mismas_lineas"], 1)
        self.assertEqual(e["parches_complementarios"], 0)

    def test_fuera_de_la_ventana_no_cuenta(self):
        repo, correccion = self._preparar_correccion()
        self._escribir(["def a():", "    if True and False:", "        return 1", "", "def b():", "    return 2"])
        self._commit("fix: incomplete validation in a()", "2026-01-20T10:00:00")

        # Con la ventana en cero dias nada entra y sirve para comprobar que el filtro temporal se aplica.
        e = reliability.medir(repo, correccion, ventana_dias=0)
        self.assertEqual(e["parches_complementarios"], 0)
        self.assertEqual(e["ventana_dias"], 0)


class PruebaArchivosIgnorados(unittest.TestCase):

    def test_archivos_de_dependencias_no_se_rastrean(self):
        # Un cambio en go.sum no habla de la correccion entonces no se rastrea
        for ruta in ("go.sum", "go.mod", "ui/package-lock.json", "api/servicio.pb.go", "zz_generated_deepcopy.go"):
            self.assertFalse(reliability._rastreable(ruta), ruta)

    def test_codigo_normal_si_se_rastrea(self):
        for ruta in ("util/db/db.go", "patcheval/repo.py", "src/main/Servicio.java"):
            self.assertTrue(reliability._rastreable(ruta), ruta)


if __name__ == "__main__":
    unittest.main()

# Se corre con:  python -m unittest discover tests