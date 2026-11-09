# patcheval

Evaluación automatizada de la eficacia y el costo arquitectónico de las correcciones de seguridad en sistemas cloud-native.

Trabajo de graduación de Angel Eduardo Tubac Simón, carné 202200309.

Escuela de Ingeniería en Ciencias y Sistemas, Facultad de Ingeniería, Universidad de San Carlos de Guatemala.

## Qué hace

Dado un repositorio y el identificador de una corrección de seguridad, el prototipo calcula un perfil de evaluación en dos dimensiones.

Eficacia: Se divide en dos subdimensiones. La fiabilidad indica si alguien tuvo que volver sobre las mismas líneas que la corrección dejó, dentro de una ventana de tiempo declarada, con un cambio que señale que quedó incompleta. La completitud indica si la corrección atacó la causa del problema o solamente una de sus manifestaciones.

El prototipo determina la primera y no determina la segunda. Establecer la completitud exige una inferencia sobre el significado del código que el prototipo no está en condiciones de sostener, de modo que queda declarada como parte del marco pero su determinación es manual.

Costo arquitectónico: Es la magnitud del deterioro que la corrección introduce respecto al estado inmediatamente anterior a su aplicación. Se observa en tres planos: el impacto estructural sobre el código, la dispersión del cambio entre los servicios del sistema y el efecto sobre la configuración de despliegue.

Ninguna de las dos dimensiones se resume en un número único. El resultado es un perfil, y las cuatro medidas se leen por separado.

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

Requiere Python 3.10 o superior y git.

```bash
git clone https://github.com/EduardoSimon01/PatchEval.git
cd PatchEval
python -m pip install -r requirements.txt
```

No hace falta configurar nada más. El prototipo no usa base de datos, no levanta servicios y no necesita credenciales ni archivos de entorno: trabaja directamente sobre repositorios clonados en el disco.

Las versiones de las tres dependencias están fijadas en `requirements.txt` y no es un detalle menor. Las mediciones de complejidad dependen de la versión de lizard: una versión distinta devuelve valores distintos sobre el mismo código, de modo que reproducir los resultados de este repositorio exige instalar exactamente las versiones declaradas.

## El repositorio de prueba

El corpus se clona dentro de la carpeta del proyecto, en `corpus/`. Así todo lo que hace falta para ejecutar y reproducir queda bajo un mismo directorio y los comandos funcionan igual en cualquier máquina sin tener que ajustar rutas.

Desde la raíz del proyecto:

```bash
git clone https://github.com/argoproj/argo-cd.git corpus/argo-cd
```

La carpeta `corpus/` está en `.gitignore`, de modo que el contenido clonado no entra a este repositorio.

**El clon completo es el recomendado.** Son unos 470 MB. Un clon parcial con `--filter=blob:none` ocupa unos 60 MB y da los mismos resultados en las cuatro métricas, pero la de fiabilidad trabaja más lento: esa métrica recorre el historial de un conjunto de líneas, y sobre un clon parcial cada versión antigua que el recorrido necesita se descarga de la red en el momento. Antes de que el rastreo se acotara a la fecha de la corrección, ese recorrido abarcaba el historial completo del archivo y sobre un clon parcial la evaluación no llegaba a terminar.

## Uso

Desde la raíz del proyecto:

```bash
python -m patcheval --repo corpus/argo-cd --commit 2df5f7572
```

Desde código:

```python
from patcheval import Repositorio
from patcheval.metrics import complexity, deployment, dispersion, reliability

repo = Repositorio("corpus/argo-cd")
c = repo.cargar_correccion("2df5f7572")

print(c.mensaje)
print(f"{len(c.archivos)} archivos, +{c.total_agregadas} / -{c.total_eliminadas}")
print(complexity.medir(repo, c)["delta_ccn"])
print(dispersion.medir(repo, c)["proporcion"])
print(deployment.medir(repo, c)["total_introducidas"])
print(reliability.medir(repo, c)["parches_complementarios"])
```

También acepta una URL en `--repo`, en cuyo caso clona el repositorio antes de trabajar sobre él.

## Cómo verificar que la instalación quedó bien

### Las pruebas

```bash
python -m unittest discover tests
```

Tienen que dar 32 OK. Veintidós verifican el detector de configuraciones inseguras y diez la métrica de fiabilidad.

El detector se verifica sobre manifiestos construidos para la prueba, con un caso positivo y uno negativo por cada una de las ocho categorías. Se hace así y no sobre una corrección real porque ninguna de las correcciones del corpus introduce ni resuelve estas configuraciones. Esa ausencia es un resultado de la aplicación, no una falla del detector, y las pruebas construidas son lo que permite distinguir una cosa de la otra.

Las pruebas de fiabilidad construyen un repositorio temporal con confirmaciones de cambio fabricadas y fechas fijadas. Dos de ellas sostienen la corrección documentada en el capítulo 4: una comprueba que un cambio posterior sobre las mismas líneas sí se detecta, y otra que un cambio sobre otras líneas del mismo archivo no se detecta, aun cuando su mensaje contenga las mismas palabras.

### Valores esperados

Sobre la corrección `2df5f7572` de Argo CD, con las versiones declaradas en `requirements.txt`:

| Medida | Valor |
|---|---|
| Archivos modificados | 50 |
| Líneas agregadas y eliminadas | +3759 / -287 |
| Servicios del repositorio | 20 |
| Archivos de código alcanzados | 17 |
| Complejidad antes y después | 343 y 509 |
| Variación de complejidad | +166 |
| Servicios afectados | 4 de 20 (0.2) |
| Manifiestos modificados | 17 |
| Configuraciones introducidas y resueltas | 0 y 0 |
| Cambios posteriores sobre las líneas | 5 |
| Candidatos a parche complementario | 1 |
| Días hasta el primero | 81 |

Si los valores de complejidad salen distintos, la causa más probable es la versión de lizard. Verificar con `python -m pip show lizard` que sea 1.17.10.

Los valores de fiabilidad corresponden a la ventana de 90 días fijada en `VENTANA_DIAS`. Es una decisión del investigador y viaja en la salida del prototipo: quien no esté de acuerdo puede cambiarla y volver a medir.

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