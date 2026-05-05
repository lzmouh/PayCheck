import streamlit as st
import pdfplumber, pytesseract, re
from pdf2image import convert_from_path
from dataclasses import dataclass
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# =========================
# 📊 MODELE
# =========================
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


# =========================
# 📥 EXTRACTION
# =========================
def extract_text(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t

    if len(text) < 100:
        images = convert_from_path(file)
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


# =========================
# 🧠 ANALYSE
# =========================
def analyze(payslips):
    issues = []
    score = 10

    for i in range(1, len(payslips)):
        if payslips[i].seniority < payslips[i-1].seniority:
            issues.append("Ancienneté incohérente")
            score -= 2

    for p in payslips:
        if abs((p.net_before_tax - p.tax) - p.net) > 5:
            issues.append(f"Incohérence calcul net ({p.month})")
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
        reco = "Validation"
    elif score >= 5:
        reco = "Vérification complémentaire"
    else:
        reco = "Refus dossier"

    return issues, score, reco


# =========================
# 📄 RAPPORT PDF
# =========================
def generate_pdf(issues, score, reco):
    file_path = "/mnt/data/rapport_analyse.pdf"
    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    content = []
    content.append(Paragraph("Rapport d'analyse des bulletins de paie", styles["Title"]))
    content.append(Spacer(1, 12))

    content.append(Paragraph(f"Score: {score}/10", styles["Normal"]))
    content.append(Paragraph(f"Recommandation: {reco}", styles["Normal"]))
    content.append(Spacer(1, 12))

    content.append(Paragraph("Anomalies détectées :", styles["Heading2"]))

    if issues:
        for i in issues:
            content.append(Paragraph(f"- {i}", styles["Normal"]))
    else:
        content.append(Paragraph("Aucune anomalie", styles["Normal"]))

    doc.build(content)

    return file_path


# =========================
# 🖥️ UI STREAMLIT
# =========================
st.title("🔎 Analyse de bulletins de paie (outil pro)")

files = st.file_uploader("Importer les PDF", type="pdf", accept_multiple_files=True)

if files:
    payslips = []

    for file in files:
        text = extract_text(file)
        p = parse(text)

        st.subheader(p.month)
        st.write(vars(p))

        payslips.append(p)

    if st.button("Analyser le dossier"):

        issues, score, reco = analyze(payslips)

        st.divider()
        st.subheader("Résultat")

        st.write(f"Score : {score}/10")
        st.write(f"Recommandation : {reco}")

        st.write("Anomalies :")
        for i in issues:
            st.write("-", i)

        # Génération PDF
        pdf_path = generate_pdf(issues, score, reco)

        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📄 Télécharger le rapport PDF",
                data=f,
                file_name="rapport_analyse.pdf",
                mime="application/pdf"
            )
