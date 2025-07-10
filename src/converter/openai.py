import openai
import time
from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


def completions_with_backoff(client, **kwargs):
    """
    OpenAI completions with exponential backoff for rate limiting.
    Simple implementation with retry logic.
    """
    max_retries = 6
    base_delay = 1
    
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except openai.RateLimitError as e:
            if attempt == max_retries - 1:
                raise e
            
            # Exponential backoff
            delay = base_delay * (2 ** attempt)
            print(f"Rate limit hit, waiting {delay} seconds before retry {attempt + 1}/{max_retries}")
            time.sleep(delay)
        except Exception as e:
            # For other errors, don't retry
            raise e


class OpenAiConverter(PDFtoMarkdown):
    def __init__(self, client: openai.OpenAI):
        self.client = client

    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF to markdown using OpenAI API.
        """
        # This would implement the conversion logic
        # For now, this is a placeholder
        return "# PDF Content\n\nExtracted with OpenAI API"