import os
import tempfile
import logging
from typing import Optional


from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.config.parser import ConfigParser

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown

logger = logging.getLogger(__name__)


class MarkerConverter(PDFtoMarkdown):
    """
    Simple Marker PDF to Markdown converter using OpenAI for enhanced quality.
    """
    
    def __init__(self, use_llm: bool = False):
        """
        Initialize the MarkerConverter.
        
        Args:
            use_llm: Whether to use OpenAI for improved quality (requires OPENAI_API_KEY)
        """
        self.use_llm = use_llm
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Disable LLM if no API key
        if self.use_llm and not self.openai_api_key:
            logger.warning("LLM enabled but OPENAI_API_KEY not found. Disabling LLM.")
            self.use_llm = False
        
        # Cache model dict for performance
        self._model_dict = None
        self._converter = None
        
        logger.info(f"MarkerConverter initialized with use_llm={self.use_llm}")
    
    def _get_model_dict(self):
        """Get model dictionary, loading if needed."""
        if self._model_dict is None:
            logger.info("Loading marker models...")
            self._model_dict = create_model_dict()
            logger.info("Marker models loaded")
        return self._model_dict
    
    def _get_converter(self):
        """Get converter instance, creating if needed."""
        if self._converter is None:
            config = {
                "output_format": "markdown",
                "use_llm": self.use_llm,
            }
            
            if self.use_llm:
                config.update({
                    "openai_api_key": self.openai_api_key,
                    "llm_service": "marker.services.openai.OpenAIService"
                })
            
            config_parser = ConfigParser(config)
            self._converter = PdfConverter(
                config=config_parser.generate_config_dict(),
                artifact_dict=self._get_model_dict(),
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
                llm_service=config_parser.get_llm_service() if self.use_llm else None
            )
            logger.info("Marker converter ready")
        
        return self._converter
    
    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF to markdown.
        
        Args:
            doc: LoadedPDF object with PDF bytes
            
        Returns:
            str: Markdown content
        """
        temp_file_path = None
        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(doc.raw_bytes)
                temp_file_path = temp_file.name
            
            logger.info(f"Converting {doc.name} ({len(doc.raw_bytes)} bytes)")
            
            # Convert to markdown
            converter = self._get_converter()
            rendered = converter(temp_file_path)
            text, _, images = text_from_rendered(rendered)
            
            if images:
                logger.info(f"Extracted {len(images)} images")
            
            return text
        
        except Exception as e:
            logger.error(f"Failed to convert {doc.name}: {e}")
            raise Exception(f"Marker conversion failed: {str(e)}")
        
        finally:
            # Cleanup
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path) 