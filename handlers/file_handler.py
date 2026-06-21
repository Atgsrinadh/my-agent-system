"""
handlers/file_handler.py — Handle all file types uploaded via Telegram.
Extracts text content and passes to appropriate agent.
Supports: PDF, Word, Excel, CSV, images, text, code files.
"""
import os, io
from pathlib import Path

async def extract_file_content(file_path: str, mime_type: str = None) -> tuple[str, str]:
    """
    Extract text content from any file.
    Returns (content_text, file_type_label).
    """
    ext = Path(file_path).suffix.lower()

    try:
        # ── PDF ──────────────────────────────────────────────────────────
        if ext == ".pdf" or mime_type == "application/pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text[:15000], "PDF document"

        # ── Word (.docx) ─────────────────────────────────────────────────
        elif ext in [".docx", ".doc"]:
            from docx import Document
            doc = Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
            return text[:15000], "Word document"

        # ── Excel (.xlsx, .xls) ──────────────────────────────────────────
        elif ext in [".xlsx", ".xls"]:
            import pandas as pd
            df = pd.read_excel(file_path)
            return df.to_string()[:15000], "Excel spreadsheet"

        # ── CSV ──────────────────────────────────────────────────────────
        elif ext == ".csv":
            import pandas as pd
            df = pd.read_csv(file_path)
            return df.to_string()[:15000], "CSV file"

        # ── Images ───────────────────────────────────────────────────────
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
            return f"[Image file: {Path(file_path).name}]", "image"

        # ── Text / Code / Markdown ────────────────────────────────────────
        elif ext in [".txt", ".md", ".py", ".js", ".ts", ".html",
                     ".css", ".json", ".yaml", ".yml", ".xml",
                     ".sh", ".go", ".rs", ".java", ".cpp", ".c"]:
            with open(file_path, "r", errors="ignore") as f:
                return f.read()[:15000], f"{ext[1:].upper()} file"

        # ── Fallback: try reading as text ─────────────────────────────────
        else:
            with open(file_path, "r", errors="ignore") as f:
                content = f.read()[:15000]
            return content, "text file"

    except Exception as e:
        return f"Could not read file: {str(e)}", "unknown"

def pick_agent_for_file(file_type: str, user_message: str = "") -> str:
    """Pick the best agent based on file type."""
    ft = file_type.lower()
    if "pdf" in ft or "word" in ft:
        return "pdf_reader"
    elif "excel" in ft or "csv" in ft or "spreadsheet" in ft:
        return "analyst"
    elif "image" in ft:
        return "vision"
    elif any(x in ft for x in ["py", "js", "go", "rust", "java", "code"]):
        return "coder"
    return "general"
