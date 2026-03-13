# AI DDR Generator  
### Automated Detailed Diagnostic Report Generation from Inspection & Thermal Reports

## Overview
The **AI DDR Generator** is a rule-based AI system that converts raw **property inspection reports and thermal inspection reports** into a structured **Detailed Diagnostic Report (DDR)**.

The system extracts textual observations, thermal readings, and images from input documents and automatically generates a client-ready diagnostic report.

This project was developed as part of an **AI Generalist / Applied AI Builder evaluation task** to demonstrate the ability to design and implement real-world AI workflows.

---

# Problem Statement
Inspection and thermal survey reports often contain unstructured information such as:

- Raw observations
- Thermal temperature readings
- Embedded images
- Engineering notes

Manually converting these reports into structured diagnostic reports is time-consuming.

The goal of this project is to **automatically analyze inspection data and generate a structured DDR report**.

---

# Features

- Extracts **text and images** from PDF reports
- Detects **areas of the property affected**
- Identifies **structural issues** such as:
  - Dampness
  - Seepage
  - Leakage
  - Tile joint gaps
  - Cracks
- Extracts **thermal hotspot and coldspot readings**
- Calculates **temperature difference for severity estimation**
- Determines **probable root cause**
- Suggests **recommended repair actions**
- Generates **structured DDR report**
- Displays extracted images for visual reference
- Allows downloading the report as **Markdown or PDF**

---

# System Workflow


The AI DDR Generator follows a structured pipeline to convert raw inspection data into a client-ready diagnostic report.

User Upload
   │
   ├── Inspection Report (PDF)
   └── Thermal Report (PDF)
           │
           ▼
PDF Processing Layer
   │
   ├── Extract Text from Documents
   └── Extract Embedded Images
           │
           ▼
Information Extraction
   │
   ├── Identify Impacted Areas
   ├── Detect Structural Issues
   │      • Dampness
   │      • Seepage
   │      • Cracks
   │      • Tile Joint Gaps
   │      • Plumbing Leakage
   │
   └── Extract Thermal Readings
          • Hotspot Temperature
          • Coldspot Temperature
          • Temperature Difference
           │
           ▼
Analysis Engine
   │
   ├── Merge Inspection + Thermal Findings
   ├── Remove Duplicate Observations
   ├── Estimate Severity Level
   ├── Identify Probable Root Cause
   └── Generate Recommended Repair Actions
           │
           ▼
DDR Report Generator
   │
   ├── Property Issue Summary
   ├── Area-wise Observations
   ├── Thermal Evidence
   ├── Severity Assessment
   ├── Root Cause Analysis
   ├── Recommended Actions
   ├── Additional Notes
   └── Missing / Unclear Information
           │
           ▼
Final Output
   │
   ├── Interactive Report Display (Streamlit UI)
   ├── Download as Markdown
   └── Download as PDF
---

# Technology Stack

| Component | Technology |
|--------|--------|
| Frontend | Streamlit |
| PDF Processing | PyMuPDF |
| Image Processing | Pillow |
| Report Generation | ReportLab |
| Language | Python |

---

# Installation

Clone the repository:


git clone https://github.com/your-username/ai-ddr-generator.git

cd ai-ddr-generator


Install dependencies:


pip install -r requirements.txt


---

# Running the Application

Start the Streamlit app:


streamlit run app.py


The application will open in your browser.

---

# Usage

1. Upload the **Inspection Report (PDF)**
2. Upload the **Thermal Report (PDF)**
3. Click **Generate DDR**
4. The system will:
   - Extract observations
   - Analyze thermal data
   - Generate structured report
5. Download the final **DDR report**

---

# DDR Report Structure

The generated report contains:

1. Property Issue Summary
2. Area-wise Observations
3. Thermal Evidence
4. Severity Assessment
5. Probable Root Cause
6. Recommended Actions
7. Additional Notes
8. Missing or Unclear Information

---

# Example Issues Detected

- Dampness at skirting level
- Bathroom tile joint gaps
- External wall cracks
- Parking ceiling leakage
- Moisture ingress through waterproofing failure

---

# Limitations

- Rule-based system may not detect all issues if wording varies significantly
- Image-to-area mapping is heuristic
- OCR for scanned documents is optional and not fully implemented

---

# Future Improvements

- Integrate NLP models for better observation extraction
- Implement OCR for scanned PDFs
- Improve image-to-observation mapping
- Add severity scoring using ML models
- Deploy as a cloud web application

---

# Author

Developed by **Ishan Toraskar**

B.Tech Information Technology  
Pimpri Chinchwad College of Engineering  

---

# License

This project is developed for evaluation and educational purposes.
