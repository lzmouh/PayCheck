import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Vérification Avancée de Paie", layout="wide")

def clean_float(value):
    if not value: return 0.0
    # Nettoie les espaces et remplace la virgule par un point
    return float(value.replace(" ", "").replace(",", "."))

def extraire_donnees_completes(texte):
    data = {}
    
    # --- Identifiants ---
    data['SIRET'] = (re.search(r"SIRET[:\s]*(\d{3}\s?\d{3}\s?\d{3}\s?\d{5})", texte, re.I) or [None, None])[1]
    
    # --- Période (Mois vs Annuel) ---
    # Extraction des valeurs du mois[cite: 1, 3, 7]
    data['m_brut'] = clean_float((re.search(r"(?:Mensuel|Mois).*?BRUT.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    data['m_heures'] = clean_float((re.search(r"Hrs trav\..*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    data['m_patronale'] = clean_float((re.search(r"Part Patronale.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    
    # Extraction des cumuls annuels[cite: 2, 6, 10]
    data['c_brut'] = clean_float((re.search(r"Annuel.*?Brut.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    data['c_heures'] = clean_float((re.search(r"Annuel.*?Heures.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])
    data['c_patronale'] = clean_float((re.search(r"Annuel.*?Ch\.\s?patronales.*?(\d[\d\s,.]*\d)", texte, re.I | re.S) or [None, "0"])[1])

    # --- Congés[cite: 1, 6, 8] ---
    cp_reste = re.search(r"Reste.*?(\d[\d\s,.]*\d)", texte, re.I | re.S)
    data['solde_conges'] = clean_float(cp_reste.group(1)) if cp_reste else 0.0

    return data

def verifier_audite(d):
    alertes = []
    
    # 1. Test de cohérence des Cumuls[cite: 2, 6, 9]
    if d['c_brut'] > 0:
        if d['m_brut'] > d['c_brut']:
            alertes.append("❌ Erreur de cumul : Le brut du mois est supérieur au brut annuel.")
        
        # Un mois ne peut pas représenter plus de 100% de l'année (test de base)
        ratio_brut = (d['m_brut'] / d['c_brut']) * 100
        if ratio_brut > 20: # Alerte si un seul mois fait plus de 20% de l'année hors primes
            alertes.append(f"⚠️ Ratio Brut : Le mois représente {ratio_brut:.1f}% de l'année. Vérifiez les primes.")

    # 2. Test des Heures[cite: 1, 7, 10]
    if d['m_heures'] > 200: # Seuil légal haut habituel
        alertes.append(f"⚠️ Volume d'heures élevé ({d['m_heures']}h). Vérifiez les heures supplémentaires.")
    
    # 3. Test Charges Patronales[cite: 2, 3, 6]
    if d['m_patronale'] > 0:
        ratio_patronal = (d['m_patronale'] / d['m_brut']) if d['m_brut'] > 0 else 0
        if not (0.20 <= ratio_patronal <= 0.55):
            alertes.append(f"❌ Ratio charges patronales suspect ({ratio_patronal:.1%}). Attendu entre 25% et 50%.")

    # 4. Test Congés[cite: 5, 8]
    if d['solde_conges'] > 60:
        alertes.append(f"⚠️ Solde de congés inhabituel ({d['solde_conges']} jours).")

    return alertes

# --- Interface ---
st.title("🛡️ Audit Profond de Fiche de Paie")
st.markdown("Vérification mathématique des cumuls et des ratios de cotisations.")

txt = st.text_area("Collez le contenu textuel ici :", height=300)

if txt:
    data = extraire_donnees_completes(txt)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Données Extraites")
        st.write(f"**Brut du mois :** {data['m_brut']} €[cite: 1, 3]")
        st.write(f"**Cumul Brut annuel :** {data['c_brut']} €[cite: 6, 10]")
        st.write(f"**Heures travaillées :** {data['m_heures']} h[cite: 7]")
        st.write(f"**Solde Congés :** {data['solde_conges']} j")
        st.write(f"**Charges Patronales :** {data['m_patronale']} €[cite: 4, 8]")

    with col2:
        st.subheader("🚩 Analyse de Cohérence")
        rapport = verifier_audite(data)
        if not rapport:
            st.success("Cohérence mathématique validée sur les points analysés.")
        else:
            for r in rapport:
                st.write(r)

    # Tableau comparatif Mois vs Année
    st.subheader("📈 Comparatif Mensuel / Annuel")
    df = pd.DataFrame({
        'Indicateur': ['Salaire Brut', 'Heures', 'Charges Pat.'],
        'Mensuel': [data['m_brut'], data['m_heures'], data['m_patronale']],
        'Annuel (Cumul)': [data['c_brut'], data['c_heures'], data['c_patronale']]
    })
    st.dataframe(df, use_container_width=True)
