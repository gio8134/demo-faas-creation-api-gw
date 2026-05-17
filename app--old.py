from flask import Flask, request, jsonify, send_from_directory
import uuid

app = Flask(__name__, static_folder='.')

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


@app.route('/post-faas-creation-request', methods=['POST'])
def post_faas():
    data = request.json

    # --- Mandatory fields ---
    for f in ["token", "author", "faas-name", "faas-source"]:
        if f not in data:
            return jsonify({"error": f"Missing {f}"}), 400

    src = data["faas-source"]

    if src["source-type"] not in ["code","registry package","local package (zip)"]:
        return jsonify({"error": "Invalid source-type"}), 400

    # --- Validate flags ---
    if not isinstance(data.get("flag-external-customer"), bool):
        return jsonify({"error": "flag-external-customer must be boolean"}), 400

    if not isinstance(data.get("flag-internal-use"), bool):
        return jsonify({"error": "flag-internal-use must be boolean"}), 400

    # --- Validate tenancy ---
    if data["flag-external-customer"]:
        for t in data.get("faas-tenancy", []):
            if t not in TENANTS_DB["tenant-list"]:
                return jsonify({"error": f"Invalid tenancy {t}"}), 400

    # --- Validate departments ---
    if data["flag-internal-use"]:
        for d in data.get("faas-internal-user", []):
            if d not in IAM_DB["departments"]:
                return jsonify({"error": f"Invalid department {d}"}), 400

    return jsonify({
        "status": "OK",
        "message": "FaaS validated and accepted",
        "faas-id": str(uuid.uuid4())
    })


@app.route('/home.html')
def home():
    return send_from_directory('.', 'home.html')


@app.route('/create_faas.html')
def create_faas():
    return send_from_directory('.', 'create_faas.html')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)