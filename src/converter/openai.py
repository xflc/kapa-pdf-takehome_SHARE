import openai
from pathlib import Path

from src.converter.utils import extract_markdown_content



from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown
import backoff

@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6)
def completions_with_backoff(client, **kwargs):
    return client.chat.completions.create(**kwargs)

class OpenAiConverter(PDFtoMarkdown):
    def __init__(self, client: openai.OpenAI):
        self.client = client

    def convert(self, doc: LoadedPDF) -> str:
        markdown = self.extract_pdf_with_gpt4o(doc.path)
        return markdown
    
    def extract_pdf_with_gpt4o(self, pdf_path: Path) -> str:
        """
        Extracts the contents of a PDF using openai.OpenAI's file API and a direct prompt for Markdown output.
        """
        prompt = (
            "Extract the content from the file provided in markdown format without altering it.\n"
            "Be very careful with tables. Dont ever truncate or summarize tables. Even if . write all the rows and columns.\n"
            "Also format headers and subheaders properly so that we can split the document into sections.\n"
            "Just output its exact content in markdown format and nothing else."
        )


        with open(pdf_path, "rb") as file_obj:
            file = self.client.files.create(file=file_obj, purpose="user_data")
        
        response = self.client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": file.id},
                        {"type": "input_text", "text": prompt},
                    ],
                }
            ],

        )
        self.client.files.delete(file.id)  

        text = response.output[0].content[0].text
        markdown_content = extract_markdown_content(text)
        return markdown_content

