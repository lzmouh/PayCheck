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
def extract_text(pdf):
    text = ""
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t:
                text += t

    if len(text) < 100:
        images = convert_from_path(pdf)
        for img in images:
            text += pytesseract.image_to_string(img)

    return text.lower()

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

def parse(text):
    text = clean(text)

    return Payslip(
        month=re.search(r"période\s*:\s*(\w+)", text).group(1),
        brut=extract([r"brut .*? (\d+\.\d+)"], text),
        net=extract([r"net payé .*? (\d+\.\d+)"], text),
        net_before_tax=extract([r"net .*? avant imp[oô]t .*? (\d+\.\d+)"], text),
        tax=extract([r"pas .*? (\d+\.\d+)"], text),
        base_salary=extract([r"151\.67 .*? (\d+\.\d+)"], text),
        bonus=extract([r"prime .*? (\d+\.\d+)"], text),
        seniority=1.0
    )

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
