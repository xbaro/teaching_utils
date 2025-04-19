import logging
import os
import shutil

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

logger = logging.getLogger(__name__)

if __name__ == '__main__':

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
    #    groups=['B', 'C'],
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

    submissions = SubmissionSet.load_submissions('../_data/sd/pr1/out/groups/C')
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
    tester.export_results('../_data/sd/pr1/out/report.csv',
                          override=True,
                          format='csv',
                          remove_groups=['2024_364312_Q2_T1']
                          )
