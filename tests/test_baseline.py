"""
Pruebas de la seleccion de la linea base.

Las dos piezas que se prueban son las que deciden que entra a la comparacion el filtro que mantiene afuera las correcciones de seguridad y el muestreo que
reparte los candidatos las dos cosas son aritmetica y texto, asi que se prueban sin repositorio.

Lo que no se prueba aqui es que git devuelva los commits correctos porque eso es responsabilidad de git.
"""

import unittest

from patcheval import baseline


class PruebaFiltroSeguridad(unittest.TestCase):

    def test_identificadores(self):
        self.assertTrue(baseline.es_seguridad("fix CVE-2024-1234 in parser"))
        self.assertTrue(baseline.es_seguridad("backport GHSA-aaaa-bbbb-cccc"))

    def test_vocabulario(self):
        self.assertTrue(baseline.es_seguridad("fix XSS in the login form"))
        self.assertTrue(baseline.es_seguridad("sanitize user input"))
        self.assertTrue(baseline.es_seguridad("prevent privilege escalation"))

    def test_no_confunde_cambios_ordinarios(self):
        # Estos tienen que pasar como ordinarios. El riesgo del filtro es al reves que el de la metrica de fiabilidad y aqui un falso positivo solo
        # descarta un candidato, pero un falso negativo mete una correccion de seguridad a la linea base y arruina el contraste que buscamos.
        self.assertFalse(baseline.es_seguridad("add retry to the sync loop"))
        self.assertFalse(baseline.es_seguridad("update docs for the helm chart"))
        self.assertFalse(baseline.es_seguridad("refactor the resource cache"))

    def test_no_distingue_mayusculas(self):
        self.assertTrue(baseline.es_seguridad("FIX SECURITY ISSUE"))

class PruebaFiltroAutomatico(unittest.TestCase):

    def test_los_tres_que_salieron_en_la_primera_corrida(self):
        # Son los mensajes exactos que la primera version selecciono comolinea base y que obligaron a agregar este filtro.
        self.assertTrue(baseline.es_automatico(
            "chore(deps): update dependency pymdown-extensions to v13 (master) (#30867)"))
        self.assertTrue(baseline.es_automatico(
            "chore(deps): bump the aws-sdk-v2 group with 3 updates (#29770)"))
        self.assertTrue(baseline.es_automatico(
            "chore(deps): bump ossf/scorecard-action from 2.4.3 to 2.4.4 (#28884)"))

    def test_no_descarta_trabajo_de_verdad(self):
        self.assertFalse(baseline.es_automatico("feat: add health check for Rollouts"))
        self.assertFalse(baseline.es_automatico("fix: handle empty resource list"))
        self.assertFalse(baseline.es_automatico("chore: simplify the sync loop"))


class PruebaFiltroBot(unittest.TestCase):

    def test_firmas_de_herramientas(self):
        self.assertTrue(baseline.es_bot("dependabot[bot]"))
        self.assertTrue(baseline.es_bot("renovate[bot]"))
        self.assertTrue(baseline.es_bot("github-actions[bot]"))

    def test_personas(self):
        self.assertFalse(baseline.es_bot("Angel Tubac"))
        self.assertFalse(baseline.es_bot("Jann Fischer"))

    def test_autor_vacio(self):
        # Puede venir vacio si el formato del log falla no debería reventar.
        self.assertFalse(baseline.es_bot(""))
        self.assertFalse(baseline.es_bot(None))

class PruebaMuestreo(unittest.TestCase):

    def test_reparte_a_lo_largo(self):
        # De diez candidatos, tres repartidos son el primero, el del medio y el ultimo.
        self.assertEqual(baseline.muestrear(list(range(10)), 3), [0, 4, 9])

    def test_uno_solo_sale_del_medio(self):
        self.assertEqual(baseline.muestrear(list(range(10)), 1), [5])

    def test_pedir_mas_de_los_que_hay(self):
        self.assertEqual(baseline.muestrear([1, 2, 3], 10), [1, 2, 3])

    def test_sin_candidatos(self):
        self.assertEqual(baseline.muestrear([], 3), [])

    def test_cantidad_cero(self):
        self.assertEqual(baseline.muestrear([1, 2, 3], 0), [])

    def test_es_deterministico(self):
        # La misma entrada tiene que dar la misma salida siempre esa es la propiedad que hace reproducible la linea base.
        candidatos = list(range(50))
        primera = baseline.muestrear(candidatos, 7)
        for _ in range(5):
            self.assertEqual(baseline.muestrear(candidatos, 7), primera)


if __name__ == "__main__":
    unittest.main()