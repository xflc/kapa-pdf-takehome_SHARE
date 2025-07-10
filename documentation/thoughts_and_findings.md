# First Approach
In this first approach, I saw that 21098-ESPS2WROOM-scan.pdf simply had no information since it is a scanned document. So, I used `page.get_textpage_ocr()` (which uses pytesseract) to extract the text. The first pdf was a success, but the other two were the same obviously.

## Results


### `21098-ESPS2WROOM-scan.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Needs improvement | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Needs improvement | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✓ Needs improvement | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

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
The second approach completely replaced the PymuConverter with a MarkerConverter that uses the marker-pdf library - a more sophisticated PDF-to-markdown conversion tool. There were other options we thought about like docling, mineru and unstructured.io. We decided to go with marker since, given that i couldnt find any decent independent benchmarks comparing these options, it was the simplest and most straightforward to control.

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
| ✓ Needs improvement | What type of equipment is **B20111311**? | Modular Approval, Wi-Fi Device | — |
| ✓ Needs improvement | When was the certificate for **US0057** issued? | 2020-11-19 | — |
| ✓ Needs improvement | Who holds the **21098-ESPS2WROOM** certificate? | ESPRESSIF SYSTEMS (SHANGHAI) CO., LTD. | — |

### `esp8266_hardware_design_guidelines_en.pdf`

| Status | Question | Correct answer (information only) | Page |
|--------|----------|-----------------------------------|------|
| ✓ Works | Can **ESP8266EX** be applied to any micro-controller design as a Wi-Fi adaptor? | Yes; via SPI/SDIO or I2C/UART interfaces | 6 |
| ✓ Needs improvement | What is the **frequency range** for ESP8266EX? | 2.4 G – 2.5 G (2400 M – 2483.5 M) | 7 |
| ✗/✓ Needs improvement | To what pin do I connect the **resistor** for ESP8266EX? | Pin ERS12K (the model wrote RES12K, but got the number right) (31) | 15 |

### `esp8266-technical_reference_en.pdf` (didn't run. too large of a file, makes the conversion very slow and breaks openai rate limits)

After I tried to customize the pipeline for esp8266-technical_reference_en.pdf, I found that marker was very slow to handle the large file size, it broke the openai rate limits and was very slow to install because of its huge list of dependecies. The speed problem was not diagnosed, but the problems with openai rate limits were because there was no way to customize the pipeline to implement a simple backoff strategy.


Therefore, I had to make a choice. Do I try these different libraries that promise to process pdfs well and risk spending a few nights of work trying to get them to work, or after studying the marker library, am I confident that I can manually and rapidly implement a pipeline that works well enough for this specific use case and these questions?

I decided to go with the second approach, since I was confident that gpt-4.1-mini would be able to parse these pages correctly if we broke down each page into its main layout blocks (marker just calls surya.layout.LayoutPredictor from an external library). 
