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
    net_avant_impot: float
    impot: float
    salaire_base: float
    heures: float
    conges_pris: float
    prime: float
    anciennete_str: str  # Original text from PDF
    anciennete_val: float # Numeric for calculation

MONTH_MAP = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
}

# -------- EXTRACTION --------
def extract_text(pdf_file):
    pdf_file.seek(0)
    text = ""
    with pdfplumber.open(pdf_file) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t: text += t

    if len(text.strip()) < 100:
        pdf_file.seek(0)
        images = convert_from_bytes(pdf_file.read())
        for img in images:
            text += pytesseract.image_to_string(img)
    return text.lower()

def clean(text):
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\d),(\d{2})", r"\1.\2", text) # Commas to dots for math
    return text

def extract_value(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                val = m.group(1).replace(" ", "").replace("o", "0")
                return float(val)
            except: continue
    return 0.0

def parse(text):
    cleaned_text = clean(text)
    
    # Date extraction
    month_match = re.search(r"(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)", cleaned_text)
    year_match = re.search(r"20\d{2}", cleaned_text)
    m_str = month_match.group(0) if month_match else "inconnu"
    y_int = int(year_match.group(0)) if year_match else datetime.now().year
    date_obj = datetime(y_int, MONTH_MAP.get(m_str, 1), 1)

    # Heures & Congés (Common French Payslip Keywords)
    heures = extract_value([r"heures\s*travaillees\s*(\d+[\s\.]?\d*)", r"(\d+\.\d{2})\s*h\s*normales"], cleaned_text)
    if heures == 0: heures = 151.67 # Default French legal month
    
    conges = extract_value([r"conges\s*pris\s*(\d+[\s\.]?\d*)", r"nb\s*jours\s*pris\s*(\d+[\s\.]?\d*)"], cleaned_text)

    # Seniority (Extracting the date or the year count)
    anc_match = re.search(r"anciennet[ée]\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}|\d+\s*ans?)", cleaned_text)
    anc_str = anc_match.group(1) if anc_match else "Non détecté"

    return Payslip(
        month=f"{m_str.capitalize()} {y_int}",
        date_obj=date_obj,
        brut=extract_value([r"total brut.*?(\d+[\s\.]?\d*\.\d{2})", r"salaire brut.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        net=extract_value([r"net payé.*?(\d+[\s\.]?\d*\.\d{2})", r"net à payer.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        net_avant_impot=extract_value([r"net avant imp[oô]t.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        impot=extract_value([r"imp[oô]t.*?(\d+[\s\.]?\d*\.\d{2})", r"pas.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        salaire_base=extract_value([r"salaire de base.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        heures=heures,
        conges_pris=conges,
        prime=extract_value([r"prime.*?(\d+[\s\.]?\d*\.\d{2})"], cleaned_text),
        anciennete_str=anc_str,
        anciennete_val=0.0 # Will be extrapolated later
    )

# -------- UI & LOGIC --------
st.set_page_config(page_title="Audit Paie AI", layout="wide")
st.title("🔎 Expert Audit de Bulletins de Paie")

files = st.file_uploader("Charger les bulletins (PDF)", type="pdf", accept_multiple_files=True)

if files:
    data_list = []
    for f in files:
        with st.spinner(f"Lecture de {f.name}..."):
            data_list.append(parse(extract_text(f)))

    if data_list:
        # Create DataFrame and Sort
        df = pd.DataFrame([vars(p) for p in data_list])
        df = df.sort_values("date_obj")

        # 1. Extrapolate Cumulative Data
        df['Brut Cumulé'] = df['brut'].cumsum()
        df['Heures Cumulées'] = df['heures'].cumsum()
        df['Congés Cumulés'] = df['conges_pris'].cumsum()
        
        # 2. Refine Table for Display (French Names)
        display_df = df.rename(columns={
            'month': 'Période',
            'brut': 'Salaire Brut (€)',
            'net': 'Net à Payer (€)',
            'net_avant_impot': 'Net Avant Impôt (€)',
            'impot': 'Impôt (PAS) (€)',
            'salaire_base': 'Salaire de Base (€)',
            'heures': 'Heures Travaillées',
            'conges_pris': 'Congés Pris (J)',
            'prime': 'Primes (€)',
            'anciennete_str': 'Ancienneté (Doc)'
        })

        # Select columns to show
        cols_to_show = [
            'Période', 'Salaire de Base (€)', 'Salaire Brut (€)', 'Brut Cumulé', 
            'Net à Payer (€)', 'Heures Travaillées', 'Heures Cumulées', 
            'Congés Pris (J)', 'Congés Cumulés', 'Ancienneté (Doc)'
        ]
        
        st.subheader("📊 Tableau Récapitulatif et Cumuls")
        st.dataframe(display_df[cols_to_show], use_container_width=True, hide_index=True)

        # 3. Enhanced Visualization
        st.divider()
        st.subheader("📈 Visualisation des Tendances")
        
        tab1, tab2 = st.tabs(["Salaires & Cumuls", "Temps de Travail & Congés"])
        
        with tab1:
            # Multi-line chart for financial data
            st.line_chart(df.set_index('month')[['brut', 'net', 'Brut Cumulé']])
            
        with tab2:
            # Bar chart for hours and leave
            st.bar_chart(df.set_index('month')[['heures', 'conges_pris']])
            st.write("**Évolution des Heures Cumulées**")
            st.line_chart(df.set_index('month')['Heures Cumulées'])

        # Simple Consistency Check for the UI
        if len(df) > 1:
            st.divider()
            st.subheader("🔍 Analyse de Cohérence")
            diff_brut = df['brut'].iloc[-1] - df['brut'].iloc[0]
            if diff_brut != 0:
                st.warning(f"Variation de salaire brut détectée sur la période : {diff_brut:+.2f}€")
            else:
                st.success("Salaire brut stable sur la période analysée.")
