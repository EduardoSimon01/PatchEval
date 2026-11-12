# patcheval

Evaluación automatizada de la eficacia y el costo arquitectónico de las correcciones de seguridad en sistemas cloud-native.

Trabajo de graduación de Angel Eduardo Tubac Simón, carné 202200309.

Escuela de Ingeniería en Ciencias y Sistemas, Facultad de Ingeniería, Universidad de San Carlos de Guatemala.

## Qué hace

Dado un repositorio y el identificador de una corrección de seguridad, el prototipo calcula un perfil de evaluación en dos dimensiones.

Eficacia: esta se divide en dos subdimensiones. La fiabilidad indica si alguien tuvo que volver sobre las mismas líneas que la corrección dejó, dentro de una ventana de tiempo declarada, con un cambio que señale que quedó incompleta. La completitud indica si la corrección atacó la causa del problema o solamente una de sus manifestaciones.

El prototipo determina la primera y no determina la segunda. Establecer la completitud exige una inferencia sobre el significado del código que el prototipo no está en condiciones de sostener de modo que queda declarada como parte del marco pero su determinación es manual.

Costo arquitectónico: Es la magnitud del deterioro que la corrección introduce respecto al estado inmediatamente anterior a su aplicación. Se observa en tres planos: el impacto estructural sobre el código, la dispersión del cambio entre los servicios del sistema y el efecto sobre la configuración de despliegue.

Ninguna de las dos dimensiones se resume en un número único. El resultado es un perfil, y las cuatro medidas se leen por separado.

## Estado

Terminado. Los seis hitos cerrados y la evaluación aplicada al corpus completo.

| Hito | Qué construye | Estado |
|------|---------------|--------|
| H1 | Acceso al repositorio y al par de versiones | listo |
| H2 | Impacto estructural y dispersión del cambio | listo |
| H3 | Impacto de despliegue sobre manifiestos | listo |
| H4 | Fiabilidad de la corrección | listo |
| H5 | Construcción del perfil y clasificación por cuartiles | listo |
| H6 | Aplicación al corpus completo y contraste | listo |

## Instalación

Requiere Python 3.10 o superior y git.

```bash
git clone https://github.com/EduardoSimon01/PatchEval.git
cd PatchEval
python -m pip install -r requirements.txt
```

No hace falta configurar nada más. El prototipo no usa base de datos, no levanta servicios y no necesita credenciales ni archivos de entorno: trabaja directamente sobre repositorios clonados en el disco.

Las versiones de las tres dependencias están fijadas en `requirements.txt` y no es un detalle menor. Las mediciones de complejidad dependen de la versión de lizard: una versión distinta devuelve valores distintos sobre el mismo código, de modo que reproducir los resultados de este repositorio exige instalar exactamente las versiones declaradas.

## Los repositorios del corpus

Se clonan dentro de la carpeta del proyecto, en `corpus/`. Así todo lo que hace falta para ejecutar y reproducir queda bajo un mismo directorio y los comandos funcionan igual en cualquier máquina sin ajustar rutas. La carpeta `corpus/` está en `.gitignore`.

Desde la raíz del proyecto:

```bash
git clone https://github.com/argoproj/argo-cd.git corpus/argo-cd
git clone https://github.com/goharbor/harbor.git corpus/harbor
git clone https://github.com/keycloak/keycloak.git corpus/keycloak
```

Son unos 1,100 MB comprimidos y alrededor de 3 GB en disco con el árbol de trabajo.

**Los clones tienen que ser completos.** Un clon parcial con `--filter=blob:none` ocupa mucho menos y funciona para las tres métricas de costo, que solo consultan dos versiones, pero vuelve impracticable la de fiabilidad porque esa métrica recorre el historial de un conjunto de líneas y sobre un clon parcial cada versión antigua que el recorrido necesita se descarga de la red en el momento. Sobre un clon completo la evaluación entera del corpus toma unos 36 minutos.

## Uso

El prototipo tiene cuatro modos.

**Una corrección suelta** para mirar un caso:

```bash
python -m patcheval --repo corpus/argo-cd --commit 8b2f081ded
```

**Descubrir las correcciones de un repositorio** que aplica el criterio de selección del corpus e imprime las entradas listas para pegar:

```bash
python -m patcheval --descubrir corpus/harbor --proyecto harbor
```

**Evaluar el corpus completo** esto mide cada corrección, selecciona su línea base, clasifica el conjunto por cuartiles y guarda los perfiles:

```bash
python -m patcheval --corpus corpus.yaml
```

**Analizar los perfiles guardados** que contrasta las correcciones contra su línea base sin volver a medir nada:

```bash
python -m patcheval --analizar
```

También acepta una URL en `--repo`, en cuyo caso clona el repositorio antes de trabajar sobre él.

## Cómo se arma el corpus

La lista de correcciones no se escoge a mano. El modo `--descubrir` aplica el criterio de que si una corrección entra si el mensaje de su commit menciona un aviso de seguridad publicado (GHSA o CVE), si no es una actualización automática de dependencias, si no la firmó una herramienta, si no menciona más de dos avisos (eso serían notas de versión y no un arreglo) y si toca al menos un archivo de código. Cuando varios commits citan el mismo aviso se toma el más antiguo porque es el que aplica la corrección y los posteriores son justamente lo que la métrica de fiabilidad debe encontrar por su cuenta.

Las correcciones descartadas se reportan con su motivo, de modo que se pueda revisar qué quedó afuera y por qué.

La línea base se selecciona con el mismo rigor. Por cada corrección se buscan cambios ordinarios del mismo proyecto dentro de una ventana de ciento ochenta días a su alrededor, se descartan los que parezcan de seguridad, los automáticos y los firmados por herramientas y de lo que queda se toman tres repartidos de forma pareja a lo largo de la ventana. El muestreo es determinístico y no usa azar asi hacemos que no haga falta declarar ninguna semilla para poder repetirlo.

## Cómo verificar que la instalación quedó bien

### Las pruebas

```bash
python -m unittest discover tests
```

Tienen que dar **87 OK**: el detector de configuraciones inseguras, la métrica de fiabilidad, la densidad de decisión, la clasificación por cuartiles, los filtros de la línea base, la extracción de identificadores de aviso, la asignación de servicios y la prueba de rangos con signo.

El detector de configuraciones inseguras se verifica sobre manifiestos construidos para la prueba, con un caso positivo y uno negativo por cada una de las ocho categorías. Se hace así y no sobre una corrección real porque casi ninguna corrección del corpus introduce ni resuelve estas configuraciones. Esa ausencia es un resultado de la aplicación, no una falla del detector y las pruebas construidas son lo que permite distinguir una cosa de la otra.

Las pruebas de fiabilidad construyen un repositorio temporal con confirmaciones de cambio fabricadas y fechas fijadas. Dos de ellas sostienen una corrección documentada una comprueba que un cambio posterior sobre las mismas líneas sí se detecta y otra que un cambio sobre otras líneas del mismo archivo no se detecta aun cuando su mensaje contenga las mismas palabras.

### Valores esperados de una corrección

Sobre la corrección `8b2f081ded` de Argo CD, que corresponde al aviso GHSA-PMJG-52H9-72QV, con las versiones declaradas en `requirements.txt`:

| Medida | Valor |
|---|---|
| Archivos modificados | 2 |
| Líneas agregadas y eliminadas | +64 / -4 |
| Servicios del repositorio | 17 |
| Archivos de código alcanzados | 2 |
| Complejidad antes y después | 93 y 100 |
| Variación de complejidad | +7 |
| Densidad de decisión | 10.94 por cada 100 líneas |
| Servicios afectados | 1 de 17 (0.0588) |
| Manifiestos modificados | 0 |
| Configuraciones introducidas y resueltas | 0 y 0 |
| Cambios posteriores sobre las líneas | 3 |
| Candidatos a parche complementario | 1 |
| Días hasta el primero | 0 |

Si los valores de complejidad salen distintos, la causa más probable es la versión de lizard. Verificar con `python -m pip show lizard` que sea 1.17.10.

Los valores de fiabilidad corresponden a la ventana de noventa días fijada en `VENTANA_DIAS`. Es una decisión del investigador y viaja en la salida del prototipo quien no esté de acuerdo puede cambiarla y volver a medir.

El candidato que reporta esta corrección ilustra por qué el prototipo entrega candidatos y no veredictos el commit señalado es otra corrección del mismo corpus, publicada el mismo día y sobre las mismas líneas. No es un parche posterior sino uno hermano de un lanzamiento coordinado. La revisión manual es la que distingue una cosa de la otra.

## Cómo reproducir los resultados del trabajo

Con los tres repositorios clonados:

```bash
python -m patcheval --corpus corpus.yaml
python -m patcheval --analizar
```

La primera orden toma unos 36 minutos y deja los perfiles en `resultados/perfiles.json` y `resultados/perfiles.csv`. La segunda es instantánea y produce el contraste.

El corpus son **109 correcciones de seguridad** de tres proyectos, más 327 cambios ordinarios como línea base:

| Proyecto | Lenguaje | Correcciones | Raíz de servicios |
|---|---|---|---|
| Argo CD | Go | 37 | raíz del repositorio |
| Harbor | Go | 10 | `src` |
| Keycloak | Java | 62 | raíz del repositorio |

El contraste se hace con la prueba de rangos con signo de Wilcoxon, α = 0.05, emparejando cada corrección con la mediana de sus tres cambios ordinarios. Los valores de p que tienen que salir:

| Medida | Argo CD (37) | Harbor (10) | Keycloak (62) | Todos (109) |
|---|---|---|---|---|
| Complejidad | 0.0024 | 0.6462 | 0.0462 | 0.0008 |
| Densidad de decisión | 0.0052 | 0.1263 | 0.0072 | 0.0001 |
| Dispersión | 0.0304 | sin pares | 0.0000 | 0.0000 |
| Despliegue | sin pares | sin pares | sin pares | sin pares |

Las tres dimensiones de costo salen mayores en las correcciones de seguridad que en los cambios ordinarios del mismo proyecto y de la misma época. Harbor no alcanza significancia en ninguna y la causa es el tamaño de su muestra. El impacto de despliegue no se puede contrastar en ningún proyecto porque sobre las 109 correcciones menos de seis tocan configuración de despliegue.

Esta evaluación se ejecutó dos veces de forma independiente y produjo perfiles idénticos en los 436 casos.

## Condiciones de reproducibilidad

Tres cosas tienen que coincidir para obtener los mismos números.

**Las versiones de las dependencias.** La complejidad ciclomática depende de la versión de lizard es decir que una posterior reconoce construcciones del lenguaje que la anterior no contabilizaba.

**El estado del repositorio.** La métrica de fiabilidad mira hacia adelante en la historia cuenta lo que vino después de la corrección y eso sigue creciendo mientras el proyecto viva. Las tres métricas de costo comparan dos versiones fijas y dan lo mismo siempre, pero la fiabilidad medida hoy puede no coincidir con la medida el año entrante. Por eso cada perfil registra el identificador del estado del repositorio contra el que se midió, en el campo `head`.

**El clon completo.** Explicado arriba.

Hay además una decisión de implementación que conviene conocer. El prototipo **no delega a git el recorte temporal** osea que en sus recorridos no usa `--since` ni `--until`. Esas banderas no filtran la lista al final sino que le indican a git que deje de recorrer la historia cuando cree que ya pasó la fecha y esa decisión depende de cachés que git regenera por su cuenta. Durante el desarrollo eso produjo resultados distintos entre dos ejecuciones sobre el mismo repositorio, el mismo código y el mismo estado. Todos los recortes por fecha se hacen en Python, donde la comparación es exacta.

## Proyectos sobre los que se aplica

Las correcciones evaluadas provienen de proyectos cloud-native de código abierto con historial público y avisos de seguridad formales:

- [Argo CD](https://github.com/argoproj/argo-cd) — entrega continua para Kubernetes
- [Harbor](https://github.com/goharbor/harbor) — registro de contenedores
- [Keycloak](https://github.com/keycloak/keycloak) — gestión de identidad y acceso

Keycloak entra por que está escrito en Java y organiza su código de forma distinta a los otros dos de modo que permite comprobar si el marco funciona fuera de un solo lenguaje y una sola convención de estructura.

Se consideró también [Traefik](https://github.com/traefik/traefik) y quedó fuera no porque el criterio lo rechazara sino porque ese proyecto no menciona el identificador del aviso en ningún mensaje de commit de toda su historia de modo que no hay de dónde descubrir nada. Es una limitación del método y está declarada como tal el descubrimiento solo funciona sobre proyectos que citan el aviso al corregir.

Cada corrección se identifica por su proyecto, por el identificador de su confirmación de cambio y por el aviso que la respalda, de modo que cualquier lector puede situarse en el mismo punto de la historia y repetir la medición.

## Dependencias

| Biblioteca | Para qué | Licencia |
|---|---|---|
| GitPython | acceso al historial de versiones | BSD de 3 cláusulas |
| lizard | complejidad ciclomática multilenguaje | MIT |
| PyYAML | análisis de manifiestos de despliegue | MIT |

La prueba de rangos con signo está implementada en el propio prototipo sin biblioteca para no agregar una dependencia pesada por una sola función. Se verificó contra una implementación de referencia.

## Licencia

MIT. Ver el archivo LICENSE.