# Import required libraries for UI, PDF processing, image handling, report generation and data manipulation
import streamlit as st
import fitz
import io
import os
import re
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from datetime import datetime
from collections import defaultdict


# Function to extract all textual content from a PDF file using PyMuPDF
def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Reads a PDF file from bytes and extracts text from all pages."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    return "\n".join(texts)


# Function to extract images embedded in a PDF and store them locally
def extract_images_from_pdf_bytes(pdf_bytes: bytes, output_dir="extracted_images", prefix="doc") -> list:
    """
    Reads a PDF file, extracts embedded images from each page,
    saves them locally, and returns metadata including file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    saved = []

    for pno in range(len(doc)):
        page = doc[pno]
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]

            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image.get("ext", "png")

                name = f"{prefix}_p{pno+1}_img{img_index+1}.{ext}"
                path = os.path.join(output_dir, name)

                with open(path, "wb") as f:
                    f.write(image_bytes)

                saved.append({
                    "path": path,
                    "page": pno+1,
                    "xref": xref,
                    "name": name
                })

            except Exception as e:
                print("Image extract error:", e)

    return saved


# Keywords used to detect building areas in sentences
AREA_KEYWORDS = [
    "hall", "living", "kitchen", "master bedroom", "bedroom", "common bathroom", "bathroom",
    "parking", "balcony", "external wall", "terrace", "staircase", "passage", "flat"
]


# Keywords used to detect construction defects or problems
ISSUE_KEYWORDS = [
    "damp", "dampness", "seepage", "leakage", "efflorescence", "spalling", "crack", "cracks",
    "hollow", "hollowness", "gaps", "gap", "tile joints", "plumbing", "nahani", "tile joint",
    "paint", "mold", "algae", "moisture", "wet", "outlet leakage"
]


# Keywords used to detect thermal readings from the thermal inspection report
THERMAL_LABELS = ["hotspot", "coldspot", "hot spot", "cold spot", "temperature", "°c", "celsius"]


# Identify which building area is mentioned in a sentence
def find_area_in_sentence(sentence: str) -> str:
    s = sentence.lower()
    for area in AREA_KEYWORDS:
        if area in s:
            return area.title()
    return "Not Available"


# Identify the defect keywords present in a sentence
def find_issue_in_sentence(sentence: str) -> str:
    s = sentence.lower()
    found = []

    for k in ISSUE_KEYWORDS:
        if k in s:
            found.append(k)

    return ", ".join(sorted(set(found))) if found else "Not Available"


# Extract key observations from the inspection report text
def extract_inspection_findings(inspection_text: str) -> list:
    """
    Breaks inspection report text into lines and detects
    observations related to structural issues.
    """

    findings = []
    lines = [ln.strip() for ln in re.split(r'[\n\r]+', inspection_text) if ln.strip()]

    for ln in lines:
        lower = ln.lower()

        if any(k in lower for k in ISSUE_KEYWORDS) or "observed" in lower:

            area = find_area_in_sentence(ln)
            issue = find_issue_in_sentence(ln)

            if len(ln) < 8:
                continue

            findings.append({
                "area": area,
                "observation": ln,
                "issues_detected": issue,
                "source": "Inspection Report"
            })

    uniq = []
    seen = set()

    for f in findings:
        key = (f["area"], f["observation"][:120])

        if key in seen:
            continue

        seen.add(key)
        uniq.append(f)

    return uniq


# Extract thermal temperature readings from the thermal report
def extract_thermal_readings(thermal_text: str) -> list:
    """
    Detects hotspot and coldspot temperatures from thermal scans
    and calculates temperature difference.
    """

    readings = []
    blocks = re.split(r'\n{2,}', thermal_text)

    for block in blocks:
        b = block.lower()

        hot = None
        cold = None

        mhot = re.search(r'hot(?:spot| spot)\s*[:\-]\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*c', b)

        if mhot:
            hot = float(mhot.group(1))

        mcold = re.search(r'cold(?:spot| spot)\s*[:\-]\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*c', b)

        if mcold:
            cold = float(mcold.group(1))

        temps = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*°\s*c', b)

        if hot is None and temps:
            hot = float(temps[0])

        if cold is None and len(temps) > 1:
            cold = float(temps[1])

        area = find_area_in_sentence(block)

        readings.append({
            "area": area,
            "hotspot": hot,
            "coldspot": cold,
            "delta": (hot - cold) if (hot is not None and cold is not None) else None,
            "raw": block[:400]
        })

    readings = [r for r in readings if (r["hotspot"] is not None or r["coldspot"] is not None)]

    return readings


# Determine severity of the issue using thermal difference and observation text
def severity_from_thermal(delta, observation_text):

    reason_parts = []
    sev = "Not Available"

    if delta is None:

        if any(x in observation_text.lower() for x in ["live leakage", "seepage", "spalling", "efflorescence"]):
            sev = "High"
            reason_parts.append("Severe visual signs")

        else:
            reason_parts.append("Thermal data not available")

    else:

        if delta >= 5.0:
            sev = "High"

        elif delta >= 3.0:
            sev = "Moderate"

        else:
            sev = "Low"

        reason_parts.append(f"Thermal delta {delta:.1f}°C")

    return sev, "; ".join(reason_parts)


# Determine root cause based on defect keywords
def probable_root_cause_from_issue(issue_text):

    s = issue_text.lower()

    if "tile" in s:
        return "Water ingress through tile joints."

    if "crack" in s:
        return "Cracks allowing rainwater penetration."

    if "terrace" in s:
        return "Failed terrace waterproofing."

    if "plumbing" in s:
        return "Defective plumbing system."

    if "damp" in s:
        return "Moisture ingress due to waterproofing failure."

    return "Not Available"


# Suggest repair actions depending on root cause
def recommended_actions_from_root(root):

    r = root.lower()

    if "tile" in r:
        return ["Re-grout tile joints with waterproof polymer grout"]

    if "terrace" in r:
        return ["Apply terrace waterproofing membrane"]

    if "plumbing" in r:
        return ["Inspect and repair plumbing pipeline"]

    if "crack" in r:
        return ["Seal cracks and apply waterproof coating"]

    return ["Further investigation required"]


# Combine inspection findings, thermal readings and images to create structured DDR entries
def generate_ddr_structure(inspection_findings, thermal_readings, images):

    thermal_by_area = defaultdict(list)

    for t in thermal_readings:
        thermal_by_area[t.get("area", "Not Available")].append(t)

    ddr_items = []

    for f in inspection_findings:

        area = f["area"]
        obs = f["observation"]
        issues = f["issues_detected"]

        t_list = thermal_by_area.get(area, [])
        thermal_info = t_list[0] if t_list else None

        delta = thermal_info["delta"] if thermal_info else None
        hotspot = thermal_info["hotspot"] if thermal_info else None
        coldspot = thermal_info["coldspot"] if thermal_info else None

        severity, reasoning = severity_from_thermal(delta, obs)

        probable_root = probable_root_cause_from_issue(issues)

        recs = recommended_actions_from_root(probable_root)

        matched_images = [img["path"] for img in images[:2]]

        ddr_items.append({
            "area": area,
            "observation": obs,
            "issues_detected": issues,
            "thermal": {
                "hotspot": hotspot,
                "coldspot": coldspot,
                "delta": delta
            },
            "severity": severity,
            "severity_reasoning": reasoning,
            "probable_root_cause": probable_root,
            "recommended_actions": recs,
            "images": matched_images
        })

    return ddr_items


# Generate summary of impacted areas and key issues
def summarize_property(ddr_items):

    areas = set(i["area"] for i in ddr_items)

    issues = set()

    for it in ddr_items:
        if it["issues_detected"]:
            issues.add(it["issues_detected"])

    summary = f"{len(areas)} impacted area(s) detected."

    return summary


# Generate a formatted DDR report PDF using ReportLab
def generate_pdf_report(file_path, ddr_items, property_summary):

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("Detailed Diagnostic Report (DDR)", styles['Title']))
    story.append(Spacer(1,12))

    story.append(Paragraph(property_summary, styles['Normal']))
    story.append(Spacer(1,12))

    for it in ddr_items:

        story.append(Paragraph(f"Area: {it['area']}", styles['Heading3']))
        story.append(Paragraph(it['observation'], styles['Normal']))

        for img in it['images']:
            story.append(RLImage(img, width=400, height=300))

        story.append(Spacer(1,10))

    doc.build(story)


# Configure Streamlit page layout
st.set_page_config(page_title="AI DDR Generator", layout="wide")

st.title("AI DDR Generator")

st.markdown("Upload inspection and thermal reports to generate the DDR.")


# File upload interface for both reports
col1, col2 = st.columns(2)

with col1:
    inspection_file = st.file_uploader("Upload Inspection Report", type=["pdf"])

with col2:
    thermal_file = st.file_uploader("Upload Thermal Report", type=["pdf"])


# Trigger analysis when user clicks button
if st.button("Generate DDR"):

    if not inspection_file or not thermal_file:
        st.warning("Upload both files")

    else:

        insp_text = extract_text_from_pdf_bytes(inspection_file.read())
        therm_text = extract_text_from_pdf_bytes(thermal_file.read())

        insp_images = extract_images_from_pdf_bytes(inspection_file.read(), prefix="insp")
        therm_images = extract_images_from_pdf_bytes(thermal_file.read(), prefix="therm")

        all_images = insp_images + therm_images

        inspection_findings = extract_inspection_findings(insp_text)

        thermal_readings = extract_thermal_readings(therm_text)

        ddr_items = generate_ddr_structure(inspection_findings, thermal_readings, all_images)

        property_summary = summarize_property(ddr_items)

        st.write(property_summary)

        for item in ddr_items:
            st.write(item)
