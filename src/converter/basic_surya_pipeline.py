"""
Pdf2Markdown Pipeline 
============================================
This is the pipeline we are using to convert pdfs to markdown.
PDF → Images → Surya Layout → GPT-4.1-mini Text → Markdown
"""

import fitz
import base64
import io
import openai
import backoff
from pathlib import Path
from PIL import Image
from openai import OpenAI
from surya.layout import LayoutPredictor
from tqdm import tqdm
from typing import List, Tuple

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
    
    prompt_out = prompts.get(block_type, None)
    if prompt_out is None:
        print(f"No prompt found for {block_type}")
        prompt_out = f"Extract all text.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else."
    
    return prompt_out


class LayoutAndLLMConverter(PDFtoMarkdown):
    """
    Basic converter using Surya layout detection + GPT-4.1-mini text extraction.
    """
    
    def __init__(self):
        """Initialize the converter with required components."""
        self.client = OpenAI()
    
    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF to markdown using the pipeline.
        """
        return self._pdf_to_markdown_pipeline(doc.path)
    
    def _pdf_to_markdown_pipeline(self, pdf_path: Path) -> str:
        """
        Main conversion pipeline: PDF → Images → Surya Layout → GPT-4.1-mini Text → Markdown
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Markdown string of the converted PDF
        """

        layout_predictor = LayoutPredictor()

        # Load PDF and extract images + text context
        images, original_text_contexts = self._pdf_preprocessing(pdf_path)
        
        # Run layout detection on all images
        layout_results = layout_predictor(images)
        
        # Process each page
        page_texts = self._process_all_pages(layout_results, images, original_text_contexts)
        
        return "\n\n".join(page_texts)
    
    def _pdf_preprocessing(self, pdf_path: Path) -> Tuple[List[Image.Image], List[str]]:
        """
        Load PDF and convert pages to images with original text layer.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (images, original_text_contexts)
        """
        images = []
        original_text_contexts = []
        
        pdf_doc = fitz.open(pdf_path)
        try:
            for page in pdf_doc:
                # Extract original text context
                original_text_contexts.append(page.get_text())
                
                # Convert page to image
                page_image = page.get_pixmap()
                img_data = page_image.tobytes("png")
                image_pil = Image.open(io.BytesIO(img_data))
                images.append(image_pil)
        finally:
            pdf_doc.close()
        
        return images, original_text_contexts
    
    
    def _process_all_pages(self, layout_results: List, images: List[Image.Image], 
                          original_text_contexts: List[str]) -> List[str]:
        """
        Process all pages with their layout results.
        
        Args:
            layout_results: List of layout detection results
            images: List of PIL images
            original_text_contexts: List of original text contexts
            
        Returns:
            List of page texts
        """
        page_texts = []
        
        with tqdm(total=len(layout_results), desc="Processing pages") as page_pbar:
            for page_num, (layout_result, page_image, original_text_context) in enumerate(
                zip(layout_results, images, original_text_contexts)
            ):
                page_text = self._process_single_page(
                    page_num, layout_result, page_image, original_text_context
                )
                page_texts.append(page_text)
                page_pbar.update(1)
        
        return page_texts
    
    def _process_single_page(self, page_num: int, layout_result, page_image: Image.Image, 
                           original_text_context: str) -> str:
        """
        Process a single page with its layout result.
        
        Args:
            page_num: Page number (0-indexed)
            layout_result: Layout detection result for this page
            page_image: PIL image of the page
            original_text_context: Original text context of the page
            
        Returns:
            Processed text for this page
        """
        # Get blocks and sort by reading order
        blocks = layout_result.bboxes
        blocks = sorted(blocks, key=lambda x: x.position)
        
        # Calculate scale factors for block resizing
        layout_size = layout_result.image_bbox[2:4]
        page_image_size = page_image.size
        scale_x = page_image_size[0] / layout_size[0]
        scale_y = page_image_size[1] / layout_size[1]
        
        # Process all blocks on this page
        block_texts = self._process_page_blocks(
            blocks, page_image, original_text_context, scale_x, scale_y, page_num
        )
        
        return "\n".join(block_texts)
    
    def _process_page_blocks(self, blocks: List, page_image: Image.Image, 
                           original_text_context: str, scale_x: float, scale_y: float, 
                           page_num: int) -> List[str]:
        """
        Process all blocks of a single page by sending them to the LLM.
        
        Args:
            blocks: List of layout blocks
            page_image: PIL image of the page
            original_text_context: Original text context of the page
            scale_x: X scaling factor to fit the block in the page
            scale_y: Y scaling factor to fit the block in the page
            page_num: Page number for progress tracking
            
        Returns:
            List of block texts
        """
        block_texts = []
        
        with tqdm(total=len(blocks), desc=f"Page {page_num + 1} blocks", leave=False) as block_pbar:
            for block in blocks:
                block_text = self._lllm_extract_text_from_block(
                    block, page_image, original_text_context, scale_x, scale_y
                )
                if block_text:
                    block_texts.append(block_text)
                block_pbar.update(1)
        
        return block_texts
    
    def _lllm_extract_text_from_block(self, block, page_image: Image.Image, 
                          original_text_context: str, scale_x: float, scale_y: float) -> str:
        """
        Extract text from a single block using LLM.
        
        Args:
            block: Layout block
            page_image: PIL image of the page
            original_text_context: Original text context of the page
            scale_x: X scaling factor
            scale_y: Y scaling factor
            
        Returns:
            Extracted text or empty string
        """
        # Prepare block image
        block_image = self._scale_crop_image(block, page_image, scale_x, scale_y)
        
        # Convert to base64
        img_base64 = self._image_to_base64(block_image)
        
        # Get specialized prompt
        block_type = block.label
        user_prompt = get_block_prompt(block_type, original_text_context)
        
        # Send to LLM
        response = completions_with_backoff(
            client=self.client,
            model="GPT-4.1-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful assistant that extracts a markdown representation from images. Use the ```markdown``` tags to wrap the markdown."
                },
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]
        )
        
        block_text = response.choices[0].message.content
        return extract_markdown_content(block_text) if block_text else ""
    
    def _scale_crop_image(self, block, page_image: Image.Image, 
                           scale_x: float, scale_y: float) -> Image.Image:
        """
        Prepare block image by scaling and cropping.
        """
        # Resize the block bbox to the size of the page
        block_bbox = [
            block.bbox[0] * scale_x, 
            block.bbox[1] * scale_y, 
            block.bbox[2] * scale_x, 
            block.bbox[3] * scale_y
        ]
        return page_image.crop(block_bbox)
    
    def _image_to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL image to base64 string.
        """
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
