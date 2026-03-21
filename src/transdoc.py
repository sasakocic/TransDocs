import re
import argparse
from docx import Document
import requests
import logging
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException


# ANSI color codes for colorful output
class ColorFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }

    RESET = "\033[0m"  # Reset color

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("translation_debug.log", "w", "utf-8")
console_handler = logging.StreamHandler()

file_handler.setLevel(logging.DEBUG)
console_handler.setLevel(logging.INFO)  # Output to console

# Use colorful formatter for console, plain text for file
console_formatter = ColorFormatter("%(asctime)s - %(levelname)s - %(message)s")
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

console_handler.setFormatter(console_formatter)
file_handler.setFormatter(file_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def detect_source_language(doc, min_words=50):
    """
    Detects the source language of the document by collecting text until reaching min_words.
    """
    collected_text = ""
    word_count = 0
    for para in doc.paragraphs:
        paragraph_text = "".join(run.text for run in para.runs).strip()
        if paragraph_text:
            collected_text += " " + paragraph_text
            word_count += len(paragraph_text.split())
            if word_count >= min_words:
                break

    if word_count == 0:
        logger.error("Not enough text to detect source language.")
        return None

    try:
        src_lang = detect(collected_text)
        logger.info(f"Detected source language: {src_lang}")
        return src_lang
    except LangDetectException as e:
        logger.error(f"Language detection failed: {e}")
        return None


def call_ollama_api(
    text, src_lang, target_lang, model, api_token, api_url, mode="translate"
):
    if mode == "proofread":
        prompt = f"""You are a professional proofreader and editor. Review the following text in {src_lang} for grammar, spelling, punctuation, clarity, and style improvements.

Rules:
- Keep math formulas (e.g., LaTeX, equations), code, symbols, URLs, numbers, dates, proper names unchanged.
- Preserve the original meaning while improving fluency, readability, and correctness.
- Fix grammatical errors, typos, and awkward phrasing.
- Maintain formatting, lists, emphasis, and document structure.
- Output ONLY the improved text—no explanations, comments, or notes about changes made.

Text: {text}"""
    else:  # translate mode
        prompt = f"""You are a professional translator like DeepL. Translate ONLY the text content from {src_lang} to {target_lang}.

Rules:
- Keep math formulas (e.g., LaTeX, equations), code, symbols, URLs, numbers, dates, proper names unchanged.
- Use precise technical terminology; preserve meaning, fluency, and structure (lists, emphasis).
- Output ONLY the translated text—no explanations, warnings, or extras.

Text: {text}"""

    payload = {"model": model, "prompt": prompt, "stream": False}

    headers = {"Content-Type": "application/json"}

    # Add authorization header only if token is provided
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        logger.debug(f"Sending API request with payload: {payload}")
        response = requests.post(api_url, json=payload, headers=headers)
        logger.debug(f"Received response with status code {response.status_code}")
        if response.status_code == 200:
            response_json = response.json()
            logger.debug(f"API response JSON: {response_json}")
            result_text = response_json.get("response", "").strip()
            logger.debug(f"{mode.capitalize()} text: {result_text}")
            return result_text
        else:
            logger.error(f"API request failed with status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return text
    except Exception as e:
        logger.exception(f"An error occurred while calling the Ollama API: {e}")
        return text


def translate_or_proofread(
    text, src_lang, target_lang, model, api_token, api_url, force_proofread=False
):
    logger.debug(f"Text to process: '{text}'")

    if not text or not text.strip():
        logger.warning(f"Text is empty or whitespace: '{text}'")
        return text

    # Determine mode based on explicit flag or language match
    if force_proofread:
        mode = "proofread"
        logger.info(f"Forced proofreading mode (explicit --proofread flag).")
    elif src_lang == target_lang:
        mode = "proofread"
        logger.info(
            f"Source and target languages are the same ({src_lang}). Running proofreading mode."
        )
    else:
        mode = "translate"
        logger.info(f"Translating from {src_lang} to {target_lang}.")

    result_text = call_ollama_api(
        text, src_lang, target_lang, model, api_token, api_url, mode=mode
    )
    return result_text


def process_paragraph(
    para, src_lang, model, target_lang, api_token, api_url, force_proofread=False
):
    try:
        paragraph_text = "".join(run.text for run in para.runs)
        logger.debug(f"Original paragraph text: '{paragraph_text}'")
        if paragraph_text.strip():
            result_text = translate_or_proofread(
                paragraph_text,
                src_lang,
                target_lang,
                model,
                api_token,
                api_url,
                force_proofread=force_proofread,
            )
            # Clear existing runs
            for run in para.runs:
                run.text = ""
            # Add a new run with the processed text
            para.add_run(result_text)
            logger.debug(f"Processed paragraph text: '{result_text}'")
        else:
            logger.debug("Paragraph is empty or whitespace.")
    except Exception as e:
        logger.exception(f"An error occurred while processing paragraph: {e}")


def process_document(
    input_file,
    output_file,
    model,
    target_lang,
    api_token,
    src_lang=None,
    api_url="http://localhost:11434/api/generate",
    force_proofread=False,
):
    try:
        logger.info(f"Opening document '{input_file}'")
        doc = Document(input_file)

        # Use provided source language or detect it
        if src_lang:
            logger.info(f"Using provided source language: {src_lang}")
        else:
            logger.info("Detecting source language...")
            src_lang = detect_source_language(doc)
            if not src_lang:
                logger.error("Source language detection failed. Exiting.")
                return

        # Check if we need proofreading or translation
        if force_proofread:
            logger.info(f"Running in PROOFREADING mode (explicit --proofread flag).")
        elif src_lang == target_lang:
            logger.info(
                f"Source ({src_lang}) equals target ({target_lang}). Running in PROOFREADING mode."
            )
        else:
            logger.info(f"Translating from {src_lang} to {target_lang}.")

        logger.info("Processing main document paragraphs")
        for para in doc.paragraphs:
            process_paragraph(
                para,
                src_lang,
                model,
                target_lang,
                api_token,
                api_url,
                force_proofread=force_proofread,
            )

        logger.info("Processing tables in the document")
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        process_paragraph(
                            para,
                            src_lang,
                            model,
                            target_lang,
                            api_token,
                            api_url,
                            force_proofread=force_proofread,
                        )

        logger.info("Processing headers and footers")
        for section in doc.sections:
            header = section.header
            footer = section.footer
            for para in header.paragraphs:
                process_paragraph(
                    para,
                    src_lang,
                    model,
                    target_lang,
                    api_token,
                    api_url,
                    force_proofread=force_proofread,
                )
            for para in footer.paragraphs:
                process_paragraph(
                    para,
                    src_lang,
                    model,
                    target_lang,
                    api_token,
                    api_url,
                    force_proofread=force_proofread,
                )

        doc.save(output_file)
        logger.info(f"Document saved to '{output_file}'")
    except Exception as e:
        logger.exception(f"An error occurred while processing the document: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Translate or proofread a Word document using the Ollama API."
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default="llama3.2",
        help="The model name to use for translation/proofreading.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        dest="input_file",
        metavar="FILE",
        help="Path to the input Word document file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        dest="output_file",
        metavar="FILE",
        help="Path to save the output Word document file.",
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        required=True,
        dest="target_lang",
        metavar="LANG",
        help="Target language code (e.g., en, de, fr). Use same as source for proofreading mode.",
    )
    parser.add_argument(
        "-k",
        "--api-token",
        type=str,
        default=None,
        dest="api_token",
        metavar="TOKEN",
        help="API token for Ollama authentication (optional).",
    )
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        default=None,
        dest="src_lang",
        metavar="LANG",
        help="Source language code (e.g., en, de, fr). Auto-detected if not provided. Use same as target for proofreading mode.",
    )
    parser.add_argument(
        "--proofread",
        action="store_true",
        help="Force proofreading mode regardless of language match.",
    )
    parser.add_argument(
        "-u",
        "--url",
        type=str,
        default="http://localhost:11434",
        dest="api_url",
        metavar="URL",
        help="Ollama API base URL (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    # Ensure the API URL ends with /api/generate
    if not args.api_url.endswith("/api/generate"):
        api_url = f"{args.api_url.rstrip('/')}/api/generate"
    else:
        api_url = args.api_url

    logger.info(f"Starting processing with API URL: {api_url}")
    process_document(
        args.input_file,
        args.output_file,
        args.model,
        args.target_lang,
        args.api_token,
        args.src_lang,
        api_url,
        force_proofread=args.proofread,
    )
    logger.info("Processing completed")


if __name__ == "__main__":
    main()
