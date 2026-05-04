import streamlit as st
import pdfplumber
import re
import pandas as pd

st.set_page_config(page_title="Audit PDF de Paie", layout="wide")

def extract_data_from_pdf(file):
    """Extrait le texte et tente de structurer les tableaux du PDF."""
    full_text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Extraction du texte brut
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text

def clean_val(value):
    if not value: return 0.0
    # Nettoyage des caractères non numériques courants dans les PDFs
    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def analyser_contenu(texte):
    res = {}
    # Extraction SIRET (14 chiffres)[cite: 1, 3]
    siret = re.search(r"SIRET[:\s]*(\d{3}\s?\d{3}\s?\d{3}\s?\d{5})", texte, re.I)
    res['siret'] = siret.group(1).replace(" ", "") if siret else "Non détecté"

    # Extraction des montants (Mois vs Cumuls)[cite: 3, 6, 10]
    # Utilisation de patterns flexibles pour s'adapter aux différents formats (DINDY, BOULANGERIE, etc.)
    res['brut_mois'] = clean_val((re.search(r"SALAIRE BRUT.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    res['brut_annuel'] = clean_val((re.search(r"Annuel.*?Brut.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    
    # Net à payer[cite: 1, 2, 7]
    net_paye = re.search(r"NET\s+PAYÉ.*?(\d[\d\s,.]*\d)|NET\s+A\s+PAYER.*?(\d[\d\s,.]*\d)", texte, re.I | re.S)
    res['net_paye'] = clean_val(net_paye.group(1) or net_paye.group(2)) if net_paye else 0.0

    # Heures et Congés[cite: 1, 6, 8]
    heures = re.search(r"Hrs trav\..*?(\d[\d\s,.]*\d)|Heures.*?(\d[\d\s,.]*\d)", texte, re.I | re.S)
    res['heures'] = clean_val(heures.group(1) or heures.group(2)) if heures else 0.0
    
    conges = re.search(r"Reste.*?(\d[\d\s,.]*\d)|Solde.*?(\d[\d\s,.]*\d)", texte, re.I | re.S)
    res['conges'] = clean_val(conges.group(1) or conges.group(2)) if conges else 0.0

    return res

# --- Interface Streamlit ---
st.title("🛡️ Vérificateur Officiel de Bulletins de Paie (PDF)")
st.write("Téléchargez un bulletin (ex: Fichier2.pdf, CAMARA MOHAMED FEVRIER.pdf) pour vérification.")

uploaded_file = st.file_uploader("Choisir un fichier PDF", type="pdf")

if uploaded_file:
    with st.spinner('Extraction des données en cours...'):
        texte_extrait = extract_data_from_pdf(uploaded_file)
        data = analyser_contenu(texte_extrait)
        
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📄 Données du Bulletin")
        st.info(f"**SIRET Employeur :** {data['siret']}[cite: 1, 9]")
        st.metric("Salaire Brut (Mois)", f"{data['brut_mois']} €")
        st.metric("Net Payé", f"{data['net_paye']} €")
        st.write(f"**Heures détectées :** {data['heures']} h[cite: 7]")
        st.write(f"**Solde Congés :** {data['conges']} jours[cite: 1, 6]")

    with col2:
        st.subheader("🚩 Analyse d'Authenticité")
        
        # Test 1 : Cohérence Net/Brut[cite: 1, 4]
        if data['brut_mois'] > 0:
            ratio = data['net_paye'] / data['brut_mois']
            if ratio > 0.9:
                st.error(f"❌ Ratio Net/Brut suspect ({ratio:.1%}). Le net est trop proche du brut.")
            elif ratio < 0.6:
                st.warning(f"⚠️ Ratio Net/Brut faible ({ratio:.1%}). Vérifiez les saisies ou absences.")
            else:
                st.success(f"✅ Ratio Net/Brut cohérent ({ratio:.1%}).")

        # Test 2 : Vérification du Cumul
        if data['brut_annuel'] > 0 and data['brut_mois'] > data['brut_annuel']:
            st.error("❌ Alerte Cumul : Le salaire du mois est supérieur au total annuel déclaré.")
        
        # Test 3 : Format SIRET[cite: 3, 9]
        if data['siret'] != "Non détecté" and len(data['siret']) != 14:
            st.warning("⚠️ Le numéro SIRET extrait ne semble pas valide (14 chiffres attendus).")

    with st.expander("Voir le texte brut extrait du PDF"):
        st.text(texte_extrait)
