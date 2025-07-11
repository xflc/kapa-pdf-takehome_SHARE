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
import openai
import backoff
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


@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6)
def completions_with_backoff(client, **kwargs):
    """OpenAI completions with exponential backoff for rate limits"""
    return client.chat.completions.create(**kwargs)


def get_block_prompt(block_type: str, original_text_context: str) -> str:
    """
    Get specialized prompt based on block type with original text context.
    
    Args:
        block_type: The type of block (e.g., "Text", "Title", "Table", etc.)
        original_text_context: The full page text for reference
        
    Returns:
        Specialized prompt for the block type
    """
    # Make it empty if original_text_context is empty e.g. an scanned pdf
    original_text_reference = "" if not original_text_context else f"\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:\n\n{original_text_context}\n\n"
    
    prompts = {
        "Text": f"Extract all text. Maintain original formatting and line breaks.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown)  and nothing else.",
        "SectionHeader": f"Extract the heading text. Format as markdown heading (# or ## or ###).{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Form": f"Extract the form text. Format as markdown form with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Title": f"Extract the title text. Format as markdown heading (# or ##).{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "ListItem": f"Extract list items. Format as markdown list with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Table": f"Extract the table. Format as markdown table with proper alignment. Include all rows and columns.{original_text_reference}\nAfter the table add a detailed a legend composed of two parts: (1) **TABLE_DESCRIPTION**: a description of the columns what the table indicates and (2) **TABLE_DATA**: a verbose Legend with a natural language description of each row of the table (e.g. '''TABLE_DATA:\n- Row1 Id: this ELEMENT_NAME has 100% of the value of COLUMN1 `string x` of COLUMN2\n ...\n- Row2 Id: ...''' or something similar in a ), line by line and incapsulate both legends in the same ```markdown``` block as well.\nJust output the exact content of the image and the legends (Use the ```markdown``` tags to wrap the markdown) and nothing else.  ",
        "Figure": f"Describe this figure briefly and extract any visible text or captions.{original_text_reference}\n After the figure add a detailed legend with a natural language description of the figure as a legend and incapsulate that in the same ```markdown``` block as well.\nJust output the exact content of the image and the legend (Use the ```markdown``` tags to wrap the markdown) and nothing else. ",
        "Picture": f"Describe this picture briefly and extract any visible text or captions.{original_text_reference}\n After the picture add a detailed legend with a natural language description of the picture as a legend and incapsulate that in the same ```markdown``` block as well.\nJust output the exact content of the image and the legend (Use the ```markdown``` tags to wrap the markdown) and nothing else. ",
        "Caption": f"Extract the caption text.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown, but don't use markdown headings like # or ## or ###) and nothing else.",
        "Footnote": f"Extract the footnote text.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Formula": f"Extract the mathematical formula. Format in LaTeX if possible.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "PageHeader": f"Extract the page header text with a markdown heading (# or ## or ###) if it contains a chapter/ section header.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "PageFooter": f"Extract the page footer text without any formatting.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Handwriting": f"Extract the handwritting text. Format as markdown with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "TableOfContents": f"Extract the table of contents. Format as markdown with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
    }
    #  "Table": f"Extract the table. Format as markdown table with proper alignment. Include all rows and columns.{original_text_reference}\nAfter the table add a detailed legend with a natural language description of what the table indicates and a Boosted Legend with a natural language description of the data in every row, line by line and incapsulate both legends in the same ```markdown``` block as well.\nJust output the exact content of the image and the legends (Use the ```markdown``` tags to wrap the markdown) and nothing else.  ",
    # "Figure": f"Describe this figure briefly and extract any visible text or captions.{original_text_reference}\n After the figure add a detailed legend with a natural language description of the figure as a legend and incapsulate that in the same ```markdown``` block as well.\nJust output the exact content of the image and the legend (Use the ```markdown``` tags to wrap the markdown) and nothing else. ",
    # "Picture": f"Describe this picture briefly and extract any visible text or captions.{original_text_reference}\n After the picture add a detailed legend with a natural language description of the picture as a legend and incapsulate that in the same ```markdown``` block as well.\nJust output the exact content of the image and the legend (Use the ```markdown``` tags to wrap the markdown) and nothing else. ",
    
    
    prompt_out = prompts.get(block_type, None)
    if prompt_out is None:
        print(f"No prompt found for {block_type}")
        prompt_out = f"Extract all text.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else."
    
    return prompt_out





def convert_pdf_basic(pdf_path: Path) -> str:
    """
    Simple sequential pipeline: PDF → Images → Surya Layout → GPT-4o-mini Text → Markdown
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Markdown string of the converted PDF
    """
    layout_predictor = LayoutPredictor()
    client = OpenAI()
    
    # Load PDF and convert pages to images
    images = []
    original_text_contexts = []
    pdf_doc = fitz.open(pdf_path)
    for page in pdf_doc:
        original_text_contexts.append(page.get_text())
        page_image = page.get_pixmap()
        img_data = page_image.tobytes("png")
        image_pil = Image.open(io.BytesIO(img_data))
        images.append(image_pil)
    pdf_doc.close()
    
    # Run layout detection on all images
    layout_results = layout_predictor(images)
    
    page_texts = []
    # Process each page sequentially
    with tqdm(total=len(layout_results), desc="Processing pages") as page_pbar:
        for page_num, (layout_result, page_image, original_text_context) in enumerate(zip(layout_results, images, original_text_contexts)):
            # Get blocks and sort by reading order
            blocks = layout_result.bboxes
            blocks = sorted(blocks, key=lambda x: x.position)
            
            # Calculate scale factors
            layout_size = layout_result.image_bbox[2:4]
            page_image_size = page_image.size
            scale_x = page_image_size[0] / layout_size[0]
            scale_y = page_image_size[1] / layout_size[1]
            
            block_texts = []
            # Process blocks sequentially
            with tqdm(total=len(blocks), desc=f"Page {page_num + 1} blocks", leave=False) as block_pbar:
                for block in blocks:
                    # Resize the block bbox to the size of the page
                    block_bbox = [
                        block.bbox[0] * scale_x, 
                        block.bbox[1] * scale_y, 
                        block.bbox[2] * scale_x, 
                        block.bbox[3] * scale_y
                    ]
                    block_image = page_image.crop(block.bbox)

                    # Convert PIL image to base64
                    buffered = io.BytesIO()
                    block_image.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Get block type and specialized prompt
                    block_type = block.label
                    user_prompt = get_block_prompt(block_type, original_text_context) 
                    
                    # Send image to gpt-4o-mini
                    response = completions_with_backoff(
                        client=client,
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that extracts a markdown representation from images. Use the ```markdown``` tags to wrap the markdown."},
                            {"role": "user", "content": [
                                {"type": "text", "text": user_prompt},
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
                    if block_text:
                        block_texts.append(extract_markdown_content(block_text))
                    
                    block_pbar.update(1)
            
            page_texts.append("\n".join(block_texts))
            page_pbar.update(1)
    
    return "\n\n".join(page_texts)







class BasicSuryaConverter(PDFtoMarkdown):
    """
    Basic converter using Surya layout detection + GPT-4o-mini text extraction.
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