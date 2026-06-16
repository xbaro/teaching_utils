import csv
import difflib
import json
import logging
import os
import re
import subprocess
from pathlib import Path

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.submissions import SubmissionSet

logger = logging.getLogger(__name__)


def _build_report_key(report):
    submission = report.submission
    student_id = getattr(submission, '_student_id', None)
    if student_id:
        return f'id:{student_id}'
    student_name = getattr(submission, '_student_fullname', None)
    if student_name:
        return f'name:{student_name}'
    return submission.get_key()


def _build_report_index(reports):
    return {_build_report_key(report): report for report in reports.values()}


def _get_report_student_info(report):
    submission = report.submission
    groups = getattr(submission, '_student_groups', []) or []
    return {
        'student_id': getattr(submission, '_student_id', None),
        'student_name': getattr(submission, '_student_fullname', submission.get_key()),
        'groups': ', '.join(sorted(groups)),
        'submission_key': submission.get_key(),
    }


def _combine_scores(primary_report, secondary_report, primary_weight=0.5, secondary_weight=0.5):
    weighted_scores = []
    if primary_report is not None and primary_report.final_score is not None:
        weighted_scores.append((primary_report.final_score, primary_weight))
    if secondary_report is not None and secondary_report.final_score is not None:
        weighted_scores.append((secondary_report.final_score, secondary_weight))

    if not weighted_scores:
        return None

    total_weight = sum(weight for _, weight in weighted_scores)
    return sum(score * weight for score, weight in weighted_scores) / total_weight


def _count_passed_test_leaves(node):
    if node is None:
        return 0
    if not node.children:
        return 1 if node.passed else 0
    return sum(_count_passed_test_leaves(child) for child in node.children)


def _get_report_test_counts(report):
    if report is None:
        return {
            'total': None,
            'passed': None,
            'failed': None,
        }

    total_tests = report.total_tests if report.total_tests is not None else 0
    passed_tests = 0

    if report.test_tree is not None:
        tests_node = next((child for child in report.test_tree.children if child.label == 'Tests'), None)
        if tests_node is not None and total_tests > 0:
            passed_tests = _count_passed_test_leaves(tests_node)

    failed_tests = total_tests - passed_tests if total_tests is not None else None

    return {
        'total': total_tests,
        'passed': passed_tests,
        'failed': failed_tests,
    }


def _iter_report_pairs(primary_reports, secondary_reports):
    primary_index = _build_report_index(primary_reports)
    secondary_index = _build_report_index(secondary_reports)

    def _report_sort_name(report_key):
        report = primary_index.get(report_key) or secondary_index.get(report_key)
        if report is None:
            return ''
        assert report is not None
        student_info = _get_report_student_info(report)
        return str(student_info.get('student_name', ''))

    combined_keys = sorted(
        set(primary_index.keys()) | set(secondary_index.keys()),
        key=_report_sort_name,
    )

    for report_key in combined_keys:
        primary_report = primary_index.get(report_key)
        secondary_report = secondary_index.get(report_key)
        base_report = primary_report or secondary_report
        yield report_key, base_report, primary_report, secondary_report


def _read_text_lines(path: str) -> list[str]:
    with open(path, 'r', encoding='utf-8', errors='ignore') as fin:
        return fin.readlines()


def _normalize_rel_path(path: str) -> str:
    return path.replace('\\', '/')


def _sanitize_path_component(value: str) -> str:
    return re.sub(r'[^0-9A-Za-z._-]+', '_', value).strip('_') or 'unknown'


def _is_ignored_source_path(rel_path: str) -> bool:
    rel_path = _normalize_rel_path(rel_path)
    parts = rel_path.split('/')
    ignored_parts = {'__pycache__', '.pytest_cache', '.venv', '.git', 'node_modules', 'results', 'tmp', 'build', 'dist'}
    if any(part in ignored_parts or part.startswith('.') for part in parts[:-1]):
        return True

    basename = parts[-1]
    if basename in {'set_info.pkl', 'backend-report.xml', '.DS_Store'}:
        return True
    if basename.endswith(('.pyc', '.pyo')):
        return True
    return False


def _should_include_source_file(rel_path: str) -> bool:
    if _is_ignored_source_path(rel_path):
        return False

    basename = os.path.basename(rel_path)
    ext = os.path.splitext(basename)[1].lower()
    if basename in {'Dockerfile', 'Makefile', 'CMakeLists.txt'}:
        return True
    return ext in {
        '.py', '.json', '.yml', '.yaml', '.md', '.txt', '.ini', '.toml', '.xml', '.sh',
        '.js', '.ts', '.tsx', '.vue', '.html', '.css', '.scss', '.sql', '.cfg', '.conf', '.env',
    }


def _find_repository_root(base_path: str) -> str:
    base_path = os.path.abspath(base_path)
    candidates = []

    for root, dirs, files in os.walk(base_path):
        dir_names = set(dirs)
        file_names = set(files)
        score = 0

        if 'docker-compose.yml' in file_names:
            score += 4
        if '.git' in dir_names:
            score += 4
        if 'backend' in dir_names:
            score += 3
        if 'frontend' in dir_names:
            score += 3
        if 'pyproject.toml' in file_names:
            score += 2
        if 'package.json' in file_names:
            score += 2
        if 'manage.py' in file_names:
            score += 1

        if score > 0:
            rel_root = os.path.relpath(root, base_path)
            depth = 0 if rel_root == '.' else rel_root.count(os.sep) + 1
            candidates.append((score, depth, len(root), root))

    if len(candidates) == 0:
        return base_path

    return max(candidates, key=lambda item: (item[0], -item[1], -item[2]))[3]


def _get_workdir_root(submission_path: str, working_directory: str = 'backend') -> str:
    repo_root = _find_repository_root(submission_path)
    workdir = os.path.join(repo_root, working_directory)
    if os.path.isdir(workdir):
        return workdir
    return repo_root


def _collect_source_files(base_path: str) -> dict[str, str]:
    files = {}
    for root, _, filenames in os.walk(base_path):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            rel_path = _normalize_rel_path(os.path.relpath(full_path, base_path))
            if _should_include_source_file(rel_path):
                files[rel_path] = full_path
    return files


def _load_coverage_execution_map(report) -> dict[str, set[int]]:
    execution_map = {}
    if report is None or report.results_path is None:
        return execution_map

    coverage_path = os.path.join(report.results_path, 'coverage.json')
    if not os.path.exists(coverage_path):
        return execution_map

    with open(coverage_path, 'r', encoding='utf-8') as fin:
        coverage_data = json.load(fin)

    for rel_path, file_report in coverage_data.get('files', {}).items():
        execution_map[_normalize_rel_path(rel_path)] = set(file_report.get('executed_lines', []))

    return execution_map


def _extract_added_lines(primary_lines: list[str], secondary_lines: list[str]) -> list[int]:
    matcher = difflib.SequenceMatcher(None, primary_lines, secondary_lines)
    added_lines = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in {'insert', 'replace'}:
            added_lines.extend(range(j1 + 1, j2 + 1))
    return added_lines


def _build_diff_summary(primary_workdir: str, secondary_workdir: str, secondary_report=None) -> dict:
    if not primary_workdir or not secondary_workdir:
        return {
            'changed_files': [],
            'total_added': 0,
            'total_covered': 0,
            'total_uncovered': 0,
            'overall_coverage': None,
        }

    primary_files = _collect_source_files(primary_workdir)
    secondary_files = _collect_source_files(secondary_workdir)
    coverage_map = _load_coverage_execution_map(secondary_report)

    changed_files = []
    total_added = 0
    total_covered = 0

    all_rel_paths = sorted(set(primary_files.keys()) | set(secondary_files.keys()))
    for rel_path in all_rel_paths:
        primary_path = primary_files.get(rel_path)
        secondary_path = secondary_files.get(rel_path)

        primary_lines = _read_text_lines(primary_path) if primary_path and os.path.exists(primary_path) else []
        secondary_lines = _read_text_lines(secondary_path) if secondary_path and os.path.exists(secondary_path) else []

        if primary_lines == secondary_lines:
            continue

        added_line_numbers = _extract_added_lines(primary_lines, secondary_lines)
        if len(added_line_numbers) == 0:
            continue

        executed_lines = coverage_map.get(rel_path, set())
        covered_lines = sorted(set(added_line_numbers) & executed_lines)
        uncovered_lines = sorted(set(added_line_numbers) - executed_lines)

        total_added += len(added_line_numbers)
        total_covered += len(covered_lines)

        changed_files.append({
            'path': rel_path,
            'added_lines': len(added_line_numbers),
            'covered_lines': len(covered_lines),
            'uncovered_lines': len(uncovered_lines),
            'coverage_percent': (100.0 * len(covered_lines) / len(added_line_numbers)) if added_line_numbers else None,
            'diff_text': ''.join(difflib.unified_diff(
                primary_lines,
                secondary_lines,
                fromfile=f'pr2/{rel_path}',
                tofile=f'exp2/{rel_path}',
                lineterm='\n',
            )),
        })

    total_uncovered = total_added - total_covered
    overall_coverage = (100.0 * total_covered / total_added) if total_added > 0 else None

    return {
        'changed_files': changed_files,
        'total_added': total_added,
        'total_covered': total_covered,
        'total_uncovered': total_uncovered,
        'overall_coverage': overall_coverage,
    }


def _format_percent(value):
    if value is None:
        return 'N/A'
    return f'{value:.2f}%'


def _format_score(report):
    if report is None or report.final_score is None:
        return 'N/A'
    return f'{float(report.final_score):.2f}'


def _render_results_markdown(student_name: str, student_key: str, primary_report, secondary_report, primary_label: str, secondary_label: str) -> str:
    primary_counts = _get_report_test_counts(primary_report)
    secondary_counts = _get_report_test_counts(secondary_report)

    def _coverage_percent(report):
        if report is None or report.results_path is None:
            return None
        path = os.path.join(report.results_path, 'coverage.json')
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as fin:
            data = json.load(fin)
        percent = data.get('totals', {}).get('percent_covered')
        if percent is None:
            percent = data.get('meta', {}).get('coverage_percent')
        return percent

    primary_cov = _coverage_percent(primary_report)
    secondary_cov = _coverage_percent(secondary_report)

    lines = [
        f'# {student_name}',
        '',
        '## Resultats dels tests',
        '',
        '| Cas | Success | Num tests | Passats | Fallats | Cobertura | Score |',
        '|---|---:|---:|---:|---:|---:|---:|',
        f'| {primary_label} | {primary_report.success if primary_report else None} | {primary_counts["total"]} | {primary_counts["passed"]} | {primary_counts["failed"]} | {_format_percent(primary_cov)} | {_format_score(primary_report)} |',
        f'| {secondary_label} | {secondary_report.success if secondary_report else None} | {secondary_counts["total"]} | {secondary_counts["passed"]} | {secondary_counts["failed"]} | {_format_percent(secondary_cov)} | {_format_score(secondary_report)} |',
        '',
    ]

    diff_summary = _build_diff_summary(
        _get_workdir_root(primary_report.submission.get_local_path(), 'backend') if primary_report else '',
        _get_workdir_root(secondary_report.submission.get_local_path(), 'backend') if secondary_report else '',
        secondary_report=secondary_report,
    )

    lines.extend([
        '## Resum dels canvis fets',
        '',
        f'- Fitxers canviats: {len(diff_summary["changed_files"])}',
        f'- Línies afegides a {secondary_label}: {diff_summary["total_added"]}',
        f'- Línies cobertes per tests: {diff_summary["total_covered"]}',
        f'- Línies no cobertes: {diff_summary["total_uncovered"]}',
        '',
        '| Fitxer | Línies afegides | Cobertes | No cobertes | Cobertura |',
        '|---|---:|---:|---:|---:|',
    ])

    for item in diff_summary['changed_files']:
        lines.append(
            f'| {item["path"]} | {item["added_lines"]} | {item["covered_lines"]} | {item["uncovered_lines"]} | {_format_percent(item["coverage_percent"])} |'
        )

    lines.extend([
        '',
        '## Cobertura dels canvis',
        '',
        f'- Cobertura global de les línies noves a {secondary_label}: {_format_percent(diff_summary["overall_coverage"])}',
        '',
        f'Vegeu també `Diff.md` per al diff unificat complet.',
        '',
    ])

    return '\n'.join(lines)


def _render_diff_markdown(student_name: str, diff_summary: dict) -> str:
    lines = [f'# Diff - {student_name}', '']
    for item in diff_summary['changed_files']:
        lines.extend([
            f'## {item["path"]}',
            '```diff',
            item['diff_text'].rstrip('\n'),
            '```',
            '',
        ])
    return '\n'.join(lines)


def export_group_results_markdown(output_root: str, group: str, primary_reports: dict, secondary_reports: dict, primary_label: str = 'lliuraments', secondary_label: str = 'exp2'):
    results_root = os.path.join(output_root, 'results', group)
    os.makedirs(results_root, exist_ok=True)

    for report_key, base_report, primary_report, secondary_report in _iter_report_pairs(primary_reports, secondary_reports):
        if base_report is None:
            continue
        assert base_report is not None
        student_info = _get_report_student_info(base_report)
        student_name = student_info['student_name']
        student_key = _sanitize_path_component(str(student_info['submission_key']))
        student_root = os.path.join(results_root, student_key)
        os.makedirs(student_root, exist_ok=True)

        primary_workdir = _get_workdir_root(primary_report.submission.get_local_path(), 'backend') if primary_report else ''
        secondary_workdir = _get_workdir_root(secondary_report.submission.get_local_path(), 'backend') if secondary_report else ''
        diff_summary = _build_diff_summary(primary_workdir, secondary_workdir, secondary_report=secondary_report)

        results_md = _render_results_markdown(str(student_name), student_key, primary_report, secondary_report, primary_label, secondary_label)
        diff_md = _render_diff_markdown(str(student_name), diff_summary)

        with open(os.path.join(student_root, 'Results.md'), 'w', encoding='utf-8') as fout:
            fout.write(results_md)
        with open(os.path.join(student_root, 'Diff.md'), 'w', encoding='utf-8') as fout:
            fout.write(diff_md)


def export_combined_results(
    output_file: str,
    primary_reports: dict,
    secondary_reports: dict,
    primary_label: str = 'lliuraments',
    secondary_label: str = 'exp2',
    primary_weight: float = 0.5,
    secondary_weight: float = 0.5,
):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                'student_id',
                'student_name',
                'groups',
                f'{primary_label}_submission_key',
                f'{primary_label}_success',
                f'{primary_label}_score',
                f'{primary_label}_tests_total',
                f'{primary_label}_tests_passed',
                f'{primary_label}_tests_failed',
                f'{secondary_label}_submission_key',
                f'{secondary_label}_success',
                f'{secondary_label}_score',
                f'{secondary_label}_tests_total',
                f'{secondary_label}_tests_passed',
                f'{secondary_label}_tests_failed',
                'combined_score',
            ],
        )
        writer.writeheader()

        for report_key, base_report, primary_report, secondary_report in _iter_report_pairs(primary_reports, secondary_reports):
            base_report = primary_report or secondary_report
            student_info = _get_report_student_info(base_report)
            primary_test_counts = _get_report_test_counts(primary_report)
            secondary_test_counts = _get_report_test_counts(secondary_report)
            combined_score = _combine_scores(
                primary_report,
                secondary_report,
                primary_weight=primary_weight,
                secondary_weight=secondary_weight,
            )

            writer.writerow({
                'student_id': student_info['student_id'],
                'student_name': student_info['student_name'],
                'groups': student_info['groups'],
                f'{primary_label}_submission_key': student_info['submission_key'] if primary_report else None,
                f'{primary_label}_success': primary_report.success if primary_report else None,
                f'{primary_label}_score': round(primary_report.final_score, 2) if primary_report and primary_report.final_score is not None else None,
                f'{primary_label}_tests_total': primary_test_counts['total'],
                f'{primary_label}_tests_passed': primary_test_counts['passed'],
                f'{primary_label}_tests_failed': primary_test_counts['failed'],
                f'{secondary_label}_submission_key': secondary_report.submission.get_key() if secondary_report else None,
                f'{secondary_label}_success': secondary_report.success if secondary_report else None,
                f'{secondary_label}_score': round(secondary_report.final_score, 2) if secondary_report and secondary_report.final_score is not None else None,
                f'{secondary_label}_tests_total': secondary_test_counts['total'],
                f'{secondary_label}_tests_passed': secondary_test_counts['passed'],
                f'{secondary_label}_tests_failed': secondary_test_counts['failed'],
                'combined_score': round(combined_score, 2) if combined_score is not None else None,
            })


def run_group_tests(
    input_path: str,
    participants_csv: str,
    output_root: str,
    target_groups: list[str],
    submission_test_class: str,
    tester_options: dict,
    report_prefix: str,
    report_remove_groups: list[str] | None = None,
    remove_existing: bool = True,
):
    if report_remove_groups is None:
        report_remove_groups = []

    teaching_lib.submission_utils.export_groups(
        input_path,
        participants_csv,
        output_root,
        remove_existing=remove_existing,
        groups=target_groups,
    )

    reports_by_group = {}
    for group in target_groups:
        submissions = SubmissionSet.load_submissions(os.path.join(output_root, 'groups', group))
        cache_file = os.path.join(output_root, f'cache_{report_prefix}_{group}.pkl')
        if remove_existing and os.path.exists(cache_file):
            os.remove(cache_file)
        tester = teaching_lib.code_tester.CodeActivityTester(
            submissions,
            submission_test_class,
            options=tester_options,
        )
        tester.run_tests(cache_file=cache_file)
        tester.export_results(
            os.path.join(output_root, f'report_{report_prefix}_{group}.csv'),
            override=True,
            format='csv',
            remove_groups=report_remove_groups,
        )
        reports_by_group[group] = tester.get_reports()

    return reports_by_group


def launch_streamlit_final_report(
    results_root: str,
    default_group: str | None = None,
    default_student: str | None = None,
    host: str = '127.0.0.1',
    port: int = 8501,
    headless: bool = False,
):
    app_path = Path(__file__).resolve().with_name('final_report.py')
    if not app_path.exists():
        raise FileNotFoundError(f'Final report app not found: {app_path}')

    env = os.environ.copy()
    env['FINAL_REPORT_RESULTS_ROOT'] = os.path.abspath(results_root)
    if default_group:
        env['FINAL_REPORT_DEFAULT_GROUP'] = default_group
    if default_student:
        env['FINAL_REPORT_DEFAULT_STUDENT'] = default_student

    cmd: list[str] = [
        'streamlit',
        'run',
        str(app_path),
        '--server.address',
        host,
        '--server.port',
        str(port),
        '--server.headless',
        'true' if headless else 'false',
    ]

    logger.info('Launching final report app: %s', cmd)
    subprocess.run(cmd, check=False, env=env)

if __name__ == '__main__':

    print("SD")

    target_groups = ['B', 'C']
    #target_groups = ['C']

    clean_data = False
    repo_stats = False

    pr1 = False
    pr2 = True
    launch_final_report_web = False

    if pr1:

        if repo_stats:

            for target_group in target_groups:
                repositories = teaching_lib.repository.CodeRepositorySet()
                repositories.load_repositories(f'SoftwareDistribuitUB-2025/practica-1-{target_group.lower()}', 11, 25)

                repositories.export_stats(f'./_data/sd/26/pr1/repo_stats/{target_group}/')

        # Exporta tots els lliuraments i els separa per grups
        teaching_lib.submission_utils.export_groups(
            './_data/sd/26/pr1/lliuraments',
            './_data/sd/26/pr1/courseid_102337_participants.csv',
            './_data/sd/26/pr1/out',
            remove_existing=True,
            groups=target_groups,
        )

        for group in target_groups:
            submissions = SubmissionSet.load_submissions(f'./_data/sd/26/pr1/out/groups/{group}')
            tester = teaching_lib.code_tester.CodeActivityTester(
                submissions,
                'teaching_utils.teaching_lib.code_tester.JavaSubmissionTest',
                options={
                    "max_time": 240,
                    "run_tests": True,
                    "docker_pull_policy": "never",
                    "perform_analysis": False,
                    "code_extraction_max_char": -1,
                    "host_tmp_basepath": "./_data/sd/26/pr1/tmp",
                    "remove_tmp": False,
                    "multi_project": True,
                    "multi_project_structure": "folder",
                    "multi_project_module_regex": {
                        'Client': 'Client',
                        'ComUtils': 'ComUtils',
                        'Server': 'Server',
                    }
                },
            )
            tester.run_tests(cache_file=f'./_data/sd/26/pr1/out/cache_group_{group}.pkl')
            tester.export_results(f'./_data/sd/26/pr1/out/report{group}.csv',
                                  override=True,
                                  format='csv',
                                  remove_groups=['2025_364312_Q2_T1']
                                  )
            tester.export_code(f'./_data/sd/26/pr1/out/prepared/{group}',
                                  override=True,
                                  format='md'
                                  )

    if pr2:

        if repo_stats:

            for target_group in target_groups:
                repositories = teaching_lib.repository.CodeRepositorySet()
                repositories.load_repositories(f'SoftwareDistribuitUB-2026/pr-actica2-{target_group.lower()}', 1, 25)

                repositories.export_stats(f'./_data/sd/26/pr2/repo_stats/{target_group}/')

        participants_csv = './_data/sd/26/pr2/courseid_102337_participants.csv'
        primary_output_root = './_data/sd/26/pr2/out'
        validation_output_root = './_data/sd/26/pr2/out_exp2'
        report_remove_groups = ['2025_364312_Q2_T1']

        tester_options = {
            "container_runtime": "podman",
            "max_time": 60,
            "perform_analysis": False,
            "code_extraction_max_char": -1,
            "host_tmp_basepath": "./_data/sd/26/pr2/tmp",
            "remove_tmp": False,
            "working_directory": "backend",
        }

        primary_reports = run_group_tests(
            input_path='./_data/sd/26/pr2/lliuraments',
            participants_csv=participants_csv,
            output_root=primary_output_root,
            target_groups=target_groups,
            submission_test_class='teaching_utils.teaching_lib.code_tester.PythonSubmissionTest',
            tester_options=tester_options,
            report_prefix='lliuraments',
            report_remove_groups=report_remove_groups,
            remove_existing=True,
        )

        validation_reports = run_group_tests(
            input_path='./_data/sd/26/pr2/exp2',
            participants_csv=participants_csv,
            output_root=validation_output_root,
            target_groups=target_groups,
            submission_test_class='teaching_utils.teaching_lib.code_tester.PythonSubmissionTest',
            tester_options=tester_options,
            report_prefix='exp2',
            report_remove_groups=report_remove_groups,
            remove_existing=True,
        )

        for group in target_groups:
            export_combined_results(
                output_file=os.path.join(primary_output_root, f'report_combined_{group}.csv'),
                primary_reports=primary_reports[group],
                secondary_reports=validation_reports[group],
                primary_label='lliuraments',
                secondary_label='exp2',
            )
            export_group_results_markdown(
                output_root=primary_output_root,
                group=group,
                primary_reports=primary_reports[group],
                secondary_reports=validation_reports[group],
                primary_label='lliuraments',
                secondary_label='exp2',
            )

        if launch_final_report_web:
            launch_streamlit_final_report(
                results_root=os.path.join(primary_output_root, 'results'),
                default_group=target_groups[0] if target_groups else None,
                headless=False,
            )


    """import json

    with open('C:\\Users\\xavie\\OneDrive\\Escriptori\\Uptitude_JSON.json', 'r', encoding='utf-8') as answ:
        data = json.load(answ)

    print(data)

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(level=logging.INFO)

    repositories = teaching_lib.repository.CodeReposotorySet()
    repositories.load_repositories('SoftwareDistribuitUB-2024/practica2-b', 1, 20)

    # repositories.clone_all(force=False)

    # test_repo = repositories[0]

    # repo_1 = repositories.get_repository('SoftwareDistribuitUB-2024/practica2-b', 3)

    # repo_stats = repo_1.get_stats()
    repositories.print_stats()

    # test_results = repo_1.test('python', './backend')

    # print(repo_stats)


    print("SD 24-25")

    clean_data = False
    submissions = None

    # Remove imported data
    if clean_data:
        shutil.rmtree('../_data/sd/pr1/out/submissions')
        print(f'Removed all imported submissions')

    # Import submissions from Moodle ZIP download
    out_path = '../_data/sd/pr1/out/submissions'
    if not os.path.exists(out_path):
        submissions = MoodleSubmissionSet('../_data/sd/pr1/courseid_87020_participants.csv', '../_data/sd/pr1/out/submissions')
        submissions.import_submissions('../_data/sd/pr1/lliuraments')
        print(f'Imported {len(submissions)} submissions')

    # Alternative (Import already extracted submissions)
    #subs = SubmissionSet.load_submissions('../_data/sd/pr1/out/submissions')

    # Export submissions of a particular group
    group = 'C'
    if not os.path.exists(f'../_data/sd/pr1/out/groups/{group}'):
        if submissions is None:
            submissions = SubmissionSet.load_submissions('../_data/sd/pr1/out/submissions')
        gr_submissions = submissions.exportGroup(group=group, output_folder=f'../_data/sd/pr1/out/groups/{group}', exist_ok=True, remove_existing=True)
        print(f'Exported {len(gr_submissions)} submissions for group {group}')

    # Grup B
    subs_B = SubmissionSet.load_submissions('../_data/sd/pr1/out/groups/B')
    print("Num lliuraments:", len(subs_B))

    # Grup C
    subs_C = SubmissionSet.load_submissions('../_data/sd/pr1/out/groups/C')
    print("Num lliuraments:", len(subs_C))
"""
    # Exporta tots els lliuraments i els separa per grups
    #teaching_lib.submission_utils.export_groups(
    #    '../_data/sd/pr1/lliuraments',
    #    '../_data/sd/pr1/courseid_87020_participants.csv',
    #    '../_data/sd/pr1/out',
    #    remove_existing=False,
    #    groups=['B', 'C', 'F'],
    #)

    #config = {
    #    "image": "maven:latest",
    #    "max_time": 30,
    #    "run_cmd": "cd /mnt/code && ./run_tests.sh",
    #    "result_path": "/mnt/code/results",
    #    "grading_file": "results.json"
    #}

    #subs_C = SubmissionSet.load_submissions('../_data/sd/pr1/out/groups/C')
    #submission = subs_C[0]

    #java_runner = teaching_lib.code_tester.JavaSubmissionTest(submission.get_local_path())
    #report = java_runner.run()

    #print(f"Final Score: {report.final_score:.2f}")
    #print(f"Tree Root: {report.test_tree.label}")
    #print(f"Num Tests: {report.total_tests}")
"""
    submissions = SubmissionSet.load_submissions('./_data/sd/pr1/out/groups/C')
    tester = teaching_lib.code_tester.CodeActivityTester(
        submissions,
        'teaching_utils.teaching_lib.code_tester.JavaSubmissionTest',
        options={
            "max_time": 30,
            "perform_analysis": False,
            "code_extraction_max_char": -1,
        },
    )
    tester.run_tests()
    tester.export_results('./_data/sd/pr1/out/report.csv',
                          override=True,
                          format='csv',
                          remove_groups=['2024_364312_Q2_T1']
                          )

"""
