import streamlit as st
import pdfplumber
import re
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Audit Intégrité Paie", layout="wide")

# --- Fonctions d'Extraction ---
def extract_all_data(files):
    all_records = []
    months_map = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
        'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }

    for file in files:
        with pdfplumber.open(file) as pdf:
            text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
            
            # Extraction de la période[cite: 3, 7, 10]
            date_match = re.search(r"Période[:\s]*([A-Za-zûé]+)\s+(\202\d)", text, re.I)
            month_str = date_match.group(1).lower() if date_match else "inconnu"
            year = int(date_match.group(2)) if date_match else 2026
            month_num = months_map.get(month_str, 0)

            # Extraction des valeurs financières[cite: 1, 6, 9]
            record = {
                "Fichier": file.name,
                "Mois_Num": month_num,
                "Période": f"{month_str.capitalize()} {year}",
                "Brut_Mois": clean_val(re.search(r"SALAIRE BRUT.*?(\d[\d\s,.]*\d)", text, re.I | re.S)),
                "Brut_Cumul": clean_val(re.search(r"Annuel.*?Brut.*?(\d[\d\s,.]*\d)", text, re.I | re.S)),
                "Net_Payé": clean_val(re.search(r"NET\s+(?:PAYÉ|A\s+PAYER).*?(\d[\d\s,.]*\d)", text, re.I | re.S)),
                "Congés_Acquis": clean_val(re.search(r"Acquis.*?(\d[\d\s,.]*\d)", text, re.I | re.S)),
                "Congés_Solde": clean_val(re.search(r"Solde.*?(\d[\d\s,.]*\d)|Reste.*?(\d[\d\s,.]*\d)", text, re.I | re.S))
            }
            all_records.append(record)
    
    # Tri par ordre chronologique[cite: 2, 9]
    return sorted(all_records, key=lambda x: x['Mois_Num'])

def clean_val(match):
    if not match: return 0.0
    val = match.group(1) if match.groups() else match.group(0)
    return float(re.sub(r"[^\d,.-]", "", str(val)).replace(",", "."))

# --- Interface Streamlit ---
st.title("🛡️ Audit de Cohérence Multi-Bulletins")
st.write("Téléchargez plusieurs mois pour vérifier l'intégrité de la progression des revenus et des congés.")

uploaded_files = st.file_uploader("Téléchargez vos PDFs (ex: Janvier, Février, Mars...)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    data = extract_all_data(uploaded_files)
    df = pd.DataFrame(data)
    
    st.subheader("📋 Récapitulatif Chronologique")
    st.dataframe(df.drop(columns=['Mois_Num']), use_container_width=True)

    st.subheader("🔍 Analyse de l'Intégrité")
    
    if len(data) > 1:
        for i in range(1, len(data)):
            prev = data[i-1]
            curr = data[i]
            
            st.markdown(f"**Comparaison : {prev['Période']} ➡️ {curr['Période']}**")
            
            # 1. Vérification mathématique du cumul Brut[cite: 6, 9]
            attendu = prev['Brut_Cumul'] + curr['Brut_Mois']
            diff = abs(curr['Brut_Cumul'] - attendu)
            
            if diff < 2.0: # Tolérance pour arrondis
                st.success(f"✅ Intégrité du cumul Brut validée ({curr['Brut_Cumul']} €).")
            else:
                st.error(f"❌ Rupture de cumul détectée ! Attendu: {attendu} €, Trouvé: {curr['Brut_Cumul']} €.")
            
            # 2. Vérification de la progression des congés[cite: 1, 6, 10]
            if curr['Congés_Solde'] < prev['Congés_Solde'] and curr['Congés_Solde'] > 0:
                st.info(f"ℹ️ Diminution du solde de congés (Prise de congés probable).")
            elif curr['Congés_Solde'] == prev['Congés_Solde']:
                st.warning(f"⚠️ Le solde de congés n'a pas bougé entre les deux mois.")
                
            st.divider()
    else:
        st.info("Téléchargez au moins deux bulletins pour activer l'analyse de progression.")
