"""
Pdf2Markdown Pipeline 
============================================
This is the pipeline we are using to convert pdfs to markdown.
PDF → Images → Surya Layout → gpt-4.1-mini Text → Markdown
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

from src.converter.utils import (
    extract_markdown_content,
    completions_with_backoff,
    get_block_prompt,
    get_user_messages,
    scale_crop_image,
    image_to_base64,
    get_legend_prompt,
)

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


class LayoutAndLLMConverter(PDFtoMarkdown):
    """
    Basic converter using Surya layout detection + gpt-4.1-mini text extraction.
    """
    
    def __init__(self, max_chars: int = 2000, num_workers: int = 1):
        """Initialize the converter."""
        self.client = OpenAI()
        self.max_chars = max_chars
        self.num_workers = num_workers
    
    def convert(self, doc: LoadedPDF) -> str:
        """
        Convert PDF to markdown using the pipeline.
        """
        return self._pdf_to_markdown_pipeline(doc.path)
    
    def _pdf_to_markdown_pipeline(self, pdf_path: Path) -> str:
        """
        Main conversion pipeline: PDF → Images → Surya Layout → gpt-4.1-mini Text → Markdown
        
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
        """
        from concurrent.futures import ThreadPoolExecutor
        from tqdm import tqdm
        blocks = sorted(layout_result.bboxes, key=lambda x: x.position)
        layout_size = layout_result.image_bbox[2:4]

        def process_block(block):
            if block.label in {"PageFooter", "PageHeader"}:
                return None
            return self._lllm_extract_text_from_block(
                block, page_image, layout_size, original_text_context
            )

        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            results = list(
                tqdm(
                    executor.map(process_block, blocks),
                    total=len(blocks),
                    desc=f"Page {page_num + 1} blocks",
                    leave=False,
                )
            )
        block_texts = [r for r in results if r]
        return "\n".join([b for b in block_texts if b])

    def _lllm_extract_text_from_block(self, block, page_image: Image.Image, layout_size, original_text_context: str) -> str:
        """
        Extract text from a single block using LLM.
        """
        block_image = scale_crop_image(block, page_image, layout_size)
        img_base64 = image_to_base64(block_image)
        block_type = block.label
        user_prompt = get_block_prompt(block_type, original_text_context)
        response = completions_with_backoff(
            client=self.client,
            model="gpt-4.1-mini",
            messages=get_user_messages(img_base64, user_prompt)
        )
        block_text = response.choices[0].message.content
        main_content = extract_markdown_content(block_text) if block_text else ""

        # For Table, Figure, Picture: generate legend in a second LLM call
        if block_type in {"Table", "Figure", "Picture"} and main_content:
            legend_prompt = get_legend_prompt(block_type, main_content)
            legend_response = completions_with_backoff(
                client=self.client,
                model="gpt-4.1-mini",
                messages=get_user_messages(img_base64, legend_prompt, system_prompt="You are a helpful assistant that generates a legend for a table, figure, or picture.")
            )
            legend_text = legend_response.choices[0].message.content
            legend_content = extract_markdown_content(legend_text) if legend_text else ""
            # If the combined length exceeds max_chars, return only legend_content
            if legend_content and len(main_content) + len(legend_content) > self.max_chars:
                return "\n\n" + legend_content + "\n\n"
            # Otherwise, append legend to main content, separated by two newlines
            return f"\n\n{main_content}\n\n{legend_content}\n\n" if legend_content else main_content
        else:
            return main_content
