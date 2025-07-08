def extract_markdown_content(text: str) -> str:
    start_tag = "```markdown"
    start = text.find(start_tag) 
    start = start if start != -1 else text.find("```\nmarkdown")
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


import os
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


def visualize_layout_blocks(layout_results, images, output_dir="debug_layout"):
    """
    Visualize layout blocks by overlaying them on images with different colors for each block type.
    
    Args:
        layout_results: List of layout results from detect_layout_blocks()
        images: List of PIL Images (can be layout_images or ocr_images)
        output_dir: Directory to save the visualized images
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Define colors for different block types
    block_colors = {
        "Text": "#FF0000",         # Red
        "Section-header": "#00FF00", # Green
        "Title": "#0000FF",        # Blue
        "List-item": "#FF00FF",    # Magenta
        "Table": "#FFFF00",        # Yellow
        "Figure": "#00FFFF",       # Cyan
        "Picture": "#FFA500",      # Orange
        "Caption": "#800080",      # Purple
        "Footnote": "#808080",     # Gray
        "Formula": "#FFC0CB",      # Pink
        "Page-header": "#008000",  # Dark Green
        "Page-footer": "#000080",  # Navy
    }
    
    # Default color for unknown block types
    default_color = "#000000"  # Black
    
    for page_num, (layout_result, image) in enumerate(zip(layout_results, images)):
        # Create a copy of the image to draw on
        img_copy = image.copy()
        draw = ImageDraw.Draw(img_copy)
        
        # Try to use a font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Get blocks and sort by reading order
        blocks = layout_result.bboxes
        blocks = sorted(blocks, key=lambda x: x.position)
        
        # Calculate scale factors if needed
        layout_size = layout_result.image_bbox[2:4]
        image_size = image.size
        scale_x = image_size[0] / layout_size[0]
        scale_y = image_size[1] / layout_size[1]
        
        # Draw each block
        for i, block in enumerate(blocks):
            # Get block coordinates
            if hasattr(block, 'bbox'):
                bbox = block.bbox
            else:
                # Convert polygon to bbox
                x_coords = [point[0] for point in block.polygon]
                y_coords = [point[1] for point in block.polygon]
                bbox = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
            
            # Scale coordinates to image size
            x1, y1, x2, y2 = bbox
            scaled_bbox = (
                int(x1 * scale_x),
                int(y1 * scale_y),
                int(x2 * scale_x),
                int(y2 * scale_y)
            )
            
            # Get color for this block type
            color = block_colors.get(block.label, default_color)
            
            # Draw bounding box
            draw.rectangle(scaled_bbox, outline=color, width=2)
            
            # Draw block type label
            label_text = f"{block.label} ({i+1})"
            text_bbox = draw.textbbox((0, 0), label_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # Position label at top-left of block
            label_x = scaled_bbox[0]
            label_y = max(0, scaled_bbox[1] - text_height - 2)
            
            # Draw background for text
            draw.rectangle(
                (label_x, label_y, label_x + text_width + 4, label_y + text_height + 2),
                fill=color
            )
            
            # Draw text
            draw.text((label_x + 2, label_y + 1), label_text, fill="white", font=font)
        
        # Save the image
        output_path = os.path.join(output_dir, f"page_{page_num + 1}_layout.png")
        img_copy.save(output_path)
        print(f"Saved layout visualization: {output_path}")
    
    # Create a legend image
    _create_legend(block_colors, output_dir)
    
    print(f"Layout visualization complete! Check {output_dir} directory for images.")


def _create_legend(block_colors, output_dir):
    """Create a legend image showing the color mapping for block types."""
    # Create legend image
    legend_width = 300
    legend_height = len(block_colors) * 25 + 40
    legend_img = Image.new('RGB', (legend_width, legend_height), 'white')
    draw = ImageDraw.Draw(legend_img)
    
    # Try to use a font, fall back to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except:
        font = ImageFont.load_default()
    
    # Title
    draw.text((10, 10), "Block Type Legend", fill="black", font=font)
    
    # Draw legend entries
    y_offset = 35
    for block_type, color in block_colors.items():
        # Draw color rectangle
        draw.rectangle((10, y_offset, 30, y_offset + 15), fill=color, outline="black")
        # Draw text
        draw.text((40, y_offset + 2), block_type, fill="black", font=font)
        y_offset += 25
    
    # Save legend
    legend_path = os.path.join(output_dir, "legend.png")
    legend_img.save(legend_path)
    print(f"Saved legend: {legend_path}")
