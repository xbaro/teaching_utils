import argparse
import os
import logging
import shutil
from teaching_utils import teaching_lib

logger = logging.getLogger(__name__)

def load_moodle_submissions(input_path: str, out_path: str, learners_csv: str, clean_data: bool = False):
    # Remove imported data
    if clean_data:
        if os.path.exists(out_path):
            shutil.rmtree(out_path)
        print(f'Removed all imported submissions')

    # Import submissions from Moodle ZIP download
    if not os.path.exists(out_path):
        submissions = teaching_lib.submissions.MoodleSubmissionSet(
            learners_csv,
            out_path)
        submissions.import_submissions(input_path)
        print(f'Imported {len(submissions)} submissions')
    else:
        # Alternative (Import already extracted submissions)
        submissions = teaching_lib.submissions.SubmissionSet.load_submissions(out_path)

    return submissions


def print_repo_stats(base: str, groups: str | list[str] | None = None, min_group: int = 1, max_group: int = 20,
                     clone: bool = False, force: bool = False, local_path: str | None = None) -> None:

    repositories = teaching_lib.repository.CodeRepositorySet(export_path=local_path)

    if groups is None:
        groups = ['a', 'b', 'c', 'f']
    elif type(groups) is str:
        groups = [groups]

    for group in groups:
        repositories.load_repositories(f'{base}{group}', min_group, max_group)

    if clone and local_path is not None:
        repositories.clone_all(force=force, export_path=local_path)
        #repositories.export_files('./_data/export_shaders/', 'resources/GPUshaders', 'glsl')

    repositories.print_stats()


def fix_data(data):
    data['COGNOMS'] = data['COGNOMS. LAST NAME.']
    data['NOM'] = data['NOM. NAME']
    data['NIUB'] = data['NIUB. PASSPORT NUMBER']
    return data

def extract_form_stats():
    form_data = teaching_lib.form_data_reader.FormDataReader('./_data/givd/2526/pr1/form/pr1_evals.xlsx',
                                                             {
                                                                 'fix_callback': fix_data,
                                                             })
    form_data.print_stats()

    form_data.export_group('./_data/givd/2526/pr2/form/grup_A_evals.txt','A')
    form_data.export_group('./_data/givd/2526/pr2/form/grup_B_evals.txt', 'B')
    form_data.export_group('./_data/givd/2526/pr2/form/grup_C_evals.txt', 'C')
    form_data.export_group('./_data/givd/2526/pr2/form/grup_F_evals.txt', 'F')


def run_moodle_import_workflow() -> None:
    data_path = './_data/GiVD2526/pr1'
    moodle_submissions = f'{data_path}/a/lliuraments'
    csv_file = f'{data_path}/b/2526GIVDD Qualificacions-20260327_0736-comma_separated.csv'
    out_path = f'{data_path}/a/output'

    load_moodle_submissions(moodle_submissions, out_path, csv_file, clean_data=False)


def run_repo_stats_workflow() -> None:
    groups = 'b'
    print_repo_stats(
        'GiVD-2025/p1-tracertoy-',
        groups,
        1,
        20,
        True,
        force=False,
        local_path='./_data/givd/2526/pr1/repositories'
    )


def run_form_stats_workflow() -> None:
    extract_form_stats()

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='GiVD teaching utilities workflows')
    parser.add_argument(
        '--workflow',
        choices=['moodle', 'repo-stats', 'form-stats'],
        default='moodle',
        help='Workflow to execute'
    )
    args = parser.parse_args()

    if args.workflow == 'moodle':
        run_moodle_import_workflow()
    elif args.workflow == 'repo-stats':
        run_repo_stats_workflow()
    else:
        run_form_stats_workflow()
