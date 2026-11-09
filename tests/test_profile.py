"""
Pruebas de la densidad de decision.

Es aritmetica sobre dos numeros, pero tiene un caso que importa que es una correccion que no agrega lineas. Ahi la division no existe, y lo que se verifica es que
devuelva None en vez de cero porque un cero diria "no agrego complejidad por linea" mientras que None dice "no hay como calcularlo", que es la verdad.
"""

import unittest

from patcheval.profile import densidad_decision


class PruebaDensidad(unittest.TestCase):

    def test_caso_conocido(self):
        # El de la correccion 2df5f7572: 166 de variacion sobre 3759 lineas.
        self.assertEqual(densidad_decision(166, 3759), 4.42)

    def test_cien_lineas_da_la_variacion(self):
        # Con exactamente cien lineas la densidad es la variacion misma, que es lo que esperamos
        self.assertEqual(densidad_decision(12, 100), 12.0)

    def test_sin_lineas_agregadas(self):
        # Una correccion que solo borra codigo.
        self.assertIsNone(densidad_decision(-5, 0))

    def test_variacion_negativa(self):
        # Una correccion que simplifica etnonces el signo debería sobrevivir.
        self.assertEqual(densidad_decision(-20, 400), -5.0)


if __name__ == "__main__":
    unittest.main()