#!/usr/bin/env python3
"""
Performance test: Batch vs Individual Layout Processing
======================================================

Test to compare performance of processing all images at once vs one by one
for the Surya layout predictor.
"""

import time
import fitz  # PyMuPDF
import io
from pathlib import Path
from PIL import Image
from surya.layout import LayoutPredictor
import psutil
import os

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def load_pdf_pages(pdf_path: Path):
    """Load all pages from PDF as PIL images"""
    images = []
    pdf_doc = fitz.open(pdf_path)
    
    print(f"Loading {len(pdf_doc)} pages from PDF...")
    for page_num, page in enumerate(pdf_doc):
        page_image = page.get_pixmap()
        img_data = page_image.tobytes("png")
        image_pil = Image.open(io.BytesIO(img_data))
        images.append(image_pil)
        print(f"  Loaded page {page_num + 1}/{len(pdf_doc)}")
    
    pdf_doc.close()
    return images

def test_batch_processing(images):
    """Test batch processing - all images at once"""
    print("\n=== BATCH PROCESSING TEST ===")
    
    layout_predictor = LayoutPredictor()
    
    # Measure memory before
    memory_before = get_memory_usage()
    print(f"Memory before: {memory_before:.2f} MB")
    
    # Time the batch processing
    start_time = time.time()
    layout_results = layout_predictor(images)
    end_time = time.time()
    
    # Measure memory after
    memory_after = get_memory_usage()
    print(f"Memory after: {memory_after:.2f} MB")
    print(f"Memory increase: {memory_after - memory_before:.2f} MB")
    
    batch_time = end_time - start_time
    print(f"Batch processing time: {batch_time:.2f} seconds")
    print(f"Time per page: {batch_time / len(images):.2f} seconds")
    
    return layout_results, batch_time

def test_individual_processing(images):
    """Test individual processing - one image at a time"""
    print("\n=== INDIVIDUAL PROCESSING TEST ===")
    
    layout_predictor = LayoutPredictor()
    
    # Measure memory before
    memory_before = get_memory_usage()
    print(f"Memory before: {memory_before:.2f} MB")
    
    layout_results = []
    total_time = 0
    
    for i, image in enumerate(images):
        print(f"Processing page {i + 1}/{len(images)}")
        
        start_time = time.time()
        result = layout_predictor([image])[0]  # Process single image
        end_time = time.time()
        
        layout_results.append(result)
        page_time = end_time - start_time
        total_time += page_time
        
        print(f"  Page {i + 1} time: {page_time:.2f} seconds")
    
    # Measure memory after
    memory_after = get_memory_usage()
    print(f"Memory after: {memory_after:.2f} MB")
    print(f"Memory increase: {memory_after - memory_before:.2f} MB")
    
    print(f"Total individual processing time: {total_time:.2f} seconds")
    print(f"Average time per page: {total_time / len(images):.2f} seconds")
    
    return layout_results, total_time

def test_model_initialization():
    """Test how long it takes to initialize the model"""
    print("\n=== MODEL INITIALIZATION TEST ===")
    
    # Test single initialization
    start_time = time.time()
    layout_predictor = LayoutPredictor()
    end_time = time.time()
    
    init_time = end_time - start_time
    print(f"Single model initialization time: {init_time:.2f} seconds")
    
    # Test multiple initializations (to simulate individual processing)
    start_time = time.time()
    for i in range(3):  # Test 3 initializations
        layout_predictor = LayoutPredictor()
    end_time = time.time()
    
    multi_init_time = end_time - start_time
    print(f"Three model initializations time: {multi_init_time:.2f} seconds")
    print(f"Average initialization time: {multi_init_time / 3:.2f} seconds")
    
    return init_time

def main():
    pdf_path = Path("data/pdfs/21098-ESPS2WROOM-scan.pdf")
    
    if not pdf_path.exists():
        print(f"PDF file not found: {pdf_path}")
        return
    
    print(f"Testing layout predictor performance with: {pdf_path}")
    print(f"File size: {pdf_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Test model initialization overhead
    init_time = test_model_initialization()
    
    # Load all pages
    print("\n=== LOADING PDF PAGES ===")
    memory_before_load = get_memory_usage()
    images = load_pdf_pages(pdf_path)
    memory_after_load = get_memory_usage()
    
    print(f"Memory for loading {len(images)} pages: {memory_after_load - memory_before_load:.2f} MB")
    print(f"Average memory per page: {(memory_after_load - memory_before_load) / len(images):.2f} MB")
    
    # Test batch processing
    batch_results, batch_time = test_batch_processing(images)
    
    # Test individual processing
    individual_results, individual_time = test_individual_processing(images)
    
    # Compare results
    print("\n=== PERFORMANCE COMPARISON ===")
    print(f"Batch processing time: {batch_time:.2f} seconds")
    print(f"Individual processing time: {individual_time:.2f} seconds")
    print(f"Speedup factor: {individual_time / batch_time:.2f}x")
    
    if batch_time < individual_time:
        print(f"✅ Batch processing is {individual_time / batch_time:.2f}x FASTER")
    else:
        print(f"❌ Individual processing is {batch_time / individual_time:.2f}x FASTER")
    
    # Account for model initialization overhead in individual processing
    # (if we were to initialize model for each page separately)
    individual_with_init = individual_time + (init_time * len(images))
    print(f"\nIf model was initialized per page:")
    print(f"Individual + init time: {individual_with_init:.2f} seconds")
    print(f"Batch vs Individual+init speedup: {individual_with_init / batch_time:.2f}x")
    
    # Verify results are similar
    print(f"\n=== RESULT VERIFICATION ===")
    print(f"Batch results: {len(batch_results)} pages")
    print(f"Individual results: {len(individual_results)} pages")
    
    # Check if we got the same number of blocks
    batch_blocks = sum(len(result.bboxes) for result in batch_results)
    individual_blocks = sum(len(result.bboxes) for result in individual_results)
    
    print(f"Total blocks (batch): {batch_blocks}")
    print(f"Total blocks (individual): {individual_blocks}")
    
    if batch_blocks == individual_blocks:
        print("✅ Results are consistent!")
    else:
        print("❌ Results differ - this needs investigation")

if __name__ == "__main__":
    main() 