# app.py
import streamlit as st
import fitz  # PyMuPDF
import os
import re
import hashlib
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from collections import defaultdict

# ---------------------------
# Utilities: PDF parsing (per-page)
# ---------------------------
def extract_text_pages(pdf_bytes: bytes):
    """
    Return list of page texts for the given PDF bytes.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    return pages

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Return full text (joined) for convenience.
    """
    pages = extract_text_pages(pdf_bytes)
    return "\n".join(pages)

# ---------------------------
# Image extraction with duplicate & logo filtering
# ---------------------------
def md5_bytes(b: bytes):
    m = hashlib.md5()
    m.update(b)
    return m.hexdigest()

def extract_images_from_pdf_bytes(pdf_bytes: bytes, output_dir="extracted_images", prefix="doc",
                                  min_width=150, min_height=150, repeat_threshold=2):
    """
    Extract images from PDF bytes and save to output_dir.
    Filters:
      - ignore images smaller than min_width/min_height
      - ignore exact-duplicate images (md5)
      - ignore images that repeat more than repeat_threshold times (likely logos)
    Returns list of dicts with keys: path, page, width, height, md5
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    saved = []
    md5_counts = defaultdict(int)

    # first pass: collect md5 counts to detect repeated images
    md5_by_xref = {}
    for pno in range(len(doc)):
        page = doc[pno]
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                b = base["image"]
                h = md5_bytes(b)
                md5_counts[h] += 1
                md5_by_xref[xref] = (h, base)
            except Exception:
                continue

    # second pass: save filtered images
    for pno in range(len(doc)):
        page = doc[pno]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                image_bytes = base["image"]
                width = base.get("width", 0)
                height = base.get("height", 0)
                ext = base.get("ext", "png")

                # skip small images
                if width < min_width or height < min_height:
                    continue

                img_md5 = md5_bytes(image_bytes)

                # skip images that appear many times (logos/watermarks)
                if md5_counts.get(img_md5, 0) > repeat_threshold:
                    continue

                name = f"{prefix}_p{pno+1}_img{img_index+1}.{ext}"
                path = os.path.join(output_dir, name)

                # write file (overwrite safe)
                with open(path, "wb") as f:
                    f.write(image_bytes)

                saved.append({
                    "path": path,
                    "page": pno + 1,
                    "width": width,
                    "height": height,
                    "md5": img_md5
                })
            except Exception:
                # skip problematic images
                continue

    # sort images by page then by size descending
    saved = sorted(saved, key=lambda x: (x["page"], -(x["width"] * x["height"])))
    return saved

# ---------------------------
# Rule-based parsers (areas, issues, thermal)
# ---------------------------
AREA_KEYWORDS = [
    "hall", "living", "kitchen", "master bedroom", "master bedroom", "bedroom", "common bathroom", "bathroom",
    "parking", "balcony", "external wall", "terrace", "staircase", "passage", "skirting", "ceiling"
]

ISSUE_KEYWORDS = [
    "damp", "dampness", "seepage", "leakage", "efflorescence", "spalling", "crack", "cracks",
    "hollow", "hollowness", "gaps", "gap", "tile joint", "tile joints", "plumbing", "nahani",
    "paint", "mold", "algae", "moisture", "wet", "outlet leakage", "gaps between tile", "hollow sound"
]

def find_area_in_sentence(sentence: str) -> str:
    s = sentence.lower()
    for area in AREA_KEYWORDS:
        if area in s:
            return area.title()
    return "Not Available"

def find_issue_in_sentence(sentence: str) -> str:
    s = sentence.lower()
    found = []
    for k in ISSUE_KEYWORDS:
        if k in s:
            found.append(k)
    return ", ".join(sorted(set(found))) if found else "Not Available"

def extract_inspection_findings_per_page(pages_text: list) -> list:
    """
    Scan each page text, find lines that contain issue keywords or 'observed',
    return findings with page number to enable image mapping.
    """
    findings = []
    for p_idx, page_text in enumerate(pages_text):
        # split into sentences/lines
        lines = [ln.strip() for ln in re.split(r'[\n\r]+', page_text) if ln.strip()]
        for ln in lines:
            lower = ln.lower()
            if any(k in lower for k in ISSUE_KEYWORDS) or "observed" in lower or "image" in lower:
                if len(ln) < 8:
                    continue
                area = find_area_in_sentence(ln)
                issue = find_issue_in_sentence(ln)
                findings.append({
                    "area": area,
                    "observation": ln,
                    "issues_detected": issue,
                    "page": p_idx + 1
                })
    # deduplicate preserving first occurrence
    uniq = []
    seen = set()
    for f in findings:
        key = (f["page"], f["area"], f["observation"][:140])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    return uniq

def extract_thermal_readings_per_page(pages_text: list) -> list:
    """
    Parse thermal report per page for hotspot/coldspot numbers and return per-page entries.
    """
    readings = []
    for p_idx, page_text in enumerate(pages_text):
        b = page_text.lower()
        hot = None
        cold = None
        # common patterns used in thermal reports
        mhot = re.search(r'hot(?:spot| spot)?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*c', b)
        mcold = re.search(r'cold(?:spot| spot)?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*°?\s*c', b)
        if mhot:
            hot = float(mhot.group(1))
        if mcold:
            cold = float(mcold.group(1))
        # fallback: any °C values on page
        temps = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*°\s*c', b)
        if hot is None and temps:
            hot = float(temps[0])
        if cold is None and len(temps) > 1:
            cold = float(temps[1])
        area = find_area_in_sentence(b)
        if hot is not None or cold is not None:
            readings.append({
                "area": area,
                "hotspot": hot,
                "coldspot": cold,
                "delta": (hot - cold) if (hot is not None and cold is not None) else None,
                "page": p_idx + 1,
                "raw": b[:400]
            })
    return readings

# ---------------------------
# Analysis & merging logic
# ---------------------------
def severity_from_thermal(delta, observation_text):
    reason_parts = []
    sev = "Not Available"
    if delta is None:
        if any(x in observation_text.lower() for x in ["live leakage", "seepage", "spalling", "efflorescence", "live leak"]):
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

def probable_root_cause_from_issue(issue_text):
    s = issue_text.lower()
    if any(x in s for x in ["tile", "nahani", "brickbat", "gaps"]):
        return "Gaps in tile joints or damaged drain assemblies allowing water ingress / capillary action."
    if any(x in s for x in ["crack", "cracks"]):
        return "Hairline or structural cracks in exterior/interior surfaces allowing ingress."
    if any(x in s for x in ["terrace", "ips", "waterproof", "hollow"]):
        return "Failed terrace waterproofing (cracked screed/hollow sections)."
    if any(x in s for x in ["plumbing", "live leakage", "outlet"]):
        return "Concealed or defective plumbing joints."
    if any(x in s for x in ["damp", "efflorescence", "spalling", "moisture"]):
        return "Moisture ingress due to surface defects or waterproofing failure."
    return "Not Available"

def recommended_actions_from_root(root):
    r = root.lower()
    if "tile" in r or "gaps" in r:
        return [
            "Cut and re-grout tile joints using polymer-modified grout (RTM).",
            "Check and repair Nahani trap / under-tile brickbat coba as needed."
        ]
    if "terrace" in r or "waterproof" in r:
        return [
            "Carry out terrace re-screeding and membrane/chemical waterproofing.",
            "Repair hollow areas and ensure adequate slope and outlets."
        ]
    if "plumbing" in r:
        return [
            "Conduct pressure test to locate concealed leak and repair plumbing joints.",
            "Replace faulty pipe segments and re-test."
        ]
    if "crack" in r:
        return [
            "Seal hairline cracks with proper filler and apply exterior-grade waterproof coating.",
            "If cracks widen, get a structural evaluation."
        ]
    return ["Site verification by a qualified technician recommended."]

# ---------------------------
# Matching images to findings
# ---------------------------
def match_images_for_finding(finding, images, images_by_page):
    """
    Strategy:
      1. Prefer images on the same page (images_by_page[finding.page])
      2. Else, try neighboring pages (page-1, page+1)
      3. Else, pick top large images overall (sorted by size)
    """
    page = finding.get("page")
    matched = []

    if page in images_by_page:
        matched = list(images_by_page[page])

    if not matched:
        # neighbor pages
        neighbors = []
        if page - 1 in images_by_page:
            neighbors.extend(images_by_page[page - 1])
        if page + 1 in images_by_page:
            neighbors.extend(images_by_page[page + 1])
        matched = neighbors

    if not matched:
        # fallback: choose top 2 largest images from all images
        sorted_images = sorted(images, key=lambda x: -(x["width"] * x["height"]))
        matched = [img["path"] for img in sorted_images[:2]]

    # ensure at most 3 images
    return matched[:3]

# ---------------------------
# DDR Construction
# ---------------------------
def generate_ddr_structure(inspection_findings, thermal_readings, images):
    # index thermal readings by area (and also by page)
    thermal_by_area = defaultdict(list)
    for t in thermal_readings:
        thermal_by_area[t.get("area", "Not Available")].append(t)

    # index images by page -> list of paths
    images_by_page = defaultdict(list)
    for img in images:
        images_by_page[img["page"]].append(img["path"])

    ddr_items = []
    for f in inspection_findings:
        area = f["area"]
        obs = f["observation"]
        page = f.get("page", None)
        issues = f["issues_detected"]

        # try to find thermal reading by area or by page
        t_candidate = None
        if thermal_by_area.get(area):
            # pick reading with largest delta if present
            t_list = [t for t in thermal_by_area[area] if t.get("delta") is not None]
            if t_list:
                t_candidate = sorted(t_list, key=lambda x: -(x.get("delta") or 0))[0]
            else:
                t_candidate = thermal_by_area[area][0]
        else:
            # fallback: thermal reading for same page
            t_by_page = [t for t in thermal_readings if t.get("page") == page]
            if t_by_page:
                t_candidate = t_by_page[0]
            elif thermal_readings:
                t_candidate = thermal_readings[0]

        hotspot = t_candidate.get("hotspot") if t_candidate else None
        coldspot = t_candidate.get("coldspot") if t_candidate else None
        delta = t_candidate.get("delta") if t_candidate else None

        severity, reasoning = severity_from_thermal(delta, obs)
        probable_root = probable_root_cause_from_issue(issues if issues != "Not Available" else obs)
        recs = recommended_actions_from_root(probable_root)

        matched_images = match_images_for_finding(f, images, images_by_page)

        ddr_items.append({
            "area": area,
            "observation": obs,
            "issues_detected": issues,
            "page": page,
            "thermal": {"hotspot": hotspot, "coldspot": coldspot, "delta": delta},
            "severity": severity,
            "severity_reasoning": reasoning,
            "probable_root_cause": probable_root,
            "recommended_actions": recs,
            "images": matched_images
        })

    return ddr_items

def summarize_property(ddr_items):
    areas = set(i["area"] for i in ddr_items if i["area"] != "Not Available")
    issues = set()
    for it in ddr_items:
        if it["issues_detected"] and it["issues_detected"] != "Not Available":
            for x in it["issues_detected"].split(","):
                issues.add(x.strip())
    issues_list = ", ".join(list(issues)[:8]) if issues else "Not Available"
    return f"{len(areas)} impacted area(s) detected. Key issues observed: {issues_list}."

# ---------------------------
# PDF report generation
# ---------------------------
def generate_pdf_report(file_path, ddr_items, property_summary, metadata=None):
    doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    styles = getSampleStyleSheet()
    Story = []
    Story.append(Paragraph("Detailed Diagnostic Report (DDR)", styles['Title']))
    Story.append(Spacer(1, 12))
    meta_text = ""
    if metadata:
        meta_text = f"Prepared For: {metadata.get('client', 'Not Available')}<br/>Date: {metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}"
    else:
        meta_text = f"Date: {datetime.now().strftime('%Y-%m-%d')}"
    Story.append(Paragraph(meta_text, styles['Normal']))
    Story.append(Spacer(1, 12))
    Story.append(Paragraph("Property Issue Summary", styles['Heading2']))
    Story.append(Paragraph(property_summary, styles['Normal']))
    Story.append(Spacer(1, 12))

    Story.append(Paragraph("Area-wise Observations", styles['Heading2']))
    for it in ddr_items:
        Story.append(Paragraph(f"<b>Area:</b> {it['area']} (Page: {it.get('page','Not Available')})", styles['Heading3']))
        Story.append(Paragraph(f"<b>Observation:</b> {it['observation']}", styles['Normal']))
        Story.append(Paragraph(f"<b>Issues Detected:</b> {it['issues_detected']}", styles['Normal']))
        th = it['thermal']
        thtext = f"Hotspot: {th.get('hotspot', 'Not Available')}, Coldspot: {th.get('coldspot', 'Not Available')}, Delta: {th.get('delta', 'Not Available')}"
        Story.append(Paragraph(f"<b>Thermal Evidence:</b> {thtext}", styles['Normal']))
        Story.append(Paragraph(f"<b>Severity:</b> {it['severity']} ({it['severity_reasoning']})", styles['Normal']))
        Story.append(Paragraph(f"<b>Probable Root Cause:</b> {it['probable_root_cause']}", styles['Normal']))
        Story.append(Paragraph(f"<b>Recommended Actions:</b>", styles['Normal']))
        for rec in it['recommended_actions']:
            Story.append(Paragraph(f"- {rec}", styles['Normal']))
        Story.append(Spacer(1, 6))
        for img_path in it['images'][:2]:
            try:
                Story.append(RLImage(img_path, width=400, height=300))
                Story.append(Spacer(1, 6))
            except Exception:
                Story.append(Paragraph(f"Image not available: {img_path}", styles['Italic']))
        Story.append(Spacer(1, 12))

    Story.append(Paragraph("Additional Notes", styles['Heading2']))
    Story.append(Paragraph("Report generated using rule-based automated extraction. Validate findings with a site engineer before execution.", styles['Normal']))
    Story.append(Spacer(1, 12))

    Story.append(Paragraph("Missing or Unclear Information", styles['Heading2']))
    missing = []
    for it in ddr_items:
        if (it['thermal']['hotspot'] is None and it['thermal']['coldspot'] is None):
            missing.append(f"Thermal data for area '{it['area']}' - Not Available")
        if not it['images']:
            missing.append(f"Image for area '{it['area']}' - Not Available")
    if missing:
        for m in missing:
            Story.append(Paragraph("- " + m, styles['Normal']))
    else:
        Story.append(Paragraph("No missing information detected.", styles['Normal']))

    doc.build(Story)

# ---------------------------
# Streamlit UI
# ---------------------------
st.set_page_config(page_title="AI DDR Generator", layout="wide")
st.title("AI DDR Generator — Rule-based (Image mapping fixed)")

st.markdown("Upload the Inspection Report (PDF) and Thermal Report (PDF). The app extracts per-page text and images, matches images to observations using page numbers, and generates a DDR.")

col1, col2 = st.columns(2)
with col1:
    inspection_file = st.file_uploader("Upload Inspection Report (PDF)", type=["pdf"])
with col2:
    thermal_file = st.file_uploader("Upload Thermal Report (PDF)", type=["pdf"])

if st.button("Generate DDR"):
    if not inspection_file or not thermal_file:
        st.warning("Please upload both files.")
    else:
        # Read files ONCE and reuse bytes
        insp_bytes = inspection_file.read()
        therm_bytes = thermal_file.read()

        # Extract per-page text
        with st.spinner("Extracting text..."):
            insp_pages = extract_text_pages(insp_bytes)
            therm_pages = extract_text_pages(therm_bytes)
            insp_text = "\n".join(insp_pages)
            therm_text = "\n".join(therm_pages)

        # Extract and filter images (uses same bytes)
        with st.spinner("Extracting images..."):
            insp_images = extract_images_from_pdf_bytes(insp_bytes, output_dir="images", prefix="insp")
            therm_images = extract_images_from_pdf_bytes(therm_bytes, output_dir="images", prefix="therm")
            all_images = insp_images + therm_images

        st.success("Parsing complete.")

        # Show small previews
        st.subheader("Inspection: text preview (page 1)")
        st.text_area("Inspection page 1", value=(insp_pages[0][:2000] if insp_pages else "No text"), height=180)
        st.subheader("Thermal: text preview (page 1)")
        st.text_area("Thermal page 1", value=(therm_pages[0][:2000] if therm_pages else "No text"), height=180)

        # Analysis
        with st.spinner("Extracting findings and matching images..."):
            inspection_findings = extract_inspection_findings_per_page(insp_pages)
            thermal_readings = extract_thermal_readings_per_page(therm_pages)
            ddr_items = generate_ddr_structure(inspection_findings, thermal_readings, all_images)
            property_summary = summarize_property(ddr_items)
        st.success("Extraction & mapping complete.")

        # Display DDR items
        st.header("Generated DDR")
        st.markdown(f"**Property Summary:** {property_summary}")

        for idx, it in enumerate(ddr_items, start=1):
            st.markdown(f"### {idx}. Area: {it['area']} (Page: {it.get('page')})")
            st.write("**Observation:**", it['observation'])
            st.write("**Issues Detected:**", it['issues_detected'])
            th = it['thermal']
            st.write("**Thermal:**", f"Hotspot: {th.get('hotspot','Not Available')}  Coldspot: {th.get('coldspot','Not Available')}  Delta: {th.get('delta','Not Available')}")
            st.write("**Severity:**", it['severity'])
            st.write("**Severity Reasoning:**", it['severity_reasoning'])
            st.write("**Probable Root Cause:**", it['probable_root_cause'])
            st.write("**Recommended Actions:**")
            for rec in it['recommended_actions']:
                st.write("-", rec)
            st.write("**Images (mapped):**")
            if it['images']:
                cols = st.columns(min(3, len(it['images'])))
                for i, p in enumerate(it['images']):
                    try:
                        img = Image.open(p)
                        cols[i % len(cols)].image(img, use_column_width=True, caption=os.path.basename(p))
                    except Exception:
                        cols[i % len(cols)].write("Image not found")
            else:
                st.write("Image Not Available")
            st.markdown("---")

        # Markdown report
        md_lines = []
        md_lines.append("# Detailed Diagnostic Report (DDR)\n")
        md_lines.append(f"**Property Summary:** {property_summary}\n\n")
        md_lines.append("## Area-wise Observations\n")
        for it in ddr_items:
            md_lines.append(f"### Area: {it['area']} (Page: {it.get('page')})\n")
            md_lines.append(f"**Observation:** {it['observation']}\n")
            md_lines.append(f"**Issues Detected:** {it['issues_detected']}\n")
            th = it['thermal']
            md_lines.append(f"**Thermal Evidence:** Hotspot: {th.get('hotspot','Not Available')}, Coldspot: {th.get('coldspot','Not Available')}, Delta: {th.get('delta','Not Available')}\n")
            md_lines.append(f"**Severity:** {it['severity']} ({it['severity_reasoning']})\n")
            md_lines.append(f"**Probable Root Cause:** {it['probable_root_cause']}\n")
            md_lines.append("**Recommended Actions:**\n")
            for rec in it['recommended_actions']:
                md_lines.append(f"- {rec}\n")
            if it['images']:
                for im in it['images']:
                    md_lines.append(f"![{os.path.basename(im)}]({im})\n")
            else:
                md_lines.append("Image Not Available\n")
            md_lines.append("\n---\n")

        md_lines.append("## Additional Notes\n")
        md_lines.append("Report generated using rule-based automated extraction. Validate before action.\n")
        md_lines.append("## Missing or Unclear Information\n")
        missing = []
        for it in ddr_items:
            if (it['thermal']['hotspot'] is None and it['thermal']['coldspot'] is None):
                missing.append(f"Thermal data for area '{it['area']}' - Not Available")
            if not it['images']:
                missing.append(f"Image for area '{it['area']}' - Not Available")
        if missing:
            for m in missing:
                md_lines.append(f"- {m}\n")
        else:
            md_lines.append("- None\n")

        md_report = "\n".join(md_lines)
        st.download_button("Download DDR as Markdown (.md)", data=md_report, file_name="DDR_Report.md", mime="text/markdown")

        # PDF generation
        pdf_path = "DDR_Report.pdf"
        with st.spinner("Generating PDF..."):
            generate_pdf_report(pdf_path, ddr_items, property_summary, metadata={"client": inspection_file.name, "date": datetime.now().strftime("%Y-%m-%d")})
        st.success("PDF generated.")
        with open(pdf_path, "rb") as f:
            st.download_button("Download DDR as PDF", data=f, file_name="DDR_Report.pdf", mime="application/pdf")

        st.info("Review the mapped images and report before using for remedial work. Heuristic mapping was used; manual validation recommended.")
