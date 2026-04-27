"""Generate grading_feedback_v2.md: personalised prose feedback per student."""
from __future__ import annotations

import csv
import io
from pathlib import Path


CSV_PATH = Path("_data/sd/26/pr1/grading.csv")
OUT_PATH = Path("_data/sd/26/pr1/grading_feedback_v2.md")


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


# ---------------------------------------------------------------------------
# Prose builders
# ---------------------------------------------------------------------------

def build_code_paragraph(c: dict) -> str:
    """Return a prose paragraph about C1-C8 indicators."""
    ok = [k for k in c if yes(c[k])]
    bad = [k for k in c if not yes(c[k])]
    n_ok = len(ok)

    # (article, label) — article used when introducing the concept
    labels = {
        "C1": ("la", "màquina d'estats"),
        "C2": ("la", "gestió de timeout als sockets"),
        "C3": ("el", "tractament d'excepcions de xarxa"),
        "C4": ("el", "multi-threading al servidor"),
        "C5": ("l'", "ús d'estructures thread-safe"),
        "C6": ("la", "gestió del catàleg de fitxers"),
        "C7": ("el", "protocol de transferència per chunks"),
        "C8": ("el", "flux de registre del client"),
    }

    improvements = {
        "C1": "caldria formalitzar millor la màquina d'estats per eliminar ambigüitats de flux",
        "C2": "incorporar la gestió de timeout als sockets evitaria bloquejos indefinits en la comunicació",
        "C3": "reforçar el tractament d'excepcions de xarxa faria la solució molt més robusta davant de fallades",
        "C4": "el servidor hauria de gestionar múltiples clients de manera concurrent per ser funcional en entorns reals",
        "C5": "les estructures compartides entre fils haurien de ser thread-safe per evitar condicions de carrera",
        "C6": "la gestió del catàleg de fitxers disponibles necessita ser més completa i consistent",
        "C7": "la transferència de fitxers hauria d'implementar el protocol de chunks per suportar arxius grans",
        "C8": "el flux de registre del client al servidor és una peça central del protocol i hauria d'estar ben integrat",
    }

    ok_labels = [labels[k] for k in ok]   # list of (art, label)
    bad_msgs = [improvements[k] for k in bad]

    def art_label(art, lbl):
        return art + lbl if art.endswith("'") else art + " " + lbl

    def join_art_labels(items):
        """Join (article, label) tuples in Catalan: 'la X, la Y i la Z'."""
        parts = [art_label(a, l) for a, l in items]
        if len(parts) == 1:
            return parts[0]
        return ", ".join(parts[:-1]) + " i " + parts[-1]

    if n_ok == 8:
        intro = (
            "Des del punt de vista de l'arquitectura i del protocol, la solució és completa: "
            "has implementat tots els aspectes avaluats, incloent "
            + join_art_labels(ok_labels) + "."
        )
        return intro

    if n_ok == 0:
        intro = (
            "La solució presentada no evidencia cap dels indicadors de qualitat avaluats. "
            "Cal un replantejament profund de l'arquitectura: "
            + "; ".join(bad_msgs) + "."
        )
        return intro

    # Partial: describe strengths and improvements
    parts = []
    if ok_labels:
        parts.append(
            "Has implementat correctament "
            + join_art_labels(ok_labels) + "."
        )
    if bad_msgs:
        if len(bad_msgs) == 1:
            parts.append(
                "Tot i això, " + bad_msgs[0][0].lower() + bad_msgs[0][1:] + "."
            )
        else:
            parts.append(
                "Tanmateix, hi ha aspectes que cal millorar: "
                + "; ".join(bad_msgs) + "."
            )
    return " ".join(parts)


def build_quality_paragraph(javadoc, compila, tests, passa, memoria) -> str:
    parts = []

    # Compilation
    if compila is not None:
        if compila >= 1.0:
            parts.append("El codi compila i s'executa sense errors en el circuit automàtic")
        elif compila >= 0.5:
            parts.append("Hi ha incidències puntuals de compilació o execució que cal resoldre")
        else:
            parts.append("El codi presenta problemes de compilació o execució que impedeixen l'avaluació automàtica")

    # Tests
    if tests is not None and tests > 0:
        if passa is not None:
            ratio = passa / tests if tests else 0
            if ratio >= 0.9:
                parts.append(
                    f"la bateria de proves automàtiques mostra uns resultats excel·lents: {passa}/{tests} casos superats"
                )
            elif ratio >= 0.5:
                parts.append(
                    f"la bateria de proves supera {passa}/{tests} casos, però hi ha marge de millora en la cobertura funcional dels tests"
                )
            else:
                parts.append(
                    f"la bateria de proves registra {passa}/{tests} casos superats, el que indica que parts de la funcionalitat no estan prou consolidades"
                )
        else:
            parts.append(f"s'han detectat proves ({tests} casos) però sense resultat clar")
    else:
        parts.append("no hi ha evidència d'execució de proves automàtiques, cosa que dificulta verificar la correcció funcional")

    # JavaDoc
    if javadoc is not None:
        if javadoc >= 1.0:
            parts.append("la documentació del codi és acurada i cobreix bé els contractes i decisions de disseny")
        elif javadoc >= 0.5:
            parts.append("la documentació és present però incompleta; caldria ampliar les descripcions de les parts més complexes")
        else:
            parts.append("la documentació tècnica és insuficient i caldria incloure comentaris que expliquin les decisions de disseny")

    # Memoria
    if memoria:
        parts.append("la memòria acompanya el lliurament amb contingut rellevant")
    else:
        parts.append("falta la memòria o no té contingut registrat, que és on has de justificar les decisions arquitectòniques preses")

    if not parts:
        return ""

    # Join naturally
    first = parts[0][0].upper() + parts[0][1:]
    rest = [p[0].lower() + p[1:] for p in parts[1:]]
    return first + ("; " if rest else "") + "; ".join(rest) + "."


def build_github_paragraph(commits, prs, bal, cont) -> str:
    parts = []

    if commits is not None:
        if commits >= 20:
            parts.append(f"Has fet {commits} commits, la qual cosa reflecteix una participació activa en el control de versions")
        elif commits >= 8:
            parts.append(f"El teu historial de {commits} commits és raonable")
        elif commits >= 1:
            parts.append(f"Amb {commits} commits al repositori, la teva traça individual és limitada")
        else:
            parts.append("No s'ha registrat activitat de commits associada al teu perfil")
    else:
        parts.append("No s'ha pogut identificar activitat de commits associada al teu compte")

    if prs is not None:
        if prs >= 5:
            parts.append(f"has participat activament en {prs} pull requests, demostrant bones pràctiques de revisió de codi")
        elif prs >= 1:
            parts.append(f"has participat en {prs} pull request(s)")
        else:
            parts.append("no hi ha evidència de pull requests individuals")
    else:
        parts.append("no s'ha registrat participació en pull requests")

    if bal is not None:
        if bal >= 1.0:
            parts.append("la contribució dins del grup és equilibrada")
        elif bal >= 0.9:
            parts.append("la teva contribució individual és bona, tot i que podria ser lleugerament més equilibrada respecte als companys")
        elif bal >= 0.5:
            parts.append("la contribució és moderada en relació al grup; convé reforçar el pes individual")
        else:
            parts.append("la teva contribució és notablement inferior a la de la resta del grup; cal implicar-se més activament")

    if cont is not None:
        if cont >= 1.0:
            parts.append("el treball ha estat ben distribuït al llarg de tot el període de la pràctica")
        elif cont >= 0.5:
            parts.append("la distribució temporal ha estat parcial; es recomana treballar de manera més sostinguda i no concentrar l'esforç al final")
        else:
            parts.append("l'activitat s'ha concentrat als darrers dies, el que indica una planificació millorable; en properes pràctiques intenta distribuir el treball de manera més regular")

    if not parts:
        return ""
    first = parts[0][0].upper() + parts[0][1:]
    rest = [p[0].lower() + p[1:] for p in parts[1:]]
    return first + ("; " if rest else "") + "; ".join(rest) + "."


def build_validation_paragraph(validation, vres) -> str:
    if validation is None or validation < 1.0:
        return (
            "No s'ha pogut processar correctament el lliurament de la prova de validació. "
            "Assegura't que el fitxer comprimit sigui vàlid i que inclogui una resposta explícita a la pregunta plantejada."
        )

    if vres is None:
        return (
            "El paquet de validació s'ha descomprimit correctament, però no s'ha trobat cap resposta a la pregunta de validació. "
            "Recorda que has d'incloure un fitxer de resposta identificable."
        )
    elif vres < 0:
        return (
            "El paquet de validació s'ha rebut, però no s'ha localitzat cap resposta explícita a la pregunta plantejada. "
            "En futures validacions, assegura't d'incloure un document de resposta clar i localitzable."
        )
    elif vres >= 1.0:
        return (
            "La resposta a la prova de validació és coherent amb l'enunciat i s'alinea amb les modificacions identificades al codi. "
            "Bon treball en aquesta part."
        )
    elif vres >= 0.75:
        return (
            "La resposta a la prova de validació és en general coherent, però la traça al codi és parcial o no del tot concloent. "
            "Caldria una argumentació una mica més sòlida."
        )
    else:
        return (
            "S'ha detectat una resposta a la prova de validació, però la coherència tècnica amb l'enunciat és limitada. "
            "Revisa bé la pregunta i assegura't que la resposta aborda els punts clau."
        )


def build_closing(n_ok: int, compila, tests, passa, cont) -> str:
    """Generate a personalised closing sentence."""
    ratio_tests = (passa / tests) if (tests and passa is not None) else None

    if n_ok >= 7 and compila is not None and compila >= 1.0 and ratio_tests is not None and ratio_tests >= 0.9:
        return (
            "En conjunt, és una pràctica ben resolta. Per a la següent entrega, centra els esforços en "
            "la documentació del codi i la memòria tècnica."
        )
    elif n_ok >= 5:
        return (
            "La pràctica té una base sòlida. Per a la propera iteració, consolida els punts de millora identificats "
            "i posa especial atenció a la verificació automàtica i a la justificació de les decisions de disseny."
        )
    elif n_ok >= 3:
        return (
            "Hi ha un esforç visible, però la solució és incompleta en aspectes rellevants del protocol. "
            "Et recomano revisar amb deteniment els punts de millora i assegurar-te que la funcionalitat bàsica és robusta "
            "abans d'afegir funcionalitats addicionals."
        )
    else:
        return (
            "Cal un replantejament important de la pràctica. Et recomano partir dels requeriments fonamentals del protocol, "
            "implementar-los de manera incremental i verificar cada pas abans de continuar."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    rows = list(csv.DictReader(io.StringIO(CSV_PATH.read_text(encoding="utf-8-sig"))))

    lines: list[str] = []
    lines.append("# Retorn Personalitzat de la Pràctica 1")
    lines.append("")
    lines.append(
        "Aquest document conté un retorn individual adreçat a cada estudiant, "
        "basat en l'anàlisi automàtica del codi, les proves, l'activitat de GitHub i la prova de validació."
    )
    lines.append("")

    for r in rows:
        if (r.get("Nom", "") or "").strip().upper() == "PESOS":
            continue

        nom = (r.get("Nom", "") or "").strip()
        cognoms = (r.get("Cognoms", "") or "").strip()
        niub = (r.get("Número ID", "") or "").strip()

        c = {f"C{i}": r.get(f"C{i}", "") for i in range(1, 9)}
        javadoc = ffloat(r.get("JavaDoc", ""))
        compila = ffloat(r.get("Compila", ""))
        tests = fint(r.get("#Tests", ""))
        passa = fint(r.get("#Passa", ""))
        prs = fint(r.get("#PR", ""))
        commits = fint(r.get("#commits", ""))
        bal = ffloat(r.get("GH_Balance", ""))
        cont = ffloat(r.get("Continuitat", ""))
        validation = ffloat(r.get("Validation", ""))
        vres = ffloat(r.get("Validation Result", ""))
        memoria = (r.get("Memòria", "") or "").strip()

        n_ok = sum(1 for k in c if yes(c[k]))

        lines.append(f"## {nom} {cognoms} ({niub})")
        lines.append("")

        # Paragraph 1: Code quality
        code_p = build_code_paragraph(c)
        lines.append(code_p)
        lines.append("")

        # Paragraph 2: Testing & documentation
        qual_p = build_quality_paragraph(javadoc, compila, tests, passa, memoria)
        if qual_p:
            lines.append(qual_p)
            lines.append("")

        # Paragraph 3: GitHub activity
        gh_p = build_github_paragraph(commits, prs, bal, cont)
        if gh_p:
            lines.append(gh_p)
            lines.append("")

        # Paragraph 4: Validation
        val_p = build_validation_paragraph(validation, vres)
        lines.append(val_p)
        lines.append("")

        # Closing
        closing = build_closing(n_ok, compila, tests, passa, cont)
        lines.append(closing)
        lines.append("")
        lines.append("---")
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {OUT_PATH}")


if __name__ == "__main__":
    main()
