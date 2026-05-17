from flask import Flask, request, jsonify, send_from_directory
import uuid
from kubernetes import client, config
import textwrap
import time

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
from kubernetes import client, config
from datetime import datetime

def customer_function(data: dict):

    config.load_incluster_config()

    v1 = client.CoreV1Api()

    timestamp = datetime.now().strftime("%H-%M-%S")

    cmap_name = f"demo-faas-result-cmap--KANICOOO--{timestamp}"

    cmap_data = {
        str(k): str(v)
        for k, v in data.items()
    }

    config_map = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=cmap_name),
        data=cmap_data
    )

    v1.create_namespaced_config_map(
        namespace="default",
        body=config_map
    )

    return cmap_name

app = Flask(__name__)

@app.route("/", methods=['POST'])
def home():

    data = {}

    try:
        data = request.get_json(force=True)
    except:
        data = { "errore-faas":"nessun parametro ricevuto"}

    customer_result = customer_function(data)

    return jsonify({
            "status": "success in faas",
            "message": "Funzione eseguita correttamente",
            "configmap-created": customer_result,
            "data":data
        }), 200

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
'''

DOCKERFILE = r'''
FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir flask
RUN pip install --no-cache-dir kubernetes

EXPOSE 5000

CMD ["python", "app.py"]
'''

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

    


def create_dockerhub_package_old():

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
                                "--destination=gio8134/demo-faas-kanico-package:1.0",
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
        "docker-image": "gio8134/demo-faas-kanico-package:1.0"
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