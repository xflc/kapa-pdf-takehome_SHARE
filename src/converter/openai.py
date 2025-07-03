from openai import OpenAI
from typing import Optional
from pathlib import Path



from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class OpenAiConverter(PDFtoMarkdown):
    def __init__(self, client: OpenAI):
        self.client = client

    def convert(self, doc: LoadedPDF) -> str:
        markdown = self.extract_pdf_with_gpt4o(doc.path)
        return markdown
    
    def extract_pdf_with_gpt4o(self, pdf_path: Path) -> str:
        """
        Extracts the contents of a PDF using OpenAI's file API and a direct prompt for Markdown output.
        """
        prompt = (
            "Extract the content from the file provided in markdown format without altering it.\n"
            "Be very careful with special content like tables and convert special characters to a readable format.\n"
            "Also format headers and subheaders properly so that we can split the document into sections.\n"
            "Just output its exact content in markdown format and nothing else."
        )


        with open(pdf_path, "rb") as file_obj:
            file = self.client.files.create(file=file_obj, purpose="user_data")
        
        response = self.client.responses.create(
            model="gpt-4.1-mini-2025-04-14",
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
        markdown_content = self.extract_markdown_content(text)
        return markdown_content

    def extract_markdown_content(self, text: str) -> str:
        start_tag = "```markdown"
        start = text.find(start_tag)
        if start != -1:
            start += len(start_tag)
            end = text.find("```", start)
            if end != -1:
                markdown_content = text[start:end].strip()
            else:
                markdown_content = text[start:].strip()
        else:
            markdown_content = text.strip()
        return markdown_content
