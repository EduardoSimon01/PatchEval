"""
Contraste de las correcciones contra la linea base.

Aqui se responde la pregunta si corregir una vulnerabilidad cuesta mas que hacer un cambio cualquiera en el mismo proyecto y tambien se responde comparando cada 
correccion contra los cambios ordinarios que salieron de su propia ventana, no contra un monton entero, porque un proyecto cambia de caracter con los años 
y comparar una correccion de 2022 por ejemplo con lo que se programa hoy pues mediria el paso del tiempo y no la naturaleza del cambio.

Cada correccion queda emparejada con la mediana de sus cambios ordinarioses se usa la mediana y no el promedio porque basta un cambio ordinario enorme para
arrastrar el promedio del par entonces la comparacion dependeria de esa sinmgularidad.

La prueba es la de rangos con signo de Wilcoxon que es la que se declaro en el marco y se escogio porque no supone que los datos se
distribuyan de ninguna forma en particular por eso resulto ser acertado ya que en el conjunto medido hay valores que se salen por mucho del resto y una
comparacion de promedios habria dicho lo contrario que la de medianas.

Se usa la aproximacion normal con correccion por continuidad y por empates esto es lo estandar para muestras de este tamaño y se declara aqui para que
quien repita el calculo con otra herramienta sepa contra que se esta comparando.
"""

import json
from math import erfc, sqrt
from statistics import median

# Nivel de significancia declarado en el marco.
ALFA = 0.05

# Por debajo de esto la aproximacion normal no se sostiene y mejor no reportar un valor de p que nadie deberia de creer.
MINIMO_PARES = 6

# Las cuatro medidas que se contrastan y el campo del perfil de donde salen.
METRICAS = {
    "complejidad": "delta_ccn",
    "densidad": "densidad_decision",
    "dispersion": "proporcion_servicios",
    "despliegue": "ponderado_introducidas",
}


def rangos_promedio(valores):
    """
    Asigna un rango a cada valor, repartiendo el promedio entre los empatados.

    Los empates importan aqui porque muchas correcciones no cambian la complejidad y quedan todas en cero entonces si a cada una se le diera un
    rango distinto el resultado dependeria del orden en que entraron a la lista.
    """
    orden = sorted(range(len(valores)), key=lambda i: valores[i])
    rangos = [0.0] * len(valores)

    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and valores[orden[j + 1]] == valores[orden[i]]:
            j += 1
        promedio = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rangos[orden[k]] = promedio
        i = j + 1

    return rangos


def wilcoxon(diferencias):
    """
    Prueba de rangos con signo sobre las diferencias de cada par.

    Las diferencias exactamente cero se descartan que es como Wilcoxon la definio un par sin diferencia no aporta evidencia hacia ningun lado.

    Se devuelve el estadistico, el valor z y el valor de p a dos colas.
    """
    d = [x for x in diferencias if x != 0]
    n = len(d)

    if n < MINIMO_PARES:
        return {"n": n, "W": None, "z": None, "p": None, "mas": 0, "menos": 0}

    absolutos = [abs(x) for x in d]
    r = rangos_promedio(absolutos)

    w_mas = sum(ri for ri, di in zip(r, d) if di > 0)
    w_menos = sum(ri for ri, di in zip(r, d) if di < 0)
    W = min(w_mas, w_menos)

    media = n * (n + 1) / 4.0

    # Correccion por empates sin esto la varianza sale inflada y el valor de p queda mas como conservador de lo que corresponde.
    conteo = {}
    for a in absolutos:
        conteo[a] = conteo.get(a, 0) + 1
    ajuste = sum(t ** 3 - t for t in conteo.values()) / 48.0

    var = n * (n + 1) * (2 * n + 1) / 24.0 - ajuste

    # El 0.5 es la correccion por continuidad porque se esta aproximando algo discreto con una curva continua.
    z = (W - media + 0.5) / sqrt(var)
    p = erfc(abs(z) / sqrt(2.0))

    # Cuantos pares van para cada lado. La prueba dice si hay diferencia pero no hacia donde y sin eso el resultado no se puede redactar.
    return {"n": n, "W": W, "z": z, "p": p, "mas": sum(1 for x in d if x > 0), "menos": sum(1 for x in d if x < 0)}


def cargar(ruta):
    """Lee los perfiles que dejo la corrida del corpus."""
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def armar_pares(perfiles, campo):
    """
    Empareja cada correccion con la mediana de sus cambios ordinarios.

    Una correccion sin cambios ordinarios asociados queda fuera y se cuenta aparte porque descartarla cambiaria el tamano de la muestra sin que nadie se entere.
    """
    seguridad = [p for p in perfiles if p.get("tipo") == "seguridad"]
    ordinarias = [p for p in perfiles if p.get("tipo") == "ordinaria"]

    pares = []
    sin_pareja = 0

    for s in seguridad:
        if s.get(campo) is None:
            sin_pareja += 1
            continue

        valores = [o[campo] for o in ordinarias
                   if o.get("pareja") == s["sha"] and o.get(campo) is not None]

        if not valores:
            sin_pareja += 1
            continue

        pares.append((s["sha"], s[campo], median(valores), len(valores)))

    return pares, sin_pareja


def analizar(perfiles):
    """
    Corre el contraste sobre las cuatro medidas.
    """
    resultado = {}

    for metrica, campo in METRICAS.items():
        pares, sin_pareja = armar_pares(perfiles, campo)
        diferencias = [c - b for _, c, b, _ in pares]

        resultado[metrica] = {
            "pares": len(pares),
            "sin_pareja": sin_pareja,
            "mediana_correcciones": median([c for _, c, _, _ in pares]) if pares else None,
            "mediana_base": median([b for _, _, b, _ in pares]) if pares else None,
            "prueba": wilcoxon(diferencias),
        }

    return resultado


def informe(resultado):
    """
    Imprime el contraste.
    """
    print()
    print(f"  CONTRASTE CONTRA LA LINEA BASE  (alfa = {ALFA})")
    print()
    print(f"  {'medida':<13} {'pares':>5} {'correc.':>9} {'base':>9} {'W':>8} {'p':>8}  resultado")
    print("  " + "-" * 72)

    for metrica, r in resultado.items():
        pr = r["prueba"]
        mc = "-" if r["mediana_correcciones"] is None else f"{r['mediana_correcciones']:.2f}"
        mb = "-" if r["mediana_base"] is None else f"{r['mediana_base']:.2f}"

        if pr["p"] is None:
            veredicto = f"pares insuficientes (hacen falta {MINIMO_PARES})"
            w = pv = "-"
        else:
            w = f"{pr['W']:.1f}"
            pv = f"{pr['p']:.4f}"
            if pr["p"] >= ALFA:
                veredicto = f"no difiere  ({pr['mas']} arriba / {pr['menos']} abajo)"
            elif pr["mas"] > pr["menos"]:
                veredicto = f"mayor en las correcciones  ({pr['mas']} / {pr['menos']})"
            else:
                veredicto = f"menor en las correcciones  ({pr['menos']} / {pr['mas']})"

        print(f"  {metrica:<13} {r['pares']:>5} {mc:>9} {mb:>9} {w:>8} {pv:>8}  {veredicto}")

    sueltas = {m: r["sin_pareja"] for m, r in resultado.items() if r["sin_pareja"]}
    if sueltas:
        print()
        print("  correcciones que quedaron fuera por falta de dato o de pareja:")
        for m, n in sueltas.items():
            print(f"    {m}: {n}")

    print()
    print("  La mediana de cada par es la de los cambios ordinarios de esa misma correccion.")
    print("  Un resultado de 'no difiere' no prueba que sean iguales, solo que el conjunto no alcanza para distinguirlos.")


def analizar_archivo(ruta):
    """
    Punto de entrada desde la linea de comandos devuelve el codigo de salida.
    """
    try:
        perfiles = cargar(ruta)
    except Exception as exc:
        print(f"error: no se pudieron leer los perfiles: {exc}")
        return 1

    print(f"ANALISIS sobre {ruta}")
    print(f"  {len(perfiles)} perfiles")

    print()
    print("=" * 76)
    print("  TODOS LOS PROYECTOS JUNTOS")
    informe(analizar(perfiles))

    # Y despues sacamos cada uno por su cuenta esto hace falta para ver si el efecto se da en todos o si el proyecto que mas correcciones
    # aporta arrastra a los demas, y porque la dispersion no es comparable entre proyectos ya que el denominador cuenta cosas distintas en cada uno.
    nombres = sorted({p.get("proyecto", "") for p in perfiles})
    if len(nombres) > 1:
        for nombre in nombres:
            solo = [p for p in perfiles if p.get("proyecto") == nombre]
            print()
            print("=" * 76)
            print(f"  {nombre.upper()}  ({len(solo)} perfiles)")
            informe(analizar(solo))

    return 0