"""
Pruebas del contraste contra la linea base.

El estadistico se verifico contra una implementacion de referencia y los valores de aqui son los que la comparacion dio lo que se prueba aqui es que la
version propia siga devolviendo los mismos numeros que el manejo de empates y que una muestra chica no reporte un valor de p.
"""

import unittest

from patcheval.analyze import armar_pares, rangos_promedio, wilcoxon


class PruebaRangos(unittest.TestCase):

    def test_sin_empates(self):
        self.assertEqual(rangos_promedio([5, 1, 3]), [3.0, 1.0, 2.0])

    def test_con_empates(self):
        # Los dos veintes se reparten los rangos 2 y 3 osea 2.5 cada uno.
        self.assertEqual(rangos_promedio([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])


class PruebaWilcoxon(unittest.TestCase):

    def test_caso_con_empates(self):
        r = wilcoxon([3, 1, 4, 1, 5, 9, 2, 6, -1, -2])
        self.assertEqual(r["n"], 10)
        self.assertEqual(r["W"], 6.5)
        self.assertAlmostEqual(r["p"], 0.03605, places=5)

    def test_todas_negativas(self):
        r = wilcoxon([-1, -2, -3, -4, -5, -6, -7])
        self.assertEqual(r["W"], 0)
        self.assertAlmostEqual(r["p"], 0.02249, places=5)

    def test_descarta_los_ceros(self):
        # Los tres ceros no cuentan, asi que quedan siete pares.
        r = wilcoxon([0, 0, 0, -1, -2, -3, -4, -5, -6, -7])
        self.assertEqual(r["n"], 7)

    def test_muestra_chica_no_reporta_p(self):
        r = wilcoxon([1, 2, 3])
        self.assertIsNone(r["p"])


class PruebaPares(unittest.TestCase):

    def setUp(self):
        self.perfiles = [
            {"sha": "aaa", "tipo": "seguridad", "pareja": "", "delta_ccn": 10},
            {"sha": "b1", "tipo": "ordinaria", "pareja": "aaa", "delta_ccn": 2},
            {"sha": "b2", "tipo": "ordinaria", "pareja": "aaa", "delta_ccn": 4},
            {"sha": "b3", "tipo": "ordinaria", "pareja": "aaa", "delta_ccn": 30},
        ]

    def test_usa_la_mediana_y_no_el_promedio(self):
        pares, sin = armar_pares(self.perfiles, "delta_ccn")
        # El promedio seria 12 y la correccion saldria por debajo de su base y con la mediana que es 4 sale por encima.
        self.assertEqual(pares, [("aaa", 10, 4, 3)])
        self.assertEqual(sin, 0)

    def test_correccion_sin_ordinarias(self):
        solo = [{"sha": "aaa", "tipo": "seguridad", "pareja": "", "delta_ccn": 10}]
        pares, sin = armar_pares(solo, "delta_ccn")
        self.assertEqual(pares, [])
        self.assertEqual(sin, 1)

    def test_valor_ausente_no_entra(self):
        con_hueco = list(self.perfiles)
        con_hueco[0] = {"sha": "aaa", "tipo": "seguridad", "pareja": "", "delta_ccn": None}
        pares, sin = armar_pares(con_hueco, "delta_ccn")
        self.assertEqual(pares, [])
        self.assertEqual(sin, 1)