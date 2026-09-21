"""Extract plain text from uploaded resume files."""
import io

import docx
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = (".pdf", ".docx")


class UnsupportedResumeFormat(ValueError):
    pass


def extract_text(filename: str, content: bytes) -> str:
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()

    if lower_name.endswith(".docx"):
        document = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in document.paragraphs]
        return "\n".join(paragraphs).strip()

    raise UnsupportedResumeFormat(
        f"Unsupported file type for '{filename}'; upload a .pdf or .docx"
    )
