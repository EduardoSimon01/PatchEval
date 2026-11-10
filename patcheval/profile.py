"""
Perfil de la correccion.

Junta en un solo objeto lo que devuelven los cuatro modulos de medicion porque hasta ahora el reporte solo llamaba a cada modulo por su cuenta y armaba la salida el
mismo, con essto alcanzaba para mirar una correccion a la vez, pero para el corpus hace falta algo que se pueda guardar, ordenar y comparar entre correcciones.

El perfil no resume nada en un numero sino que las cuatro medidas se guardan por separado porque combinarlas exigiria justificar unos pesos, y no hay con que
justificarlos no existe forma de sostener que un punto de complejidad valga tanto como un servicio alcanzado.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from .metrics import complexity, deployment, dispersion, reliability


@dataclass
class Perfil:
    # de que correccion estamos hablando
    proyecto: str
    sha: str
    mensaje: str
    fecha: str

    # alcance del cambio
    archivos: int
    lineas_agregadas: int
    lineas_eliminadas: int
    servicios_totales: int

    # impacto estructural
    archivos_codigo: int
    ccn_antes: int
    ccn_despues: int
    delta_ccn: int
    # Esta es la variacion de complejidad por cada cien lineas agregadas la variacion a secas crece con el tamaño del cambio, asi que por si sola dice mas del
    # tamano que de la estructura por eso esta se divide por el tamano, y con eso dejamos de medir cuanto se escribio para medir que tan enredado es lo que se escribio.
     
    # Se queda en None cuando la correccion no agrega lineas porque dividir entre cero no tiene lectura y poner un cero mentiria.
    densidad_decision: Optional[float]

    # dispersion del cambio
    servicios_afectados: int
    proporcion_servicios: float
    manifiestos_modificados: int

    # impacto de despliegue
    manifiestos_analizados: int
    introducidas: int
    ponderado_introducidas: int
    resueltas: int
    ponderado_resueltas: int
    detalle_introducidas: dict = field(default_factory=dict)
    detalle_resueltas: dict = field(default_factory=dict)

    # fiabilidad
    es_fiable: bool = True
    cambios_sobre_las_mismas_lineas: int = 0
    parches_complementarios: int = 0
    dias_hasta_el_primero: Optional[int] = None
    ventana_dias: int = 0
    candidatos: list = field(default_factory=list)

    # contra que estado del repositorio se midio mira sha_actual en repo.py.
    head: str = ""
    evaluado_en: str = ""

    # la linea base son cambios ordinarios del mismo proyecto y sin esta marca no habria como separarlos al analizar.
    tipo: str = "seguridad"
    # El aviso publicado que respalda a la correccion porque una correccion sin fuente no es verificable por nadie mas y queda como afirmacion mia.
    fuente: str = ""

    # Vamos a sacar de cual correccion salio este cambio ordinario si queda vacio en las correcciones de seguridad es porque ellas no salieron de ninguna sin esto 
    # las filas ordinarias quedan sueltas en el csv y la prueba de rangos con signo, que compara pares, no se puede armar.
    pareja: str = ""

    def como_diccionario(self):
        """Para escribirlo a disco y no tener que volver a medir."""
        return asdict(self)


def densidad_decision(delta_ccn, lineas_agregadas):
    """
    Variacion de complejidad por cada cien lineas agregadas.

    Sale aparte de construir para poder probarla sin necesitar el repositorio aparte es aritmetica sobre dos numeros y no tiene por que depender de git.
    """
    if not lineas_agregadas:
        return None
    return round(100 * delta_ccn / lineas_agregadas, 2)


def construir(repo, correccion, proyecto="", tipo="seguridad", fuente="", pareja=""):
    """
    Corre las cuatro mediciones sobre una misma correccion y arma su perfil.

    El orden importa poco salvo por el tiempo: las tres primeras consultan dos versiones y terminan rapido pero la de fiabilidad recorre historia y es la que
    se tarda un poco y va de ultima para que si algo revienta antes, reviente barato.
    """
    s = complexity.medir(repo, correccion)
    disp = dispersion.medir(repo, correccion)
    g = deployment.medir(repo, correccion)
    e = reliability.medir(repo, correccion)

    densidad = densidad_decision(s["delta_ccn"], correccion.total_agregadas)

    return Perfil(
        proyecto=proyecto,
        sha=correccion.sha,
        mensaje=correccion.mensaje[:110],
        fecha=correccion.fecha,

        archivos=len(correccion.archivos),
        lineas_agregadas=correccion.total_agregadas,
        lineas_eliminadas=correccion.total_eliminadas,
        servicios_totales=disp["servicios_totales"],

        archivos_codigo=s["archivos_codigo"],
        ccn_antes=s["ccn_antes"],
        ccn_despues=s["ccn_despues"],
        delta_ccn=s["delta_ccn"],
        densidad_decision=densidad,

        servicios_afectados=disp["servicios_afectados"],
        proporcion_servicios=disp["proporcion"],
        manifiestos_modificados=disp["manifiestos_modificados"],

        manifiestos_analizados=g["manifiestos_analizados"],
        introducidas=g["total_introducidas"],
        ponderado_introducidas=g["ponderado_introducidas"],
        resueltas=g["total_resueltas"],
        ponderado_resueltas=g["ponderado_resueltas"],
        detalle_introducidas=g["introducidas"],
        detalle_resueltas=g["resueltas"],

        es_fiable=e["es_fiable"],
        cambios_sobre_las_mismas_lineas=e["cambios_sobre_las_mismas_lineas"],
        parches_complementarios=e["parches_complementarios"],
        dias_hasta_el_primero=e["dias_hasta_el_primero"],
        ventana_dias=e["ventana_dias"],
        candidatos=e["candidatos"],

        head=repo.sha_actual(),
        evaluado_en=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        
        tipo=tipo,
        fuente=fuente,
        pareja=pareja,
    )