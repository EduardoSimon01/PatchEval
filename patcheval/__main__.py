"""
Punto de entrada del paquete.

Permite correr el prototipo desde la terminal con `python -m patcheval`.
Hoy solo muestra lo que la capa de acceso logra resolver de una correccion.
Las metricas se agregan en los hitos siguientes.
"""

import argparse
import sys

from . import Repositorio, __version__
from .metrics import complexity, dispersion, deployment


def main(argv=None):
    # el argparse arma el parseo de argumentos ytambien  el texto de ayuda
    # que sale con --help. argv queda como parametro en lugar de leer
    # sys.argv directo para poder llamar a main() desde una prueba.
    ap = argparse.ArgumentParser(
        prog="patcheval",
        description="Evalua la eficacia y el costo arquitectonico de correcciones de seguridad en proyectos cloud-native")

    # --repo acepta las dos cosas: una carpeta ya clonada o una URL. En el modulo se ve que se mando
    ap.add_argument("--repo", required=True,
                    help="ruta local o URL del repositorio")

    # El identificador puede ser el sha completo, uno abreviado o cualquier referencia que git sepa resolver (una etiqueta una etiqueta por ejemplo como HEAD~3).
    ap.add_argument("--commit", required=True, help="identificador de la correccion a inspeccionar")

    ap.add_argument("--version", action="version", version=f"patcheval {__version__}")

    args = ap.parse_args(argv)

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

    # Reporte que se ve en pantalla
    print(f"CORRECCION {c.sha[:12]}")
    print(f"  {c.mensaje[:70]}")
    print(f"  fecha ............. {c.fecha[:10]}")
    print(f"  padre ............. {c.sha_padre[:12]}")
    print(f"  archivos .......... {len(c.archivos)}")
    print(f"  lineas ............ +{c.total_agregadas} / -{c.total_eliminadas}")

    # Se pide el conteo de servicios en el punto de la correccion a evaluar y no en el HEAD porque un repositorio puede haber ganado o perdido servicios 
    # desde entonces, y la dispersion se mide contra el sistema tal como estaba.
    print(f"  servicios del repo  {len(repo.servicios(c.sha))}")

        # Medimos la complejidad
    s = complexity.medir(repo, c)
    print()
    print("  COSTO ESTRUCTURAL")
    print(f"    archivos de codigo  {s['archivos_codigo']}")
    print(f"    complejidad antes   {s['ccn_antes']}")
    print(f"    complejidad despues {s['ccn_despues']}")
    # El :+d fuerza el signo para saber si es + o - pq sino si es positivo sale sin signo
    print(f"    variacion .........  {s['delta_ccn']:+d}")

        # Se mide la dispersion
    disp = dispersion.medir(repo, c)
    print()
    print("  DISPERSION DEL CAMBIO")
    print(f"    servicios afectados {disp['servicios_afectados']} de {disp['servicios_totales']}")
    print(f"    proporcion ........ {disp['proporcion']}")
    print(f"    manifiestos ....... {disp['manifiestos_modificados']}")
    print()

        # Se mide el impacto sobre la configuracion de despliegue
    g = deployment.medir(repo, c)
    print()
    print("  COSTO DE DESPLIEGUE")
    print(f"    manifiestos ....... {g['manifiestos_analizados']}")
    print(f"    introducidas ...... {g['total_introducidas']} (ponderado {g['ponderado_introducidas']})")
    print(f"    resueltas ......... {g['total_resueltas']} (ponderado {g['ponderado_resueltas']})")
    # Las categorias se listan solo si hay algo que listar .
    for k, v in g["introducidas"].items():
        print(f"      + {deployment.CATEGORIAS[k]['etiqueta']}: {v}")
    for k, v in g["resueltas"].items():
        print(f"      - {deployment.CATEGORIAS[k]['etiqueta']}: {v}")

    print("  La metrica de eficacia entra en el hito H4.")
    return 0


if __name__ == "__main__":
    # sys.exit propaga el codigo de main() al sistema operativo. Si se usa solo a main(), el proceso terminaria siempre en 0 aunque hubiera fallado.
    sys.exit(main())