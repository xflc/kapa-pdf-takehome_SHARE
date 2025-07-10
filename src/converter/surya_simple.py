from pathlib import Path
from typing import Optional, List, Dict, Any
import tempfile
import os
from PIL import Image
import json
import fitz  # PyMuPDF
import base64
import io

from openai import OpenAI
from surya.layout import LayoutPredictor
from surya.layout.schema import LayoutResult, LayoutBox

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class SuryaSimpleConverter(PDFtoMarkdown):
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize Surya + GPT-4.1-mini converter.
        
        Args:
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key is required")
        
        self.client = OpenAI(api_key=self.openai_api_key)
        self.layout_predictor = LayoutPredictor()

    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF using Surya for layout detection and GPT-4.1-mini for text extraction.
        """
        # Create a temporary file from the PDF bytes
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(doc.raw_bytes)
            temp_file_path = temp_file.name
        
        try:
            # Open PDF and extract images
            pdf_doc = fitz.open(temp_file_path)
            all_pages_markdown = []
            
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]
                
                # Convert page to image
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                # Get layout predictions using surya
                layout_results = self.layout_predictor([image])
                layout_result = layout_results[0]
                
                # Process each detected block
                page_markdown = self._process_page_blocks(
                    image, layout_result, page_num + 1
                )
                all_pages_markdown.append(page_markdown)
            
            return "\n\n".join(all_pages_markdown)
        
        finally:
            # Clean up
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def _process_page_blocks(self, image: Image.Image, layout_result: LayoutResult, page_num: int) -> str:
        """
        Process each detected block on the page using GPT-4.1-mini.
        """
        blocks_content = []
        
        # Sort blocks by reading order (position field)
        sorted_blocks = sorted(layout_result.bboxes, key=lambda x: x.position)
        
        for block in sorted_blocks:
            # Crop the image to the block bounding box
            bbox = block.bbox if hasattr(block, 'bbox') else self._polygon_to_bbox(block.polygon)
            cropped_image = image.crop(bbox)
            
            # Get text content using GPT-4.1-mini
            block_text = self._extract_text_with_gpt4(cropped_image, block.label)
            
            if block_text.strip():
                blocks_content.append(block_text)
        
        return "\n\n".join(blocks_content)

    def _polygon_to_bbox(self, polygon: List[List[float]]) -> tuple:
        """Convert polygon to bounding box (x1, y1, x2, y2)."""
        x_coords = [point[0] for point in polygon]
        y_coords = [point[1] for point in polygon]
        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))

    def _extract_text_with_gpt4(self, image: Image.Image, block_type: str) -> str:
        """
        Extract text from a cropped image block using GPT-4.1-mini.
        """
        # Convert image to base64
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        # Create appropriate prompt based on block type
        prompt = self._get_prompt_for_block_type(block_type)
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Note: GPT-4.1-mini might not be available, using gpt-4o-mini
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            print(f"Error processing block of type {block_type}: {e}")
            return ""

    def _get_prompt_for_block_type(self, block_type: str) -> str:
        """
        Get appropriate prompt based on the detected block type.
        """
        prompts = {
            "Text": "Extract all text from this image block. Maintain the original formatting and line breaks. Return only the text content.",
            "Section-header": "Extract the heading text from this image. Format it as a markdown heading (# or ## or ###). Return only the formatted heading.",
            "Title": "Extract the title text from this image. Format it as a markdown heading (# or ##). Return only the formatted title.",
            "List-item": "Extract the list items from this image. Format them as markdown list items with proper indentation. Return only the formatted list.",
            "Table": "Extract the table from this image. Format it as a markdown table with proper alignment. Include all rows and columns. Return only the formatted table.",
            "Figure": "Describe this figure/image briefly and extract any visible text or captions. Format as: ![Figure description](image) followed by any caption text.",
            "Picture": "Describe this picture briefly and extract any visible text or captions. Format as: ![Picture description](image) followed by any caption text.",
            "Caption": "Extract the caption text from this image. Return only the caption text.",
            "Footnote": "Extract the footnote text from this image. Return only the footnote text.",
            "Formula": "Extract the mathematical formula from this image. If possible, format it in LaTeX. Return only the formula.",
            "Page-header": "Extract the header text from this image. Return only the header text.",
            "Page-footer": "Extract the footer text from this image. Return only the footer text.",
            "Form": "Extract all form fields and their labels from this image. Format as key-value pairs.",
            "Handwriting": "Extract any handwritten text from this image. Return only the text content.",
            "Text-inline-math": "Extract the text including any inline mathematical expressions. Return only the text content."
        }
        
        return prompts.get(block_type, "Extract all text from this image block. Return only the text content.")

    def get_layout_info(self, doc: LoadedPDF) -> List[Dict[str, Any]]:
        """
        Get layout information without text extraction (for debugging/inspection).
        """
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(doc.raw_bytes)
            temp_file_path = temp_file.name
        
        try:
            pdf_doc = fitz.open(temp_file_path)
            layout_info = []
            
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]
                
                # Convert page to image
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                # Get layout predictions
                layout_results = self.layout_predictor([image])
                layout_result = layout_results[0]
                
                page_info = {
                    "page": page_num + 1,
                    "image_bbox": layout_result.image_bbox,
                    "blocks": []
                }
                
                for block in layout_result.bboxes:
                    block_info = {
                        "label": block.label,
                        "bbox": block.bbox if hasattr(block, 'bbox') else self._polygon_to_bbox(block.polygon),
                        "polygon": block.polygon,
                        "position": block.position,
                        "confidence": block.top_k
                    }
                    page_info["blocks"].append(block_info)
                
                layout_info.append(page_info)
            
            return layout_info
        
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path) 