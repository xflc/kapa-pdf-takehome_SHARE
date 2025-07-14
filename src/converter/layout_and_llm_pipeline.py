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
    
    def __init__(self, max_chars: int = 5000, num_workers: int = 25):
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
        """
        layout_predictor = LayoutPredictor()

        # Load PDF and extract images + text context
        images, original_text_contexts = self._pdf_preprocessing(pdf_path)
        
        # Scale images by 1.1x before layout detection
        scaled_images = [img.resize((int(img.width * 0.9), int(img.height * 0.9)), Image.Resampling.LANCZOS) for img in images]
        
        # Run layout detection on all images
        layout_results = layout_predictor(scaled_images)

        # --- Extract TOC text from all pages before processing any page ---
        toc_texts = []
        for page_num, (layout_result, page_image) in enumerate(zip(layout_results, images)):
            layout_size = layout_result.image_bbox[2:4]
            for block in layout_result.bboxes:
                if block.label == "TableOfContents":
                    toc_text = self._lllm_extract_text_from_block(
                        block, page_image, layout_size, original_text_contexts[page_num], toc_text=None
                    )
                    if toc_text:
                        toc_texts.append(toc_text)
        combined_toc_text = "\n".join(toc_texts) if toc_texts else None
        # ---------------------------------------------------------------

        # Process each page, passing the combined TOC text
        page_texts = self._process_all_pages(layout_results, images, original_text_contexts, toc_text=combined_toc_text)
        
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
                          original_text_contexts: List[str], toc_text: str = None) -> List[str]:
        """
        Process all pages with their layout results.
        """
        page_texts = []
        
        with tqdm(total=len(layout_results), desc="Processing pages") as page_pbar:
            for page_num, (layout_result, page_image, original_text_context) in enumerate(
                zip(layout_results, images, original_text_contexts)
            ):
                page_text = self._process_single_page(
                    page_num, layout_result, page_image, original_text_context, toc_text=toc_text
                )
                page_texts.append(page_text)
                page_pbar.update(1)
        
        return page_texts
    
    def _merge_consecutive_list_items(self, blocks):
        """
        Merge consecutive blocks with label 'ListItem' into a single block.
        Returns a new list of blocks.
        Assumes every block has a label and can be constructed with bbox and label.
        """
        merged = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if block.label == 'ListItem':
                start = i
                while i + 1 < len(blocks) and blocks[i+1].label == 'ListItem':
                    i += 1
                if i > start:
                    bboxes = [blocks[j].bbox for j in range(start, i+1)]
                    x0 = min(b[0] for b in bboxes)
                    y0 = min(b[1] for b in bboxes)
                    x1 = max(b[2] for b in bboxes)
                    y1 = max(b[3] for b in bboxes)
                    # Create a new block instance with merged bbox and label
                    block_type = type(blocks[start])
                    attrs = vars(blocks[start]).copy()
                    merged_polygon = [
                        [x0, y0],
                        [x1, y0],
                        [x1, y1],
                        [x0, y1]
                    ]
                    attrs['polygon'] = merged_polygon
                    attrs['label'] = 'ListItem'
                    merged_block = block_type(**attrs)
                    merged.append(merged_block)
                else:
                    merged.append(block)
            else:
                merged.append(block)
            i += 1
        return merged

    def _process_single_page(self, page_num: int, layout_result, page_image: Image.Image, 
                   original_text_context: str | None= None, toc_text: str | None = None) -> str:
        """
        Process a single page with its layout result.
        """
        from concurrent.futures import ThreadPoolExecutor
        from tqdm import tqdm
        blocks = sorted(layout_result.bboxes, key=lambda x: x.position)
        layout_size = layout_result.image_bbox[2:4]

        if "ListItem" in {block.label for block in blocks}:
            # Merge consecutive ListItem blocks
            blocks = self._merge_consecutive_list_items(blocks)


        def process_block(block):
            if block.label in {"PageFooter", "PageHeader", "TableOfContents"}:
                return None
            return self._lllm_extract_text_from_block(
                block, page_image, layout_size, original_text_context, toc_text=toc_text
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
        return "\n".join(block_texts)

    def _lllm_extract_text_from_block(self, block, page_image: Image.Image, layout_size, original_text_context: str | None = None, toc_text: str | None = None) -> str:
        """
        Extract text from a single block using LLM.
        """
        block_image = scale_crop_image(block, page_image, layout_size)
        img_base64 = image_to_base64(block_image)
        block_type = block.label
        user_prompt = get_block_prompt(block_type, original_text_context, toc_text)
        response = completions_with_backoff(
            client=self.client,
            model="gpt-4.1-mini",
            messages=get_user_messages(img_base64, user_prompt),
            temperature=0.2
        )
        block_text = response.choices[0].message.content
        main_content = extract_markdown_content(block_text) if block_text else ""

        # For Table, Figure, Picture: generate legend in a second LLM call
        if block_type in {"Table"} and main_content:
            legend_prompt = get_legend_prompt(block_type, main_content)
            legend_response = completions_with_backoff(
                client=self.client,
                model="gpt-4.1-mini",
                messages=get_user_messages(img_base64, legend_prompt, system_prompt="You are a helpful assistant that generates a readable representation of a table"),
                temperature=0.2
            )
            legend_text = legend_response.choices[0].message.content
            legend_content = extract_markdown_content(legend_text) if legend_text else ""
            # If the combined length exceeds max_chars, return only legend_content
            if legend_content and len(main_content) + len(legend_content) > self.max_chars:
                return "\n\n" + legend_content + "\n\n" if len(legend_content) < self.max_chars or len(main_content) > self.max_chars else "\n\n" + main_content + "\n\n"
            # Otherwise, append legend to main content, separated by two newlines
            return f"\n\n{main_content}\n\n{legend_content}\n\n" if legend_content else main_content
        else:
            return main_content
