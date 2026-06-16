from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


class _MissingStreamlit:
    def __getattr__(self, name: str):
        if name == 'cache_data':
            def _decorator(*args, **kwargs):
                def _wrap(func):
                    return func

                return _wrap

            return _decorator
        raise ModuleNotFoundError('streamlit is required to run this app')


try:
    st = importlib.import_module('streamlit')
except ModuleNotFoundError:
    st = _MissingStreamlit()


APP_TITLE = 'Final report'
DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parents[1] / '_data' / 'sd' / '26' / 'pr2' / 'out' / 'results'
ENV_RESULTS_ROOT = 'FINAL_REPORT_RESULTS_ROOT'
ENV_DEFAULT_GROUP = 'FINAL_REPORT_DEFAULT_GROUP'
ENV_DEFAULT_STUDENT = 'FINAL_REPORT_DEFAULT_STUDENT'


@dataclass(frozen=True)
class TestCaseRow:
    case: str
    success: str
    num_tests: str
    passed: str
    failed: str
    coverage: str
    score: str


@dataclass(frozen=True)
class FileDiffRow:
    path: str
    added_lines: str
    covered_lines: str
    uncovered_lines: str
    coverage: str
    diff_text: str


@dataclass(frozen=True)
class StudentReportBundle:
    group: str
    student_key: str
    student_name: str
    results_path: Path
    diff_path: Path
    test_rows: list[TestCaseRow]
    summary_lines: list[str]
    file_rows: list[FileDiffRow]
    results_text: str
    diff_text: str


@st.cache_data(show_spinner=False)
def _safe_read_text(path: Path) -> str:
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8', errors='ignore')


def _parse_markdown_table(block_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    for line in block_lines:
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        cells = [cell.strip() for cell in stripped.strip('|').split('|')]
        rows.append(cells)
    if len(rows) < 2:
        return [], []
    header = rows[0]
    data_rows = [row for row in rows[2:] if len(row) == len(header)]
    return header, data_rows


def _extract_section(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx + 1
            break
    if start is None:
        return []
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith('## '):
            break
        collected.append(line)
    return collected


def _parse_file_coverage_table(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == '| Fitxer | Línies afegides | Cobertes | No cobertes | Cobertura |':
            start = idx
            break
    if start is None:
        return []

    block: list[str] = []
    for line in lines[start:]:
        if block and not line.strip():
            break
        if line.strip().startswith('|'):
            block.append(line)

    _, data_rows = _parse_markdown_table(block)
    parsed: list[dict[str, str]] = []
    for row in data_rows:
        if len(row) != 5:
            continue
        parsed.append(
            {
                'Fitxer': row[0],
                'Línies afegides': row[1],
                'Cobertes': row[2],
                'No cobertes': row[3],
                'Cobertura': row[4],
            }
        )
    return parsed


def _parse_results_md(path: Path) -> tuple[str, list[TestCaseRow], list[str], list[dict[str, str]]]:
    text = _safe_read_text(path)
    if not text:
        return '', [], [], []

    title = ''
    for line in text.splitlines():
        if line.startswith('# '):
            title = line[2:].strip()
            break

    test_section = _extract_section(text, '## Resultats dels tests')
    _, test_data = _parse_markdown_table(test_section)
    test_rows: list[TestCaseRow] = []
    for row in test_data:
        if len(row) != 7:
            continue
        test_rows.append(
            TestCaseRow(
                case=row[0],
                success=row[1],
                num_tests=row[2],
                passed=row[3],
                failed=row[4],
                coverage=row[5],
                score=row[6],
            )
        )

    summary_section = _extract_section(text, '## Resum dels canvis fets')
    summary_lines = [line.strip()[2:].strip() for line in summary_section if line.strip().startswith('- ')]

    coverage_rows = _parse_file_coverage_table(text)

    return title, test_rows, summary_lines, coverage_rows


_DIFF_BLOCK_RE = re.compile(r'^## (?P<path>.+?)\n```diff\n(?P<diff>.*?)\n```\s*$', re.M | re.S)


def _parse_diff_md(path: Path) -> list[FileDiffRow]:
    text = _safe_read_text(path)
    if not text:
        return []

    rows: list[FileDiffRow] = []
    for match in _DIFF_BLOCK_RE.finditer(text):
        rows.append(
            FileDiffRow(
                path=match.group('path').strip(),
                added_lines='',
                covered_lines='',
                uncovered_lines='',
                coverage='',
                diff_text=match.group('diff').rstrip(),
            )
        )
    return rows


def _discover_groups(results_root: Path) -> list[str]:
    if not results_root.exists():
        return []
    groups = [entry.name for entry in results_root.iterdir() if entry.is_dir()]
    return sorted(groups)


def _discover_students(results_root: Path, group: str) -> list[Path]:
    group_root = results_root / group
    if not group_root.exists():
        return []
    return sorted([entry for entry in group_root.iterdir() if entry.is_dir() and (entry / 'Results.md').exists()])


def _student_label(results_root: Path, group: str, student_dir: Path) -> str:
    title, *_ = _parse_results_md(student_dir / 'Results.md')
    if title:
        return f'{title} — {student_dir.name}'
    return student_dir.name


@st.cache_data(show_spinner=False)
def _load_student_bundle(results_root_str: str, group: str, student_key: str) -> StudentReportBundle:
    results_root = Path(results_root_str)
    student_root = results_root / group / student_key
    results_path = student_root / 'Results.md'
    diff_path = student_root / 'Diff.md'

    results_text = _safe_read_text(results_path)
    diff_text = _safe_read_text(diff_path)
    student_name, test_rows, summary_lines, coverage_rows = _parse_results_md(results_path)
    diff_rows = _parse_diff_md(diff_path)

    coverage_map = {row['Fitxer']: row for row in coverage_rows}
    merged_rows: list[FileDiffRow] = []
    for item in diff_rows:
        coverage_row = coverage_map.get(item.path, {})
        merged_rows.append(
            FileDiffRow(
                path=item.path,
                added_lines=coverage_row.get('Línies afegides', ''),
                covered_lines=coverage_row.get('Cobertes', ''),
                uncovered_lines=coverage_row.get('No cobertes', ''),
                coverage=coverage_row.get('Cobertura', ''),
                diff_text=item.diff_text,
            )
        )

    return StudentReportBundle(
        group=group,
        student_key=student_key,
        student_name=student_name or student_key,
        results_path=results_path,
        diff_path=diff_path,
        test_rows=test_rows,
        summary_lines=summary_lines,
        file_rows=merged_rows,
        results_text=results_text,
        diff_text=diff_text,
    )


def _table_to_dataframe(rows: list[Any]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _render_header(bundle: StudentReportBundle) -> None:
    st.title(APP_TITLE)
    st.caption(f'Visor local per revisar PR2 vs exp2 · grup {bundle.group} · {bundle.student_name} · `{bundle.student_key}`')


def _render_test_comparison(bundle: StudentReportBundle) -> None:
    st.subheader('Comparativa de tests')

    if not bundle.test_rows:
        st.warning('No s\'ha pogut llegir la taula de tests del `Results.md`.')
        return

    labels = [row.case for row in bundle.test_rows]
    cols = st.columns(max(1, len(labels)))
    for col, row in zip(cols, bundle.test_rows, strict=False):
        with col:
            st.metric(
                label=row.case,
                value=f'{row.score}',
                delta=f'{row.passed}/{row.num_tests} tests',
            )
            st.write(
                {
                    'success': row.success,
                    'passed': row.passed,
                    'failed': row.failed,
                    'coverage': row.coverage,
                }
            )

    st.dataframe(
        _table_to_dataframe([row.__dict__ for row in bundle.test_rows]),
        use_container_width=True,
        hide_index=True,
    )


def _render_summary(bundle: StudentReportBundle) -> None:
    st.subheader('Resum dels canvis')
    if not bundle.summary_lines:
        st.info('No s\'ha trobat cap resum de canvis en el `Results.md`.')
        return

    for line in bundle.summary_lines:
        st.write(f'- {line}')

    st.divider()
    st.subheader('Cobertura del codi nou')

    rows = []
    for item in bundle.file_rows:
        rows.append(
            {
                'Fitxer': item.path,
                'Línies afegides': item.added_lines or '—',
                'Cobertes': item.covered_lines or '—',
                'No cobertes': item.uncovered_lines or '—',
                'Cobertura': item.coverage or '—',
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info('No s\'han trobat seccions de diff al `Diff.md`.')


def _render_diff_view(bundle: StudentReportBundle) -> None:
    st.subheader('Diff navegable')

    if not bundle.file_rows:
        st.warning('El `Diff.md` és buit o no s\'ha pogut parsejar.')
        return

    search = st.text_input('Filtra fitxers', value='')
    filtered = [item for item in bundle.file_rows if search.lower() in item.path.lower()]

    if not filtered:
        st.warning('No hi ha fitxers que coincideixin amb el filtre.')
        return

    chosen_path = st.selectbox('Selecciona un fitxer', [item.path for item in filtered])
    selected = next(item for item in filtered if item.path == chosen_path)

    st.markdown(f'### `{selected.path}`')
    st.write(
        {
            'línies afegides': selected.added_lines or '—',
            'cobertes': selected.covered_lines or '—',
            'no cobertes': selected.uncovered_lines or '—',
            'cobertura': selected.coverage or '—',
        }
    )
    st.code(selected.diff_text, language='diff')

    with st.expander('Mostra tots els fitxers', expanded=False):
        for item in filtered:
            with st.expander(item.path, expanded=False):
                st.code(item.diff_text, language='diff')


def _render_raw_files(bundle: StudentReportBundle) -> None:
    st.subheader('Fitxers font')
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            'Descarrega `Results.md`',
            data=bundle.results_text or '',
            file_name='Results.md',
            mime='text/markdown',
            use_container_width=True,
        )
    with col2:
        st.download_button(
            'Descarrega `Diff.md`',
            data=bundle.diff_text or '',
            file_name='Diff.md',
            mime='text/markdown',
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon='📊', layout='wide')

    st.markdown(
        '''
        <style>
        .stMetric { border: 1px solid rgba(128,128,128,0.18); padding: 0.4rem 0.6rem; border-radius: 0.6rem; }
        </style>
        ''',
        unsafe_allow_html=True,
    )

    default_root = os.getenv(ENV_RESULTS_ROOT, str(DEFAULT_RESULTS_ROOT))
    default_group = os.getenv(ENV_DEFAULT_GROUP)
    default_student = os.getenv(ENV_DEFAULT_STUDENT)

    with st.sidebar:
        st.header('Configuració')
        results_root = Path(st.text_input('Ruta arrel dels resultats', value=default_root))
        groups = _discover_groups(results_root)
        if not groups:
            st.warning('No hi ha grups visibles en aquesta carpeta.')
            st.stop()
        group_index = groups.index(default_group) if default_group in groups else 0
        group = st.selectbox('Grup', groups, index=group_index)
        student_dirs = _discover_students(results_root, group)
        if not student_dirs:
            st.warning('No hi ha estudiants amb `Results.md` per a aquest grup.')
            st.stop()
        student_labels = [_student_label(results_root, group, entry) for entry in student_dirs]
        default_student_index = 0
        if default_student:
            for idx, entry in enumerate(student_dirs):
                if entry.name == default_student:
                    default_student_index = idx
                    break
        student_key = st.selectbox('Estudiant', student_labels, index=default_student_index)
        st.caption('La web llegeix els `Results.md` i `Diff.md` ja generats.')

    # Recover the directory key from the label if we enriched it with the title.
    student_dir_key = student_key.rsplit(' — ', 1)[-1]
    bundle = _load_student_bundle(str(results_root), group, student_dir_key)

    _render_header(bundle)
    _render_test_comparison(bundle)
    st.divider()
    _render_summary(bundle)
    st.divider()
    _render_diff_view(bundle)
    st.divider()
    _render_raw_files(bundle)


if __name__ == '__main__':
    main()

