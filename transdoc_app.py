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


@app.route("/query_ollama", methods=["POST"])
def query_ollama():
    """API endpoint to test Ollama connection and get available models."""
    api_url = request.form.get("api_url", "http://localhost:11434").strip()

    try:
        response = http_requests.get(f"{api_url}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return jsonify({"success": True, "models": models})
        else:
            return jsonify(
                {"success": False, "error": f"HTTP {response.status_code}"}
            ), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        # Check if this is a test connection action (for backward compatibility)
        if request.form.get("action") == "test":
            api_url = request.form.get("api_url", "http://localhost:11434").strip()

            try:
                response = http_requests.get(f"{api_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    model_names = [m["name"] for m in models] if models else []

                    if model_names:
                        result = f"✓ Connected successfully!<br>Available models: {', '.join(model_names)}"
                        return render_template(
                            "upload.html",
                            connection_result=result,
                            connection_success=True,
                        )
                    else:
                        result = "✓ Connected! No models loaded. Load a model first."
                        return render_template(
                            "upload.html",
                            connection_result=result,
                            connection_success=True,
                        )
                else:
                    result = f"✗ Connection failed! HTTP {response.status_code}"
                    return render_template(
                        "upload.html",
                        connection_result=result,
                        connection_success=False,
                    )
            except Exception as e:
                result = f"✗ Connection failed!<br>Error: {str(e)}<br><br>Make sure Ollama is running and the URL is correct."
                return render_template(
                    "upload.html", connection_result=result, connection_success=False
                )

        # Get form data for translation
        file = request.files.get("input_file")
        target_lang = request.form.get("target_lang", "").strip()
        src_lang = request.form.get("src_lang", "").strip() or None
        api_token = request.form.get("api_token", "").strip() or None
        model = request.form.get("model", "")

        if not model:
            return render_template(
                "upload.html",
                error="Please select a valid model from the dropdown (query first)",
            )
        model = model.strip()

        api_url = request.form.get("api_url", "http://localhost:11434").strip()

        # Auto-append /api/chat endpoint (modern Ollama API)
        if not api_url.endswith(("/api/generate", "/api/chat")):
            api_url = f"{api_url.rstrip('/')}/api/chat"

        logger = __import__("logging").getLogger(__name__)
        logger.debug(f"Using API URL: {api_url}")

        if not target_lang:
            return render_template("upload.html", error="Target language is required")

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
                )
                return redirect(url_for("download_file", filename=output_filename))
            except Exception as e:
                return render_template(
                    "upload.html", error=f"Error processing document: {str(e)}"
                )

        if not file or not allowed_file(file.filename):
            return render_template(
                "upload.html", error="Please upload a valid .docx file"
            )

    return render_template("upload.html")


@app.route("/downloads/<filename>")
def download_file(filename):
    return send_file(
        os.path.join(app.config["OUTPUT_FOLDER"], filename), as_attachment=True
    )


if __name__ == "__main__":
    import os

    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    host = os.environ.get(
        "FLASK_HOST", "0.0.0.0"
    )  # Default to all interfaces for LAN access
    app.run(host=host, debug=debug)
