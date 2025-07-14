import base64
import io
from PIL import Image
import openai
import backoff
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6, logger=logger, jitter=backoff.full_jitter)
def completions_with_backoff(client, **kwargs):
    """OpenAI completions with exponential backoff for rate limits"""
    return client.chat.completions.create(**kwargs)


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

def image_to_base64(image: Image.Image) -> str:
    """
    Convert PIL image to base64 string.
    """
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def scale_crop_image(block, page_image: Image.Image, layout_size) -> Image.Image:
    """
    Prepare block image by scaling and cropping.
    """
    page_image_size = page_image.size
    scale_x = page_image_size[0] / layout_size[0]
    scale_y = page_image_size[1] / layout_size[1]
    block_bbox = [
        block.bbox[0] * scale_x, 
        block.bbox[1] * scale_y, 
        block.bbox[2] * scale_x, 
        block.bbox[3] * scale_y
    ]
    return page_image.crop(block_bbox)


def get_block_prompt(block_type: str, original_text_context: str | None = None, toc_text: str | None = None) -> str:
    """
    Get specialized prompt based on block type with original text context and optional TOC text.
    """
    original_text_reference = "" if not original_text_context else f"\n\nHere is the original extracted text of the whole pdf page where the attached png came from, probably with wrong formatting, for you to use as a reference, don't use it to generate the text, just use it as a reference if your OCR is unclear:\n\n{original_text_context}\n\n"
    toc_reference = (
        "Always use the corresponding markdown heading ('#', or '##', or '###', etc.). e.g., a section called 3.2 should be written as ### 3.2 or ## 3.2, never as # 3.2 or just 3.2\n" 
        if not toc_text 
        else f"\n\nFormat this heading as a markdown section heading. If it starts with numbers, use the corresponding level of markdown heading ('3.' -> '##', '2.3' -> '###', or '5.6.6' -> '####', etc.). If there is no number, check the Table of Contents of the document, to help you clarify how many '#' you should use (use '####' if it is not present in the TOC). Things like legends, footnotes, captions, etc. should have no '#' at all, just unformatted text:\n\n{toc_text}\n\n"
    )
    prompts = {
        "Text": f"Extract only the text from the attached png. Maintain original formatting and line breaks.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown)  and nothing else.",
        "SectionHeader": f"Extract only the heading text from the attached png.{toc_reference}\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Form": f"Extract only the form text from the attached png. Format as markdown form with proper formatting and indentation.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Title": f"Extract only the title text from the attached png. Format as markdown heading (# or ##).\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "ListItem": f"Extract only the list items from the attached png. Format as markdown list with proper formatting and indentation.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Table": f"Extract only the table from the attached png. Format as markdown table with proper alignment. Include all rows and columns.{original_text_reference}\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Figure": f"Describe only the figure very briefly.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Picture": f"Describe only the picture briefly and extract any visible text or captions. If it has no technical information, just write the text that is visible in the image if any. If its has no text just write '<IMAGE_ONLY>' and nothing else.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Caption": f"Extract only the caption text.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown, but don't use markdown headings like # or ## or ###) and nothing else.",
        "Footnote": f"Extract only the footnote text.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Formula": f"Extract only the mathematical formula. Format in LaTeX if possible.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Handwriting": f"Extract only the handwritting text. Format as markdown with proper formatting and indentation.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "TableOfContents": f"Extract only the table of contents. Format as markdown with proper formatting and indentation.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
    }
    prompt_out = prompts.get(block_type, None)
    if prompt_out is None:
        print(f"No prompt found for {block_type}")
        prompt_out = f"Extract all text.\nJust output the exact content of the attached image (Use the ```markdown``` tags to wrap the markdown) and nothing else."
    return prompt_out


def get_legend_prompt(block_type: str, extracted_content: str) -> str:
    """
    Get prompt for generating a legend for Table, Figure, or Picture based on extracted content.
    """
    if block_type == "Table":
        return (
            "Given the following markdown table, generate a detailed legend composed of the following bullet list: "
            "TABLE_DATA: a verbose legend in bullet list markdown format with a natural language description of each row of the table."
            "(e.g. '''TABLE_DATA:\n- Row1_Id_name: ELEMENT_NAME has 60% of the value of COLUMN1 `string x` of COLUMN2\n ...\n- Row2_Id_name: ...'''). "
            "Encapsulate both legends in a single ```markdown``` block. And dont use markdown headings like # or ## or ###. Just use the bullet list format.\n\n"
            f"Here is the extracted table:\n\n{extracted_content}\n"
        )
    elif block_type == "Figure":
        return (
            "Given the following figure description and any visible text or captions, generate a legend "
            "with a natural language description of the figure. Encapsulate the legend in a single ```markdown``` block.\n\n"
            f"Here is the extracted figure content:\n\n{extracted_content}\n"
        )
    elif block_type == "Picture":
        return (
            "Given the following picture description and any visible text or captions, generate a legend "
            "with a natural language description of the picture. Encapsulate the legend in a single ```markdown``` block.\n\n"
            f"Here is the extracted picture content:\n\n{extracted_content}\n"
        )
    else:
        raise ValueError(f"Legend prompt not supported for block type: {block_type}")

def get_user_messages(img_base64, user_prompt, system_prompt=None):
    return [
        {
            "role": "system", 
            "content": "You are a helpful assistant that extracts a markdown representation from images. Use the ```markdown``` tags to wrap the markdown." if not system_prompt else system_prompt
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
