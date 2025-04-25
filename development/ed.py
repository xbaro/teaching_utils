import logging
import os
import shutil

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    print("ED")

    clean_data = False

    pr1 = False
    pr2 = True

    if pr1:
        # Remove imported data
        if clean_data:
            shutil.rmtree('../_data/ed/pr1/out/submissions')
            print(f'Removed all imported submissions')

        # Import submissions from Moodle ZIP download
        out_path = '../_data/ed/pr1/out/submissions'
        if not os.path.exists(out_path):
            submissions = MoodleSubmissionSet('../_data/ed/pr1/courseid_87000_participants.csv', '../_data/ed/pr1/out/submissions')
            submissions.import_submissions('../_data/ed/pr1/lliuraments')
            print(f'Imported {len(submissions)} submissions')

        # Alternative (Import already extracted submissions)
        #subs = SubmissionSet.load_submissions('../_data/ed/pr1/out/submissions')

        # Export submissions of a particular group
        group = 'GrupB'
        if not os.path.exists(f'../_data/ed/pr1/out/groups/{group}'):
            grupB = submissions.exportGroup(group=group, output_folder=f'../_data/ed/pr1/out/groups/{group}', exist_ok=True, remove_existing=True)
            print(f'Exported {len(grupB)} submissions for group {group}')

        # Grup B
        subs = SubmissionSet.load_submissions('../_data/ed/pr1/out/groups/GrupB')
        print("Num lliuraments:", len(subs))


    if pr2:
        # Exporta tots els lliuraments i els separa per grups
        teaching_lib.submission_utils.export_groups(
            '../_data/ed/pr2/lliuraments',
            '../_data/ed/courseid_87000_participants.csv',
            '../_data/ed/pr2/out',
            remove_existing=False,
            groups=['GrupA', 'GrupB', 'GrupC', 'GrupD', 'GrupF'],
        )

        submissions = SubmissionSet.load_submissions('../_data/ed/pr2/out/submissions')
        tester = teaching_lib.code_tester.CodeActivityTester(
            submissions,
            'teaching_utils.teaching_lib.code_tester.CSubmissionTest',
            options={
                "max_time": 30,
                "perform_analysis": False,
                "code_extraction_max_char": -1,
                "data_path": "../_data/ed/pr2/data",
            },
        )
        tester.run_tests(start=0, limit=3, cache_file='../_data/ed/pr2/out/cache_all_groups.pkl')
        tester.export_results('../_data/ed/pr2/out/report.csv',
                              override=True,
                              format='csv',
                              remove_groups=['2024_364301_Q2_M1', '2024_364301_Q2_M2']
                              )

