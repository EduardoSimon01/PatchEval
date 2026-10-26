# patcheval

Evaluación automatizada de la eficacia y el costo arquitectónico de las correcciones de seguridad en sistemas cloud-native.

Trabajo de graduación de Angel Eduardo Tubac Simón, carné 202200309.

Escuela de Ingeniería en Ciencias y Sistemas, Facultad de Ingeniería, Universidad de San Carlos de Guatemala.

## Qué hace

Dado un repositorio y el identificador de una corrección de seguridad, el prototipo calcula un perfil de evaluación en dos dimensiones.

Eficacia: Se divide en dos subdimensiones. La fiabilidad indica si alguien tuvo que volver sobre las mismas líneas que la corrección dejó, dentro de una ventana de tiempo declarada, con un cambio que señale que quedó incompleta. La completitud indica si la corrección atacó la causa del problema o solamente una de sus manifestaciones.

El prototipo determina la primera y no determina la segunda. Establecer la completitud exige una inferencia sobre el significado del código que el prototipo no está en condiciones de sostener, de modo que queda declarada como parte del marco pero su determinación es manual.

Costo arquitectónico: Es la magnitud del deterioro que la corrección introduce respecto al estado inmediatamente anterior a su aplicación. Se observa en tres planos: el impacto estructural sobre el código, la dispersión del cambio entre los servicios del sistema y el efecto sobre la configuración de despliegue.

## Estado

En construcción. El plan avanza por hitos y cada uno deja algo que se puede ejecutar y verificar.

| Hito | Qué construye | Estado |
|------|---------------|--------|
| H1 | Acceso al repositorio y al par de versiones | listo |
| H2 | Impacto estructural y dispersión del cambio | listo |
| H3 | Impacto de despliegue sobre manifiestos | listo |
| H4 | Fiabilidad de la corrección | listo |
| H5 | Construcción del perfil y clasificación | pendiente |
| H6 | Aplicación al corpus completo | pendiente |

## Instalación

Requiere Python 3.10 o superior.

```bash
git clone https://github.com/EduardoSimon01/PatchEval.git
cd PatchEval
pip install -r requirements.txt
```

No hace falta configurar nada más. El prototipo no usa base de datos, no levanta servicios y no necesita credenciales ni archivos de entorno lo que hace es que trabaja sobre repositorios locales o sobre repositorios públicos que clona él mismo.

## Uso

El prototipo trabaja sobre un repositorio ya clonado en el disco. Entra a esa carpeta y consulta el historial de git directamente: no usa la API de GitHub ni necesita conexión. Si en lugar de una carpeta se le entrega una URL, la clona él y después trabaja sobre esa copia local.

Para tener un repositorio sobre el que probar:

```bash
git clone --filter=blob:none https://github.com/argoproj/argo-cd.git C:\Users\<usuario>\corpus\argo-cd
```

El filtro baja el historial completo pero sin el contenido de los archivos, que se trae a medida que se pide. Son unos 60 MB en vez de 470.

Desde la terminal:

```powershell
python -m patcheval --repo C:\Users\<usuario>\corpus\argo-cd --commit 2df5f7572
```

Desde código:

```python
from patcheval import Repositorio
from patcheval.metrics import complexity, deployment, dispersion

repo = Repositorio(r"C:\Users\<usuario>\corpus\argo-cd")
c = repo.cargar_correccion("2df5f7572")

print(c.mensaje)
print(f"{len(c.archivos)} archivos, +{c.total_agregadas} / -{c.total_eliminadas}")
print(complexity.medir(repo, c)["delta_ccn"])
print(dispersion.medir(repo, c)["proporcion"])
print(deployment.medir(repo, c)["total_introducidas"])
```



## Cómo verificar lo que hay hasta ahora

### Las pruebas del detector

```powershell
python -m unittest discover tests
```

Tienen que dar 22 OK. 

El detector de configuraciones inseguras se verifica con manifiestos construidos para la prueba y por cada categoría hay un caso donde la configuración insegura está presente y otro donde está resuelta de la forma correcta.

Se hace así y no sobre un caso real porque el detector no reporta nada sobre una corrección del corpus, pero es porque todo esta bien, entonces con los tests se valida el funcionamiento.



## Proyectos sobre los que se aplica

Las correcciones evaluadas provienen de proyectos cloud-native de código abierto con historial público y avisos de seguridad formales:

- [Argo CD](https://github.com/argoproj/argo-cd) — entrega continua para Kubernetes
- [Harbor](https://github.com/goharbor/harbor) — registro de contenedores

Cada corrección se identifica por su proyecto y por el identificador de su confirmación de cambio, de modo que cualquier lector puede situarse en el mismo punto de la historia y repetir la medición.

## Dependencias

| Biblioteca | Para qué | Licencia |
|---|---|---|
| GitPython | acceso al historial de versiones | BSD de 3 cláusulas |
| lizard | complejidad ciclomática multilenguaje | MIT |
| PyYAML | análisis de manifiestos de despliegue | MIT |

## Licencia

MIT. Ver el archivo LICENSE.