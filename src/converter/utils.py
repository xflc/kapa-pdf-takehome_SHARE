import base64
import io
from PIL import Image
import openai
import backoff

@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6)
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


def get_block_prompt(block_type: str, original_text_context: str) -> str:
    """
    Get specialized prompt based on block type with original text context.
    """
    original_text_reference = "" if not original_text_context else f"\n\nHere is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:\n\n{original_text_context}\n\n"
    prompts = {
        "Text": f"Extract all text. Maintain original formatting and line breaks.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown)  and nothing else.",
        "SectionHeader": f"Extract the heading text. Format as markdown heading (# or ## or ###).{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Form": f"Extract the form text. Format as markdown form with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Title": f"Extract the title text. Format as markdown heading (# or ##).{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "ListItem": f"Extract list items. Format as markdown list with proper formatting and indentation.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Table": f"Extract the table. Format as markdown table with proper alignment. Include all rows and columns.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Figure": f"Describe this figure briefly and extract any visible text or captions.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
        "Picture": f"Describe this picture briefly and extract any visible text or captions.{original_text_reference}\nJust output the exact content of the image (Use the ```markdown``` tags to wrap the markdown) and nothing else.",
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