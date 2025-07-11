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
import asyncio
import aiohttp
import concurrent.futures
from threading import Thread
import queue
import time
import backoff
import openai

from tqdm import tqdm

from src.utils import extract_markdown_content

from ..loader.types import LoadedPDF
from .base import PDFtoMarkdown


@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6)
def completions_with_backoff(client, **kwargs):
    """OpenAI completions with exponential backoff for rate limits"""
    return client.chat.completions.create(**kwargs)


def convert_pdf_basic(pdf_path: Path) -> str:
    """
    Optimized pipeline: PDF → Images → Surya Layout → GPT-4o-mini Text → Markdown
    
    Key optimization: Process pages individually and run layout detection in parallel
    with OpenAI API calls from previous pages.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Markdown string of the converted PDF
    """
    return convert_pdf_pipelined(pdf_path)


def convert_pdf_pipelined(pdf_path: Path) -> str:
    """
    Pipelined version: Layout detection and OpenAI calls run in parallel
    """
    layout_predictor = LayoutPredictor()
    client = OpenAI()
    
    # Get total page count for progress bar
    pdf_doc = fitz.open(pdf_path)
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    # Results storage - ordered by page number
    page_results = {}
    
    # Thread-safe queues for pipeline
    layout_queue = queue.Queue()  # (page_num, layout_result, page_image)
    
    # Progress tracking variables
    layout_progress = {"completed": 0}
    openai_progress = {"completed": 0}
    
    def layout_worker():
        """Worker thread for layout detection"""
        pdf_doc = fitz.open(pdf_path)
        with tqdm(total=total_pages, desc="📄 Layout Detection", position=0, leave=True) as layout_pbar:
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]
                # Convert page to image
                page_image = page.get_pixmap()  # type: ignore
                img_data = page_image.tobytes("png")
                image_pil = Image.open(io.BytesIO(img_data))
                
                # Run layout detection on single page
                layout_result = layout_predictor([image_pil])[0]
                
                # Put result in queue for OpenAI worker
                layout_queue.put((page_num, layout_result, image_pil))
                
                # Update progress
                layout_progress["completed"] += 1
                layout_pbar.update(1)
        
        # Signal completion
        layout_queue.put(None)
        pdf_doc.close()
    
    def openai_worker():
        """Worker thread for OpenAI API calls"""
        with tqdm(total=total_pages, desc="🤖 OpenAI Processing", position=1, leave=True) as openai_pbar:
            while True:
                item = layout_queue.get()
                if item is None:  # Completion signal
                    break
                    
                page_num, layout_result, page_image = item
                
                # Process blocks for this page
                blocks = layout_result.bboxes
                blocks = sorted(blocks, key=lambda x: x.position)
                
                # Calculate scale factors
                layout_size = layout_result.image_bbox[2:4]
                page_image_size = page_image.size
                scale_x = page_image_size[0] / layout_size[0]
                scale_y = page_image_size[1] / layout_size[1]
                
                def process_block(block_data):
                    """Process a single block with OpenAI"""
                    block_idx, block = block_data
                    
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
                    
                    # Send image to gpt-4o-mini
                    response = completions_with_backoff(
                        client,
                        model="gpt-4o-mini",
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
                    if block_text:
                        return block_idx, extract_markdown_content(block_text)
                    else:
                        return block_idx, ""  # Handle None case
                
                # Process blocks in parallel (up to 3 at a time)
                block_texts = [""] * len(blocks)  # Initialize with correct size
                
                # Nested progress bar for blocks within the page
                with tqdm(total=len(blocks), desc=f"  📝 Page {page_num + 1} blocks", position=2, leave=False) as block_pbar:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        # Submit all blocks with their indices
                        future_to_block = {
                            executor.submit(process_block, (idx, block)): idx 
                            for idx, block in enumerate(blocks)
                        }
                        
                        # Collect results as they complete
                        for future in concurrent.futures.as_completed(future_to_block):
                            try:
                                block_idx, block_text = future.result()
                                block_texts[block_idx] = block_text
                                block_pbar.update(1)
                            except Exception as exc:
                                block_idx = future_to_block[future]
                                print(f'Block {block_idx} generated an exception: {exc}')
                                block_texts[block_idx] = ""  # Handle exception
                                block_pbar.update(1)
                
                # Store result for this page
                page_results[page_num] = "\n".join(block_texts)
                layout_queue.task_done()
                
                # Update progress
                openai_progress["completed"] += 1
                openai_pbar.update(1)
    
    # Start both workers
    layout_thread = Thread(target=layout_worker)
    openai_thread = Thread(target=openai_worker)
    
    layout_thread.start()
    openai_thread.start()
    
    # Wait for completion
    layout_thread.join()
    openai_thread.join()
    
    # Combine results in order
    page_texts = []
    for page_num in range(total_pages):
        if page_num in page_results:
            page_texts.append(page_results[page_num])
        else:
            page_texts.append("")  # Handle missing pages
    
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