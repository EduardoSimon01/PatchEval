"""
Pruebas del detector de configuraciones inseguras.

Estas pruebas existen porque al aplicar el marco sobre el corpus, ninguna de las 26 correcciones evaluadas introdujo ni resolvio
configuraciones inseguras.

Con estos manifiestos fabricados a proposito cada regla se prueba contra un caso que debe marcar y contra uno que no, de modo que
 queda verificado por construccion y no depende de que el corpus tenga la suerte de contener el caso.

Esto corre con  python -m unittest discover tests
"""

import unittest

from patcheval.metrics import deployment


def contar(texto, categoria):
    return deployment.detectar(texto)[categoria]


class PruebaSecretos(unittest.TestCase):

    def test_valor_escrito_en_la_variable_se_marca(self):
        # El patron name/value de Kubernetes trae el dato es sensible y el valor viene escrito alli mismo.
        m = """
        kind: Deployment
        spec:
          containers:
          - name: app
            env:
            - name: DB_PASSWORD
              value: superclave123
        """
        self.assertEqual(contar(m, "secretos_incrustados"), 1)

    def test_referencia_a_un_secret_no_se_marca(self):
        # valueFrom apunta a un Secret de Kubernetes en vez de traer el dato que es la forma correcta y no debe marcarse.
        m = """
        kind: Deployment
        spec:
          containers:
          - name: app
            env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-creds
                  key: password
        """
        self.assertEqual(contar(m, "secretos_incrustados"), 0)

    def test_volumen_que_referencia_un_secret_no_se_marca(self):
        # Este es el caso que lo marcaba mal. El patron usaba \\s, entonces inluia el salto de linea, asi que tomaba la clave "secret:"
        # y leia el "secretName" de la linea siguiente como si fuera su valor y terminaba marcando como problema justo lo contrario.
        m = """
        kind: Deployment
        spec:
          volumes:
          - name: tls
            secret:
              secretName: argocd-repo-server-tls
        """
        self.assertEqual(contar(m, "secretos_incrustados"), 0)


class PruebaPrivilegios(unittest.TestCase):

    def test_contenedor_privilegiado(self):
        m = """
        kind: Pod
        spec:
          containers:
          - name: app
            securityContext:
              privileged: true
        """
        self.assertEqual(contar(m, "privilegios_excesivos"), 1)

    def test_tres_formas_distintas_suman_por_separado(self):
        # Un contenedor puede traer las tres a la vez y cada una es un problema en si, de modo que se cuentan aparte.
        m = """
        kind: Pod
        spec:
          containers:
          - name: app
            securityContext:
              privileged: true
              allowPrivilegeEscalation: true
              runAsUser: 0
        """
        self.assertEqual(contar(m, "privilegios_excesivos"), 3)

    def test_contenedor_endurecido_no_se_marca(self):
        m = """
        kind: Pod
        spec:
          containers:
          - name: app
            securityContext:
              privileged: false
              allowPrivilegeEscalation: false
              runAsNonRoot: true
        """
        self.assertEqual(contar(m, "privilegios_excesivos"), 0)


class PruebaPermisos(unittest.TestCase):

    def test_comodin_en_verbos(self):
        m = """
        kind: ClusterRole
        rules:
        - verbs: ["*"]
          resources: ["pods"]
        """
        self.assertEqual(contar(m, "permisos_amplios"), 1)

    def test_permisos_acotados_no_se_marcan(self):
        m = """
        kind: ClusterRole
        rules:
        - verbs: ["get", "list"]
          resources: ["pods"]
        """
        self.assertEqual(contar(m, "permisos_amplios"), 0)


class PruebaCifrado(unittest.TestCase):

    def test_http_hacia_afuera(self):
        self.assertEqual(contar("url: http://api.ejemplo.com/datos", "sin_cifrado"), 1)

    def test_http_a_localhost_no_se_marca(self):
        # Trafico que no sale de la maquina. Marcarlo seria por gusto.
        self.assertEqual(contar("url: http://localhost:8080/salud", "sin_cifrado"), 0)

    def test_https_no_se_marca(self):
        self.assertEqual(contar("url: https://api.ejemplo.com/datos", "sin_cifrado"), 0)


class PruebaExposicion(unittest.TestCase):

    def test_loadbalancer(self):
        # Un Service de tipo LoadBalancer le pide al proveedor de nube una IP publica, o sea que el servicio queda alcanzable.
        self.assertEqual(contar("kind: Service\nspec:\n  type: LoadBalancer", "exposicion_puertos"), 1)

    def test_clusterip_no_se_marca(self):
        # ClusterIP es el tipo por defecto y solo es alcanzable desde adentro del cluster.
        self.assertEqual(contar("kind: Service\nspec:\n  type: ClusterIP", "exposicion_puertos"), 0)


class PruebaRaizEscribible(unittest.TestCase):

    def test_ausencia_del_campo_cuenta(self):
        # El valor por defecto de Kubernetes es escribible, de modo que no declararlo es lo mismo declararlo en false.
        m = "kind: Pod\nspec:\n  containers:\n  - name: app\n    securityContext: {}"
        self.assertEqual(contar(m, "raiz_escribible"), 1)

    def test_solo_lectura_no_se_marca(self):
        m = "kind: Pod\nspec:\n  containers:\n  - name: app\n    securityContext:\n      readOnlyRootFilesystem: true"
        self.assertEqual(contar(m, "raiz_escribible"), 0)


class PruebaImagen(unittest.TestCase):

    def test_etiqueta_latest(self):
        # latest es una etiqueta entonces hoy apunta a una imagen y despues a otra.
        m = "kind: Pod\nspec:\n  containers:\n  - name: app\n    image: miapp:latest"
        self.assertEqual(contar(m, "imagen_sin_version"), 1)

    def test_sin_etiqueta(self):
        # Sin etiqueta Kubernetes asume latest y nos da el mismo problema
        m = "kind: Pod\nspec:\n  containers:\n  - name: app\n    image: miapp"
        self.assertEqual(contar(m, "imagen_sin_version"), 1)

    def test_fijada_por_digest_no_se_marca(self):
        # El digest es el hash de la imagen que siempre apunta a los mismos bytes y nadie lo puede mover. Es la forma reproducible.
        m = "kind: Pod\nspec:\n  containers:\n  - name: app\n    image: miapp@sha256:abc123def456"
        self.assertEqual(contar(m, "imagen_sin_version"), 0)


class PruebaPonderacion(unittest.TestCase):

    def test_la_severidad_multiplica(self):
        # Tres de severidad alta valen 9, una de media vale 2, una de baja vale 1.
        h = {k: 0 for k in deployment.CATEGORIAS}
        h["secretos_incrustados"] = 3
        h["sin_cifrado"] = 1
        h["imagen_sin_version"] = 1
        self.assertEqual(deployment.ponderar(h), 3 * 3 + 2 + 1)


class PruebaRobustez(unittest.TestCase):

    def test_yaml_invalido_no_revienta(self):
        # Los repos tienen plantillas de Helm con {{ }} que no son YAML valido. No vale la pena hecharse todo por eso.
        h = deployment.detectar("kind: Deployment\nname: {{ .Values.nombre }}\n  mal: [")
        self.assertIsInstance(h, dict)

    def test_contenido_vacio(self):
        self.assertEqual(deployment.detectar(None)["secretos_incrustados"], 0)
        self.assertEqual(deployment.detectar("")["secretos_incrustados"], 0)

    def test_varios_documentos_en_un_archivo(self):
        # Un archivo de Kubernetes suele traer varios documentos separados por --- si solo se lee el primero, el resto pasaria sin revisar.
        # Hay que tener cuidado con la indentacion porque el --- tiene que ir pegado al margen izquierdo con identacion deja de ser separador de documentos y YAML
        # lo lee como parte del contenido, con lo que el segundo Service nunca aparece. Me paso al escribir la prueba y tardo en verse.
        m = (
            "kind: Service\n"
            "spec:\n"
            "  type: LoadBalancer\n"
            "---\n"
            "kind: Service\n"
            "spec:\n"
            "  type: NodePort\n"
        )
        self.assertEqual(contar(m, "exposicion_puertos"), 2)


if __name__ == "__main__":
    unittest.main()