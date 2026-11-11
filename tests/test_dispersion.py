"""
Pruebas de a que servicio pertenece un archivo.

Es la pieza que decide el numerador de la dispersion y tiene varios casos que no son obvios sobre todo desde que la carpeta raiz se declara por proyecto.
"""

import unittest

from patcheval.metrics.dispersion import servicio_de


class PruebaSinRaiz(unittest.TestCase):

    def setUp(self):
        self.conocidos = ["cmd", "controller", "server"]

    def test_caso_normal(self):
        self.assertEqual(servicio_de("cmd/argocd/main.go", self.conocidos), "cmd")

    def test_carpeta_que_no_es_servicio(self):
        self.assertIsNone(servicio_de("docs/index.md", self.conocidos))

    def test_archivo_suelto_en_la_raiz(self):
        self.assertIsNone(servicio_de("go.mod", self.conocidos))


class PruebaConRaiz(unittest.TestCase):

    def setUp(self):
        # Este es para Harbor, que mete todo bajo src.
        self.conocidos = ["core", "jobservice", "portal"]

    def test_toma_el_tramo_de_adentro(self):
        self.assertEqual(
            servicio_de("src/core/api/base.go", self.conocidos, "src"), "core")

    def test_lo_de_afuera_no_cuenta(self):
        # La documentacion de Harbor vive fuera de src y no pertenece a ningun servicio.
        self.assertIsNone(servicio_de("docs/install.md", self.conocidos, "src"))

    def test_archivo_suelto_dentro_de_la_raiz(self):
        self.assertIsNone(servicio_de("src/Makefile", self.conocidos, "src"))

    def test_carpeta_desconocida_dentro_de_la_raiz(self):
        self.assertIsNone(servicio_de("src/vendor/x/y.go", self.conocidos, "src"))