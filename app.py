import streamlit as st
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import re
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

# -------- DATA --------
@dataclass
class Payslip:
    month: str
    date_obj: datetime
    brut: float
    net: float
    net_before_tax: float
    tax: float
    base_salary: float
    bonus: float
    seniority: float

# Mapping for French months to sortable dates
MONTH_MAP = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}

# -------- EXTRACTION --------
def extract_text(pdf_file):
    """Extracts text using pdfplumber with a fallback to OCR."""
    text = ""
    # Ensure we are at the start of the file stream
    pdf_file.seek(0)
    
    with pdfplumber.open(pdf_file) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t:
                text += t

    # Fallback to OCR if text is sparse (likely a scanned image)
    if len(text.strip()) < 100:
        pdf_file.seek(0)
        images = convert_from_bytes(pdf_file.read())
        for img in images:
            text += pytesseract.image_to_string(img)

    return text.lower()

def clean(text):
    """Normalizes the text for regex parsing."""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    # Replace French decimal comma with dot, but avoid breaking dates or other patterns
    # This specific regex targets commas between digits
    text = re.sub(r"(\d),(\d{2})", r"\1.\2", text)
    return text

def extract_value(patterns, text):
    """Helper to try multiple regex patterns and return a float."""
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                # Remove spaces (thousands separator) and convert to float
                val = m.group(1).replace(" ", "").replace("o", "0") 
                return float(val)
            except (ValueError, IndexError):
                continue
    return 0.0

def parse(text):
    """Parses the cleaned text into a Payslip object."""
    cleaned_text = clean(text)
    
    # Extract Month and Year
    month_match = re.search(r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)", cleaned_text)
    year_match = re.search(r"20\d{2}", cleaned_text)
    
    month_str = month_match.group(0) if month_match else "inconnu"
    year_int = int(year_match.group(0)) if year_match else datetime.now().year
    
    # Create a date object for sorting
    month_idx = MONTH_MAP.get(month_str, 1)
    date_obj = datetime(year_int, month_idx, 1)

    return Payslip(
        month=f"{month_str.capitalize()} {year_int}",
        date_obj=date_obj,
        # Improved patterns for French payslip variations
        brut=extract_value([r"total brut.*?(\d+[\s\.]?\d*\.\d{2})", r"salaire brut.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        net=extract_value([r"net payé.*?(\d+[\s\.]?\d*\.\d{2})", r"net à payer.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        net_before_tax=extract_value([r"net avant imp[oô]t.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        tax=extract_value([r"montant de l'imp[oô]t.*?(\d+[\s\.]?\d*\.\d{2})", r"pas.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        base_salary=extract_value([r"salaire de base.*?(\d+[\s\.]?\d*\.\d{2})", r"151\.67.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        bonus=extract_value([r"prime.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        seniority=extract_value([r"anciennet[ée].*?(\d+[\s\.]?\d*)"], cleaned_text)
    )

# -------- ANALYSE --------
def analyze(payslips):
    """Evaluates the consistency of the uploaded documents."""
    if not payslips:
        return [], 0, "Aucune donnée"
    
    # Sort payslips by date
    payslips.sort(key=lambda x: x.date_obj)
    
    issues = []
    score = 10

    # 1. Seniority Check
    for i in range(1, len(payslips)):
        if payslips[i].seniority < payslips[i-1].seniority:
            issues.append(f"Incohérence d'ancienneté entre {payslips[i-1].month} et {payslips[i].month}")
            score -= 2

    # 2. Mathematical Consistency (Net = Net before tax - Tax)
    for p in payslips:
        if p.net_before_tax > 0:
            diff = abs((p.net_before_tax - p.tax) - p.net)
            if diff > 2.0: # Allowance for small rounding errors
                issues.append(f"Erreur de calcul net sur {p.month} (écart: {diff:.2f}€)")
                score -= 3

    # 3. Brut/Net Variation Check
    for i in range(1, len(payslips)):
        if payslips[i].brut == payslips[i-1].brut and abs(payslips[i].net - payslips[i-1].net) > 50:
            issues.append(f"Variation suspecte du net sans changement du brut ({payslips[i].month})")
            score -= 2

    # 4. Constant Bonus Check
    bonuses = [p.bonus for p in payslips if p.bonus > 0]
    if len(bonuses) > 2 and len(set(bonuses)) == 1:
        issues.append("Primes identiques sur tous les mois (atypique)")
        score -= 1

    score = max(score, 0)
    reco = "✅ Dossier fiable" if score >= 8 else "⚠️ Doute" if score >= 5 else "❌ Probable falsification"
    
    return issues, score, reco

# -------- UI --------
st.set_page_config(page_title="Vérificateur de Bulletins", layout="wide")
st.title("🔎 Analyseur de Bulletins de Paie")
st.info("Déposez vos bulletins (PDF) pour vérifier la cohérence des données.")

uploaded_files = st.file_uploader("Importer les PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    payslips = []
    
    for file in uploaded_files:
        try:
            with st.spinner(f"Traitement de {file.name}..."):
                raw_text = extract_text(file)
                data = parse(raw_text)
                payslips.append(data)
        except Exception as e:
            st.error(f"Erreur sur le fichier {file.name}: {e}")

    if payslips:
        # Sort for display and analysis
        payslips.sort(key=lambda x: x.date_obj)
        
        # Display Data Table
        df = pd.DataFrame([vars(p) for p in payslips]).drop(columns=['date_obj'])
        st.subheader("Données extraites")
        st.dataframe(df, use_container_width=True)

        # Analysis Section
        issues, score, reco = analyze(payslips)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Score de fiabilité", f"{score}/10")
            st.subheader(reco)
            
            if issues:
                st.write("### Anomalies détectées :")
                for issue in issues:
                    st.error(issue)
            else:
                st.success("Aucune anomalie mathématique détectée.")

        with col2:
            st.write("### Évolution du Salaire")
            chart_data = pd.DataFrame({
                'Mois': [p.month for p in payslips],
                'Brut': [p.brut for p in payslips],
                'Net': [p.net for p in payslips]
            }).set_index('Mois')
            st.line_chart(chart_data)
