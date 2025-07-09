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
