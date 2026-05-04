import streamlit as st
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
import re
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
from Levenshtein import ratio

# -------- DATA STRUCTURE --------
@dataclass
class Payslip:
    filename: str
    month_str: str
    date_obj: datetime
    siret: str
    adresse_emp: str
    statut: str
    salaire_base: float
    brut: float
    net_paye: float
    net_avant_impot: float
    impot_pas: float
    prev_sociale: float # Total cotisations
    cumul_brut: float
    cumul_net_imposable: float
    prime: float
    anciennete_mois: int
    date_paiement: datetime

# -------- EXTRACTION ENGINE --------
def extract_value(patterns, text, is_float=True):
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                raw = m.group(1).replace(" ", "").replace(",", ".")
                return float(raw) if is_float else m.group(1).strip()
            except: continue
    return 0.0 if is_float else ""

def parse_payslip(file):
    file.seek(0)
    text = ""
    with pdfplumber.open(file) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t: text += t
    
    if len(text) < 100:
        file.seek(0)
        images = convert_from_bytes(file.read())
        text = "".join([pytesseract.image_to_string(img) for img in images])
    
    clean_text = text.lower().replace("\n", " ")
    
    # Date & Period
    months = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    m_match = re.search(r"(?P<m>"+ "|".join(months) + r")\s*(?P<y>20\d{2})", clean_text)
    date_obj = datetime(int(m_match.group('y')), months.index(m_match.group('m'))+1, 1) if m_match else datetime.now()

    # Payment Date
    pay_match = re.search(r"payé\s*le\s*(\d{2}/\d{2}/\d{4})", clean_text)
    pay_date = datetime.strptime(pay_match.group(1), "%d/%m/%Y") if pay_match else None

    return Payslip(
        filename=file.name,
        month_str=m_match.group(0) if m_match else "Inconnu",
        date_obj=date_obj,
        siret=extract_value([r"siret\s*[:\s]*(\d{14})", r"(\d{3}\s\d{3}\s\d{3}\s\d{5})"], clean_text, False),
        adresse_emp=extract_value([r"employeur\s*:(.*?)(?=siret|code|$)"], clean_text, False),
        statut=extract_value([r"statut\s*[:\s]*(.*?)(?=coefficient|échelon|$)"], clean_text, False),
        salaire_base=extract_value([r"salaire\s*de\s*base\s*(\d+[\s\.,]\d{2})"], clean_text),
        brut=extract_value([r"total\s*brut\s*(\d+[\s\.,]\d{2})"], clean_text),
        net_paye=extract_value([r"net\s*payé\s*(\d+[\s\.,]\d{2})", r"net\s*à\s*payer\s*(\d+[\s\.,]\d{2})"], clean_text),
        net_avant_impot=extract_value([r"net\s*avant\s*imp[oô]t\s*(\d+[\s\.,]\d{2})"], clean_text),
        impot_pas=extract_value([r"imp[oô]t\s*sur\s*le\s*revenu\s*(\d+[\s\.,]\d{2})", r"pas\s*(\d+[\s\.,]\d{2})"], clean_text),
        prev_sociale=extract_value([r"total\s*des\s*cotisations\s*(\d+[\s\.,]\d{2})"], clean_text),
        cumul_brut=extract_value([r"cumul\s*brut\s*(\d+[\s\.,]\d{2})"], clean_text),
        cumul_net_imposable=extract_value([r"cumul\s*net\s*imposable\s*(\d+[\s\.,]\d{2})"], clean_text),
        prime=extract_value([r"prime\s*exceptionnelle\s*(\d+[\s\.,]\d{2})", r"prime\s*de\s*rendement\s*(\d+[\s\.,]\d{2})"], clean_text),
        anciennete_mois=int(extract_value([r"anciennet[ée]\s*:\s*(\d+)\s*mois"], clean_text)),
        date_paiement=pay_date
    )

# -------- PROFESSIONAL AUDIT ENGINE --------
def run_audit(payslips):
    ps = sorted(payslips, key=lambda x: x.date_obj)
    reports = []
    total_score = 10
    
    # 1. Identity & Employer Verification
    if len(set([p.siret for p in ps])) > 1:
        reports.append(("❌ SIRET Incohérent", "Le numéro SIRET change d'un mois à l'autre.", "MAJEUR"))
        total_score -= 3
    
    for i in range(1, len(ps)):
        if ratio(ps[i].adresse_emp, ps[i-1].adresse_emp) < 0.8:
            reports.append(("⚠️ Adresse Employeur", f"Variation d'adresse suspecte entre {ps[i-1].month_str} et {ps[i].month_str}.", "MINEUR"))
            total_score -= 1

    # 2. Chronology & Payment Logic
    for p in ps:
        if p.date_paiement and p.date_paiement.month == p.date_obj.month and p.date_paiement.day < 25:
            reports.append(("❌ Date de Paiement Illogique", f"Paiement le {p.date_paiement.day} pour le mois de {p.month_str}.", "MAJEUR"))
            total_score -= 2
            
    for i in range(1, len(ps)):
        if ps[i].anciennete_mois <= ps[i-1].anciennete_mois:
             reports.append(("❌ Ancienneté Incohérente", f"L'ancienneté n'augmente pas entre {ps[i-1].month_str} et {ps[i].month_str}.", "MAJEUR"))
             total_score -= 3

    # 3. Math Consistency (Brut -> Net)
    for p in ps:
        theorique_net = p.net_avant_impot - p.impot_pas
        if abs(theorique_net - p.net_paye) > 0.05:
            reports.append(("❌ Erreur de Calcul Net", f"Calcul Net/PAS faux sur {p.month_str}.", "MAJEUR"))
            total_score -= 4

    # 4. YTD / Cumuls (The "Fatal" Test)
    for i in range(1, len(ps)):
        if ps[i].cumul_brut <= ps[i-1].cumul_brut:
            reports.append(("❌ Cumul Annuel Bloqué", f"Le cumul brut de {ps[i].month_str} n'est pas supérieur à {ps[i-1].month_str}.", "CRITIQUE"))
            total_score -= 5

    # 5. Suspicious Repetitions ("Too Perfect")
    if len(ps) > 1:
        if len(set([p.brut for p in ps])) == 1 and len(set([p.net_paye for p in ps])) > 1:
            reports.append(("❌ Brut constant / Net variable", "Mathématiquement impossible si les cotisations sont fixes.", "CRITIQUE"))
            total_score -= 4
        if len(set([p.prime for p in ps])) == 1 and ps[0].prime > 0:
            reports.append(("⚠️ Prime Suspecte", "Prime identique répétée sans aucune variation.", "MINEUR"))
            total_score -= 1

    return reports, max(0, total_score)

# -------- UI --------
st.set_page_config(page_title="Audit Expert Paie", layout="wide")
st.title("🛡️ Audit Professionnel de Documents de Paie")

uploaded_files = st.file_uploader("Fichiers PDF", accept_multiple_files=True)

if uploaded_files:
    extracted_data = [parse_payslip(f) for f in uploaded_files]
    anomalies, score = run_audit(extracted_data)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.metric("SCORE DE FIABILITÉ", f"{score}/10")
        if score >= 8: st.success("Dossier Conforme")
        elif score >= 5: st.warning("Dossier Douteux")
        else: st.error("Dossier NON FIABLE / REJET")
        
        st.write("### Détail des Anomalies")
        for title, msg, severity in anomalies:
            color = "red" if severity in ["MAJEUR", "CRITIQUE"] else "orange"
            st.markdown(f"**<span style='color:{color}'>{title}</span>** : {msg}", unsafe_allow_html=True)

    with col2:
        df = pd.DataFrame([vars(p) for p in extracted_data]).sort_values("date_obj")
        st.write("### Données pour Vérification Manuelle")
        st.dataframe(df[['month_str', 'siret', 'salaire_base', 'brut', 'net_paye', 'cumul_brut', 'anciennete_mois']])
        
        st.write("### Graphique de Cohérence des Cumuls")
        st.line_chart(df.set_index('month_str')[['cumul_brut', 'cumul_net_imposable']])
