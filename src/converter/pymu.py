import pymupdf
import pymupdf4llm

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class PymuConverter(PDFtoMarkdown):
    def convert(self, doc: LoadedPDF) -> str:
        pdf = pymupdf.open(stream=doc.raw_bytes, filetype="pdf")
        markdown = pymupdf4llm.to_markdown(pdf, page_chunks=False)
        return markdown
