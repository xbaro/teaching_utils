from __future__ import annotations

import csv
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

from github import Auth, Github, GithubException

from teaching_utils.config import settings


ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS_DIR = ROOT / "_data" / "sd" / "26" / "pr1" / "out" / "submissions"
OUTPUT_DIR = ROOT / "_data" / "sd" / "26" / "pr1" / "cross_testing"
REPORT_PATH = ROOT / "_data" / "sd" / "26" / "pr1" / "cross_testing_report.md"
REPORT_B_PATH = ROOT / "_data" / "sd" / "26" / "pr1" / "out" / "reportB.csv"
REPORT_C_PATH = ROOT / "_data" / "sd" / "26" / "pr1" / "out" / "reportC.csv"
GITHUB_ORG = os.environ.get("GITHUB_ORG", "SoftwareDistribuitUB-2026")

GROUP_RE = re.compile(r"practica-1-([bc]\d+)", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"\[(.*?)\]")
HEADING_GROUP_PATTERNS = [
    re.compile(r"PROVA\s+\d+\s*\(([BC]\d+)\)", re.IGNORECASE),
    re.compile(r"Grup Avaluat:?\s*([BC]\d+)", re.IGNORECASE),
    re.compile(r"Tested Group:?\s*([BC]\d+)", re.IGNORECASE),
    re.compile(r"Proves realitzades\s*[—-]\s*Grup\s*([BC]\d+)", re.IGNORECASE),
    re.compile(r"^###\s*GRUP\s*\(([BC]\d+)\)\s*###$", re.IGNORECASE),
    re.compile(r"^([BC]\d+)\s*:\s*$", re.IGNORECASE),
    re.compile(r"avaluat\s+al\s+grup\s+([BC]\d+)", re.IGNORECASE),
]

CRITERIA = [
    ("server_start", "Servidor: arrencada i registre"),
    ("server_announce", "Servidor: announce/configuracio"),
    ("server_search", "Servidor: cerca"),
    ("server_download", "Servidor: descarrega 1 client"),
    ("server_multi", "Servidor: descarrega multi-client"),
    ("client_register", "Client: connexio i registre"),
    ("client_announce", "Client: announce/configuracio"),
    ("client_search", "Client: cerca"),
    ("client_transfer", "Client: transferencia"),
]

INTERESTING_DOCS = {
    "testreport.md",
    "testreport2.md",
    "testreport3.md",
    "testreport4.md",
    "testreport5.md",
    "testreport6.md",
    "readme.md",
    "memoria.md",
    "pr_description.md",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name_key(value: str) -> str:
    lowered = (value or "").casefold()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def normalize_submission_person_name(value: str) -> str:
    key = normalize_name_key(value)
    return re.sub(r"\d+$", "", key)


def checkbox_to_bool(line: str) -> bool | None:
    match = CHECKBOX_RE.search(line)
    if not match:
        return None
    marker = match.group(1).strip().casefold()
    if marker in {"x", "check", "checked"}:
        return True
    if marker == "":
        return False
    if "x" in marker or "check" in marker:
        return True
    return False


def criterion_from_line(line: str) -> str | None:
    lowered = normalize_text(line).casefold()
    if "servidor" in lowered or "server" in lowered:
        if "multi-client" in lowered or "multiple candidate" in lowered:
            return "server_multi"
        if "amb un client" in lowered or "download negotiation" in lowered or "descarrega de fitxers **amb un client**" in lowered:
            return "server_download"
        if "cerca" in lowered or "search" in lowered:
            return "server_search"
        if "configuraci" in lowered or "announce" in lowered or "share" in lowered:
            return "server_announce"
        if "arranca" in lowered or "starts" in lowered or "identificador" in lowered or "registration" in lowered:
            return "server_start"
    if "client" in lowered:
        if "transfer" in lowered or "requester mode" in lowered or "source mode" in lowered or "rebent els que ha" in lowered:
            return "client_transfer"
        if "cerca" in lowered or "search" in lowered:
            return "client_search"
        if "configuraci" in lowered or "announce" in lowered:
            return "client_announce"
        if "connecta" in lowered or "register" in lowered or "s'hi registra" in lowered:
            return "client_register"
    return None


def safe_read(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def find_group_docs() -> dict[str, dict[Path, list[Path]]]:
    grouped: dict[str, dict[Path, list[Path]]] = defaultdict(lambda: defaultdict(list))
    for submission_dir in sorted(SUBMISSIONS_DIR.iterdir()):
        if not submission_dir.is_dir():
            continue
        for file_path in submission_dir.rglob("*.md"):
            if file_path.name.lower() not in INTERESTING_DOCS:
                continue
            match = GROUP_RE.search(str(file_path.relative_to(submission_dir)).replace("\\", "/"))
            if not match:
                continue
            group_code = match.group(1).upper()
            if not group_code.startswith(("B", "C")):
                continue
            grouped[group_code][file_path.parent].append(file_path)
    return grouped


def choose_root(root_map: dict[Path, list[Path]]) -> tuple[Path, list[Path]]:
    def score(item: tuple[Path, list[Path]]) -> tuple[int, int, int]:
        root, files = item
        names = {file_path.name.lower() for file_path in files}
        return (
            100 if "testreport.md" in names else 0,
            50 if "memoria.md" in names else 0,
            20 if "readme.md" in names else 0,
        ), len(files), -len(str(root))

    root, files = max(root_map.items(), key=score)
    return root, sorted(files)


def _finalize_members(candidates: list[dict[str, str]], source_hint: str) -> tuple[list[dict[str, str]], str | None]:
    unique: list[dict[str, str]] = []
    for candidate in candidates:
        if normalize_name_key(candidate["name"]) in {normalize_name_key(item["name"]) for item in unique}:
            continue
        unique.append(candidate)

    warning = None
    if len(unique) > 2:
        warning = (
            f"S'han detectat {len(unique)} membres al document ({source_hint}). "
            "Probablement hi ha files de taules de proves creuades o entrades duplicades; "
            "s'han conservat només els 2 primers membres del bloc principal del grup."
        )
    return unique[:2], warning


def parse_members(text: str, group_code: str | None = None) -> tuple[list[dict[str, str]], str | None]:
    members: list[dict[str, str]] = []
    lines = text.splitlines()
    normalized_group = (group_code or "").upper()
    include_blank_row = False

    for index, line in enumerate(lines):
        lowered = line.casefold()
        if "github" in lowered and "|" in line:
            table_lines = []
            for table_line in lines[index:index + 8]:
                if "|" not in table_line:
                    break
                table_lines.append(table_line)
            for row in table_lines[2:]:
                parts = [part.strip() for part in row.strip().strip("|").split("|")]
                if len(parts) < 2:
                    continue
                if any(
                    token in normalize_text(part).casefold()
                    for part in parts
                    for token in ["components", "usuari github", "nombre de github", "members", "github user"]
                ):
                    continue
                if len(parts) >= 3:
                    group_or_name, name, github = parts[0], parts[1], parts[2]
                else:
                    group_or_name, name, github = parts[0], parts[0], parts[1]

                group_candidate = group_or_name.strip().upper()
                if normalized_group:
                    if re.fullmatch(r"[BC]\d+", group_candidate):
                        include_blank_row = group_candidate == normalized_group
                        if not include_blank_row:
                            continue
                    elif group_candidate == "":
                        if not include_blank_row:
                            continue
                    elif group_candidate == "EQUIP":
                        include_blank_row = True

                if "grup" in group_or_name.casefold() or re.fullmatch(r"[BC]\d+|Equip", group_or_name.strip(), re.IGNORECASE):
                    member_name = name
                elif group_or_name.strip() == "":
                    member_name = name
                else:
                    member_name = group_or_name
                    github = parts[1] if len(parts) == 2 else github
                github = github.strip().lstrip("@")
                if member_name and github and normalize_name_key(member_name) not in {normalize_name_key(item["name"]) for item in members}:
                    members.append({"name": normalize_text(member_name), "github": normalize_text(github)})
            if members:
                return _finalize_members(members, "taula amb camp GitHub")

    bullet_re = re.compile(r"Membre\s*\d+.*?:\s*(.*?)\s*-\s*GitHub:\s*(.+)", re.IGNORECASE)
    for line in lines[:40]:
        match = bullet_re.search(line)
        if match:
            members.append({"name": normalize_text(match.group(1)), "github": normalize_text(match.group(2).lstrip("@"))})
    if members:
        return _finalize_members(members, "llista de membres al README")

    pair_re = re.compile(r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|")
    for index, line in enumerate(lines):
        if "Nombre de GitHub" in line or "Usuari GitHub" in line:
            for row in lines[index + 2:index + 8]:
                match = pair_re.match(row.strip())
                if not match:
                    break
                name = normalize_text(match.group(1))
                github = normalize_text(match.group(2).lstrip("@"))
                if name and github:
                    members.append({"name": name, "github": github})
            break
    return _finalize_members(members, "taula simplificada de noms")


def extract_section(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    lowered = text.casefold()
    start_index = -1
    for pattern in start_patterns:
        idx = lowered.find(pattern.casefold())
        if idx != -1 and (start_index == -1 or idx < start_index):
            start_index = idx
    if start_index == -1:
        return ""
    end_index = len(text)
    tail = text[start_index + 1:]
    for pattern in end_patterns:
        idx = tail.casefold().find(pattern.casefold())
        if idx != -1:
            end_index = min(end_index, start_index + 1 + idx)
    return text[start_index:end_index]


def parse_self_evaluation(text: str) -> dict[str, bool | None]:
    section = extract_section(
        text,
        [
            "### La vostra pràctica",
            "## Status of Our Implementation",
            "En aquest apartat cal explicar l'estat inicial de la vostra pràctica",
        ],
        [
            "### Proves realitzades",
            "# Cross Tests",
            "## Summary Table",
            "### Proves realitzades —",
            "## Reported Issues Before Cross Testing",
        ],
    )
    results = {criterion: None for criterion, _ in CRITERIA}
    for line in section.splitlines():
        value = checkbox_to_bool(line)
        if value is None:
            continue
        criterion = criterion_from_line(line)
        if criterion:
            results[criterion] = value
    return results


def parse_external_blocks(text: str, own_group: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    blocks: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        criteria = current.get("criteria", {})
        notes = [normalize_text(line) for line in current.get("notes", []) if normalize_text(line)]
        if criteria or notes:
            current["notes"] = notes[:8]
            blocks.append(current)
        current = None

    for raw_line in lines:
        line = raw_line.rstrip()
        matched_group = None
        for pattern in HEADING_GROUP_PATTERNS:
            match = pattern.search(line)
            if match:
                matched_group = match.group(1).upper()
                break
        if matched_group and matched_group != own_group:
            flush()
            current = {"target": matched_group, "criteria": {}, "notes": []}
            continue
        if not current:
            continue
        if line.startswith("#") and current["criteria"]:
            flush()
            continue
        criterion = criterion_from_line(line)
        value = checkbox_to_bool(line)
        if criterion and value is not None:
            current["criteria"][criterion] = value
            continue
        stripped = normalize_text(line)
        if stripped and not stripped.startswith("|"):
            current["notes"].append(stripped)
    flush()
    return blocks


def summarize_notes(notes: list[str], limit: int = 2) -> str:
    if not notes:
        return "Sense detall textual explícit."
    sentences: list[str] = []
    for note in notes:
        if normalize_text(note).casefold() in {
            "- __servidor__",
            "- __client__",
            "servidor",
            "client",
            "a més a més, caldrà explicar les proves fetes, els resultats obtinguts i si s'ha detectat errors o no.",
        }:
            continue
        for part in re.split(r"(?<=[.!?])\s+", note):
            part = normalize_text(part)
            if part and part not in sentences:
                sentences.append(part)
            if len(sentences) >= limit:
                return " ".join(sentences[:limit])
    return " ".join(sentences[:limit])


def load_csv_results(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    results: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return results
        for row in reader:
            if len(row) < 7:
                continue
            full_name = normalize_name_key(f"{row[1]} {row[0]}")
            results[full_name] = {
                "qualification": row[5],
                "feedback": row[6],
            }
    return results


def bool_symbol(value: bool | None) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "N/A"


def summarize_given_vs_received(given_block: dict[str, object] | None, received_blocks: list[dict[str, object]]) -> tuple[str, str]:
    def score(criteria: dict[str, bool]) -> str:
        positives = sum(1 for value in criteria.values() if value)
        total = len(criteria)
        if total == 0:
            return "N/A"
        return f"{positives}/{total}"

    given_score = score(given_block["criteria"]) if given_block else "N/A"
    merged: dict[str, bool] = {}
    for block in received_blocks:
        merged.update(block.get("criteria", {}))
    received_score = score(merged)
    return given_score, received_score


def extract_pr_summary(root: Path, files: list[Path]) -> list[str]:
    summaries: list[str] = []
    pr_file = next((file_path for file_path in files if file_path.name.lower() == "pr_description.md"), None)
    if pr_file:
        text = safe_read(pr_file)
        for line in text.splitlines():
            stripped = normalize_text(line.lstrip("-#* "))
            if stripped and stripped not in summaries and not stripped.lower().startswith("overview"):
                summaries.append(stripped)
            if len(summaries) >= 4:
                return summaries
    for file_path in files:
        text = safe_read(file_path)
        for line in text.splitlines():
            if "pull request" not in line.casefold():
                continue
            stripped = normalize_text(line)
            if stripped and stripped not in summaries:
                summaries.append(stripped)
            if len(summaries) >= 4:
                return summaries
    return summaries


def _github_client() -> Github | None:
    token = getattr(settings, "GITHUB_TOKEN", None)
    if not token or token == "invalid":
        return None
    try:
        auth = Auth.Token(token)
        return Github(auth=auth)
    except Exception:
        return None


def _find_repo_name_for_group(client: Github, group_code: str) -> str | None:
    group_lower = group_code.lower()
    candidates = [
        f"practica-1-{group_lower}",
        f"practica-1-{group_lower}-master",
        f"practica1-{group_lower}",
        f"practica1-{group_lower}-master",
    ]

    for candidate in candidates:
        full_name = f"{GITHUB_ORG}/{candidate}"
        try:
            repo = client.get_repo(full_name)
            if repo is not None:
                return repo.full_name
        except GithubException:
            continue

    try:
        query = f"org:{GITHUB_ORG} in:name practica-1-{group_lower}"
        search_result = client.search_repositories(query=query, sort="updated", order="desc")
        for repo in search_result:
            name_lower = repo.name.casefold()
            if group_lower in name_lower and "practica" in name_lower:
                return repo.full_name
    except Exception:
        return None

    return None


def fetch_group_prs(group_code: str) -> dict[str, object]:
    client = _github_client()
    if client is None:
        return {
            "repo": None,
            "items": [],
            "note": "No hi ha GITHUB_TOKEN vàlid a l'entorn; no es poden consultar PRs de GitHub.",
        }

    try:
        repo_name = _find_repo_name_for_group(client, group_code)
        if not repo_name:
            return {
                "repo": None,
                "items": [],
                "note": f"No s'ha trobat repositori GitHub per al grup {group_code} dins de {GITHUB_ORG}.",
            }

        repo = client.get_repo(repo_name)
        pulls = repo.get_pulls(state="all", sort="updated", direction="desc")
        items: list[dict[str, str]] = []
        count = 0
        for pr in pulls:
            state = "merged" if pr.merged_at else pr.state
            items.append(
                {
                    "number": str(pr.number),
                    "title": pr.title or "(sense títol)",
                    "state": state,
                    "author": pr.user.login if pr.user else "unknown",
                    "url": pr.html_url,
                    "updated": pr.updated_at.isoformat() if pr.updated_at else "",
                }
            )
            count += 1
            if count >= 8:
                break

        return {
            "repo": repo.full_name,
            "items": items,
            "note": "",
        }
    except Exception as exc:
        return {
            "repo": None,
            "items": [],
            "note": f"Error consultant GitHub PRs: {exc}",
        }
    finally:
        try:
            client.close()
        except Exception:
            pass


def build_alignment(group_code: str, received_blocks: list[dict[str, object]], pr_summary: list[str], csv_result: dict[str, str] | None) -> str:
    notes = [note for block in received_blocks for note in block.get("notes", [])]
    if csv_result and csv_result.get("qualification") == "1.00":
        base = "El lliurament actual passa els tests automàtics disponibles en aquest workspace."
    elif csv_result and csv_result.get("qualification") == "0.00":
        base = "El lliurament actual no passa els tests automàtics disponibles en aquest workspace."
    else:
        base = "No hi ha una correcció automàtica disponible en aquest workspace per validar l'estat final del codi."

    if not received_blocks:
        return base + " No hi ha prou evidència externa per saber si es van corregir punts reportats per altres grups."

    if pr_summary:
        return base + " Hi ha evidència documental de canvis al repositori via PR/descricpions de canvi, així que és plausible que part dels punts reportats s'hagin revisat."

    if any("solucion" in note.casefold() or "fix" in note.casefold() for note in notes):
        return base + " El text de les evidències apunta a correccions explícites d'algunes incidències detectades a la sessió."

    return base + " No es troba una evidència explícita de correcció dels punts reportats; només es pot contrastar amb el resultat actual del lliurament."


def copy_evidence(group_code: str, root: Path, files: list[Path], summary: dict[str, object]) -> None:
    group_dir = OUTPUT_DIR / group_code
    if group_dir.exists():
        shutil.rmtree(group_dir)
    group_dir.mkdir(parents=True, exist_ok=True)
    for file_path in files:
        destination = group_dir / file_path.name
        shutil.copy2(file_path, destination)
    (group_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (group_dir / "source_root.txt").write_text(str(root), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    docs_by_group = find_group_docs()
    report_b = load_csv_results(REPORT_B_PATH)
    report_c = load_csv_results(REPORT_C_PATH)
    report_lookup = {**report_b, **report_c}

    group_data: dict[str, dict[str, object]] = {}
    all_external_blocks: list[dict[str, object]] = []

    for group_code in sorted(docs_by_group):
        root, files = choose_root(docs_by_group[group_code])
        texts = {file_path.name: safe_read(file_path) for file_path in files}
        combined_text = "\n\n".join(texts.values())
        members = []
        members_warning = None
        for preferred in ("TestReport.md", "Memoria.md", "README.md"):
            for file_path in files:
                if file_path.name == preferred:
                    members, members_warning = parse_members(texts[file_path.name], group_code)
                    if members:
                        break
            if members:
                break

        self_eval = parse_self_evaluation(combined_text)
        external_blocks = parse_external_blocks(combined_text, group_code)
        for block in external_blocks:
            block["source"] = group_code
        all_external_blocks.extend(external_blocks)

        candidate_keys = set()
        for candidate_root in docs_by_group[group_code]:
            submission_name = candidate_root.relative_to(SUBMISSIONS_DIR).parts[0]
            base_name = submission_name.split("_assignsubmission_file")[0]
            candidate_keys.add(normalize_submission_person_name(base_name))
        csv_result = None
        for candidate_key in candidate_keys:
            if candidate_key in report_lookup:
                csv_result = report_lookup[candidate_key]
                break
        pr_from_docs = extract_pr_summary(root, files)
        pr_from_github = fetch_group_prs(group_code)

        group_data[group_code] = {
            "root": root,
            "files": files,
            "members": members,
            "members_warning": members_warning,
            "self_eval": self_eval,
            "given_blocks": external_blocks,
            "csv_result": csv_result,
            "pr_summary": pr_from_docs,
            "pr_github": pr_from_github,
        }

    received_by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    for block in all_external_blocks:
        received_by_group[block["target"]].append(block)

    # --- global summary stats ---
    total_groups = len(group_data)
    groups_with_auto = sum(1 for d in group_data.values() if d["csv_result"])
    groups_with_member_warning = sum(1 for d in group_data.values() if d["members_warning"])
    groups_with_prs = sum(
        1 for d in group_data.values()
        if d["pr_github"].get("items")
    )
    groups_b = sum(1 for g in group_data if g.upper().startswith("B"))
    groups_c = sum(1 for g in group_data if g.upper().startswith("C"))

    report_lines = [
        "# Cross Testing Report",
        "",
        "Informe agregat generat a partir de la documentació de proves creuades trobada als lliuraments dels grups B i C.",
        "",
        "## Resum global",
        "",
        f"| Indicador | Valor |",
        f"|---|---|",
        f"| Total de grups analitzats | {total_groups} ({groups_b} grup B, {groups_c} grup C) |",
        f"| Grups amb resultat automàtic disponible | {groups_with_auto} / {total_groups} |",
        f"| Grups amb Pull Requests detectats a GitHub | {groups_with_prs} / {total_groups} |",
        f"| Grups amb incidència en el nombre de membres | {groups_with_member_warning} / {total_groups} |",
        "",
        "---",
        "",
    ]

    for group_code in sorted(group_data):
        data = group_data[group_code]
        received_blocks = received_by_group.get(group_code, [])
        csv_result = data["csv_result"]
        pr_items = data["pr_github"].get("items", [])
        alignment = build_alignment(group_code, received_blocks, pr_items or data["pr_summary"], csv_result)

        members = data["members"] or [{"name": "No identificat a la documentació", "github": "N/A"}]
        members_warning = data.get("members_warning")
        self_eval = data["self_eval"]
        given_blocks = data["given_blocks"]

        report_lines.append(f"## {group_code}")
        report_lines.append("")
        report_lines.append("### Membres")
        report_lines.append("")
        for member in members:
            report_lines.append(f"- {member['name']} ({member['github']})")
        if members_warning:
            report_lines.append(f"- Avis membres: {members_warning}")
        report_lines.append("")

        report_lines.append("### Resum de l'avaluació del grup")
        report_lines.append("")
        report_lines.append("| Aspecte | Self | Rebuda d'altres grups |")
        report_lines.append("|---|---|---|")
        for criterion, label in CRITERIA:
            received_values = [block.get("criteria", {}).get(criterion) for block in received_blocks if criterion in block.get("criteria", {})]
            if received_values:
                positives = sum(1 for value in received_values if value)
                received_summary = f"{positives}/{len(received_values)}" if len(received_values) > 1 else bool_symbol(received_values[0])
            else:
                received_summary = "N/A"
            report_lines.append(f"| {label} | {bool_symbol(self_eval.get(criterion))} | {received_summary} |")
        report_lines.append("")

        report_lines.append("### Resum de les avaluacions creuades")
        report_lines.append("")
        report_lines.append("| Grup comparat | Avaluació feta per aquest grup | Avaluació rebuda d'aquest grup | Notes |")
        report_lines.append("|---|---|---|---|")
        compared_groups = sorted({block["target"] for block in given_blocks} | {block["source"] for block in received_blocks})
        if compared_groups:
            for other_group in compared_groups:
                given_block = next((block for block in given_blocks if block["target"] == other_group), None)
                reciprocal_blocks = [block for block in received_blocks if block["source"] == other_group]
                given_score, received_score = summarize_given_vs_received(given_block, reciprocal_blocks)
                notes_parts = []
                if given_block:
                    notes_parts.append("Feta: " + summarize_notes(given_block.get("notes", []), limit=1))
                if reciprocal_blocks:
                    notes_parts.append("Rebuda: " + summarize_notes([note for block in reciprocal_blocks for note in block.get("notes", [])], limit=1))
                report_lines.append(f"| {other_group} | {given_score} | {received_score} | {' '.join(notes_parts) if notes_parts else 'Sense detall creuat explícit.'} |")
        else:
            report_lines.append("| N/A | N/A | N/A | No hi ha evidències de proves creuades amb altres grups. |")
        report_lines.append("")

        report_lines.append("### Pull Requests")
        report_lines.append("")
        if data["pr_github"].get("repo"):
            report_lines.append(f"Repositori: {data['pr_github']['repo']}")
            report_lines.append("")
        if pr_items:
            for item in pr_items:
                report_lines.append(
                    f"- PR #{item['number']} [{item['state']}] ({item['author']}): {item['title']} - {item['url']}"
                )
        else:
            note = data["pr_github"].get("note", "")
            if note:
                report_lines.append(f"- {note}")
            elif data["pr_summary"]:
                report_lines.append("- No s'han pogut recuperar PRs de GitHub; evidència local trobada:")
                for item in data["pr_summary"]:
                    report_lines.append(f"- {item}")
            else:
                report_lines.append("- No s'ha trobat cap PR al repositori GitHub del grup.")
        report_lines.append("")

        report_lines.append("### Alineació del codi amb les avaluacions")
        report_lines.append("")
        if csv_result:
            report_lines.append(f"Resultat automàtic disponible: qualificació {csv_result['qualification']}.")
            report_lines.append("")
        report_lines.append(alignment)
        report_lines.append("")

        evidence_summary = {
            "group": group_code,
            "members": members,
            "members_warning": members_warning,
            "root": str(data["root"]),
            "files": [str(path) for path in data["files"]],
            "self_eval": self_eval,
            "given_blocks": given_blocks,
            "received_blocks": received_blocks,
            "pr_summary": data["pr_summary"],
            "pr_github": data["pr_github"],
            "csv_result": csv_result,
            "alignment": alignment,
        }
        copy_evidence(group_code, data["root"], data["files"], evidence_summary)

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()