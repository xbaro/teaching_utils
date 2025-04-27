import logging
import os
import shutil
import json

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.code_tester import TestResultNode
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

logger = logging.getLogger(__name__)


def parse_gtest_results(testsuite):

    # Get data from current test suite
    test_results = TestResultNode(
        label=testsuite.get("name", "Unknown"),
        weight = 1.0,
        children = []
    )

    if 'testsuites' in testsuite:
        # Iterate over all testsuites
        for testsuite in testsuite['testsuites']:
            test_results.children.append(parse_gtest_results(testsuite))
    elif 'testsuite' in testsuite:
        # Iterate over all tests
        for testsuite in testsuite['testsuite']:
            test_results.children.append(parse_gtest_results(testsuite))
    else:
        # Iterate over all tests
        for test in testsuite['testcase']:
            test_results.children.append(
                TestResultNode(
                    label=test.get("name", "Unknown"),
                    weight = 1.0,
                    passed=test.get("status", "Unknown") == "passed",
                    message=test.get("message", ""),
                    children=[]
                )
            )
    return test_results

def load_test_results():

    raw = json.load(open('../_data/ed/pr2/tmp/submission_1a7a5ca3ed6446dc8ea9c3880ead849d/code/results/report_ex1.json', 'r'))

    return parse_gtest_results(raw)




if __name__ == '__main__':

    print("ED")

    clean_data = False

    pr1 = False
    pr2 = True


    #load_test_results()


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

        #submissions = SubmissionSet.load_submissions('../_data/ed/pr2/out/submissions')
        submissions = SubmissionSet.load_submissions('../_data/ed/pr2/out/groups/GrupB')
        tester = teaching_lib.code_tester.CodeActivityTester(
            submissions,
            'teaching_utils.teaching_lib.code_tester.CSubmissionTest',
            options={
                "max_time": 240,
                "perform_analysis": False,
                "code_extraction_max_char": -1,
                "data_path": "../_data/ed/pr2/data",
                "host_tmp_basepath": "../_data/ed/pr2/tmp",
                "remove_tmp": False,
            },
        )
        #tester.run_tests(start=0, limit=3, cache_file='../_data/ed/pr2/out/cache_all_groups.pkl')
        tester.run_tests(start=1, limit=3)
        tester.export_results('../_data/ed/pr2/out/report.csv',
                              override=True,
                              format='csv',
                              remove_groups=['2024_364301_Q2_M1', '2024_364301_Q2_M2']
                              )

