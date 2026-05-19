from flask import Flask, request, jsonify, send_from_directory
import uuid
from kubernetes import client, config
import textwrap
import time
import subprocess
import yaml

app = Flask(__name__, static_folder='.')

# =========================
# DATABASE MOCK
# =========================

TENANTS_DB = {
    "tenant-list": [
        {"tenant-name": "bancaintesa", "workspace-name": "ws1"},
        {"tenant-name": "poste", "workspace-name": "ws3"},
        {"tenant-name": "poste", "workspace-name": "ws4"}
    ]
}

IAM_DB = {
    "departments": ["marketing", "operation", "mobile core"]
}

CRD_DB = [
    {
        "kind": "TimMultiCloudCluster",
        "short": "tmcc",
        "status": ["creating","created","ready","error"]
    },
    {
        "kind": "TimMultiCloudVirtualMachine",
        "short": "tmcvm",
        "status": ["creating","created","ready","error"]
    }
]

# =========================
# TEMPLATE FILES
# =========================

APP_PY = r'''
from flask import Flask, request, jsonify
import os
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
app = Flask(__name__)
@app.route("/", methods=['POST'])
def handler():
    data = request.get_json(force=True)
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    timestamp = datetime.now().strftime("%H-%M-%S")
    cmap_name = f"demo-faas-result-cmap--{timestamp}"
    cmap_data = {
        str(k): str(v)
        for k, v in data.items()
    }
    config_map = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=cmap_name),
        data=cmap_data
    )
    v1.create_namespaced_config_map(
        namespace=data.get("faas-namespace","default"),
        body=config_map
    )
    return jsonify({
            "status": "success in faas",
            "message": "FAAS eseguita correttamente",
            "data": data
        }), 200
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT", 8080)))
'''

DOCKERFILE = r'''
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir flask
RUN pip install --no-cache-dir kubernetes
EXPOSE 8080
CMD ["python", "app.py"]
'''

# =========================
# UPDATE FAAS LIST CONFIGMAP
# =========================

from kubernetes import client, config
from kubernetes.client.rest import ApiException


def wait_for_job(job_name, namespace="default", timeout=300):
    config.load_incluster_config()
    batch = client.BatchV1Api()
    start = time.time()
    while time.time() - start < timeout:
        job = batch.read_namespaced_job(
            name=job_name,
            namespace=namespace
        )
        if job.status.succeeded:
            return True
        if job.status.failed:
            raise RuntimeError("Kaniko build failed")
        time.sleep(2)
    raise TimeoutError("Kaniko build timeout")


def add_package(
    package: str,
    configmap_name: str = "faas-packages-list",
    namespace: str = "default",
    url_package: str = "",
    ns_package: str = ""
) -> None:

    # Carica la configurazione Kubernetes dal POD
    config.load_incluster_config()

    v1 = client.CoreV1Api()

    try:
        # Legge la ConfigMap
        configmap = v1.read_namespaced_config_map(
            name=configmap_name,
            namespace=namespace
        )

        # Recupera il contenuto YAML del campo packages
        packages_raw = (
            configmap.data.get("packages", "")
            if configmap.data else ""
        )

        # Parsing YAML -> lista Python
        packages = yaml.safe_load(packages_raw) or []

        # Verifica se il package esiste già
        already_exists = any(
            p.get("faas-name") == package
            for p in packages
        )

        # Aggiunge nuovo oggetto
        if not already_exists:
            packages.append({
                "faas-name": package,
                "faas-url": url_package,
                "faas-namespace": ns_package
            })

        # Assicura che data esista
        if configmap.data is None:
            configmap.data = {}

        # Serializza nuovamente in YAML
        configmap.data["packages"] = yaml.dump(
            packages,
            default_flow_style=False
        )

        # Aggiorna la ConfigMap
        v1.patch_namespaced_config_map(
            name=configmap_name,
            namespace=namespace,
            body=configmap
        )

    except ApiException as e:
        raise RuntimeError(
            f"Errore Kubernetes API ({e.status}): {e.reason}"
        ) from e






def create_namespace(namespace_name: str) -> bool:
    # Carica automaticamente la configurazione in-cluster
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    try:
        # Verifica se il namespace esiste già
        v1.read_namespace(name=namespace_name)
        print(f"Namespace '{namespace_name}' già esistente.")
        return False
    except ApiException as e:
        if e.status != 404:
            raise
    # Namespace non trovato -> creazione
    namespace = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=namespace_name)
    )
    v1.create_namespace(body=namespace)
    print(f"Namespace '{namespace_name}' creato con successo.")
    return True


def create_knative_service(
    namespace: str,
    service_name: str = "demo-faas-sheepcounter",
    image: str = "gio8134/demo-faas-sheepcounter:6.0"
) -> bool:
    # Configurazione in-cluster
    config.load_incluster_config()
    # CustomObjectsApi serve per CRD come Knative
    api = client.CustomObjectsApi()
    group = "serving.knative.dev"
    version = "v1"
    plural = "services"
    try:
        # Verifica esistenza
        api.get_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=service_name
        )
        return False
    except ApiException as e:
        if e.status != 404:
            raise
    # Manifest Knative Service
    body = {
        "apiVersion": "serving.knative.dev/v1",
        "kind": "Service",
        "metadata": {
            "name": service_name,
            "namespace": namespace
        },
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "autoscaling.knative.dev/minScale": "0",
                        "autoscaling.knative.dev/maxScale": "1"
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "image": image,
                            "ports": [
                                {
                                    "containerPort": 8080
                                }
                            ],
                            "readinessProbe": {
                                "httpGet": {
                                    "path": "/",
                                    "port": 8080
                                },
                                "initialDelaySeconds": 2,
                                "periodSeconds": 5
                            }
                        }
                    ]
                }
            }
        }
    }
    # Creazione Knative Service
    api.create_namespaced_custom_object(
        group=group,
        version=version,
        namespace=namespace,
        plural=plural,
        body=body
    )
    return True


# =========================
# CREATE DOCKER PACKAGE
# =========================


def create_dockerhub_package(author, pkg_name, pkg_version):

    destination = f"{author}/{pkg_name}:{pkg_version}"
    config.load_incluster_config()

    v1 = client.CoreV1Api()
    batch = client.BatchV1Api()

    timestamp = str(int(time.time()))

    configmap_name = f"faas-build-context-{timestamp}"
    job_name = f"kaniko-build-{timestamp}"

    # ====================================
    # CREATE CONFIGMAP WITH BUILD FILES
    # ====================================

    cmap = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=configmap_name
        ),
        data={
            "app.py": APP_PY,
            "Dockerfile": DOCKERFILE
        }
    )

    v1.create_namespaced_config_map(
        namespace="default",
        body=cmap
    )

    # ====================================
    # KANIKO JOB
    # ====================================

    job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name
        ),
        spec=client.V1JobSpec(
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",

                    containers=[
                        client.V1Container(
                            name="kaniko",

                            image="gcr.io/kaniko-project/executor:latest",

                            args=[
                                "--dockerfile=/workspace/Dockerfile",
                                "--context=/workspace",
                                f"--destination={destination}",
                                "--skip-tls-verify"
                            ],

                            volume_mounts=[

                                client.V1VolumeMount(
                                    name="build-context",
                                    mount_path="/workspace"
                                ),

                                client.V1VolumeMount(
                                    name="docker-config",
                                    mount_path="/kaniko/.docker"
                                )
                            ]
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="build-context",

                            config_map=client.V1ConfigMapVolumeSource(
                                name=configmap_name
                            )
                        ),
                        client.V1Volume(
                            name="docker-config",
                            secret=client.V1SecretVolumeSource(
                                secret_name="dockerhub-secret",
                                items=[
                                    client.V1KeyToPath(
                                        key=".dockerconfigjson",
                                        path="config.json"
                                    )
                                ]
                            )
                        )
                    ]
                )
            )
        )
    )
    batch.create_namespaced_job(
        namespace="default",
        body=job
    )

    return {
        "job-name": job_name,
        "configmap-name": configmap_name,
        "docker-image": destination
    }

    
# =========================
# ROUTES
# =========================

@app.route('/post-faas-creation-request', methods=['POST'])
def post_faas():

    data = request.json

    # --- Mandatory fields ---
    for f in ["token", "author", "faas-name", "faas-source"]:
        if f not in data:
            return jsonify({"error": f"Missing {f}"}), 400


    author = data["author"]
    pkg_name = data["faas-source"]["target-registry-package-name"]
    pkg_version = data["faas-source"]["target-registry-package-version"]


    src = data["faas-source"]

    if src["source-type"] not in [
        "code",
        "registry package",
        "local package (zip)"
    ]:
        return jsonify({"error": "Invalid source-type"}), 400

    # --- Validate flags ---

    if not isinstance(data.get("flag-external-customer"), bool):
        return jsonify({
            "error": "flag-external-customer must be boolean"
        }), 400

    if not isinstance(data.get("flag-internal-use"), bool):
        return jsonify({
            "error": "flag-internal-use must be boolean"
        }), 400

    # --- Validate tenancy ---

    if data["flag-external-customer"]:

        for t in data.get("faas-tenancy", []):

            if t not in TENANTS_DB["tenant-list"]:

                return jsonify({
                    "error": f"Invalid tenancy {t}"
                }), 400
            
            else:
                create_namespace(f"{t.get('tenant-name')}-{t.get('workspace-name')}")
                create_knative_service(
                    f"{t.get('tenant-name')}-{t.get('workspace-name')}",
                    pkg_name,
                    f"{author}/{pkg_name}:{pkg_version}"
                )

    # --- Validate departments ---

    if data["flag-internal-use"]:

        for d in data.get("faas-internal-user", []):

            if d not in IAM_DB["departments"]:

                return jsonify({
                    "error": f"Invalid department {d}"
                }), 400

    # ==================================
    # BUILD DOCKER IMAGE
    # ==================================

    # build_result = create_dockerhub_package()
    
    build_result = create_dockerhub_package(
        author,
        pkg_name,
        pkg_version
    )
    
    #add_package(f"{author}/{pkg_name}:{pkg_version}")
    tbuf = f"{t.get('tenant-name')}-{t.get('workspace-name')}"
    pbuf = f"http://{pkg_name}.{tbuf}.svc.cluster.local"
    ppv = f"{pkg_name}:{pkg_version}"
    add_package(
        package=ppv,
        configmap_name="faas-packages-list",
        namespace="default",
        url_package=pbuf,
        ns_package=tbuf
    )
    

    return jsonify({
        "status": "OK",
        "message": "FaaS validated and accepted",
        "faas-id": str(uuid.uuid4()),
        "build-result": build_result
    })


@app.route('/home.html')
def home():
    return send_from_directory('.', 'home.html')


@app.route('/create_faas.html')
def create_faas():
    return send_from_directory('.', 'create_faas.html')


if __name__ == "__main__":

    app.run(
        host='0.0.0.0',
        port=5000
    )