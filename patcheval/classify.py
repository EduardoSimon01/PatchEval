"""
Clasificacion de las correcciones en niveles.

Cosas como un valor suelto o que una correccion agregue 166 de complejidad no es alto ni bajo hasta que se sabe cuanto agregan las demas. Por eso los niveles
salen del propio conjunto evaluado entonces el cuartil inferior es nivel bajo, el superior es alto, y lo del medio es solo medio.

La consecuencia hay que decirla y es que los niveles son relativos al corpus por lo que la misma correccion puede salir alta en un conjunto y media en otro, y eso no es
un defecto sino lo que significa la medida

Hacen falta al menos cuatro correcciones. Con tres o menos los cuartiles se calculan igual pero no separan nada, y publicar un nivel ahi seria darle peso
a un reparto que no tiene sustento.
"""

from statistics import quantiles

# Minimo de correcciones para que los cuartiles separen algo.
MINIMO = 4

# Las metricas que se clasifican y el atributo del perfil de donde salen. Mas alto significa peor de modo que alto significa lo mismo en todas.
# La de fiabilidad no entra porque no es una cantidad sino un estado, y se reporta como viene.
METRICAS = {
    "complejidad": "delta_ccn",
    "densidad": "densidad_decision",
    "dispersion": "proporcion_servicios",
    "despliegue": "ponderado_introducidas",
}


def cuartiles(valores):
    """
    Devuelve el primer y el tercer cuartil de una lista de numeros.

    Se usa el metodo inclusive de la biblioteca estandar porque toma los extremos como parte de la muestra. 
    
    Se declara aqui porque los metodos de calculo de cuartiles no coinciden entre si y con otro metodo los mismos datos dan
    cortes distintos y se tendria que repetir la clasificacion porque se necesita saber cual se uso.
    """
    if len(valores) < MINIMO:
        raise ValueError(f"hacen falta al menos {MINIMO} valores, llegaron {len(valores)}")

    q1, _, q3 = quantiles(sorted(valores), n=4, method="inclusive")
    return q1, q3


def nivel(valor, p25, p75):
    """
    Ubica un valor en bajo, medio o alto.

    Los empates se van al extremo un valor igual al corte inferior es bajo y uno igual al superior es alto y es una decision arbitraria por eso se escribe
    pero tiene que ser la misma siempre para que dos corridas coincidan.
    """
    if valor <= p25:
        return "bajo"
    if valor >= p75:
        return "alto"
    return "medio"


def clasificar(perfiles):
    """
    Asigna un nivel a cada correccion en cada metrica.

    Devuelve un diccionario con los cortes usados y tambien por cada perfil el nivel que le toco. Una metrica sin dispersion (todos los valores iguales) no se
    clasifica cuando los dos cortes coinciden y el reparto seria una mentira.

    Las correcciones a las que les falta el valor de una metrica, como la densidad cuando la correccion no agrega lineas, quedan sin nivel en esa y
    no entran al calculo de sus cortes.
    """
    if len(perfiles) < MINIMO:
        raise ValueError(
            f"la clasificacion necesita al menos {MINIMO} correcciones, "
            f"el conjunto tiene {len(perfiles)}")

    cortes = {}
    niveles = {p.sha: {} for p in perfiles}

    for metrica, atributo in METRICAS.items():
        medidos = [(p.sha, getattr(p, atributo)) for p in perfiles]
        valores = [v for _, v in medidos if v is not None]

        if len(valores) < MINIMO:
            cortes[metrica] = None
            for sha, _ in medidos:
                niveles[sha][metrica] = None
            continue

        p25, p75 = cuartiles(valores)

        if p25 == p75:
            # Sin dispersion no hay nada que repartir.
            cortes[metrica] = {"p25": p25, "p75": p75, "discrimina": False}
            for sha, _ in medidos:
                niveles[sha][metrica] = None
            continue

        cortes[metrica] = {"p25": p25, "p75": p75, "discrimina": True}
        for sha, valor in medidos:
            niveles[sha][metrica] = None if valor is None else nivel(valor, p25, p75)

    return {"cortes": cortes, "niveles": niveles, "correcciones": len(perfiles)}


def informe(resultado):
    """Imprime los cortes y el reparto."""
    print()
    print(f"  CLASIFICACION sobre {resultado['correcciones']} correcciones")

    for metrica, corte in resultado["cortes"].items():
        if corte is None:
            print(f"    {metrica:<12} sin datos suficientes")
        elif not corte["discrimina"]:
            print(f"    {metrica:<12} todos los valores coinciden, no separa")
        else:
            print(f"    {metrica:<12} bajo <= {corte['p25']:.2f}   alto >= {corte['p75']:.2f}")

    print()
    print(f"  {'sha':<10} " + " ".join(f"{m:<12}" for m in METRICAS))
    print("  " + "-" * 60)
    for sha, asignados in resultado["niveles"].items():
        fila = " ".join(f"{(asignados[m] or '-'):<12}" for m in METRICAS)
        print(f"  {sha[:10]:<10} {fila}")