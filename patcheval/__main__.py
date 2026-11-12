"""
Punto de entrada del paquete.

Permite correr el prototipo desde la terminal con `python -m patcheval`.
Desde el H5 el reporte no llama a los modulos de medicion: le pide el perfil de una vez a profile.construir y se limita a imprimirlo. Asi el calculo queda en un solo
lugar y lo podremos ver en la terminal.
"""

import argparse
import sys

from . import Repositorio, __version__
from . import corpus
from . import profile
from .metrics import deployment
from . import discover
from . import analyze


def main(argv=None):
    # el argparse arma el parseo de argumentos ytambien  el texto de ayuda
    # que sale con --help. argv queda como parametro en lugar de leer
    # sys.argv directo para poder llamar a main() desde una prueba.
    ap = argparse.ArgumentParser(
        prog="patcheval",
        description="Evalua la eficacia y el costo arquitectonico de correcciones de seguridad en proyectos cloud-native")

    # --repo acepta las dos cosas: una carpeta ya clonada o una URL. En el modulo se ve que se mando
    # Ya no es obligatorio porque con --corpus las rutas salen del archivo.
    ap.add_argument("--repo", help="ruta local o URL del repositorio")

    # El identificador puede ser el sha completo, uno abreviado o cualquier referencia que git sepa resolver (una etiqueta una etiqueta por ejemplo como HEAD~3).
    ap.add_argument("--commit", help="identificador de la correccion a inspeccionar")

    # Con --corpus se evaluan de corrido todas las correcciones declaradas en un archivo que ess lo que necesita la clasificacion para calcular.
    ap.add_argument("--corpus", help="archivo con la lista de correcciones a evaluar")
    ap.add_argument("--salida", default="resultados/perfiles.json", help="donde guardar los perfiles del corpus")

    ap.add_argument("--version", action="version", version=f"patcheval {__version__}")

    # Con --descubrir se aplica el criterio de seleccion del corpus sobre un repositorio y se imprimen las entradas listas para pegar. Asi la lista
    # de correcciones no la escojo yo a mano sino que sale de la regla escrita.
    ap.add_argument("--descubrir", help="ruta del repositorio donde buscar correcciones de seguridad")
    ap.add_argument("--proyecto", default="", help="nombre del proyecto para la entrada del corpus")


    # Con --analizar se contrastan las correcciones contra su linea base sobre los perfiles que ya quedaron guardados sin volver a medir nada.
    ap.add_argument("--analizar", nargs="?", const="resultados/perfiles.json", help="contrasta los perfiles guardados contra la linea base")

    args = ap.parse_args(argv)

    if args.analizar:
        return analyze.analizar_archivo(args.analizar)

    # Tenemos los dos modos: una correccion suelta o el corpus completo. El corpus se atiende aqui y se sale, porque de ahi en adelante todo el reporte esta
    # escrito para una sola correccion.
    if args.corpus:
        return corpus.evaluar_archivo(args.corpus, args.salida)

    if args.descubrir:
        return discover.descubrir_archivo(args.descubrir, args.proyecto)

    if not (args.repo and args.commit):
        ap.error("hacen falta --repo y --commit, o bien --corpus")

    # Los dos pasos que pueden fallar van dentro del mismo try: abrir el repositorio y resolver la correccion. Se atrapa Exception a secas
    # porque las causas son muy variadas (ruta inexistente, carpeta que no es un repo, sha que no resuelve, repo sin permisos, etc).
    try:
        repo = Repositorio(args.repo)
        c = repo.cargar_correccion(args.commit)
    except Exception as exc:
        # El mensaje va a la salida de error, no a la normal. Asi por si alguien encadena varias corridas y redirige la salida a un
        # archivo, los errores siguen apareciendo en pantalla.
        print(f"error: {exc}", file=sys.stderr)
        # Codigo distinto de cero si salio mal.
        return 1

    p = profile.construir(repo, c)

    # Reporte que se ve en la termi 
    print(f"CORRECCION {p.sha[:12]}")
    print(f"  {p.mensaje[:70]}")
    print(f"  fecha ............. {p.fecha[:10]}")
    print(f"  padre ............. {c.sha_padre[:12]}")
    print(f"  archivos .......... {p.archivos}")
    print(f"  lineas ............ +{p.lineas_agregadas} / -{p.lineas_eliminadas}")
    print(f"  servicios del repo  {p.servicios_totales}")

    print()
    print("  COSTO ESTRUCTURAL")
    print(f"    archivos de codigo  {p.archivos_codigo}")
    print(f"    complejidad antes   {p.ccn_antes}")
    print(f"    complejidad despues {p.ccn_despues}")
    # El :+d fuerza el signo para saber si es + o - pq sino si es positivo sale sin signo
    print(f"    variacion .........  {p.delta_ccn:+d}")
    # La densidad se imprime solo si hay con que calcularla.
    if p.densidad_decision is not None:
        print(f"    densidad ..........  {p.densidad_decision} por cada 100 lineas")

    print()
    print("  DISPERSION DEL CAMBIO")
    print(f"    servicios afectados {p.servicios_afectados} de {p.servicios_totales}")
    print(f"    proporcion ........ {p.proporcion_servicios}")
    print(f"    manifiestos ....... {p.manifiestos_modificados}")
    print()

    print()
    print("  COSTO DE DESPLIEGUE")
    print(f"    manifiestos ....... {p.manifiestos_analizados}")
    print(f"    introducidas ...... {p.introducidas} (ponderado {p.ponderado_introducidas})")
    print(f"    resueltas ......... {p.resueltas} (ponderado {p.ponderado_resueltas})")
    # Las categorias se listan solo si hay algo que listar .
    for k, v in p.detalle_introducidas.items():
        print(f"      + {deployment.CATEGORIAS[k]['etiqueta']}: {v}")
    for k, v in p.detalle_resueltas.items():
        print(f"      - {deployment.CATEGORIAS[k]['etiqueta']}: {v}")

    print()
    print("  EFICACIA")
    estado = "sin indicios de parche complementario" if p.es_fiable else "requiere revision manual"
    print(f"    estado ............ {estado}")
    print(f"    candidatos ........ {p.parches_complementarios}")
    print(f"    sobre las lineas .. {p.cambios_sobre_las_mismas_lineas} (ventana de {p.ventana_dias} dias)")
    if p.dias_hasta_el_primero is not None:
        print(f"    primero a los ..... {p.dias_hasta_el_primero} dias")
    for cand in p.candidatos[:3]:
        print(f"      ? [{cand['senal']}] {cand['mensaje'][:58]}")

    print()
    print()
    print("  La clasificacion del conjunto sale con --corpus, que la calcula sobre el conjunto completo.")

    return 0


if __name__ == "__main__":
    # sys.exit propaga el codigo de main() al sistema operativo. Si se usa solo a main(), el proceso terminaria siempre en 0 aunque hubiera fallado.
    sys.exit(main())