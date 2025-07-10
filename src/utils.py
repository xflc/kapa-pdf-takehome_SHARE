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