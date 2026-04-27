"""
Automated code analysis report generator for SD PR1 groups.

For each B/C group:
  - Fetches the group's GitHub repo
  - Compares implemented files vs base scaffold (PR1 repo)
  - Detects key implementation patterns in Java code
  - Collects GitHub metrics (commits per author, PRs, code reviews)
  - Loads cross-testing summary.json
  - Generates _data/sd/26/pr1/auto_analysis/<GROUP>/analysis.md
  - Generates _data/sd/26/pr1/auto_analysis/summary.md (global)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from github import Auth, Github, GithubException

from teaching_utils.config import settings

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "_data" / "sd" / "26" / "pr1" / "auto_analysis"
CROSS_TESTING_DIR = ROOT / "_data" / "sd" / "26" / "pr1" / "cross_testing"

GITHUB_ORG = "SoftwareDistribuitUB-2026"
BASE_REPO_NAME = "PR1"
BASE_BRANCH = "master"

# ── what the base scaffold already contains ─────────────────────────────────────
BASE_JAVA_FILES = {
    "Client/src/main/java/p1/client/Client.java",
    "Client/src/main/java/p1/client/GameClient.java",
    "Client/src/test/java/ClientTest.java",
    "ComUtils/src/main/java/utils/ComUtils.java",
    "ComUtils/src/test/java/utils/ComUtilsTest.java",
    "Server/src/main/java/p1/server/GameHandler.java",
    "Server/src/main/java/p1/server/Server.java",
    "Server/src/test/java/ServerTest.java",
}

# ── evaluation criteria mapped from cross-testing report ───────────────────────
CRITERIA_LABELS = {
    "server_start": "Servidor: arrencada i registre",
    "server_announce": "Servidor: announce/configuració",
    "server_search": "Servidor: cerca",
    "server_download": "Servidor: descarrega (1 client)",
    "server_multi": "Servidor: descarrega multi-client",
    "client_register": "Client: connexió i registre",
    "client_announce": "Client: announce/configuració",
    "client_search": "Client: cerca",
    "client_transfer": "Client: transferència",
}

# ── code-pattern detectors ─────────────────────────────────────────────────────
PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # (id, label, regex)
    ("state_machine_enum", "Màquina d'estats (enum/switch)", re.compile(
        r"\benum\b.*\{[^}]*(INIT|REGISTER|ANNOUNCE|SEARCH|DOWNLOAD|CHUNK|IDLE|CONNECTED)[^}]*\}|"
        r"\bswitch\s*\(.*state.*\)|"
        r"\.INIT\b|\.REGISTER\b|\.ANNOUNCE\b|\.SEARCHING\b|\.DOWNLOADING\b",
        re.IGNORECASE | re.DOTALL,
    )),
    ("threading", "Multi-threading (Thread/Runnable/ExecutorService)", re.compile(
        r"\bimplements\s+Runnable\b|\bextends\s+Thread\b|\bExecutorService\b|\bnew\s+Thread\s*\(|\bThreadPool\b",
        re.IGNORECASE,
    )),
    ("concurrent_map", "Estructures thread-safe (ConcurrentHashMap)", re.compile(
        r"\bConcurrentHashMap\b",
        re.IGNORECASE,
    )),
    ("file_io", "E/S de fitxers (FileInputStream/FileOutputStream/RandomAccessFile)", re.compile(
        r"\bFileInputStream\b|\bFileOutputStream\b|\bRandomAccessFile\b|\bFiles\.write\b|\bFiles\.read\b",
        re.IGNORECASE,
    )),
    ("chunk_protocol", "Protocol de chunks (CHUNK_REQUEST/CHUNK_RESPONSE)", re.compile(
        r"\bCHUNK_REQUEST\b|\bCHUNK_RESPONSE\b|\bchunkRequest\b|\bchunkResponse\b|"
        r"readChunk|writeChunk|sendChunk|receiveChunk",
        re.IGNORECASE,
    )),
    ("announce_msg", "Missatge ANNOUNCE implementat", re.compile(
        r"\bANNOUNCE\b|\bannounce\s*\(|handleAnnounce|writeAnnounce|readAnnounce",
        re.IGNORECASE,
    )),
    ("search_msg", "Missatge SEARCH implementat", re.compile(
        r"\bSEARCH\b|\bsearch\s*\(|handleSearch|writeSearch|readSearch",
        re.IGNORECASE,
    )),
    ("download_msg", "Missatge DOWNLOAD implementat", re.compile(
        r"\bDOWNLOAD\b|\bdownload\s*\(|handleDownload|writeDownload|readDownload",
        re.IGNORECASE,
    )),
    ("comutils_extended", "ComUtils estès (nous mètodes read/write)", re.compile(
        r"public\s+\w+\s+(?:read|write)_\w+\s*\(",
        re.IGNORECASE,
    )),
    ("javadoc", "Javadoc present", re.compile(
        r"/\*\*.*?\*/",
        re.DOTALL,
    )),
    ("unit_tests", "Tests unitaris no trivials", re.compile(
        r"@Test\b",
    )),
    ("multi_client_accept", "Bucle d'acceptació multi-client", re.compile(
        r"while\s*\([^)]*true[^)]*\)\s*\{[^}]*\.accept\(\)|"
        r"serverSocket\.accept\(\).*\bThread\b",
        re.DOTALL | re.IGNORECASE,
    )),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def get_group_repos(g: Github) -> list[str]:
    """Return sorted list of group repo names for B and C groups."""
    org = g.get_organization(GITHUB_ORG)
    names = []
    for repo in org.get_repos():
        m = re.fullmatch(r"practica-1-([bc]\d+)", repo.name, re.IGNORECASE)
        if m:
            names.append(repo.name)
    return sorted(names)


def load_repo_java_files(repo) -> dict[str, str]:
    """Return {path: content} for all .java files in the repo."""
    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
    except GithubException:
        return {}
    files: dict[str, str] = {}
    for el in tree.tree:
        if el.type == "blob" and el.path.endswith(".java"):
            try:
                content = repo.get_contents(el.path)
                files[el.path] = content.decoded_content.decode("utf-8", errors="replace")
            except GithubException:
                files[el.path] = ""
    return files


def detect_patterns(java_files: dict[str, str]) -> dict[str, bool]:
    """Run all pattern detectors over all java source; return {id: found}."""
    all_source = "\n".join(java_files.values())
    return {pid: bool(regex.search(all_source)) for pid, _, regex in PATTERNS}


def get_commit_stats(repo) -> dict[str, int]:
    """Return {author_login: commit_count} via contributors list (single API call)."""
    stats: dict[str, int] = {}
    try:
        for contributor in repo.get_contributors():
            login = contributor.login if contributor.login else "unknown"
            stats[login] = contributor.contributions
    except GithubException:
        pass
    return stats


def get_pr_stats(repo) -> dict:
    """Return summary of PRs including review comment counts."""
    total = 0
    merged = 0
    authors: dict[str, int] = defaultdict(int)
    review_comments = 0
    try:
        for pr in repo.get_pulls(state="all"):
            total += 1
            if pr.merged:
                merged += 1
            login = pr.user.login if pr.user else "unknown"
            authors[login] += 1
            try:
                review_comments += pr.get_review_comments().totalCount
            except GithubException:
                pass
    except GithubException:
        pass
    return {"total": total, "merged": merged, "authors": dict(authors), "review_comments": review_comments}


def load_cross_summary(group_code: str) -> dict | None:
    path = CROSS_TESTING_DIR / group_code.upper() / "summary.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def bool_icon(value: bool | None) -> str:
    if value is True:
        return "✅"
    if value is False:
        return "❌"
    return "—"


def pr_authors_table(pr_stats: dict) -> str:
    rows = []
    for login, count in sorted(pr_stats["authors"].items(), key=lambda x: -x[1]):
        rows.append(f"| {login} | {count} |")
    return "\n".join(rows)


def commit_table(commit_stats: dict) -> str:
    rows = []
    for login, count in sorted(commit_stats.items(), key=lambda x: -x[1]):
        rows.append(f"| {login} | {count} |")
    return "\n".join(rows)


def render_group_report(
    group_code: str,
    repo_name: str,
    java_files: dict[str, str],
    base_files: set[str],
    patterns: dict[str, bool],
    commit_stats: dict[str, int],
    pr_stats: dict,
    cross_summary: dict | None,
) -> str:
    lines: list[str] = []

    lines += [f"# Informe d'anàlisi: {group_code}", ""]
    lines += [f"**Repositori:** https://github.com/{GITHUB_ORG}/{repo_name}", ""]

    # ── membres ────────────────────────────────────────────────────────────────
    members = cross_summary.get("members", []) if cross_summary else []
    if members:
        lines += ["## Membres", ""]
        for m in members:
            lines.append(f"- {m.get('name', 'Desconegut')} (@{m.get('github', 'N/A')})")
        lines.append("")

    # ── resultat automàtic ─────────────────────────────────────────────────────
    csv_result = cross_summary.get("csv_result") if cross_summary else None
    if csv_result:
        q = csv_result.get("qualification", "N/A")
        lines += ["## Resultat automàtic de les proves", ""]
        lines += [f"**Qualificació:** {q}", ""]
        feedback = csv_result.get("feedback", "")
        if feedback:
            lines += ["```", feedback.strip(), "```", ""]

    # ── autoavaluació (cross-testing) ──────────────────────────────────────────
    self_eval = cross_summary.get("self_eval", {}) if cross_summary else {}
    lines += ["## Autoavaluació declarada (TestReport)", ""]
    lines += ["| Funcionalitat | Auto-eval |", "|---|---|"]
    for cid, clabel in CRITERIA_LABELS.items():
        lines.append(f"| {clabel} | {bool_icon(self_eval.get(cid))} |")
    lines.append("")

    # ── fitxers Java: nou vs base ──────────────────────────────────────────────
    new_files = sorted(p for p in java_files if p not in base_files)
    modified_base = sorted(p for p in java_files if p in base_files)
    lines += ["## Fitxers Java afegits (vs scaffold base)", ""]
    if new_files:
        for f in new_files:
            lines.append(f"- `{f}`")
    else:
        lines.append("- *(cap fitxer nou fora del scaffold)*")
    lines.append("")

    lines += ["## Fitxers base presents", ""]
    for f in modified_base:
        lines.append(f"- `{f}`")
    missing_base = sorted(base_files - set(java_files.keys()))
    if missing_base:
        lines += ["", "**Fitxers base absents:**"]
        for f in missing_base:
            lines.append(f"- `{f}` ⚠️")
    lines.append("")

    # ── patrons detectats ──────────────────────────────────────────────────────
    lines += ["## Patrons d'implementació detectats", ""]
    lines += ["| Patró | Detectat |", "|---|---|"]
    for pid, plabel, _ in PATTERNS:
        lines.append(f"| {plabel} | {bool_icon(patterns.get(pid))} |")
    lines.append("")

    # ── mancances detectades ───────────────────────────────────────────────────
    lines += ["## Mancances detectades", ""]
    issues: list[str] = []

    # from self-eval
    missing_self = [clabel for cid, clabel in CRITERIA_LABELS.items() if self_eval.get(cid) is False]
    if missing_self:
        issues.append("**Funcionalitats no assolides (autoavaluació):**")
        for m in missing_self:
            issues.append(f"  - {m}")

    # from patterns
    if not patterns.get("threading"):
        issues.append("- No s'ha detectat multi-threading al servidor (Thread/Runnable)")
    if not patterns.get("state_machine_enum"):
        issues.append("- No s'ha detectat una màquina d'estats explícita (enum/switch)")
    if not patterns.get("file_io"):
        issues.append("- No s'ha detectat E/S de fitxers (FileInputStream/FileOutputStream)")
    if not patterns.get("chunk_protocol"):
        issues.append("- No s'ha detectat lògica de chunks (CHUNK_REQUEST/CHUNK_RESPONSE)")
    if not patterns.get("unit_tests"):
        issues.append("- No s'han detectat tests unitaris (@Test)")
    if not patterns.get("javadoc"):
        issues.append("- No s'ha detectat Javadoc (/** ... */)")

    # from github
    total_commits = sum(commit_stats.values())
    if total_commits < 10:
        issues.append(f"- Nombre baix de commits ({total_commits}): pot indicar manca de continuïtat")
    if pr_stats["total"] < 4:
        issues.append(f"- Nombre baix de PRs ({pr_stats['total']}): s'esperava mínim 1 per persona per sessió")
    if pr_stats["review_comments"] < 2:
        issues.append(f"- Pocs comentaris de revisió als PRs ({pr_stats['review_comments']}): possiblement sense code review real")

    if not issues:
        lines.append("Cap mancança rellevant detectada de forma automàtica.")
    else:
        lines += issues
    lines.append("")

    # ── activitat GitHub ───────────────────────────────────────────────────────
    lines += ["## Activitat GitHub", ""]
    lines += [f"**Total commits:** {sum(commit_stats.values())}  "]
    lines += [f"**Total PRs:** {pr_stats['total']} ({pr_stats['merged']} fusionats)  "]
    lines += [f"**Comentaris de revisió als PRs:** {pr_stats['review_comments']}", ""]

    lines += ["### Commits per autor", ""]
    lines += ["| Autor | Commits |", "|---|---|"]
    lines += [commit_table(commit_stats)] if commit_stats else ["| *(sense dades)* | — |"]
    lines.append("")

    lines += ["### PRs per autor", ""]
    lines += ["| Autor | PRs |", "|---|---|"]
    lines += [pr_authors_table(pr_stats)] if pr_stats["authors"] else ["| *(sense dades)* | — |"]
    lines.append("")

    # ── alineació creu (avaluació rebuda) ──────────────────────────────────────
    received = cross_summary.get("received_blocks", []) if cross_summary else []
    if received:
        lines += ["## Avaluació creuada rebuda d'altres grups", ""]
        lines += ["| Grup | Aspectes OK | Aspectes KO | Notes |", "|---|---|---|---|"]
        for block in received:
            src = block.get("source", "?")
            criteria = block.get("criteria", {})
            ok = sum(1 for v in criteria.values() if v)
            ko = sum(1 for v in criteria.values() if v is False)
            note = "; ".join(block.get("notes", []))[:120]
            lines.append(f"| {src} | {ok} | {ko} | {note} |")
        lines.append("")

    return "\n".join(lines)


def render_summary(group_reports: list[dict]) -> str:
    lines = [
        "# Resum global de l'anàlisi de codi - PR1",
        "",
        f"Total de grups analitzats: **{len(group_reports)}**",
        "",
        "| Grup | Qualif. | Commits | PRs | Threading | SM | File I/O | Chunks | Tests |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(group_reports, key=lambda x: x["group"]):
        q = r["qualification"]
        p = r["patterns"]
        lines.append(
            f"| [{r['group']}](./{r['group']}/analysis.md)"
            f" | {q}"
            f" | {r['commits']}"
            f" | {r['prs']}"
            f" | {bool_icon(p.get('threading'))}"
            f" | {bool_icon(p.get('state_machine_enum'))}"
            f" | {bool_icon(p.get('file_io'))}"
            f" | {bool_icon(p.get('chunk_protocol'))}"
            f" | {bool_icon(p.get('unit_tests'))}"
            " |"
        )
    lines.append("")
    lines.append("**Llegenda:** SM = Màquina d'estats")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    g = Github(auth=Auth.Token(settings.GITHUB_TOKEN))
    org = g.get_organization(GITHUB_ORG)

    # ── load base scaffold file list ───────────────────────────────────────────
    print("Carregant scaffold base (PR1)...")
    try:
        base_repo = org.get_repo(BASE_REPO_NAME)
        base_tree = base_repo.get_git_tree(BASE_BRANCH, recursive=True)
        base_java_files = {el.path for el in base_tree.tree if el.type == "blob" and el.path.endswith(".java")}
    except GithubException as exc:
        print(f"  WARN: no s'ha pogut carregar el repo base: {exc}")
        base_java_files = BASE_JAVA_FILES

    # ── collect group repos ────────────────────────────────────────────────────
    group_repo_names = get_group_repos(g)
    print(f"Grups trobats: {len(group_repo_names)}")

    group_reports_meta: list[dict] = []

    for repo_name in group_repo_names:
        # derive group code like B01, C03
        m = re.fullmatch(r"practica-1-([bc]\d+)", repo_name, re.IGNORECASE)
        group_code = m.group(1).upper() if m else repo_name

        print(f"  Analitzant {group_code} ({repo_name})...")

        try:
            repo = org.get_repo(repo_name)
        except GithubException as exc:
            print(f"    WARN: no s'ha pogut accedir al repo: {exc}")
            continue

        # load all java files
        java_files = load_repo_java_files(repo)

        # detect patterns
        patterns = detect_patterns(java_files)

        # github stats
        commit_stats = get_commit_stats(repo)
        pr_stats = get_pr_stats(repo)

        # cross-testing summary
        cross_summary = load_cross_summary(group_code)

        # render per-group report
        report_md = render_group_report(
            group_code=group_code,
            repo_name=repo_name,
            java_files=java_files,
            base_files=base_java_files,
            patterns=patterns,
            commit_stats=commit_stats,
            pr_stats=pr_stats,
            cross_summary=cross_summary,
        )

        group_dir = OUTPUT_DIR / group_code
        group_dir.mkdir(parents=True, exist_ok=True)
        (group_dir / "analysis.md").write_text(report_md, encoding="utf-8")

        # save raw evidence json
        evidence = {
            "group": group_code,
            "repo": repo_name,
            "java_files": sorted(java_files.keys()),
            "new_files": sorted(p for p in java_files if p not in base_java_files),
            "missing_base_files": sorted(base_java_files - set(java_files.keys())),
            "patterns": patterns,
            "commit_stats": commit_stats,
            "pr_stats": pr_stats,
        }
        (group_dir / "code_evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        qualification = (cross_summary or {}).get("csv_result", {}) or {}
        group_reports_meta.append({
            "group": group_code,
            "qualification": qualification.get("qualification", "N/A"),
            "commits": sum(commit_stats.values()),
            "prs": pr_stats["total"],
            "patterns": patterns,
        })

        print(f"    OK  ({len(java_files)} fitxers Java, {sum(commit_stats.values())} commits, {pr_stats['total']} PRs)")

    # ── global summary ─────────────────────────────────────────────────────────
    summary_md = render_summary(group_reports_meta)
    (OUTPUT_DIR / "summary.md").write_text(summary_md, encoding="utf-8")
    print(f"\nReport generat: {OUTPUT_DIR / 'summary.md'}")
    print(f"Informes per grup: {OUTPUT_DIR}/<GRUP>/analysis.md")


if __name__ == "__main__":
    main()
