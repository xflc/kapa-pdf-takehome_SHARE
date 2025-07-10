#!/usr/bin/env python3
"""
Basic Surya Pipeline - First Working Version
============================================

Minimal viable implementation:
PDF → Images → Surya Layout → GPT-4o-mini Text → Markdown

This is the skeleton for the first working pipeline.
Function implementations to be filled in.
"""

import os
import fitz  # PyMuPDF
import tempfile
import base64
import io
from pathlib import Path
from PIL import Image
from openai import OpenAI
from surya.layout import LayoutPredictor, LayoutResult
from surya.layout.schema import LayoutBox
from typing import List, Tuple

from tqdm import tqdm

from src.utils import extract_markdown_content

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


def convert_pdf_basic(pdf_path: Path) -> str:
    """
    Minimal working pipeline: PDF → Images → Surya Layout → GPT-4o-mini Text → Markdown
    
    Args:
        pdf_bytes: Raw PDF bytes
        openai_api_key: OpenAI API key
        
    Returns:
        Markdown string of the converted PDF
    """
    # 1. Load PDF and convert pages to images
    # 2  Use Surya to detect layout blocks in each image
    # 3. Use GPT-4o-mini to extract text from each layout block
    # 4. Convert the extracted text to markdown
    # 5. Return the markdown string
    
    layout_predictor = LayoutPredictor()
    
    images = []
    pdf_doc = fitz.open(pdf_path)
    for page in pdf_doc:
        page_image = page.get_pixmap()
        img_data = page_image.tobytes("png")
        image_pil = Image.open(io.BytesIO(img_data))
        #TODO: check if we have memory for this, maybe its better to save memory for the model:
        images.append(image_pil) 

    layout_blocks = layout_predictor(images)

    client = OpenAI()
    page_texts = []
    # Overall progress bar for pages
    with tqdm(total=len(layout_blocks), desc="Processing document pages") as page_pbar:
        for page_num, (layout_result, page_image) in enumerate(zip(layout_blocks, images)):

            # Get blocks and sort by reading order
            blocks = layout_result.bboxes
            blocks = sorted(blocks, key=lambda x: x.position)
            
            # Calculate scale factors
            layout_size = layout_result.image_bbox[2:4]
            page_image_size = page_image.size
            scale_x = page_image_size[0] / layout_size[0]
            scale_y = page_image_size[1] / layout_size[1]
            
            block_texts = []
            # Progress bar for blocks within current page (disappears after page is done)
            with tqdm(total=len(blocks), desc=f"Page {page_num + 1} blocks", leave=False) as block_pbar:
                for block in blocks:
                    #resize the block bbox to the size of the page
                    block_bbox = [block.bbox[0] * scale_x, block.bbox[1] * scale_y, block.bbox[2] * scale_x, block.bbox[3] * scale_y]                    
                    block_image = page_image.crop(block.bbox)

                    # Convert PIL image to base64
                    buffered = io.BytesIO()
                    block_image.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Send image to gpt-4o-mini
                    response = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that extracts a markdown representation from images. Use the ```markdown``` tags to wrap the markdown."},
                            {"role": "user", "content": [
                                {"type": "text", "text": "Extract text from the following image:"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_base64}"
                                    }
                                }
                            ]}
                        ]
                    )
                    block_text = response.choices[0].message.content
                    block_texts.append(extract_markdown_content(block_text))
                    block_pbar.update(1)

            page_texts.append("\n".join(block_texts))
            page_pbar.update(1)

    return "\n\n".join(page_texts)




class BasicSuryaConverter(PDFtoMarkdown):
    """
    Basic converter using Surya layout detection + GPT-4o-mini text extraction.
    """
    
    def __init__(self):
        """
        Initialize the basic converter.
        
        Args:
            openai_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """

    
    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF to markdown using basic pipeline.
        
        Args:
            doc: Loaded PDF document
            
        Returns:
            Markdown string
        """
        return convert_pdf_basic(doc.path) 