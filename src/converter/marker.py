from pathlib import Path
from typing import Optional
import tempfile
import os

# Load environment variables from .env automatically
from dotenv import load_dotenv
load_dotenv()

from marker.converters.pdf import PdfConverter
from marker.services.openai import OpenAIService
from marker.renderers.markdown import MarkdownRenderer
from marker.models import create_model_dict

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class MarkerConverter(PDFtoMarkdown):
    def __init__(self, openai_api_key: Optional[str] = None, use_llm: bool = False):
        """
        Initialize Marker converter with optional OpenAI integration.
        
        Args:
            openai_api_key: OpenAI API key for LLM enhancement (defaults to OPENAI_API_KEY env var)
            use_llm: Whether to use LLM for improved quality
        """
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.use_llm = use_llm
        
        # Initialize OpenAI service if API key is provided and LLM is enabled
        self.llm_service = None
        if self.openai_api_key and self.use_llm:
            self.llm_service = OpenAIService(
                config={
                    "openai_api_key": self.openai_api_key,
                    "openai_model": "gpt-4o-mini",
                    "timeout": 60,        # Increase timeout (default: 30)
                    "max_retries": 5,     # Increase retries (default: 2)
                    "retry_wait_time": 5  # Increase wait time (default: 3)
                }
            )

    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert a loaded PDF file to markdown using Marker.
        """
        # Create a temporary file from the PDF bytes
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(doc.raw_bytes)
            temp_file_path = temp_file.name
        
        try:
            # Get the model artifacts
            models = create_model_dict()
            
            # Initialize PDF converter with minimal configuration
            converter = PdfConverter(
                config={
                    "debug_pdf_images": False,
                    "debug_layout_images": True,
                    "debug_json": True,
                    "disable_multiprocessing": True,
                    "disable_image_extraction": False,
                    "openai_api_key": self.openai_api_key,
                    "use_llm": self.use_llm,
                    # LLM table processing configuration
                    "max_rows_per_batch": 15,  # Smaller chunks for better LLM handling
                    "max_table_rows": 80,      # Skip very large tables
                    "max_chars_per_chunk": 6000,  # Conservative character limit
                    "max_retries": 10,         # Maximum retries for rate limits
                    "initial_delay": 1.0,      # Initial delay for exponential backoff
                    "timeout": 60,
                },
                artifact_dict=models,
                processor_list=None,  # Use default processors
                llm_service="marker.services.openai.OpenAIService",
            )
            
            # Convert the PDF to markdown
            result = converter(temp_file_path)
            
            # Extract markdown content from the result
            if hasattr(result, 'markdown'):
                return result.markdown
            elif hasattr(result, 'text'):
                return result.text
            else:
                # Fallback: try to get content from the result object
                return str(result)
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path) 