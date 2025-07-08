import sys
import os
from pathlib import Path

# Add the project root to the path so we can import the pipeline
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.converter.pipeline.simple_pdf_pipeline import process_pdf_simple
from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class SimplePipelineConverter(PDFtoMarkdown):
    """
    Simple converter that uses the functional pipeline approach.
    
    Uses two-stage image processing like Marker:
    1. Low-res images for layout detection (faster)
    2. High-res images for text extraction (better quality)
    """
    
    def __init__(self, openai_api_key=None, batch_size=6):
        """
        Initialize the simple pipeline converter.
        
        Args:
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            batch_size: Batch size for layout detection (default 6)
        """
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.batch_size = batch_size
    
    def convert(self, doc: LoadedPDF) -> str:
        """Convert using the simple functional pipeline."""
        return process_pdf_simple(doc.raw_bytes, self.openai_api_key, self.batch_size, debug_visualize=True)