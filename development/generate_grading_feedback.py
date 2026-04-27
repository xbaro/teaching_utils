from __future__ import annotations

import csv
import io
from pathlib import Path


CSV_PATH = Path("_data/sd/26/pr1/grading.csv")
OUT_PATH = Path("_data/sd/26/pr1/grading_feedback.md")


def ffloat(v):
    try:
        return float(str(v).strip())
    except Exception:
        return None


def fint(v):
    try:
        return int(str(v).strip())
    except Exception:
        return None


def yes(v):
    return str(v).strip() == "1"


def no(v):
    return str(v).strip() == "0"


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(CSV_PATH.read_text(encoding="utf-8-sig"))))

    lines: list[str] = []
    lines.append("# Retorn Personalitzat de la Pràctica 1")
    lines.append("")
    lines.append(
        "Aquest document recull un retorn individual sintetitzat a partir de les evidències tècniques analitzades."
    )
    lines.append("")

    for r in rows:
        if (r.get("Nom", "") or "").strip().upper() == "PESOS":
            continue

        nom = (r.get("Nom", "") or "").strip()
        cognoms = (r.get("Cognoms", "") or "").strip()
        niub = (r.get("Número ID", "") or "").strip()
        grup = (r.get("Grup", "") or "").strip()
        login = (r.get("GitHub Login", "") or "").strip()

        c = {f"C{i}": r.get(f"C{i}", "") for i in range(1, 9)}
        javadoc = ffloat(r.get("JavaDoc", ""))
        compila = ffloat(r.get("Compila", ""))
        tests = fint(r.get("#Tests", ""))
        passa = fint(r.get("#Passa", ""))
        coverage = (r.get("%Coverage", "") or "").strip()
        prs = fint(r.get("#PR", ""))
        commits = fint(r.get("#commits", ""))
        bal = ffloat(r.get("GH_Balance", ""))
        cont = ffloat(r.get("Continuitat", ""))
        validation = ffloat(r.get("Validation", ""))
        vres = ffloat(r.get("Validation Result", ""))
        memoria = (r.get("Memòria", "") or "").strip()

        lines.append(f"## {nom} {cognoms} ({niub})")
        lines.append("")
        lines.append(f"- Grup de treball detectat: {grup if grup else 'No constatat'}.")
        if login:
            lines.append(f"- Identificador de repositori utilitzat: {login}.")
        else:
            lines.append(
                "- No s'ha pogut consolidar automàticament l'identificador de repositori; convé verificar la traçabilitat del lliurament."
            )

        strengths = []
        improvements = []

        if yes(c["C1"]):
            strengths.append("modelització de comportament amb mecanismes de màquina d'estats")
        else:
            improvements.append("formalitzar millor la màquina d'estats per reduir ambigüitats de flux")

        if yes(c["C2"]):
            strengths.append("control de timeout de sockets per evitar bloquejos")
        else:
            improvements.append("incorporar gestió explícita de timeout a la comunicació per sockets")

        if yes(c["C3"]):
            strengths.append("tractament d'errors de comunicació orientat a robustesa")
        else:
            improvements.append("reforçar el tractament d'excepcions de xarxa i casos límit")

        if yes(c["C4"]):
            strengths.append("gestió concurrent al servidor")
        else:
            improvements.append("millorar la concurrència del servidor en escenaris multi-client")

        if yes(c["C5"]):
            strengths.append("ús de patrons de seguretat de fils en estructures compartides")
        else:
            improvements.append("revisar la sincronització i la seguretat de fils de les estructures compartides")

        if yes(c["C6"]):
            strengths.append("gestió funcional del catàleg de fitxers")
        else:
            improvements.append("fer més robusta la gestió del llistat i estat dels fitxers disponibles")

        if yes(c["C7"]):
            strengths.append("implementació del protocol de chunks coherent amb la transferència")
        else:
            improvements.append("revisar la implementació del protocol de chunks (fraccionament i reconstrucció)")

        if yes(c["C8"]):
            strengths.append("gestió de registre de client integrada al flux de connexió")
        else:
            improvements.append("millorar la gestió de registre i identificació de clients")

        if strengths:
            lines.append("- Punts tècnics consolidats: " + "; ".join(strengths) + ".")
        if improvements:
            lines.append("- Aspectes prioritaris de millora del codi: " + "; ".join(improvements) + ".")

        quality_msgs = []
        if javadoc is not None:
            if javadoc >= 1.0:
                quality_msgs.append("documentació tècnica molt ben integrada al codi")
            elif javadoc >= 0.5:
                quality_msgs.append("documentació present però encara millorable en cobertura i precisió")
            else:
                quality_msgs.append("documentació tècnica insuficient; convé ampliar comentaris de disseny i contractes")

        if compila is not None:
            if compila >= 1.0:
                quality_msgs.append("execució/compilació consistent en el circuit automàtic")
            elif compila >= 0.5:
                quality_msgs.append("compilació parcial o amb incidències puntuals en execució")
            else:
                quality_msgs.append("incidències de compilació o execució que cal estabilitzar")

        if tests is not None and tests > 0:
            if passa is None:
                quality_msgs.append(f"ús de proves detectat (aprox. {tests} casos)")
            else:
                quality_msgs.append(f"resultat de proves automàtiques: {passa}/{tests} casos superats")
        else:
            quality_msgs.append(
                "no hi ha evidència clara d'execució de bateria de proves en el registre automàtic"
            )

        if coverage and coverage.upper() != "N/A":
            quality_msgs.append(f"cobertura informada: {coverage}")
        else:
            quality_msgs.append("cobertura no reportada; seria recomanable incorporar-la per validar la qualitat de test")

        if memoria:
            quality_msgs.append("memòria lliurada amb contingut registrat")
        else:
            quality_msgs.append("cal completar la memòria per reforçar la justificació de decisions de disseny")

        lines.append("- Qualitat i verificació: " + "; ".join(quality_msgs) + ".")

        gh_msgs = []
        if commits is not None:
            gh_msgs.append(f"activitat de commits registrada: {commits}")
        else:
            gh_msgs.append("activitat de commits no identificada automàticament")

        if prs is not None:
            gh_msgs.append(f"participació en pull requests: {prs}")
        else:
            gh_msgs.append("sense evidència de pull requests personals en el registre")

        if bal is not None:
            if bal >= 1.0:
                gh_msgs.append("repartiment de contribució equilibrat dins del grup")
            elif bal >= 0.9:
                gh_msgs.append("bona contribució individual, amb marge d'equilibri addicional")
            elif bal >= 0.5:
                gh_msgs.append("participació moderada; convé reforçar el pes tècnic individual")
            else:
                gh_msgs.append("contribució desequilibrada o poc visible en el control de versions")

        if cont is not None:
            if cont >= 1.0:
                gh_msgs.append("treball sostingut al llarg del període de pràctiques")
            elif cont >= 0.5:
                gh_msgs.append("continuïtat parcial; es recomana una distribució temporal més estable")
            else:
                gh_msgs.append("activitat concentrada al final; convé planificar iteracions més regulars")

        lines.append("- Traçabilitat i dinàmica de treball: " + "; ".join(gh_msgs) + ".")

        val_msgs = []
        if validation is not None and validation >= 1.0:
            val_msgs.append("lliurament de validació present i descomprimible correctament")
        else:
            val_msgs.append("no s'ha pogut validar correctament el paquet lliurat de validació")

        if vres is None:
            val_msgs.append("sense evidència suficient de resposta a la prova de validació")
        elif vres < 0:
            val_msgs.append("no s'ha localitzat resposta explícita a la pregunta de validació")
        elif vres >= 1.0:
            val_msgs.append("resposta coherent amb l'enunciat i alineada amb indicis de canvis al codi")
        elif vres >= 0.75:
            val_msgs.append("resposta coherent, però la traça en codi és parcial o no prou concloent")
        else:
            val_msgs.append("resposta detectada però amb coherència tècnica limitada respecte a l'enunciat")

        lines.append("- Prova de validació: " + "; ".join(val_msgs) + ".")

        lines.append(
            "- Recomanació de progrés: en la següent iteració, prioritza estabilitat de comunicació, verificació automatitzada i justificació tècnica explícita de les decisions implementades."
        )
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {OUT_PATH}")


if __name__ == "__main__":
    main()
