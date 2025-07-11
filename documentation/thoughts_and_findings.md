# First Approach
In this first approach, I saw that 21098-ESPS2WROOM-scan.pdf simply had no information since it is a scanned document. So, I used `page.get_textpage_ocr()` (which uses pytesseract) to extract the text. The first pdf was a success, but the other two were the same obviously.

## Results


### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Works | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✓ Works | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✗ Needs improvement | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✗ Needs improvement | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (31) | 15 |

### `esp8266-technical_reference_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What’s the **flash memory** of EFM8BB31F32G-D-QFP32? | 32 kB | 4 |
| ✓ Works | What is the **maximum storage temperature** for EFM8BB3? | 150 °C | 40 |
| ✗ Needs improvement | How many **multi-function I/O pins** does EFM8BB3 have? | Up to 29 | 10 |
| ✗ Needs improvement | What is the **minimum Voltage Reference Range for DACs**? | 1.15 V | 31 |
| ✗ Needs improvement | What are the different **power modes** for EFM8BB3? | Normal, Idle, Suspend, Stop, Snooze, Shutdown | 10 |



# Second Approach
The second approach completely replaced the PymuConverter with a MarkerConverter that uses the marker-pdf library - a more sophisticated PDF-to-markdown conversion tool. There were other options we thought about like docling, mineru and unstructured.io. We decided to go with marker since, given that i couldnt find any decent independent benchmarks comparing these options, it was the simplest and most straightforward to control locally (i.e. small models locally, openai integration for high quality OCR)

Key Features of MarkerConverter:
- Advanced PDF Processing: Uses marker-pdf library instead of the simpler PyMuPDF approach
- OpenAI LLM Integration: Optional LLM enhancement for improved conversion quality
- Performance Optimization:
  - Lazy loading of models (_get_model_dict())
  - Caching of converter instances
  - Efficient temporary file handling
- Image Extraction: Can extract and handle images from PDFs
- Configurable Pipeline: Flexible configuration system with processors and renderers

## Results

The preliminary results were promising since it got the second and almost the third questions of esp8266_hardware_design_guidelines_en.pdf correctly (the model wrote RES12K, but got the pin number right). However, the model broke the openai rate limits when trying to process esp8266-technical_reference_en.pdf.


### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Works | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✓ Works | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✓ Works | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✗/✓ Works | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (the model wrote RES12K, but got the number right) (31) | 15 |

### `esp8266-technical_reference_en.pdf` (didn't run. too large of a file, makes the conversion very slow and breaks openai rate limits)

After I tried to customize the pipeline for esp8266-technical_reference_en.pdf, I found that marker was very slow to handle the large file size, it broke the openai rate limits and was very slow to install because of its huge list of dependecies. The speed problem was not diagnosed, but the problems with openai rate limits were because there was no way to customize the pipeline to implement a simple backoff strategy.


Therefore, I had to make a choice. Do I try these different libraries that promise to process pdfs well and risk spending a few nights of work trying to get them to work, or after studying the marker library, am I confident that I can manually and rapidly implement a pipeline that works well enough for this specific use case and these questions?

I decided to go with the second approach, since I was confident that gpt-4.1-mini would be able to parse these pages correctly if we broke down each page into its main layout blocks (marker just calls surya.layout.LayoutPredictor from an external library).

# Third Approach: Custom Surya Pipeline

Building a custom pipeline using Surya layout detection + GPT-4o-mini for text extraction:

1. **PDF → Images**: Convert PDF pages to PIL images using PyMuPDF
2. **Layout Detection**: Use Surya LayoutPredictor to detect text blocks and layout elements
3. **Block Extraction**: Crop individual layout blocks from page images
4. **Text Extraction**: Send block images to GPT-4o-mini for markdown extraction
5. **Assembly**: Combine extracted text blocks back into complete markdown

**Key Features**:
- Direct control over the pipeline (no rate limiting issues)
- Batch processing for layout detection efficiency
- Pipelined workflow to parallelize layout detection and OpenAI API calls
- Handles scanned documents through vision models rather than OCR

**Status**: Implementation in progress (`src/converter/basic_surya_pipeline.py`)

## Performance Note: Layout Processing

**CPU Utilization Optimization**: Since we're just using CPU, waiting for layout detection and OpenAI API calls to finish sequentially is clearly inefficient. 

**Quick Test Results** (`test_layout_performance.py` on 21098-ESPS2WROOM-scan.pdf):
- Batch layout processing: 8.13s (1.32x faster than in sequence)
- Individual processing: 10.74s 
- Batch uses more memory (+370MB) but is more efficient overall

**Conclusion**: Use batch processing for layout detection, but pipeline the workflow so OpenAI API calls happen in parallel with layout detection of subsequent chunks. 

## Results


### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✗ Needs improvement | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Works | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✗ Needs improvement | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✗ Needs improvement | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✗ Needs improvement | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (31) | 15 |

### `esp8266-technical_reference_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✗ Needs improvement | What’s the **flash memory** of EFM8BB31F32G-D-QFP32? | 32 kB | 4 |
| ✗ Needs improvement | What is the **maximum storage temperature** for EFM8BB3? | 150 °C | 40 |
| ✗/✓ Works | How many **multi-function I/O pins** does EFM8BB3 have? | Up to 29 | 10 |
| ✓ Works | What is the **minimum Voltage Reference Range for DACs**? | 1.15 V | 31 |
| ✗ Needs improvement | What are the different **power modes** for EFM8BB3? | Normal, Idle, Suspend, Stop, Snooze, Shutdown | 10 |

## Comments
There are a few things that are not working well:
- The markdown hierarchy is not working. I need to improve the prompt for the model to know if it is a header or normal text
- some contents like table of contents are not well formated. Again, we should add that context to the prompt
- I should add the original text to the prompt to help


# Fourth Approach: Improved Prompt

This approach focused on improving the prompts sent to the model for better text extraction and formatting. Key improvements included:

## Prompt Enhancements

### 1. **Block-Type Specialized Prompts (`get_block_prompt` Function)**

The core innovation was implementing specialized prompts for different layout elements detected by Surya. Instead of using a generic "extract text" prompt for all blocks, we created tailored instructions for each block type:

**Logic Behind Specialized Prompts:**
- **Different Content Types Need Different Handling**: A table requires different formatting than a title or caption
- **Preserve Document Structure**: Headers should become markdown headings, lists should maintain proper indentation
- **Optimize for Retrieval**: Well-formatted markdown improves chunking and semantic search quality
- **Context-Aware Processing**: Each block type has specific formatting requirements and common patterns

**Block Type Categories:**
- **Structural Elements**: `Title`, `SectionHeader` → Format as markdown headings (`# ## ###`)
- **Text Content**: `Text`, `Form`, `Handwriting` → Preserve formatting and indentation
- **Lists**: `ListItem`, `TableOfContents` → Maintain list structure with proper indentation
- **Data**: `Table` → Convert to markdown table format with proper alignment
- **Visual Elements**: `Figure`, `Picture` → Extract and describe visual content (no extra legends yet)
- **Metadata**: `PageHeader`, `PageFooter`, `Caption`, `Footnote` → Handle appropriately (headers can be headings, footers are plain text)
- **Special Content**: `Formula` → Format in LaTeX when possible

**Original Text Context Integration:**
- Added original text from the PDF page as reference context to help the model understand the content better
- Format: `"Here is the original extracted text of the whole page where the attachment came from, probably with wrong formatting, for you to use as a reference:\n\n{original_text_context}\n\n"`

### 2. **Rate Limiting Solution**
- Implemented exponential backoff using the `backoff` library
- Added `completions_with_backoff()` function to handle OpenAI rate limits gracefully
- Configuration: max 60 seconds, max 6 tries with exponential backoff




### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Works | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✗ Needs improvement | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — | (the model wrote 2109B instead of 21098 so it thinks the answer is not there even though it was retreived. this works much better when there is original text to reference)

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✓ Works | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✓ Works | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (31) | 15 |

### `esp8266-technical_reference_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What’s the **flash memory** of EFM8BB31F32G-D-QFP32? | 32 kB | 4 |
| ✗ Needs improvement | What is the **maximum storage temperature** for EFM8BB3? | 150 °C | 40 |
| ✓ Works | How many **multi-function I/O pins** does EFM8BB3 have? | Up to 29 | 10 |
| ✓ Works | What is the **minimum Voltage Reference Range for DACs**? | 1.15 V | 31 |
| ✗ Needs improvement | What are the different **power modes** for EFM8BB3? | Normal, Idle, Suspend, Stop, Snooze, Shutdown | 10 | (one of the three chunks was just a caption, so the model couldnt retrieve the right info in top_3. I'm confident it would work if we had more chunks, but we can improve the markdown headers to increase the quality of the chunks by finetuning the prompt)

Possible Next steps:
- Improve the markdown headers to increase the quality of the chunks by finetuning the prompt by being more opinionated about the hierarchy of each block type 
- Add captions for complex elements like tables and pictures describing its content
- call a model after the whole page is aggregated to fix the markdown headers and the hierarchy of the markdown
- Technical goal: add concurrency to the openai api calls and parallelize with the layout detection to speed up the process


# Fifth Approach: Improved Prompt for Tables and Pictures

I asked for a detailed legend for tables and pictures since i understood that the model was not able to understand the meaning of specific cells even though we were retreiving the right chunk. I asked for a legend explaining the table and a boosted legend explaining the data in every row (but the model rarely follows the latter).


//These results were ran in a sliced version of the pdf and needs to be rerun
### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Works | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✓ Works | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✓ Works | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✓ Works | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (31) | 15 |

### `esp8266-technical_reference_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | What’s the **flash memory** of EFM8BB31F32G-D-QFP32? | 32 kB | 4 |
| ✓ Works | What is the **maximum storage temperature** for EFM8BB3? | 150 °C | 40 |
| ✓ Works | How many **multi-function I/O pins** does EFM8BB3 have? | Up to 29 | 10 |
| ✓ Works | What is the **minimum Voltage Reference Range for DACs**? | 1.15 V | 31 |
| ✓ Works | What are the different **power modes** for EFM8BB3? | Normal, Idle, Suspend, Stop, Snooze, Shutdown | 10 |


Every answer is correct. Great news! 

We still see some weird chunks. Some with very few text, some with weird markdown headers, etc. 

Possible Next steps:
- Check linting and formatting of the codebase
- Cal an LLM  after the whole markdown page is aggregated to uniformize the markdown headers their hierarchy
- Add concurrency to the openai api calls and parallelize with the layout detection to speed up the process
- Add a Load/Save Index button to the app so that we dont have to wait for the whole process every time we want to test queries
- Evaluate the quality of the markdown by comparing it with the original pdf. overlap of text, overlap of tables, llm-as-a-judge, etc. Just because these tests are passing does not mean the markdown is good. We have to be careful with overfitting to these tests, so we should create a more robust evaluation pipeline.
