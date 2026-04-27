"""
generate_grading_csv.py

Generates _data/sd/26/pr1/grading.csv from:
  - courseid_102337_participants.csv    (participants per group B/C)
  - reportB.csv / reportC.csv           (auto test results per NIUB)
  - auto_analysis/<GROUP>/code_evidence.json  (patterns, commits, PRs)
  - cross_testing/<GROUP>/summary.json  (members with names+logins)
  - GitHub API                          (Java sources for new patterns,
                                         JavaDoc ratio, commit dates,
                                         PR dates, user real names)

Output columns per participant:
  Nom, Cognoms, Número ID, Grups, Grup,
  C1..C8,   Nota_Codi,
  JavaDoc,  Memòria, Compila,
  #Tests,   #Passa,  %Coverage,
  #PR,      #commits,
  GH_Balance,  Continuitat

Row 2 (weights): weight for each C_i column, computed Nota_Codi.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
import shutil
import tarfile
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from github import Auth, Github, GithubException

from teaching_utils.config import settings

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "_data" / "sd" / "26" / "pr1"
PARTICIPANTS_CSV = DATA_DIR / "courseid_102337_participants.csv"
REPORT_B_CSV = DATA_DIR / "out" / "reportB.csv"
REPORT_C_CSV = DATA_DIR / "out" / "reportC.csv"
AUTO_ANALYSIS_DIR = DATA_DIR / "auto_analysis"
CROSS_TESTING_DIR = DATA_DIR / "cross_testing"
SUBMISSIONS_DIR = DATA_DIR / "out" / "submissions"
VALIDATION_DIR = ROOT / "_data" / "sd" / "26" / "ValPr1"
OUTPUT_CSV = DATA_DIR / "grading.csv"

GITHUB_ORG = "SoftwareDistribuitUB-2026"

# ── session schedule (B/C Thursday sessions, 2026) ────────────────────────────
# S0 Thu 12-Feb, S1 Thu 19-Feb, S2 Thu 26-Feb, S3 Thu 5-Mar, S4 Thu 12-Mar
SESSION_DATES = [
    date(2026, 2, 11),  # week of S0
    date(2026, 2, 18),  # week of S1
    date(2026, 2, 25),  # week of S2
    date(2026, 3, 4),   # week of S3
    date(2026, 3, 11),  # week of S4 (cross-testing)
]

# ── code checks and weights (must sum to 10) ──────────────────────────────────
CODE_CHECKS: list[tuple[str, str, float]] = [
    # (column_id, label, weight)
    ("C1", "Màquina d'estats", 2.0),
    ("C2", "Timeout sockets", 1.0),
    ("C3", "Control errors socket", 0.5),
    ("C4", "Multi-threading servidor", 2.0),
    ("C5", "Thread-safe (HashMap...)", 0.5),
    ("C6", "Gestió llistat fitxers", 1.0),
    ("C7", "Protocol chunks", 2.0),
    ("C8", "Gestió registre client", 1.0),
]
# Verify
_total_w = sum(w for _, _, w in CODE_CHECKS)
assert abs(_total_w - 10.0) < 1e-9, f"Weights sum {_total_w} != 10"

# ── new patterns for the code checks above ────────────────────────────────────
NEW_PATTERNS: dict[str, re.Pattern[str]] = {
    "C2_timeout": re.compile(r"setSoTimeout\s*\(", re.IGNORECASE),
    "C3_errors": re.compile(
        r"catch\s*\(\s*(SocketException|IOException|ConnectException|SocketTimeoutException)",
        re.IGNORECASE,
    ),
    "C6_filelist": re.compile(
        r"FileRegistry|fileList|fileInventory|sharedFiles|availableFiles|"
        r"ConcurrentHashMap.*File|Map.*File.*Info",
        re.IGNORECASE,
    ),
    "C8_register": re.compile(
        r"\bREGISTER\b|handleRegister|sendRegister|receiveRegister|"
        r"writeRegister|readRegister|clientId\s*=|assignId\s*\(",
        re.IGNORECASE,
    ),
}

# ── existing pattern → check mapping ─────────────────────────────────────────
EXISTING_PATTERN_MAP: dict[str, str] = {
    "C1": "state_machine_enum",
    "C4": "threading",
    "C5": "concurrent_map",
    "C7": "chunk_protocol",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, strip accents, keep only alphanum + space."""
    nfkd = unicodedata.normalize("NFD", (text or "").casefold())
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", ascii_str).strip()


def name_tokens(text: str) -> set[str]:
    """Return set of significant words from a name (length >= 3)."""
    return {t for t in normalize(text).split() if len(t) >= 3}


def names_match(candidate: str, participant_full: str) -> bool:
    """Return True if candidate name tokens are a subset of participant tokens."""
    cand_tokens = name_tokens(candidate)
    part_tokens = name_tokens(participant_full)
    if not cand_tokens:
        return False
    return cand_tokens <= part_tokens


def safe_read_csv(path: Path) -> list[dict]:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
            return list(csv.DictReader(io.StringIO(text)))
        except UnicodeDecodeError:
            continue
    return []


def parse_test_feedback(feedback: str) -> tuple[int, int]:
    """Return (tests_found, tests_passed) from Maven feedback string."""
    found = 0
    passed = 0
    m = re.search(r"(\d+)\s+tests?\s+found", feedback, re.IGNORECASE)
    if m:
        found = int(m.group(1))
    # Count passed/failed modules
    pass_count = len(re.findall(r":\s*Passed", feedback, re.IGNORECASE))
    fail_count = len(re.findall(r":\s*Failed", feedback, re.IGNORECASE))
    total_modules = pass_count + fail_count
    if total_modules > 0 and found > 0:
        passed = round(found * pass_count / total_modules)
    elif found > 0 and not fail_count:
        passed = found
    return found, passed


def compila_score(qualification: str, feedback: str) -> float:
    """Return 0, 0.5, or 1 based on compilation/test result."""
    q = float(qualification) if qualification else 0.0
    if q >= 1.0:
        return 1.0
    found, _ = parse_test_feedback(feedback)
    if found > 0:
        return 0.5  # compiled, some tests ran, but not all pass
    return 0.0


def javadoc_ratio(java_contents: list[str]) -> float:
    """Return fraction [0..1] of files with adequate Javadoc."""
    if not java_contents:
        return 0.0
    documented = 0
    for src in java_contents:
        javadoc_count = src.count("/**")
        # count public/protected declarations
        decl_count = len(re.findall(
            r"\b(public|protected)\s+(static\s+)?\w+\s+\w+\s*\(",
            src,
        ))
        if decl_count == 0:
            decl_count = 1  # avoid division by zero; base minimum
        if javadoc_count / decl_count >= 0.5:
            documented += 1
    return documented / len(java_contents)


def javadoc_score(ratio: float) -> float:
    if ratio >= 0.7:
        return 1.0
    if ratio >= 0.3:
        return 0.5
    return 0.0


def gh_balance(commits_per_person: dict[str, int]) -> dict[str, float]:
    """Return per-login balance score."""
    filtered = {k: v for k, v in commits_per_person.items()
                if "bot" not in k.lower() and v > 0}
    if not filtered:
        return {k: 0.0 for k in commits_per_person}
    total = sum(filtered.values())
    result: dict[str, float] = {}
    max_commits = max(filtered.values())
    min_commits = min(filtered.values())
    ratio = min_commits / max_commits if max_commits > 0 else 1.0
    if ratio >= 0.35:
        score = {k: 1.0 for k in filtered}
    elif ratio >= 0.15:
        score = {k: (0.9 if v == max_commits else 0.5) for k, v in filtered.items()}
    else:
        score = {k: (0.9 if v == max_commits else 0.0) for k, v in filtered.items()}
    # bots and zero-commit authors get 0
    for k in commits_per_person:
        result[k] = score.get(k, 0.0)
    return result


def continuity_score(commit_dates: list[date]) -> float:
    """
    1   = commits spread across ≥4 session weeks, no end-spike
    0.5 = commits in ≥2 weeks but <4, or mild end-spike
    0   = all commits in 1 week or heavy end-spike (>60% in S4 week)
    """
    if not commit_dates:
        return 0.0
    week_sets: set[int] = set()
    last_week = 0
    for d in commit_dates:
        for i, sw in enumerate(SESSION_DATES):
            sw_end = sw + timedelta(days=10)
            if sw <= d <= sw_end:
                week_sets.add(i)
                if i == len(SESSION_DATES) - 1:
                    last_week += 1
                break
    weeks_active = len(week_sets)
    total = len(commit_dates)
    last_fraction = last_week / total if total else 0.0

    if weeks_active >= 4 and last_fraction < 0.5:
        return 1.0
    if weeks_active >= 2 and last_fraction < 0.65:
        return 0.5
    return 0.0


# ── GitHub data fetching ──────────────────────────────────────────────────────

def fetch_new_java_patterns(
    org, repo_name: str, java_file_paths: list[str]
) -> dict[str, bool]:
    """Fetch Java files and detect new patterns."""
    result = {k: False for k in NEW_PATTERNS}
    try:
        repo = org.get_repo(repo_name)
        all_source = ""
        for path in java_file_paths:
            try:
                content = repo.get_contents(path)
                all_source += content.decoded_content.decode("utf-8", errors="replace") + "\n"
            except GithubException:
                pass
        for key, pattern in NEW_PATTERNS.items():
            result[key] = bool(pattern.search(all_source))
    except GithubException:
        pass
    return result


def fetch_javadoc_ratio_score(
    org, repo_name: str, new_file_paths: list[str]
) -> float:
    """Fetch new (non-base) Java files and compute Javadoc ratio."""
    if not new_file_paths:
        return 0.0
    contents = []
    try:
        repo = org.get_repo(repo_name)
        for path in new_file_paths:
            try:
                content = repo.get_contents(path)
                contents.append(content.decoded_content.decode("utf-8", errors="replace"))
            except GithubException:
                pass
    except GithubException:
        pass
    return javadoc_ratio(contents)


def fetch_commit_dates_per_author(
    org, repo_name: str
) -> dict[str, list[date]]:
    """Return {author_login: [commit_date, ...]} limited to session period."""
    result: dict[str, list[date]] = defaultdict(list)
    since = datetime(2026, 2, 1, tzinfo=timezone.utc)
    until = datetime(2026, 4, 15, tzinfo=timezone.utc)
    try:
        repo = org.get_repo(repo_name)
        commits = repo.get_commits(since=since, until=until)
        for commit in commits:
            if commit.author and "bot" not in commit.author.login.lower():
                login = commit.author.login
                d = commit.commit.author.date
                if hasattr(d, "date"):
                    d = d.date()
                result[login].append(d)
    except GithubException:
        pass
    return dict(result)


def fetch_pr_dates_per_author(
    org, repo_name: str
) -> dict[str, list[date]]:
    """Return {author_login: [pr_created_date, ...]}."""
    result: dict[str, list[date]] = defaultdict(list)
    try:
        repo = org.get_repo(repo_name)
        for pr in repo.get_pulls(state="all"):
            if pr.user and "bot" not in pr.user.login.lower():
                d = pr.created_at
                if hasattr(d, "date"):
                    d = d.date()
                result[pr.user.login].append(d)
    except GithubException:
        pass
    return dict(result)


def resolve_github_names(g: Github, logins: set[str]) -> dict[str, str]:
    """Return {login: real_name} for given logins."""
    names: dict[str, str] = {}
    for login in logins:
        if not login or login in {"N/A", "Usuari", "unknown"}:
            continue
        try:
            user = g.get_user(login)
            names[login] = user.name or login
        except GithubException:
            names[login] = login
    return names


def fetch_readme_members(org, repo_name: str) -> list[dict]:
    """
    Fetch README.md from a GitHub repo and extract member names/logins.
    Returns list of {name, github} dicts (empty list if not found).
    """
    try:
        repo = org.get_repo(repo_name)
    except GithubException:
        return []

    # Try common README filenames
    readme_content = None
    for fname in ("README.md", "readme.md", "Readme.md", "README.MD"):
        try:
            f = repo.get_contents(fname)
            readme_content = f.decoded_content.decode("utf-8", errors="replace")
            break
        except GithubException:
            continue

    if not readme_content:
        return []

    members: list[dict] = []
    seen_names: set[str] = set()

    # Strategy 1: Markdown table with column headers containing "nom", "name", "membre", "member"
    # e.g. | Nom | Cognoms | GitHub |
    #      |-----|---------|--------|
    #      | Nom Exemple | Cognoms Exemple | login_exemple |
    table_re = re.compile(r"\|([^\n]+)\|", re.MULTILINE)
    lines = readme_content.splitlines()
    header_line_idx = -1
    name_col = -1
    gh_col = -1

    for idx, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Detect header row
        header_candidates = [normalize(c) for c in cells]
        # Look for name/member column
        for ci, cell_n in enumerate(header_candidates):
            if any(kw in cell_n for kw in ("nom", "name", "membre", "member", "cognom", "surname", "alumne")):
                name_col = ci
                header_line_idx = idx
            if any(kw in cell_n for kw in ("github", "login", "usuari", "user")):
                gh_col = ci

        if header_line_idx == idx and name_col >= 0:
            # Parse data rows after separator line
            for data_line in lines[idx + 2:]:
                if "|" not in data_line:
                    break
                data_cells = [c.strip() for c in data_line.strip("|").split("|")]
                name = data_cells[name_col] if name_col < len(data_cells) else ""
                gh = data_cells[gh_col].strip("@").strip() if gh_col >= 0 and gh_col < len(data_cells) else ""
                name = name.strip()
                if name and name not in ("---", "") and normalize(name) not in seen_names:
                    seen_names.add(normalize(name))
                    members.append({"name": name, "github": gh})
            if members:
                return members

    # Strategy 2: Bullet / numbered list items with names
    # Looks for a section header with "membre", "equip", "team", "grup"
    in_member_section = False
    for line in lines:
        line_norm = normalize(line)
        if re.match(r"#{1,4}\s+", line):
            in_member_section = any(
                kw in line_norm
                for kw in ("membre", "equip", "team", "grup", "autors", "autor", "participants")
            )
            continue
        if not in_member_section:
            continue
        # Match list items: "- Name" or "* Name" or "1. Name"
        m = re.match(r"^\s*[-*\d.]+\s+(.+)", line)
        if not m:
            continue
        item = m.group(1).strip()
        # Extract github login if present (@login or (login))
        gh_m = re.search(r"@([\w-]+)|\(([\w-]+)\)", item)
        gh = (gh_m.group(1) or gh_m.group(2)) if gh_m else ""
        # Strip the github part to get name
        name = re.sub(r"\s*[@(][\w-]+[)]?\s*", "", item).strip(", ").strip()
        if name and normalize(name) not in seen_names:
            seen_names.add(normalize(name))
            members.append({"name": name, "github": gh})

    return members


def fetch_all_contributors_map(
    org,
    repo_names: list[str],
) -> dict[str, list[dict]]:
    """
    Return {group_code: [{login, name}]} from GitHub contributors for each repo.
    group_code is derived from repo name (e.g. practica-1-b04 → B04).
    """
    result: dict[str, list[dict]] = {}
    for repo_name in repo_names:
        code = repo_name.replace("practica-1-", "").upper()
        # Normalize b7 → B07, b01 → B01, etc.
        m = re.match(r"([BC])(\d+)$", code)
        if m:
            code = f"{m.group(1)}{int(m.group(2)):02d}"
        try:
            repo = org.get_repo(repo_name)
            members = []
            for c in repo.get_contributors():
                if "bot" not in c.login.lower():
                    members.append({"login": c.login, "name": c.name or ""})
            result[code] = members
        except GithubException:
            result[code] = []
    return result


def build_submission_group_overrides(submissions_dir: Path) -> dict[str, str]:
    """
    Build {normalized_student_name: group_code} from submissions folder names and ZIP names.

        Example:
            COGNOMS NOM_12345678_assignsubmission_file/
                ..._C13.zip
            -> {"cognoms nom": "C13"}
    """
    overrides: dict[str, str] = {}
    if not submissions_dir.exists():
        return overrides

    for student_dir in submissions_dir.iterdir():
        if not student_dir.is_dir():
            continue
        # Moodle-like folder: "SURNAME NAME_12345678_assignsubmission_file"
        name = student_dir.name
        if "_assignsubmission_file" not in name:
            continue
        prefix = name.split("_assignsubmission_file", 1)[0]
        if "_" not in prefix:
            continue
        student_name = prefix.rsplit("_", 1)[0].strip()
        if not student_name:
            continue
        group_code = ""

        for item in student_dir.iterdir():
            if item.is_file() and item.suffix.lower() == ".zip":
                # Accept patterns such as "..._C13", "...-b7", "... C02"
                mg = re.search(r"([BC])\s*0?(\d{1,2})(?!\d)", item.stem, re.IGNORECASE)
                if mg:
                    group_code = f"{mg.group(1).upper()}{int(mg.group(2)):02d}"
                    break

        if group_code:
            overrides[normalize(student_name)] = group_code

    return overrides


def find_submission_group_for_participant(
    nom: str,
    cognoms: str,
    submission_overrides: dict[str, str],
) -> str:
    """
    Return group code from submissions map using exact and token-overlap matching.
    This avoids hardcoded personal data while handling order/format differences.
    """
    k1 = normalize(f"{nom} {cognoms}")
    k2 = normalize(f"{cognoms} {nom}")

    # 1) Exact normalized key
    exact = submission_overrides.get(k1) or submission_overrides.get(k2)
    if exact:
        return exact

    # 2) Token-overlap fallback
    target_tokens = name_tokens(f"{nom} {cognoms}")
    if not target_tokens:
        return ""

    best_group = ""
    best_score = 0.0
    for sub_name, grp in submission_overrides.items():
        sub_tokens = name_tokens(sub_name)
        if not sub_tokens:
            continue
        inter = len(target_tokens & sub_tokens)
        union = len(target_tokens | sub_tokens)
        score = inter / union if union else 0.0

        # require at least 2 shared tokens and decent overlap
        if inter >= 2 and score > best_score and score >= 0.5:
            best_group = grp
            best_score = score

    return best_group


def build_validation_index(validation_dir: Path) -> list[dict]:
    """Return entries with validation submission folder metadata."""
    entries: list[dict] = []
    if not validation_dir.exists():
        return entries

    for letter_dir in validation_dir.iterdir():
        if not letter_dir.is_dir() or letter_dir.name.upper() not in {"B", "C"}:
            continue
        letter = letter_dir.name.upper()
        for student_dir in letter_dir.iterdir():
            if not student_dir.is_dir():
                continue
            name = student_dir.name
            if "_assignsubmission_file" not in name:
                continue
            prefix = name.split("_assignsubmission_file", 1)[0]
            if "_" not in prefix:
                continue
            student_name = prefix.rsplit("_", 1)[0].strip()
            norm = normalize(student_name)
            entries.append({
                "letter": letter,
                "name_norm": norm,
                "path": student_dir,
            })
    return entries


def find_validation_submission_dir(
    nom: str,
    cognoms: str,
    letter: str,
    validation_entries: list[dict],
) -> Path | None:
    """Find best validation submission folder for participant."""
    k1 = normalize(f"{cognoms} {nom}")
    k2 = normalize(f"{nom} {cognoms}")
    candidates = [e for e in validation_entries if e["letter"] == letter.upper()]

    for e in candidates:
        if e["name_norm"] in {k1, k2}:
            return e["path"]

    target_tokens = name_tokens(f"{nom} {cognoms}")
    if not target_tokens:
        return None

    best_path = None
    best_score = 0.0
    for e in candidates:
        toks = name_tokens(e["name_norm"])
        if not toks:
            continue
        inter = len(target_tokens & toks)
        union = len(target_tokens | toks)
        score = inter / union if union else 0.0
        if inter >= 2 and score > best_score and score >= 0.5:
            best_score = score
            best_path = e["path"]
    return best_path


def _archive_files(student_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in student_dir.iterdir():
        if not p.is_file():
            continue
        lower = p.name.lower()
        if lower.endswith(".zip") or lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar") or lower.endswith(".gz"):
            files.append(p)
    return sorted(files)


def _safe_extract_archive(archive_path: Path, target_dir: Path) -> bool:
    """Extract archive into target_dir. Return True on success."""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        lower = archive_path.name.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(target_dir)
            return True
        if lower.endswith(".tar.gz") or lower.endswith(".tgz") or lower.endswith(".tar"):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(target_dir)
            return True
        if lower.endswith(".gz"):
            out_name = archive_path.stem
            out_file = target_dir / out_name
            with gzip.open(archive_path, "rb") as src, out_file.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            return True
    except Exception:
        return False
    return False


def _find_validation_response_file(search_dirs: list[Path]) -> Path | None:
    """Find likely answer file (.txt/.md/.pdf) in the extracted delivery."""
    candidates: list[Path] = []
    for base in search_dirs:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".txt", ".md", ".pdf"}:
                continue
            candidates.append(p)

    if not candidates:
        return None

    strong_terms = ("valid", "validacio", "validación", "validacion", "prova", "examen", "resposta", "respuesta", "solucio", "solution")
    for p in sorted(candidates):
        name_norm = normalize(p.name)
        if any(t in name_norm for t in strong_terms):
            return p

    # fallback to shortest path depth
    return min(candidates, key=lambda x: len(x.parts))


def _read_response_text(path: Path) -> str:
    """Extract text from txt/md/pdf with best-effort parsing (no extra deps)."""
    if not path.exists():
        return ""
    try:
        if path.suffix.lower() in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".pdf":
            # Best effort without external PDF libs.
            return path.read_bytes().decode("latin-1", errors="replace")
    except Exception:
        return ""
    return ""


def _collect_java_text(search_dirs: list[Path], max_files: int = 120) -> str:
    snippets: list[str] = []
    count = 0
    for base in search_dirs:
        if not base.exists():
            continue
        for jf in base.rglob("*.java"):
            try:
                snippets.append(jf.read_text(encoding="utf-8", errors="replace"))
                count += 1
                if count >= max_files:
                    return "\n".join(snippets)
            except Exception:
                continue
    return "\n".join(snippets)


def _score_validation_result(response_text: str, java_text: str) -> float:
    """Score according to rubric: -1, 0.5, 0.75, 1."""
    if not response_text.strip():
        return -1.0

    txt = normalize(response_text)
    concepts = [
        any(k in txt for k in ("desconnect", "disconnect", "desconnex")),
        any(k in txt for k in ("missatge", "mensaje", "message", "payload")),
        any(k in txt for k in ("client id", "2 bytes", "2byte")),
        any(k in txt for k in ("menu", "opcio", "opcion", "option")),
        any(k in txt for k in ("servidor", "server", "llista clients", "clients connectats", "fitxers disponibles", "available files")),
    ]
    coherent = sum(1 for c in concepts if c) >= 3
    if not coherent:
        return 0.5

    code = normalize(java_text)
    code_signals = [
        any(k in code for k in ("disconnect", "desconnect", "logout", "bye")),
        any(k in code for k in ("message type", "msgtype", "case disconnect", "handledisconnect")),
        any(k in code for k in ("remove", "clients remove", "connectedclients", "clientmap")),
        any(k in code for k in ("filelist", "fileregistry", "availablefiles", "sharedfiles")),
        any(k in code for k in ("close", "socket close", "disconnect client")),
    ]
    if sum(1 for c in code_signals if c) >= 2:
        return 1.0
    return 0.75


def evaluate_validation_submission(student_dir: Path) -> tuple[float, float]:
    """
    Return (Validation, Validation Result).
    Validation: 1 if a delivery archive was found and extracted correctly, else 0.
    Validation Result: rubric score (-1 / 0.5 / 0.75 / 1).
    """
    archives = _archive_files(student_dir)
    if not archives:
        return 0.0, -1.0

    extracted_dirs: list[Path] = []
    valid = 0.0
    first_ok_archive: Path | None = None

    for arch in archives:
        extract_dir = student_dir / f"_extracted_{arch.stem.replace(' ', '_')}"
        ok = _safe_extract_archive(arch, extract_dir)
        if ok:
            valid = 1.0
            extracted_dirs.append(extract_dir)
            if first_ok_archive is None:
                first_ok_archive = arch

    search_roots = [student_dir] + extracted_dirs
    response_file = _find_validation_response_file(search_roots)
    if response_file is None:
        return valid, -1.0

    # Copy detected answer file beside the archive as requested.
    if first_ok_archive is not None:
        dest = first_ok_archive.parent / f"{first_ok_archive.stem}__validation_response{response_file.suffix.lower()}"
        try:
            shutil.copy2(response_file, dest)
        except Exception:
            pass

    response_text = _read_response_text(response_file)
    java_text = _collect_java_text(extracted_dirs)
    return valid, _score_validation_result(response_text, java_text)


# ── participant → group matching ──────────────────────────────────────────────

def build_member_map(
    cross_dir: Path,
    gh_names: dict[str, str],
    readme_members: dict[str, list[dict]] | None = None,
    contributor_map: dict[str, list[dict]] | None = None,
) -> tuple[dict, dict]:
    """
    Returns (group_members, name_lookup).
    Sources:
      1. cross_testing/<GROUP>/summary.json members
      2. auto_analysis/<GROUP>/code_evidence.json commit_stats (groups with no cross-testing)
      3. README members (readme_members param)
      4. GitHub contributors (contributor_map param)
    """
    group_members: dict[str, list[dict]] = {}

    # Source 1: cross-testing summary.json
    for grp_dir in sorted(cross_dir.iterdir()):
        if not grp_dir.is_dir():
            continue
        sj = grp_dir / "summary.json"
        if not sj.exists():
            continue
        data = json.loads(sj.read_text(encoding="utf-8"))
        group_members[grp_dir.name] = data.get("members", [])

    # Source 2: auto_analysis commit_stats (groups not in cross-testing)
    auto_dir = cross_dir.parent / "auto_analysis"
    for grp_dir in sorted(auto_dir.iterdir()):
        if not grp_dir.is_dir() or grp_dir.name == "summary.md":
            continue
        code = grp_dir.name
        if code not in group_members:
            ev_path = grp_dir / "code_evidence.json"
            if ev_path.exists():
                ev = json.loads(ev_path.read_text())
                logins = list(ev.get("commit_stats", {}).keys())
                group_members[code] = [
                    {"name": gh_names.get(lx, lx), "github": lx}
                    for lx in logins
                    if "bot" not in lx.lower()
                ]

    # Source 3: README members
    if readme_members:
        for code, members in readme_members.items():
            existing = group_members.setdefault(code, [])
            existing_logins = {em.get("github", "").lower() for em in existing}
            existing_names = {normalize(em.get("name", "")) for em in existing}
            for rm in members:
                rn = normalize(rm.get("name", ""))
                rl = rm.get("github", "").lower()
                if rn and rn not in existing_names:
                    existing.append(rm)
                    existing_names.add(rn)
                elif rl and rl not in existing_logins:
                    for em in existing:
                        if normalize(em.get("name", "")) == rn and not em.get("github"):
                            em["github"] = rm["github"]
                    existing_logins.add(rl)

    # Source 4: GitHub contributors
    if contributor_map:
        for code, contribs in contributor_map.items():
            existing = group_members.setdefault(code, [])
            existing_logins = {em.get("github", "").lower() for em in existing}
            for cb in contribs:
                cb_login = cb["login"]
                real_name = cb["name"] or gh_names.get(cb_login, cb_login)
                if cb_login.lower() not in existing_logins:
                    existing.append({"name": real_name, "github": cb_login})
                    existing_logins.add(cb_login.lower())
                elif cb["name"]:
                    for em in existing:
                        if em.get("github", "").lower() == cb_login.lower() and not em.get("name"):
                            em["name"] = cb["name"]

    # Build name -> (group, login) lookup
    name_lookup: dict[str, tuple[str, str]] = {}
    for group_code, members in group_members.items():
        for m in members:
            mname = m.get("name", "")
            mlogin = m.get("github", "")
            if mname and mname not in {
                "No identificat a la documentacio",
                "No identificat a la documentació",
                "Cognoms, Nom",
                "N/A",
            }:
                name_lookup[normalize(mname)] = (group_code, mlogin)
            if mlogin and mlogin in gh_names:
                rname = gh_names[mlogin]
                if rname and rname != mlogin:
                    name_lookup[normalize(rname)] = (group_code, mlogin)

    return group_members, name_lookup

def match_participant(
    nom: str,
    cognoms: str,
    group_letter: str,
    name_lookup: dict[str, tuple[str, str]],
    group_members: dict[str, list[dict]],
) -> tuple[str, str]:
    """
    Returns (group_code, github_login) or ("", "") if not found.
    Filters by group_letter prefix (B or C).
    """
    full_name = f"{nom} {cognoms}"

    # 1. Try direct normalized key match
    candidate = normalize(full_name)
    if candidate in name_lookup:
        gc, login = name_lookup[candidate]
        if gc.upper().startswith(group_letter.upper()):
            return gc, login

    # 2. Try partial token match across all member names in matching groups
    for group_code, members in group_members.items():
        if not group_code.upper().startswith(group_letter.upper()):
            continue
        for m in members:
            name = m.get("name", "")
            login = m.get("github", "")
            if names_match(name, full_name) or names_match(full_name, name):
                return group_code, login

    # 3. Try matching Cognoms only (first lastname)
    first_lastname = cognoms.split()[0] if cognoms.split() else ""
    if len(first_lastname) >= 3:
        first_ln_norm = normalize(first_lastname)
        for group_code, members in group_members.items():
            if not group_code.upper().startswith(group_letter.upper()):
                continue
            for m in members:
                if first_ln_norm in normalize(m.get("name", "")):
                    return group_code, m.get("github", "")

    return "", ""


# ── load group data from local files ─────────────────────────────────────────

def load_group_data() -> dict[str, dict]:
    """Return {group_code: combined_data} from auto_analysis + cross_testing."""
    groups: dict[str, dict] = {}

    for grp_dir in sorted(AUTO_ANALYSIS_DIR.iterdir()):
        if not grp_dir.is_dir():
            continue
        code = grp_dir.name
        ev_path = grp_dir / "code_evidence.json"
        if not ev_path.exists():
            continue
        ev = json.loads(ev_path.read_text())

        # cross-testing summary (optional)
        cts_path = CROSS_TESTING_DIR / code / "summary.json"
        cts = json.loads(cts_path.read_text(encoding="utf-8")) if cts_path.exists() else {}

        groups[code] = {
            "repo": ev.get("repo", ""),
            "java_files": ev.get("java_files", []),
            "new_files": ev.get("new_files", []),
            "patterns": ev.get("patterns", {}),
            "commit_stats": ev.get("commit_stats", {}),
            "pr_stats": ev.get("pr_stats", {}),
            "members": cts.get("members", []),
            "csv_result": cts.get("csv_result"),
            "self_eval": cts.get("self_eval", {}),
        }
    return groups


def load_report_lookup() -> dict[str, dict]:
    """Return {niub: {qualification, feedback}} from reportB + reportC."""
    lookup: dict[str, dict] = {}
    for path in [REPORT_B_CSV, REPORT_C_CSV]:
        if not path.exists():
            continue
        for row in safe_read_csv(path):
            niub = row.get("Número ID", "")
            if niub:
                lookup[niub] = {
                    "qualification": row.get("Qualificació", ""),
                    "feedback": row.get("Feedback", ""),
                }
    return lookup


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    g = Github(auth=Auth.Token(settings.GITHUB_TOKEN))
    org = g.get_organization(GITHUB_ORG)

    print("Carregant dades locals...")
    group_data = load_group_data()
    report_lookup = load_report_lookup()
    participants = safe_read_csv(PARTICIPANTS_CSV)
    # filter to B/C only
    bc_participants = []
    for row in participants:
        grups = row.get("Grups", "")
        m = re.search(r"\b([BC])\b", grups)
        if m:
            bc_participants.append({**row, "grup_letter": m.group(1)})
    print(f"  {len(bc_participants)} participants B/C, {len(group_data)} grups")

    # collect all unique GitHub logins
    all_logins: set[str] = set()
    for gd in group_data.values():
        all_logins.update(gd["commit_stats"].keys())
        all_logins.update(gd["pr_stats"].get("authors", {}).keys())
    all_logins = {l for l in all_logins if l and "bot" not in l.lower()}

    print(f"Resolent noms GitHub per a {len(all_logins)} logins...")
    gh_names = resolve_github_names(g, all_logins)

    # Repo names for all B/C groups
    repo_names = [gd["repo"] for gd in group_data.values() if gd.get("repo")]

    print("Llegint READMEs dels repositoris per obtenir membres...")
    readme_members: dict[str, list[dict]] = {}
    for repo_name in repo_names:
        code = repo_name.replace("practica-1-", "").upper()
        m2 = re.match(r"([BC])(\d+)$", code)
        if m2:
            code = f"{m2.group(1)}{int(m2.group(2)):02d}"
        rmembers = fetch_readme_members(org, repo_name)
        if rmembers:
            readme_members[code] = rmembers
            print(f"  {code}: {len(rmembers)} membres al README")
        else:
            print(f"  {code}: README sense membres estructurats")

    print("Obtenint contributors de tots els repos...")
    contributor_map = fetch_all_contributors_map(org, repo_names)

    print("Construint mapa participants→grups...")
    group_members, name_lookup = build_member_map(
        CROSS_TESTING_DIR,
        gh_names,
        readme_members=readme_members,
        contributor_map=contributor_map,
    )

    print("Indexant lliuraments de validació...")
    validation_entries = build_validation_index(VALIDATION_DIR)
    validation_cache: dict[Path, tuple[float, float]] = {}

    # Fallback map from LMS submissions ZIP names (contains group code in filename)
    submission_overrides = build_submission_group_overrides(SUBMISSIONS_DIR)
    print(f"Submissions amb grup detectat: {len(submission_overrides)}")
    # ── per-group GitHub data fetch ────────────────────────────────────────────
    print("Obtenint dades per grup de GitHub (patrons nous, JavaDoc, dates commits/PRs)...")
    group_extra: dict[str, dict] = {}
    for code, gd in sorted(group_data.items()):
        repo_name = gd["repo"]
        print(f"  {code} ({repo_name})...")

        new_patterns = fetch_new_java_patterns(org, repo_name, gd["java_files"])
        jd_ratio = fetch_javadoc_ratio_score(org, repo_name, gd["new_files"])
        commit_dates = fetch_commit_dates_per_author(org, repo_name)
        pr_dates = fetch_pr_dates_per_author(org, repo_name)

        # combine code checks: existing + new
        checks: dict[str, bool] = {}
        for cid, _, _ in CODE_CHECKS:
            if cid in EXISTING_PATTERN_MAP:
                checks[cid] = bool(gd["patterns"].get(EXISTING_PATTERN_MAP[cid]))
            else:
                # map from new patterns
                new_key = {
                    "C2": "C2_timeout",
                    "C3": "C3_errors",
                    "C6": "C6_filelist",
                    "C8": "C8_register",
                }.get(cid, "")
                checks[cid] = bool(new_patterns.get(new_key, False))

        nota_codi = sum(
            (1.0 if checks.get(cid) else 0.0) * w
            for cid, _, w in CODE_CHECKS
        )

        # GH balance (commit-based)
        commit_balance = gh_balance(gd["commit_stats"])

        group_extra[code] = {
            "checks": checks,
            "nota_codi": round(nota_codi, 2),
            "javadoc": javadoc_score(jd_ratio),
            "commit_dates": commit_dates,   # {login: [date,...]}
            "pr_dates": pr_dates,            # {login: [date,...]}
            "commit_balance": commit_balance,
        }
        print(f"    OK  jd={jd_ratio:.2f} nota_codi={nota_codi:.1f}")

    # ── build output rows ──────────────────────────────────────────────────────
    print("Generant CSV...")
    cid_labels = [cid for cid, _, _ in CODE_CHECKS]
    weights_map = {cid: w for cid, _, w in CODE_CHECKS}

    fieldnames = (
        ["Nom", "Cognoms", "Número ID", "Grups", "Grup", "GitHub Login"]
        + cid_labels
        + ["Nota_Codi", "JavaDoc", "Memòria", "Compila",
           "#Tests", "#Passa", "%Coverage",
            "#PR", "#commits", "GH_Balance", "Continuitat",
            "Validation", "Validation Result"]
    )

    rows: list[dict] = []

    # Weight row (row index 0 in data, row 2 in file after header)
    weight_row = {f: "" for f in fieldnames}
    weight_row["Nom"] = "PESOS"
    for cid, _, w in CODE_CHECKS:
        weight_row[cid] = w
    weight_row["Nota_Codi"] = f"sum(C_i * W_i) / 10"
    rows.append(weight_row)

    unmatched: list[dict] = []
    for p in bc_participants:
        nom = p.get("Nom", "")
        cognoms = p.get("Cognoms", "")
        niub = p.get("Número ID", "")
        grups = p.get("Grups", "")
        letter = p.get("grup_letter", "")

        group_code, login = match_participant(nom, cognoms, letter, name_lookup, group_members)

        if not group_code:
            # Try overrides from submissions (exact + token overlap)
            group_code = find_submission_group_for_participant(
                nom,
                cognoms,
                submission_overrides,
            )

        if not group_code:
            unmatched.append(p)

        gd = group_data.get(group_code, {})
        gex = group_extra.get(group_code, {})
        report = report_lookup.get(niub, {})

        # Test results from report
        qualification = report.get("qualification", "")
        feedback = report.get("feedback", "")
        n_tests, n_passa = parse_test_feedback(feedback)
        comp = compila_score(qualification, feedback)

        # Per-person GitHub stats
        commit_stats = gd.get("commit_stats", {})
        pr_authors = gd.get("pr_stats", {}).get("authors", {})
        # try to find the login in commit_stats (case-insensitive)
        matched_login = login
        if login and login not in commit_stats:
            for k in commit_stats:
                if k.lower() == login.lower():
                    matched_login = k
                    break
        n_commits = commit_stats.get(matched_login, "")
        n_prs = pr_authors.get(matched_login, "")

        # GH Balance for this login
        balance_map = gex.get("commit_balance", {})
        gh_bal = balance_map.get(matched_login, "")
        if gh_bal == "" and matched_login:
            # try case-insensitive
            for k, v in balance_map.items():
                if k.lower() == matched_login.lower():
                    gh_bal = v
                    break

        # Continuity for this login
        commit_dates_map = gex.get("commit_dates", {})
        person_dates = commit_dates_map.get(matched_login, [])
        if not person_dates and matched_login:
            for k, v in commit_dates_map.items():
                if k.lower() == matched_login.lower():
                    person_dates = v
                    break
        cont = continuity_score(person_dates) if person_dates else ""

        # Validation (ValPr1): submission extractability + answer coherence score
        v_dir = find_validation_submission_dir(nom, cognoms, letter, validation_entries)
        if v_dir is None:
            validation = 0.0
            validation_result = -1.0
        else:
            if v_dir not in validation_cache:
                validation_cache[v_dir] = evaluate_validation_submission(v_dir)
            validation, validation_result = validation_cache[v_dir]

        row = {
            "Nom": nom,
            "Cognoms": cognoms,
            "Número ID": niub,
            "Grups": grups,
            "Grup": group_code or "NO_MATCH",
            "GitHub Login": matched_login or login,
        }
        checks = gex.get("checks", {})
        for cid in cid_labels:
            v = checks.get(cid)
            row[cid] = 1 if v is True else (0 if v is False else "")
        row["Nota_Codi"] = gex.get("nota_codi", "")
        row["JavaDoc"] = gex.get("javadoc", "")
        row["Memòria"] = ""  # manual
        row["Compila"] = comp if qualification else ""
        row["#Tests"] = n_tests if n_tests else ""
        row["#Passa"] = n_passa if n_passa else ""
        row["%Coverage"] = "N/A"
        row["#PR"] = n_prs
        row["#commits"] = n_commits
        row["GH_Balance"] = gh_bal
        row["Continuitat"] = cont
        row["Validation"] = validation
        row["Validation Result"] = validation_result

        rows.append(row)

    # write CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nCSV generat: {OUTPUT_CSV}")
    print(f"Files: {len(rows) - 1} participants (+ 1 fila de pesos)")
    if unmatched:
        print(f"\nATENCIÓ: {len(unmatched)} participants sense grup assignat:")
        for p in unmatched:
            print(f"  - {p['Nom']} {p['Cognoms']} ({p.get('Número ID','')})")


if __name__ == "__main__":
    main()
