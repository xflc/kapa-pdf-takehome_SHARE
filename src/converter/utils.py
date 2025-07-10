from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path


def extract_markdown_content(text: str) -> str:
    """Extract markdown content from text that might be wrapped in code blocks."""
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


def visualize_layout_blocks(layout_results, images, output_dir="debug_layout"):
    """
    Visualize detected layout blocks on images for debugging.
    
    Args:
        layout_results: List of layout results from detect_layout_blocks()
        images: List of PIL Images corresponding to layout_results
        output_dir: Directory to save visualized images (default "debug_layout")
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(exist_ok=True)
    
    # Define colors for different block types
    colors = {
        "Text": "#FF0000",      # Red
        "SectionHeader": "#00FF00",  # Green
        "Title": "#0000FF",     # Blue
        "ListItem": "#FFFF00",  # Yellow
        "Table": "#FF00FF",     # Magenta
        "Figure": "#00FFFF",    # Cyan
        "Picture": "#FFA500",   # Orange
        "Caption": "#800080",   # Purple
        "Footnote": "#808080",  # Gray
        "Formula": "#FFC0CB",   # Pink
        "PageHeader": "#A52A2A", # Brown
        "PageFooter": "#4B0082", # Indigo
        "Form": "#008000",      # Dark Green
        "Handwriting": "#FF4500", # Orange Red
        "TableOfContents": "#2E8B57" # Sea Green
    }
    
    for page_idx, (layout_result, image) in enumerate(zip(layout_results, images)):
        # Create a copy of the image to draw on
        viz_image = image.copy()
        draw = ImageDraw.Draw(viz_image)
        
        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 12)
        except:
            font = ImageFont.load_default()
        
        # Draw each block
        for block in layout_result.bboxes:
            # Get bounding box
            if hasattr(block, 'bbox'):
                bbox = block.bbox
            else:
                # Convert polygon to bbox
                x_coords = [point[0] for point in block.polygon]
                y_coords = [point[1] for point in block.polygon]
                bbox = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
            
            # Get color for this block type
            color = colors.get(block.label, "#000000")  # Default to black
            
            # Draw bounding box
            draw.rectangle(bbox, outline=color, width=2)
            
            # Draw label
            label_text = f"{block.label}"
            text_bbox = draw.textbbox((0, 0), label_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # Position label at top-left of bounding box
            label_x = bbox[0]
            label_y = max(0, bbox[1] - text_height - 2)
            
            # Draw background rectangle for label
            draw.rectangle(
                [label_x, label_y, label_x + text_width + 4, label_y + text_height + 2],
                fill=color
            )
            
            # Draw label text
            draw.text((label_x + 2, label_y + 1), label_text, fill="white", font=font)
        
        # Save the visualized image
        output_path = os.path.join(output_dir, f"page_{page_idx + 1:03d}_layout.png")
        viz_image.save(output_path)
        print(f"Saved layout visualization: {output_path}") 