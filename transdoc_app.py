"""
Flask web application for TransDocs - Document Translation and Proofreading Tool.
"""

import os
import requests as http_requests
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from werkzeug.utils import secure_filename

# Import from the src package
from src.transdoc import process_document

app = Flask(__name__, template_folder="templates")  # Templates in templates/ subfolder
app.secret_key = "your_secret_key"

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = "uploads/"
OUTPUT_FOLDER = "outputs/"
ALLOWED_EXTENSIONS = {"docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER

# Ensure the upload and output directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def build_models_endpoints(api_url, backend):
    """Build ordered model-list endpoint candidates for the selected backend."""
    base_url = api_url.rstrip("/")
    endpoints = []

    def add(url):
        if url not in endpoints:
            endpoints.append(url)

    if backend == "openai_compatible":
        if base_url.endswith(("/v1/models", "/models")):
            add(base_url)
        elif base_url.endswith("/v1"):
            add(f"{base_url}/models")
        else:
            add(f"{base_url}/v1/models")
        # Fallback for Ollama-style gateways
        if base_url.endswith("/api/tags"):
            add(base_url)
        else:
            add(f"{base_url}/api/tags")
        return endpoints

    # Default: ollama
    if base_url.endswith("/api/tags"):
        add(base_url)
    else:
        add(f"{base_url}/api/tags")
    # Fallback for OpenAI-compatible gateways
    if base_url.endswith(("/v1/models", "/models")):
        add(base_url)
    elif base_url.endswith("/v1"):
        add(f"{base_url}/models")
    else:
        add(f"{base_url}/v1/models")
    return endpoints


def extract_model_names(data):
    """Extract model names from either Ollama or OpenAI-compatible responses."""
    items = data.get("data", [])
    openai_models = [
        m.get("id") for m in items if isinstance(m, dict) and m.get("id")
    ]
    if openai_models:
        return openai_models
    items = data.get("models", [])
    return [m.get("name") for m in items if isinstance(m, dict) and m.get("name")]


@app.route("/query_ollama", methods=["POST"])  # backward-compatible endpoint name
@app.route("/query_models", methods=["POST"])
def query_models():
    """API endpoint to test backend connection and get available models."""
    api_url = request.form.get("api_url", "http://localhost:11434").strip()
    backend = request.form.get("backend", "ollama").strip() or "ollama"
    api_token = request.form.get("api_token", "").strip() or None
    if backend not in {"ollama", "openai_compatible"}:
        backend = "ollama"
    models_urls = build_models_endpoints(api_url, backend)
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
        headers["X-API-Key"] = api_token
        headers["api-key"] = api_token

    try:
        last_status = None
        last_text = ""
        for models_url in models_urls:
            response = http_requests.get(models_url, headers=headers, timeout=8)
            if response.status_code == 200:
                data = response.json()
                models = extract_model_names(data)
                return jsonify({"success": True, "models": models})
            last_status = response.status_code
            last_text = response.text[:500]
        return jsonify(
            {
                "success": False,
                "error": f"HTTP {last_status}",
                "details": last_text,
            }
        ), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        # Check if this is a test connection action (for backward compatibility)
        if request.form.get("action") == "test":
            api_url = request.form.get("api_url", "http://localhost:11434").strip()
            backend = request.form.get("backend", "ollama").strip() or "ollama"
            api_token = request.form.get("api_token", "").strip() or None
            models_urls = build_models_endpoints(api_url, backend)
            headers = {}
            if api_token:
                headers["Authorization"] = f"Bearer {api_token}"
                headers["X-API-Key"] = api_token
                headers["api-key"] = api_token

            try:
                model_names = []
                last_status = None
                for models_url in models_urls:
                    response = http_requests.get(models_url, headers=headers, timeout=8)
                    if response.status_code == 200:
                        data = response.json()
                        model_names = extract_model_names(data)
                        break
                    last_status = response.status_code
                if model_names:
                    result = "✓ Connected!"
                    return render_template(
                        "upload.html",
                        connection_result=result,
                        connection_success=True,
                        selected_backend=backend,
                        selected_api_url=api_url,
                    )
                if last_status:
                    result = f"✗ Connection failed! HTTP {last_status}"
                    return render_template(
                        "upload.html",
                        connection_result=result,
                        connection_success=False,
                        selected_backend=backend,
                        selected_api_url=api_url,
                    )
                result = "✓ Connected! No models loaded. Load a model first."
                return render_template(
                    "upload.html",
                    connection_result=result,
                    connection_success=True,
                    selected_backend=backend,
                    selected_api_url=api_url,
                )
            except Exception as e:
                result = (
                    f"✗ Connection failed!<br>Error: {str(e)}<br><br>"
                    "Check URL, backend type, and API token if required."
                )
                return render_template(
                    "upload.html",
                    connection_result=result,
                    connection_success=False,
                    selected_backend=backend,
                    selected_api_url=api_url,
                )

        # Get form data for translation
        file = request.files.get("input_file")
        target_lang = request.form.get("target_lang", "").strip()
        src_lang = request.form.get("src_lang", "").strip() or None
        api_token = request.form.get("api_token", "").strip() or None
        model = request.form.get("model", "")
        backend = request.form.get("backend", "ollama").strip() or "ollama"
        if backend not in {"ollama", "openai_compatible"}:
            backend = "ollama"

        if not model:
            return render_template(
                "upload.html",
                error="Please select a valid model from the dropdown (query first)",
                selected_backend=backend,
                selected_api_url=request.form.get("api_url", "http://localhost:11434").strip(),
            )
        model = model.strip()

        api_url = request.form.get("api_url", "http://localhost:11434").strip()

        logger = __import__("logging").getLogger(__name__)
        logger.debug(f"Using backend '{backend}' with API base URL: {api_url}")

        if not target_lang:
            return render_template(
                "upload.html",
                error="Target language is required",
                selected_backend=backend,
                selected_api_url=api_url,
            )

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            input_filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            output_filename = f"translated_{filename}"
            output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
            file.save(input_filepath)

            # Call your translation function here
            try:
                process_document(
                    input_filepath,
                    output_filepath,
                    model,
                    target_lang,
                    api_token,
                    src_lang,
                    api_url=api_url,
                    backend=backend,
                )
                return redirect(url_for("download_file", filename=output_filename))
            except Exception as e:
                return render_template(
                    "upload.html",
                    error=f"Error processing document: {str(e)}",
                    selected_backend=backend,
                    selected_api_url=api_url,
                )

        if not file or not allowed_file(file.filename):
            return render_template(
                "upload.html",
                error="Please upload a valid .docx file",
                selected_backend=backend,
                selected_api_url=api_url,
            )

    return render_template(
        "upload.html",
        selected_backend="ollama",
        selected_api_url="http://localhost:11434",
    )


@app.route("/downloads/<filename>")
def download_file(filename):
    return send_file(
        os.path.join(app.config["OUTPUT_FOLDER"], filename), as_attachment=True
    )


if __name__ == "__main__":
    import os

    debug = os.environ.get("FLASK_DEBUG", "0") != "0"
    host = os.environ.get(
        "FLASK_HOST", "0.0.0.0"
    )  # Default to all interfaces for LAN access
    app.run(host=host, debug=debug)
