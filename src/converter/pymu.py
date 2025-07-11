import logging

import pymupdf
import pymupdf4llm

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown

logger = logging.getLogger(__name__)


class PymuConverter(PDFtoMarkdown):
    def convert(self, doc: LoadedPDF) -> str:
        pdf = pymupdf.open(stream=doc.raw_bytes, filetype="pdf")

        # Check if OCR is needed and process accordingly
        if self._needs_ocr(pdf):
            return self._convert_with_ocr(pdf)
        else:
            return pymupdf4llm.to_markdown(pdf, page_chunks=False)

    def _needs_ocr(self, pdf: pymupdf.Document) -> bool:
        """
        Determine if OCR is needed
        """
        return any(
            len(pdf[page_num].get_text().strip()) < 50
            for page_num in range(min(5, len(pdf)))
        )

    def _add_page_header(self, page_num: int) -> str:
        """Generate page header with separator for pages after the first."""
        separator = "\n\n---\n\n" if page_num > 0 else ""
        return f"{separator}# Page {page_num + 1}\n\n"

    def _convert_with_ocr(self, pdf: pymupdf.Document) -> str:
        """
        Convert PDF using OCR, following the best practice of creating
        TextPage objects once and reusing them.
        """
        markdown_parts = []

        for page_num in range(len(pdf)):
            page = pdf[page_num]

            # Create TextPage with OCR once per page
            textpage = None
            try:
                textpage = page.get_textpage_ocr()

                # Extract text using the OCR TextPage
                text = page.get_text(textpage=textpage)

                if text.strip():
                    # Add page separator for multi-page documents
                    markdown_parts.append(self._add_page_header(page_num))

                    # Clean up the OCR text and add to markdown
                    cleaned_text = self._clean_ocr_text(text)
                    markdown_parts.append(cleaned_text)

            except Exception as e:
                # Fallback to regular text extraction if OCR fails
                logger.error(f"OCR failed for page {page_num + 1}: {e}")
                text = page.get_text()
                if text.strip():
                    markdown_parts.append(self._add_page_header(page_num))
                    markdown_parts.append(text)

        return "\n".join(markdown_parts)

    def _clean_ocr_text(self, text: str) -> str:
        """
        Clean up OCR text to improve markdown quality.
        """
        # Remove empty lines and excessive whitespace
        cleaned_lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned_text = "\n".join(cleaned_lines)
        # Fix common OCR spacing issues
        return cleaned_text.replace("  ", " ")
