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
The second approach completely replaced the PymuConverter with a MarkerConverter that uses the marker-pdf library - a more sophisticated PDF-to-markdown conversion tool. There were other options we thought about like docling, mineru and unstructured.io. Since i couldnt find any decent independent benchmarks comparing these options We decided to go with marker since its own benchmark showed better performance than comparable cloud services like Llamaparse and Mathpix, it was a customizable solution that allowed changing the pipeline, it works with the openai api and it didn't require a GPU to run models locally, and it had specialised approaches and heuristics for tables, equations, footers/headers, etc.

Key Features of MarkerConverter:
- Advanced PDF Processing: Uses marker-pdf library instead of the simpler PyMuPDF approach
- OpenAI LLM Integration: Optional LLM enhancement for improved conversion quality
- Performance Optimization:
  - Caching of converter instances
  - Efficient temporary file handling
- Image Extraction: Can extract and handle images from PDFs and reference them in the markdown
- Configurable Pipeline: Flexible configuration system with processors and renderers


How it works:
- Extract text, OCR if necessary (heuristics, surya)
- Detect page layout and find reading order (surya)
- Clean and format each block (heuristics, texify, surya)
- Optionally use an LLM to improve quality
- Combine blocks and postprocess complete text

## Results

The preliminary results were promising since it got the second and almost the third questions of esp8266_hardware_design_guidelines_en.pdf correctly (the model wrote RES12K, but got the pin number right. see NOTE below*). However, the model broke the openai rate limits when trying to process esp8266-technical_reference_en.pdf.

* **NOTE**: after encountering this error a few times during the following approaches, I went to the original PDF and saw that the ground truth itself was wrong in the initial `README.md`. The model predicted "RES12K" correctly 

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
- Direct control over the pipeline (by using the library backoff we have no more rate limiting issues)
- Batch processing for layout detection efficiency
- Pipelined workflow to parallelize layout detection and OpenAI API calls
- Handles scanned documents through vision models rather than OCR

**Status**: Implementation in progress (`src/converter/basic_surya_pipeline.py`)

**NOTE:**
Surya Documentation reads the following regarding their license:
> The weights for the models are licensed cc-by-nc-sa-4.0, but I will waive that for any organization under $2M USD in gross revenue in the most recent 12-month period AND under $2M in lifetime VC/angel funding raised. You also must not be competitive with the Datalab API. If you want to remove the GPL license requirements (dual-license) and/or use the weights commercially over the revenue limit, check out the options here.

If we were not in a technical challenge for a job opening we would have to analyze this and check if this model is appropriate for kapa.ai

## Performance Note: Layout Processing

**CPU Utilization Optimization**: Since we're just using CPU, waiting for layout detection and OpenAI API calls to finish sequentially is clearly inefficient. 

**Quick Test Results** (`test_layout_performance.py` on 21098-ESPS2WROOM-scan.pdf):
- Batch layout processing: 8.13s (1.32x faster than in sequence)
- Individual processing: 10.74s 
- Batch uses more memory (+370MB) but is more efficient overall

**Conclusion**: Use batch processing for layout detection, but pipeline the workflow so OpenAI API calls happen in parallel with layout detection of subsequent chunks. 

Note: These performance optimizations initially made the pipeline faster and improved iteration speed. However, debugging the optimized version proved difficult. As a result, we decided to simplify the process by extracting only the pages containing answers to the test questions—along with their neighboring pages to introduce some noise. This change significantly sped up the overall workflow.

In the future, we can reintroduce the optimization for a smoother production experience. When doing so, we should be mindful of designing the code architecture in a way that supports modular testing—specifically, by isolating key functions from the parallelized code.

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

This approach focused on improving the prompts sent to the model for better text extraction and formatting.

## Prompt Enhancements

### 1. **Block-Type Specialized Prompts (`get_block_prompt` Function)**

The core innovation was implementing specialized prompts for different layout elements detected by Surya. Instead of using a generic "extract text" prompt for all blocks, we created tailored instructions for each block type:

**Logic Behind Specialized Prompts:**
- **Different Content Types Need Different Handling**: A table requires different formatting than a title or caption
- **Preserve Document Structure**: Headers should become markdown headings, lists should maintain proper indentation
- **Optimize for Retrieval**: Well-formatted markdown improves chunking and semantic search quality

**Block Type Categories:**
- **Structural Elements**: `Title`, `SectionHeader` → Format as markdown headings (`# ## ###`)
- **Text Content**: `Text`, `Form`, `Handwriting` → Preserve formatting and indentation
- **Lists**: `ListItem`, `TableOfContents` → Maintain list structure with proper indentation
- **Data**: `Table` → Convert to markdown table format with proper alignment
- **Visual Elements**: `Figure`, `Picture` → Extract and describe visual content (no extra legends yet)
- **Metadata**: `PageHeader`, `PageFooter`, `Caption`, `Footnote` → Handle appropriately (page headers could be be headings, footers are plain text)
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

We still see some non perfect chunks. Some with very few text, some with weird markdown headers, etc. 

Possible Next steps:
- Check linting and formatting of the codebase
- Call an LLM after the whole markdown page is aggregated to uniformize the markdown headers their hierarchy
- Put back the code that implemented concurrency to the openai api calls and parallelize with the layout detection to speed up the process
- Evaluate the quality of the markdown by comparing it with the original pdf. overlap of text, overlap of tables, llm-as-a-judge, etc. Just because these tests are passing does not mean the markdown is good. We have to be careful with overfitting to these tests, so we should create a more robust evaluation pipeline.
- Add a Load/Save Index button to the app so that we dont have to wait for the whole process every time we want to test queries


# Sixth Approach: Tackling Flakiness and Real-World Robustness

## Motivation and Initial Experimentation

1. After running the full PDFs through the pipeline—rather than just sampled pages as in previous approaches—we discovered significant flakiness in the results. The retrieval of relevant chunks, and thus the answers to our test questions, varied greatly between runs. In other words, the outcome was highly sensitive to the random seed and other sources of nondeterminism: sometimes the model would fail catastrophically on multiple questions, even though our very first run yielded a perfect score (a result we were never able to reproduce). This means that the test results from Approaches 4 and 5, which used only a sample of the PDFs for each test, were overly optimistic and did not reflect the true variability and instability of the system.

2. A major motivation for this new approach was observing that the output from gpt-4.1-mini was often excessively verbose. For example, we initially provided the original text layer to every block type to help with OCR errors. However, this led the model to generate much longer outputs and increased the frequency of hallucinations, especially in cases where the OCR layer contained errors. We noticed this most acutely in large tables with very similar strings (e.g., "EFM8BB31F32G-D-QFP32" vs. "EFM8BB31F32G-D-QFN32"), where the model would sometimes repeat or conflate entries.

3. Another issue arose with the representation of tables. By including the markdown table, a legend, and a natural language description for every row, we ended up with an explosion of chunks. The natural language lines were often very similar to each other, which likely resulted in highly similar embeddings. This made retrieval unstable, as the right chunk was less likely to consistently appear in the top results.

4. Section headings also proved problematic. They are crucial for chunking, but gpt-4.1-mini lacked the context to reliably determine the correct number of '#' symbols for each heading. The model frequently omitted the appropriate markdown heading, leading to inconsistent document structure. To address this, we started injecting the PDF’s table of contents into the prompt for each section heading, giving the model the necessary context to infer the correct hierarchy.

5. Finally, we found that when section heading prediction failed, the page header often contained valuable information about the page’s topic. For example, the answer to the "maximum storage temperature" question was frequently missed because the relevant chunk did not mention "EFM8BB3," even though it was present in the page header. To mitigate this, we decided to prepend the page header to every section header. While this can introduce some repetition when the hierarchy is working well, it provides crucial context in cases where heading prediction fails—which can happen for a variety of reasons. A different idea we had that will be left for next steps would be to let the model analyze the TOC and a few pages to evaluate if a specific's pdf's page headers contained useful information to include in the sections' headings or not.

Section TLDR: we found problems with the model's ability to understand the table structure, the section headings, and the document context for each chunk. We also found that the model was often excessively verbose, which led to hallucinations and instability in the results.

## Decisions and Results

Throughout this process, I continuously refined prompts, information flows, and the way different content types were curated in the final markdown, all in an effort to address persistent instability in the results. Every attempt to resolve one category of errors—such as helping the model recognize that a row labeled `Storage Temperature` and a column labeled `max` together indicate "Maximum Storage Temperature"—often gave rise to new problems. For instance, generating natural language descriptions for table rows to aid the embedding model resulted in a surge of tokens, quickly reaching the max_token_size limit. Even after reducing the detail in these representations, the outcome was many nearly identical rows and chunks, leading to similar embeddings and making it unlikely that the correct answer would consistently appear among the top 3 retrieved chunks.

After considerable effort to perfect the test set, it became clear that optimizing for these tests risked overfitting our solution to the test set, falling into Goodhart’s Law: "When a measure becomes a target, it ceases to be a good measure." The results remained highly sensitive to random seeds and other sources of nondeterminism, and the system was fundamentally limited by embedding model size, chunk size, and retrieval settings. Given the constraints of the take-home challenge, I now believe that a robust solution wasn’t possible without changing these parameters.

Therefore, to improve consistency—especially for table-heavy technical PDFs—I increased the retrieval top_k to 10 and used a larger embedding model. While this helped it is still unstable, and it also highlighted the system’s limitations. At minimum, a more capable embedding model, larger chunk sizes, and a higher top_k are essential.

Beyond that, advanced RAG methods—like storing provenance metadata, enriching chunks with contextual summaries, table-aware chunking, and context window retrieval (including neighboring chunks)—are essential for robust performance. Converter improvements alone can’t address the core retrieval and grounding limitations.

Section TLDR: 
- Many approaches were tried, but the results were still unstable. So I concluded that the whole RAG should be tweaked.
- I increased the retrieval top_k to 10 and used a larger embedding model. While this helped it is still unstable, and it also highlighted the system’s limitations.


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


## Extra findings, decisions, and future steps

- Legends for figures and pictures were found to add little value for this use case, but a similar approach of writing a natural language description of visual elements is a must for a production ready approach. (Some visual elements in these test pdfs already contain technical information, but we didn't implement it yet given the types of questions in the test set. But the prompts are already written).
- Section heading prediction remains a challenge; injecting the TOC and page headers helps, but a more robust solution may require a post-processing LLM pass to unify and correct markdown hierarchy.
- The system is still sensitive to random seed and other sources of nondeterminism; further work is needed to improve determinism and robustness for real-world use.
- "TableOfContents" blocks are skipped in the output to avoid redundancy, as their main value is in providing context for heading hierarchy. Table of contents is a good example of top_3 being too little, because there is a considerable possibility of a keyword match with something in the TOC. Still, it is useful contextually for things like the level of the header: The Table of Contents is extracted and injected into section heading prompts for better hierarchy inference.
- Consecutive "ListItem" blocks are now merged to improve list coherence, though this may occasionally combine items that should remain separate.
- I ended up parallelizing just the OCR to the blocks within each page. It sped up the process considerably, but the full concurrent approach of layout detection and OCR in parallel should be the optimal one.
- After visually analyzing the layout blocks extracted for each pdf, the 4th page of `efm8bb3-datasheet.pdf` started yielding weird boxes. It was very strange and I intuited that there was some hidden weird artifact in the image that was messing the model. So, I simply tried to scale the Images by 1.1x before passing through the layout detection and it fixed the problem. This suggests that a general solution should be tried regarding the correct scaling of the images to pass through the model.


