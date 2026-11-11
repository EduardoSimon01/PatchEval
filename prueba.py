# poner la ruta del repo que queremos usar "." si queremos usar este repo pa pruebas
# ahora el corpus vive adentro del proyecto asi que la ruta es relativa y sirve en cualquier maquina.

# Con esto se cazo que el --since del rastreo perdia commits. Sobre 8b2f081ded dejaba afuera a f223182ddc, que es del mismo dia de la correccion
# y trae un GHSA en el mensaje, o sea que era candidato. Peor todavia, cuales perdia cambiaba entre corridas sin que cambiara nada mas.
# Ya quitado el --since, esto sirve para ver que el candidato volvio a aparecer.

from datetime import datetime, timezone

from patcheval import Repositorio
from patcheval.metrics import reliability

RUTA = "corpus/argo-cd"
COMMIT = "8b2f081ded"

repo = Repositorio(RUTA)
c = repo.cargar_correccion(COMMIT)
corte = datetime.fromisoformat(c.fecha).timestamp()

print("correccion :", c.sha[:10], c.fecha[:10])
print()

for a in c.archivos:
    for inicio, fin in repo.rangos_modificados(c, a.ruta):
        encontrados = repo.commits_sobre_rango(a.ruta, inicio, fin)
        print(f"{a.ruta}  lineas {inicio}-{fin}  ->  {len(encontrados)} commits")

        for sha, marca, asunto in encontrados:
            dia = datetime.fromtimestamp(marca, tz=timezone.utc).date().isoformat()
            # Solo los posteriores entran a la metrica, los de antes los descarta el filtro de fiabilidad.
            cuando = "despues" if marca > corte else "antes  "
            senal = reliability._senal(asunto) or "-"
            print(f"   {sha[:10]}  {dia}  {cuando}  {senal:<14} {asunto[:48]}")
        print()

e = reliability.medir(repo, c)
print("-" * 60)
print("sobre las mismas lineas :", e["cambios_sobre_las_mismas_lineas"])
print("candidatos              :", e["parches_complementarios"])
for cand in e["candidatos"]:
    print(f"   {cand['sha']}  a los {cand['dias_despues']} dias  [{cand['senal']}]  {cand['mensaje'][:50]}")