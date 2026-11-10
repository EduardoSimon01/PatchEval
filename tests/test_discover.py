"""
Pruebas de la extraccion de identificadores de aviso.

Es lo unico del descubrimiento que se puede probar sin repositorio ya lo demas son los filtros del baseline que ya tienen sus propias pruebas y la regla
del commit mas antiguo que necesita historia de verdad para ejercitarse.
"""

import unittest

from patcheval.discover import avisos_en


class PruebaAvisos(unittest.TestCase):

    def test_ghsa_en_el_asunto(self):
        self.assertEqual(
            avisos_en("fix: limit OCI manifest size (GHSA-w996-f2wq-x9c6)"),
            ["GHSA-W996-F2WQ-X9C6"])

    def test_cve(self):
        self.assertEqual(avisos_en("fix: CVE-2023-1732 (#13748)"), ["CVE-2023-1732"])

    def test_el_patron_de_merge_de_github(self):
        self.assertEqual(
            avisos_en("Merge pull request from GHSA-3cqf-953p-h5cp"),
            ["GHSA-3CQF-953P-H5CP"])

    def test_no_repite_el_mismo_aviso(self):
        # Suele aparecer en el asunto y otra vez en el cuerpo.
        mensaje = "fix: algo (GHSA-m3vr-7329-44ww)\n\nCierra GHSA-m3vr-7329-44ww."
        self.assertEqual(avisos_en(mensaje), ["GHSA-M3VR-7329-44WW"])

    def test_varios_avisos_en_un_commit(self):
        self.assertEqual(
            avisos_en("fix: CVE-2024-21538 y CVE-2024-45296"),
            ["CVE-2024-21538", "CVE-2024-45296"])

    def test_sin_aviso(self):
        self.assertEqual(avisos_en("fix: handle empty resource list"), [])

    def test_mensaje_vacio(self):
        self.assertEqual(avisos_en(""), [])
        self.assertEqual(avisos_en(None), [])

    def test_no_confunde_un_numero_cualquiera(self):
        # Sin la forma completa no es un identificador.
        self.assertEqual(avisos_en("bump to CVE-20 something"), [])