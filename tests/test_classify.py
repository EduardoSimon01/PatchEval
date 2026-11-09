"""
Pruebas de la clasificacion por cuartiles.

Lo que se verifica no es que la biblioteca calcule bien los cuartiles que eso ya esta probado sino las decisiones que tomamos encima el minimo de cuatro correcciones, 
hacia donde caen los empates y que una metrica sin dispersion no reparta niveles que no significan nada.
"""

import unittest

from patcheval import classify
from patcheval.profile import Perfil


def perfil(sha, delta_ccn, densidad, dispersion, despliegue):
    """
    Un perfil con lo justo para clasificar el resto queda en sus valores por defecto.
    """
    return Perfil(
        proyecto="prueba", sha=sha, mensaje="", fecha="2026-01-01T00:00:00",
        archivos=1, lineas_agregadas=100, lineas_eliminadas=0, servicios_totales=10,
        archivos_codigo=1, ccn_antes=0, ccn_despues=delta_ccn, delta_ccn=delta_ccn,
        densidad_decision=densidad,
        servicios_afectados=1, proporcion_servicios=dispersion, manifiestos_modificados=0,
        manifiestos_analizados=0, introducidas=0, ponderado_introducidas=despliegue,
        resueltas=0, ponderado_resueltas=0,
    )


class PruebaCuartiles(unittest.TestCase):

    def test_valores_conocidos(self):
        # Con el metodo inclusive, 1 2 3 4 corta en 1.75 y 3.25.
        self.assertEqual(classify.cuartiles([1, 2, 3, 4]), (1.75, 3.25))

    def test_no_depende_del_orden(self):
        self.assertEqual(classify.cuartiles([4, 1, 3, 2]), (1.75, 3.25))

    def test_menos_del_minimo(self):
        with self.assertRaises(ValueError):
            classify.cuartiles([1, 2, 3])


class PruebaNivel(unittest.TestCase):

    def test_empate_abajo_es_bajo(self):
        self.assertEqual(classify.nivel(10, 10, 20), "bajo")

    def test_empate_arriba_es_alto(self):
        self.assertEqual(classify.nivel(20, 10, 20), "alto")

    def test_en_medio(self):
        self.assertEqual(classify.nivel(15, 10, 20), "medio")


class PruebaClasificar(unittest.TestCase):

    def setUp(self):
        self.perfiles = [
            perfil("aaa", 1, 1.0, 0.1, 1),
            perfil("bbb", 2, 2.0, 0.2, 2),
            perfil("ccc", 3, 3.0, 0.3, 3),
            perfil("ddd", 4, 4.0, 0.4, 4),
        ]

    def test_reparte_los_extremos(self):
        r = classify.clasificar(self.perfiles)
        self.assertEqual(r["niveles"]["aaa"]["complejidad"], "bajo")
        self.assertEqual(r["niveles"]["ddd"]["complejidad"], "alto")
        self.assertEqual(r["niveles"]["bbb"]["complejidad"], "medio")

    def test_tres_correcciones_no_alcanzan(self):
        with self.assertRaises(ValueError):
            classify.clasificar(self.perfiles[:3])

    def test_metrica_sin_dispersion_no_reparte(self):
        # Las cuatro con el mismo valor de despliegue.
        iguales = [perfil(p.sha, p.delta_ccn, p.densidad_decision,
                          p.proporcion_servicios, 0) for p in self.perfiles]
        r = classify.clasificar(iguales)
        self.assertFalse(r["cortes"]["despliegue"]["discrimina"])
        for sha in r["niveles"]:
            self.assertIsNone(r["niveles"][sha]["despliegue"])

    def test_densidad_ausente_queda_sin_nivel(self):
        # Una correccion sin densidad deja a esa metrica con tres valores, por
        # debajo del minimo, asi que la metrica entera se queda sin cortes.
        con_hueco = list(self.perfiles)
        con_hueco[0] = perfil("aaa", 1, None, 0.1, 1)
        r = classify.clasificar(con_hueco)
        self.assertIsNone(r["niveles"]["aaa"]["densidad"])
        # Las otras metricas no se ven afectadas.
        self.assertIsNotNone(r["niveles"]["aaa"]["complejidad"])


if __name__ == "__main__":
    unittest.main()