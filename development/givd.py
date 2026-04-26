import argparse
import os
import logging
import shutil
from teaching_utils import teaching_lib

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

def load_moodle_submissions(input_path:str, out_path: str, learners_csv: str, clean_data: bool = False):
    # Remove imported data
    if clean_data:
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

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    # logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    #logging.basicConfig(level=logging.CRITICAL)

    #group = 'f'
    #repositories = teaching_lib.repository.CodeRepositorySet(export_path=f'./_data/GiVD2526/pr1/{group}/repositories')
    #repositories.load_repositories('GiVD2023/p2-zbtoy-b', 1, 9)
    #repositories.load_repositories('GiVD-2024/p1-pathtracingtoy-a', 1, 14)
    #repositories.load_repositories(f'GiVD-2025/p1-tracertoy-{group}', 4, 20)

    #repositories.clone_all(export_path=f'./_data/GiVD2526/pr1/{group}/repositories', force=False)

    # repositories.export_files('./_data/export_shaders/', 'resources/GPUshaders', 'glsl')

    #repositories.print_stats()

    data_path = './_data/GiVD2526/pr1'
    moodle_submissions = f'{data_path}/a/lliuraments'
    csv_file = f'{data_path}/b/2526GIVDD Qualificacions-20260327_0736-comma_separated.csv'
    out_path = f'{data_path}/a/output'

    submissions = load_moodle_submissions(moodle_submissions, out_path, csv_file, clean_data=False)


