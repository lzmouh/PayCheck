import streamlit as st
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import re
from dataclasses import dataclass

# -------- DATA --------
@dataclass
class Payslip:
    month: str
    brut: float
    net: float
    net_before_tax: float
    tax: float
    base_salary: float
    bonus: float
    seniority: float

# -------- EXTRACTION --------
def extract_text(pdf_file):
    text = ""
    # Reset stream position to ensure it's readable
    pdf_file.seek(0) 
    with pdfplumber.open(pdf_file) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t: text += t

    if len(text) < 100:
        from pdf2image import convert_from_bytes
        pdf_file.seek(0)
        images = convert_from_bytes(pdf_file.read())
        for img in images:
            text += pytesseract.image_to_string(img)

    return text.lower()

def parse(text):
    text = clean(text)
    
    # Safe month extraction
    month_match = re.search(r"période\s*:\s*(\w+)", text)
    month_val = month_match.group(1) if month_match else "Inconnu"

    return Payslip(
        month=month_val,
        brut=extract([r"brut\s*[:\s]*(\d+[\s\.]?\d*\.\d{2})"], text),
        # ... repeat for others with improved regex
        seniority=1.0 # Consider extracting this from "Ancienneté" keywords
    )

def clean(text):
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(",", ".")
    return text

def extract(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                return float(m.group(1).replace(" ", ""))
            except:
                pass
    return 0

# -------- ANALYSE --------
def analyze(payslips):
    issues = []
    score = 10

    for i in range(1, len(payslips)):
        if payslips[i].seniority < payslips[i-1].seniority:
            issues.append("Ancienneté incohérente")
            score -= 2

    for p in payslips:
        if abs((p.net_before_tax - p.tax) - p.net) > 5:
            issues.append(f"Incohérence net ({p.month})")
            score -= 2

    for i in range(1, len(payslips)):
        if payslips[i].brut == payslips[i-1].brut and payslips[i].net != payslips[i-1].net:
            issues.append("Variation incohérente")
            score -= 2

    bonuses = [p.bonus for p in payslips]
    if len(set(bonuses)) == 1 and bonuses[0] > 0:
        issues.append("Prime suspecte constante")
        score -= 1

    score = max(score, 0)

    if score >= 8:
        reco = "✅ Dossier fiable"
    elif score >= 5:
        reco = "⚠️ Doute"
    else:
        reco = "❌ Probable falsification"

    return issues, score, reco

# -------- UI --------
st.title("🔎 Analyse de bulletins de paie")

files = st.file_uploader("Importer les PDF", type="pdf", accept_multiple_files=True)

if files:
    payslips = []

    for file in files:
        text = extract_text(file)
        p = parse(text)

        st.subheader(p.month)
        st.write(vars(p))

        payslips.append(p)

    issues, score, reco = analyze(payslips)

    st.divider()
    st.subheader("Résultat")

    st.write("### Score :", score, "/10")
    st.write("### Recommandation :", reco)

    st.write("### Anomalies détectées :")
    for i in issues:
        st.write("-", i)
