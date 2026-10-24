from patcheval import Repositorio
from patcheval.metrics import complexity

# poner la ruta del repo que queremos usar "." si queremos usar este repo pa pruebas
repo = Repositorio(r"C:\Users\Eduar\corpus\argo-cd")
c = repo.cargar_correccion("2df5f7572")

s = complexity.medir(repo, c)
print("archivos de codigo :", s["archivos_codigo"])
print("ccn antes          :", s["ccn_antes"])
print("ccn despues        :", s["ccn_despues"])
print("delta_ccn          :", s["delta_ccn"])
print("detalle            :", s["detalle"])