import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import re
from dataclasses import dataclass

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
# 📥 EXTRACTION TEXTE (PDF + OCR)
# =========================
def extract_text(file):
    text = ""

    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t
    except:
        pass

    # OCR fallback
    if len(text) < 100:
        try:
            images = convert_from_path(file)
            for img in images:
                text += pytesseract.image_to_string(img)
        except:
            pass

    return text.lower()


# =========================
# 🧹 NETTOYAGE
# =========================
def clean(text):
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(",", ".")
    return text


# =========================
# 🔍 EXTRACTION VALEURS
# =========================
def extract(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            try:
                return float(m.group(1).replace(" ", ""))
            except:
                continue
    return 0.0


def extract_month(text):
    m = re.search(r"période\s*:\s*(\w+)", text)
    return m.group(1) if m else "unknown"


def extract_seniority(text):
    m = re.search(r"ancienneté\s*:\s*(\d+)\s*an[s]?\s*(\d+)?", text)
    if m:
        years = int(m.group(1))
        months = int(m.group(2)) if m.group(2) else 0
        return years + months / 12
    return 0.0


# =========================
# 🧠 PARSING BULLETIN
# =========================
def parse(text):
    text = clean(text)

    return Payslip(
        month=extract_month(text),
        brut=extract([
            r"salaire brut .*? (\d+\.\d+)",
            r"brut .*? (\d+\.\d+)"
        ], text),

        net=extract([
            r"net payé .*? (\d+\.\d+)",
            r"net a payer .*? (\d+\.\d+)"
        ], text),

        net_before_tax=extract([
            r"net .*? avant imp[oô]t .*? (\d+\.\d+)"
        ], text),

        tax=extract([
            r"pas .*? (\d+\.\d+)",
            r"imp[oô]t .*? (\d+\.\d+)"
        ], text),

        base_salary=extract([
            r"151\.67 .*? (\d+\.\d+)",
            r"salaire de base .*? (\d+\.\d+)"
        ], text),

        bonus=extract([
            r"prime .*? (\d+\.\d+)"
        ], text),

        seniority=extract_seniority(text)
    )


# =========================
# 👀 DEBUG AFFICHAGE
# =========================
def show(p):
    print(f"\n--- {p.month.upper()} ---")
    print(f"Brut: {p.brut}")
    print(f"Net avant impôt: {p.net_before_tax}")
    print(f"Impôt: {p.tax}")
    print(f"Net payé: {p.net}")
    print(f"Salaire base: {p.base_salary}")
    print(f"Prime: {p.bonus}")
    print(f"Ancienneté: {round(p.seniority, 2)}")


# =========================
# 🧠 ANALYSE METIER
# =========================
def analyze(payslips):
    results = {
        "coherence": [],
        "chronology": [],
        "financial": [],
        "risk_flags": []
    }

    # Chronologie
    for i in range(1, len(payslips)):
        if payslips[i].seniority < payslips[i-1].seniority:
            results["chronology"].append("Ancienneté incohérente")

    # Calculs
    for p in payslips:
        if abs((p.net_before_tax - p.tax) - p.net) > 5:
            results["financial"].append(f"Incohérence calcul net ({p.month})")

    # Variation
    for i in range(1, len(payslips)):
        prev = payslips[i-1]
        curr = payslips[i]

        if prev.brut == curr.brut and prev.net != curr.net:
            results["coherence"].append("Variation incohérente")

    # Prime suspecte
    bonuses = [p.bonus for p in payslips]
    if len(set(bonuses)) == 1 and bonuses[0] > 0:
        results["risk_flags"].append("Prime constante suspecte")

    return results


# =========================
# 📊 SCORING
# =========================
def compute_score(results):

    weights = {
        "coherence": 3,
        "chronology": 3,
        "financial": 3,
        "risk_flags": 1
    }

    score = 10

    for section, issues in results.items():
        score -= len(issues) * weights[section] * 0.5

    score = max(score, 0)

    if score >= 8:
        grade = "A - Fiable"
    elif score >= 6:
        grade = "B - Acceptable"
    elif score >= 4:
        grade = "C - Risqué"
    else:
        grade = "D - Refus"

    return score, grade


# =========================
# 📄 RAPPORT
# =========================
def generate_report(results, score, grade):
    print("\n===== RAPPORT D'ANALYSE =====")

    for section, issues in results.items():
        print(f"\n[{section.upper()}]")
        if issues:
            for i in issues:
                print("-", i)
        else:
            print("OK")

    print("\nScore :", round(score, 2), "/10")
    print("Classe :", grade)

    if grade.startswith("A"):
        print("Recommandation : ✅ Validation")
    elif grade.startswith("B"):
        print("Recommandation : ⚠️ Vérification complémentaire")
    else:
        print("Recommandation : ❌ Refus dossier")


# =========================
# 🚀 MAIN
# =========================
if __name__ == "__main__":

    files = [
        "CAMARA MOHAMED FEVRIER.pdf",
        "CAMARA MOHAMED MARS (1).pdf",
        "CAMARA MOHAMED AVRIL.pdf"
    ]

    payslips = []

    for f in files:
        print(f"\nLecture : {f}")
        text = extract_text(f)
        p = parse(text)
        show(p)
        payslips.append(p)

    results = analyze(payslips)
    score, grade = compute_score(results)

    generate_report(results, score, grade)
