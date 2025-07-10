#!/usr/bin/env python3
"""
Simple PDF Processing Pipeline
==============================

A straightforward functional pipeline that connects:
1. PDF loading → 2. Surya layout detection → 3. GPT-4.1-mini text extraction

No complex classes, just simple functions you can chain together.
"""

import os
import fitz  # PyMuPDF
import tempfile
import base64
import io
from pathlib import Path
from PIL import Image
from openai import OpenAI
from surya.layout import LayoutPredictor
from surya.layout.schema import LayoutBox
from ..openai import completions_with_backoff
from ..utils import extract_markdown_content, visualize_layout_blocks
import structlog
import numpy as np
import logging
import structlog
from tqdm import tqdm

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger()

# Global predictor instance for reuse
_layout_predictor = None


def _polygon_to_bbox(polygon):
    """Convert polygon to bounding box (x1, y1, x2, y2)."""
    x_coords = [point[0] for point in polygon]
    y_coords = [point[1] for point in polygon]
    return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))


def get_layout_predictor():
    """
    Get or create a LayoutPredictor instance for reuse.
    This prevents loading the model multiple times.
    """
    global _layout_predictor
    if _layout_predictor is None:
        _layout_predictor = LayoutPredictor()
    return _layout_predictor


def load_pdf_as_images(pdf_path_or_bytes, zoom_layout=.5, zoom_ocr=1.2):
    """
    Step 1: Load PDF and convert pages to images at two different resolutions.
    
    Args:
        pdf_path_or_bytes: Path to PDF file or raw bytes
        zoom_layout: Lower resolution for layout detection (default 1.0)
        zoom_ocr: Higher resolution for text extraction (default 2.0)
    
    Returns:
        Tuple of (layout_images, ocr_images, original_texts) - images are lists of PIL Images, original_texts is list of strings
    """
    if isinstance(pdf_path_or_bytes, (str, Path)):
        pdf_doc = fitz.open(pdf_path_or_bytes)
    else:
        # Handle raw bytes
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(pdf_path_or_bytes)
            temp_file_path = temp_file.name
        pdf_doc = fitz.open(temp_file_path)
    
    layout_images = []
    ocr_images = []
    original_texts = []
    
    for page_num in range(len(pdf_doc)):
        page = pdf_doc[page_num]
        
        # Extract original text from this page
        original_text = page.get_text()  # type: ignore
        original_texts.append(original_text)
        
        # Low-res image for layout detection
        mat_layout = fitz.Matrix(zoom_layout, zoom_layout)
        pix_layout = page.get_pixmap(matrix=mat_layout)  # type: ignore
        img_data_layout = pix_layout.tobytes("png")
        layout_image = Image.open(io.BytesIO(img_data_layout))
        layout_images.append(layout_image)
        
        # High-res image for OCR/text extraction
        mat_ocr = fitz.Matrix(zoom_ocr, zoom_ocr)
        pix_ocr = page.get_pixmap(matrix=mat_ocr)  # type: ignore
        img_data_ocr = pix_ocr.tobytes("png")
        ocr_image = Image.open(io.BytesIO(img_data_ocr))
        ocr_images.append(ocr_image)
    
    pdf_doc.close()
    
    # Clean up temp file if we created one
    if not isinstance(pdf_path_or_bytes, (str, Path)):
        os.unlink(temp_file_path)
    
    return layout_images, ocr_images, original_texts


def detect_layout_blocks(layout_images, layout_predictor=None, batch_size=6):
    """
    Step 2: Use Surya to detect layout blocks in low-res images with batching.
    
    Args:
        layout_images: List of low-res PIL Images for layout detection
        layout_predictor: Pre-loaded LayoutPredictor (optional, will create if None)
        batch_size: Number of images to process at once (default 6)
    
    Returns:
        List of layout results, one per page
        Each result contains: bboxes with {label, bbox, polygon, position, confidence}
    """
    if layout_predictor is None:
        layout_predictor = get_layout_predictor()
    
    # Process all images in batches for better performance
    print(f"Processing {len(layout_images)} images with batch size {batch_size}")
    layout_results = layout_predictor(layout_images, batch_size=batch_size)
    
    return layout_results


def extract_text_from_blocks(layout_results, ocr_images, original_texts, openai_api_key=None):
    """
    Step 3: Extract text from each block using GPT-4.1-mini on high-res images.
    
    Args:
        layout_results: Output from detect_layout_blocks()
        ocr_images: List of high-res PIL Images for text extraction
        original_texts: List of original text strings from PDF pages
        openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
    
    Returns:
        List of page texts (markdown strings)
    """
    api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key required")
    
    client = OpenAI(api_key=api_key)
    page_texts = []
    
    # Overall progress bar for pages
    with tqdm(total=len(layout_results), desc="Processing document pages") as page_pbar:
        for page_num, (layout_result, ocr_image, original_text) in enumerate(zip(layout_results, ocr_images, original_texts)):
            # Get blocks and sort by reading order
            blocks = layout_result.bboxes
            blocks = sorted(blocks, key=lambda x: x.position)
            
            # Calculate scale factors
            layout_size = layout_result.image_bbox[2:4]
            ocr_size = ocr_image.size
            scale_x = ocr_size[0] / layout_size[0]
            scale_y = ocr_size[1] / layout_size[1]
            
            block_texts = []
            
            # Progress bar for blocks within current page (disappears after page is done)
            with tqdm(total=len(blocks), desc=f"Page {page_num + 1} blocks", leave=False) as block_pbar:
                for block in blocks:
                    try:
                        # Get block coordinates
                        bbox = block.bbox if hasattr(block, 'bbox') else _polygon_to_bbox(block.polygon)
                        
                        # Scale to OCR image size
                        x1, y1, x2, y2 = bbox
                        scaled_bbox = (
                            int(x1 * scale_x),
                            int(y1 * scale_y),
                            int(x2 * scale_x),
                            int(y2 * scale_y)
                        )
                        
                        # Crop and convert to base64
                        cropped_image = ocr_image.crop(scaled_bbox)
                        buffer = io.BytesIO()
                        cropped_image.save(buffer, format="PNG")
                        image_base64 = base64.b64encode(buffer.getvalue()).decode()
                        
                        # Get text from GPT-4o-mini with exponential backoff and retry logic
                        prompt = _get_prompt_for_block_type(block.label, original_text)
                        
                        # Retry logic for refusal responses
                        max_retries = 3
                        for retry_attempt in range(max_retries):
                            response = completions_with_backoff(
                                client,
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {
                                            "url": f"data:image/png;base64,{image_base64}",
                                            "detail": "high"
                                        }}
                                    ]
                                }],
                                model="gpt-4o-mini",
                                temperature=0
                            )
                            
                            content = response.choices[0].message.content
                            if content:
                                text = content.strip()
                                
                                # Check for refusal patterns
                                refusal_patterns = [
                                    "im unable",
                                    "i'm unable", 
                                    "i cannot",
                                    "i can't",
                                    "unable to",
                                    "cannot process",
                                    "can't process",
                                    "sorry, but i",
                                    "i'm sorry, but",
                                    "i apologize, but"
                                ]
                                
                                text_lower = text.lower()
                                is_refusal = any(pattern in text_lower for pattern in refusal_patterns)
                                
                                if is_refusal and retry_attempt < max_retries :
                                    print(f"  Retry {retry_attempt + 1}/{max_retries} for {block.label} block (refusal detected)")
                                    continue  # Retry
                                elif text and not is_refusal:
                                    block_texts.append(extract_markdown_content(text))
                                    break  # Success
                            else:
                                break  # No content, don't retry
                            
                    except Exception as e:
                        print(f"Error processing {block.label} block: {str(e)}")
                    
                    block_pbar.update(1)
            
            # Join all block texts for this page
            page_text = "\n\n".join(block_texts)
            page_texts.append(page_text)
            
            # Update page progress
            page_pbar.set_postfix({"Page": f"{page_num + 1}/{len(layout_results)}"})
            page_pbar.update(1)
    
    return page_texts


def process_pdf_simple(pdf_path_or_bytes, openai_api_key=None, batch_size=6, debug_visualize=False, merge_list_blocks=True):
    """
    Complete pipeline: PDF → Layout Images → Layout → OCR Images → Text extraction.
    
    Args:
        pdf_path_or_bytes: Path to PDF or raw PDF bytes
        openai_api_key: OpenAI API key
        batch_size: Batch size for layout detection (default 6)
        debug_visualize: If True, save debug images showing detected blocks (default False)
        merge_list_blocks: If True, merge consecutive List-item blocks (default True)
    
    Returns:
        String with full markdown content
    """
    print("Step 1: Loading PDF as images...")
    layout_images, ocr_images, original_texts = load_pdf_as_images(pdf_path_or_bytes)
    print(f"Loaded {len(layout_images)} pages (layout: {layout_images[0].size}, OCR: {ocr_images[0].size})")
    
    print("Step 2: Detecting layout blocks...")
    # Use shared predictor for better performance
    layout_predictor = get_layout_predictor()
    layout_results = detect_layout_blocks(layout_images, layout_predictor=layout_predictor, batch_size=batch_size)
    total_blocks = sum(len(result.bboxes) for result in layout_results)
    print(f"Found {total_blocks} blocks across all pages")
    
    # Optional: merge consecutive List-item blocks
    if merge_list_blocks:
        print("Step 2.1: Merging consecutive List-item blocks...")
        layout_results = merge_consecutive_list_blocks(layout_results, layout_images)
        total_blocks_after_merge = sum(len(result.bboxes) for result in layout_results)
        print(f"After merging: {total_blocks_after_merge} blocks across all pages")
    
    # Optional: visualize layout blocks for debugging
    if debug_visualize:
        print(f"Step 2.{2 if merge_list_blocks else 1}: Saving layout visualization...")
        visualize_layout_blocks(layout_results, layout_images)
    
    print("Step 3: Extracting text with GPT-4.1-mini...")
    page_texts = extract_text_from_blocks(layout_results, ocr_images, original_texts, openai_api_key)
    
    return "\n\n---\n\n".join(page_texts)



# Helper functions
def _get_prompt_for_block_type(block_type, original_text=""):
    """Get appropriate prompt for each block type, including original text reference."""
    # Add original text context if available
    original_text_context = ""
    if original_text.strip():
        original_text_context = f"'''\n\n{original_text.strip()}\n\n'''"
    
    prompts = {
        "Text": f"Extract all text. Maintain original formatting and line breaks.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```)  and nothing else.",
        "SectionHeader": f"Extract the heading text. Format as markdown heading (# or ## or ###).\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Form": f"Extract the form text. Format as markdown form with proper indentation.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Title": f"Extract the title text. Format as markdown heading (# or ##).\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "ListItem": f"Extract list items. Format as markdown list with proper indentation.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Table": f"Extract the table. Format as markdown table with proper alignment. Include all rows and columns.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Figure": f"Describe this figure briefly and extract any visible text or captions.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Picture": f"Describe this picture briefly and extract any visible text or captions.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Caption": f"Extract the caption text.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Footnote": f"Extract the footnote text.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Formula": f"Extract the mathematical formula. Format in LaTeX if possible.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "PageHeader": f"Extract the header text.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "PageFooter": f"Extract the footer text.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "Handwriting": f"Extract the handwritting text. Format as markdown with proper indentation.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
        "TableOfContents": f"Extract the table of contents. Format as markdown with proper indentation.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else.",
    }
    prompt_out = prompts.get(block_type, None)
    if prompt_out is None:
        print(f"No prompt found for {block_type}")
        prompt_out = f"Extract all text.\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:{original_text_context}\nJust output the exact content of the image (just start with ```markdown...```) and nothing else."
    return prompt_out


def merge_consecutive_list_blocks(layout_results, images):
    """
    Merge consecutive List-item blocks into single blocks.
    
    Args:
        layout_results: List of layout results from detect_layout_blocks()
        images: List of PIL Images corresponding to layout_results
    
    Returns:
        Modified layout_results with merged List-item blocks
    """
    merged_results = []
    
    for page_idx, (layout_result, image) in enumerate(zip(layout_results, images)):
        blocks = layout_result.bboxes
        # Sort blocks by position for proper consecutive detection
        blocks = sorted(blocks, key=lambda x: x.position)
        
        merged_blocks = []
        i = 0
        
        while i < len(blocks):
            current_block = blocks[i]
            
            # If this is a List-item block, look for consecutive List-item blocks
            if current_block.label == "ListItem":
                consecutive_blocks = [current_block]
                j = i + 1
                
                # Find all consecutive List-item blocks
                while j < len(blocks) and blocks[j].label == "ListItem":
                    consecutive_blocks.append(blocks[j])
                    j += 1
                
                # If we found multiple consecutive List-item blocks, merge them
                if len(consecutive_blocks) > 1:
                    # Get all bounding boxes
                    all_bboxes = []
                    for block in consecutive_blocks:
                        if hasattr(block, 'bbox'):
                            all_bboxes.append(block.bbox)
                        else:
                            all_bboxes.append(_polygon_to_bbox(block.polygon))
                    
                    # Calculate merged bounding box (min/max coordinates)
                    min_x = min(bbox[0] for bbox in all_bboxes)
                    min_y = min(bbox[1] for bbox in all_bboxes)
                    max_x = max(bbox[2] for bbox in all_bboxes)
                    max_y = max(bbox[3] for bbox in all_bboxes)
                    
                    merged_bbox = (min_x, min_y, max_x, max_y)
                    merged_polygon = [
                        [min_x, min_y], [max_x, min_y], 
                        [max_x, max_y], [min_x, max_y]
                    ]
                    
                    # Create a new LayoutBox using the actual class
                    merged_block = LayoutBox(
                        polygon=merged_polygon,
                        label=consecutive_blocks[0].label,
                        position=consecutive_blocks[0].position
                    )
                    
                    merged_blocks.append(merged_block)
                    print(f"Page {page_idx + 1}: Merged {len(consecutive_blocks)} consecutive ListItem blocks")
                else:
                    # Single List-item block, keep as is
                    merged_blocks.append(current_block)
                
                # Move index to after the processed consecutive blocks
                i = j
            else:
                # Non-List-item block, keep as is
                merged_blocks.append(current_block)
                i += 1
        
        #print the before and after of the merged blocks in a single print:
        print(f"before/after merging: {len(blocks)}/{len(merged_blocks)}")

        # Update the layout result with merged blocks
        layout_result.bboxes = merged_blocks
        merged_results.append(layout_result)
    
    return merged_results 