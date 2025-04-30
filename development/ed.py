import logging
import os
import shutil
import json

from teaching_utils import teaching_lib
from teaching_utils.teaching_lib.code_tester import TestResultNode
from teaching_utils.teaching_lib.submissions import SubmissionSet, MoodleSubmissionSet

from teaching_utils.teaching_lib.gtest_utils import load_gtest_results

logger = logging.getLogger(__name__)

if __name__ == '__main__':

    print("ED")

    clean_data = False

    pr1 = False
    pr2 = True

    if pr1:
        # Remove imported data
        if clean_data:
            shutil.rmtree('./_data/ed/pr1/out/submissions')
            print(f'Removed all imported submissions')

        # Import submissions from Moodle ZIP download
        out_path = './_data/ed/pr1/out/submissions'
        if not os.path.exists(out_path):
            submissions = MoodleSubmissionSet('./_data/ed/pr1/courseid_87000_participants.csv', './_data/ed/pr1/out/submissions')
            submissions.import_submissions('./_data/ed/pr1/lliuraments')
            print(f'Imported {len(submissions)} submissions')

        # Alternative (Import already extracted submissions)
        #subs = SubmissionSet.load_submissions('../_data/ed/pr1/out/submissions')

        # Export submissions of a particular group
        group = 'GrupB'
        if not os.path.exists(f'./_data/ed/pr1/out/groups/{group}'):
            grupB = submissions.exportGroup(group=group, output_folder=f'./_data/ed/pr1/out/groups/{group}', exist_ok=True, remove_existing=True)
            print(f'Exported {len(grupB)} submissions for group {group}')

        # Grup B
        subs = SubmissionSet.load_submissions('./_data/ed/pr1/out/groups/GrupB')
        print("Num lliuraments:", len(subs))


    if pr2:
        # Exporta tots els lliuraments i els separa per grups
        teaching_lib.submission_utils.export_groups(
            './_data/ed/pr2/lliuraments',
            './_data/ed/courseid_87000_participants.csv',
            './_data/ed/pr2/out',
            remove_existing=True,
            groups=['GrupA', 'GrupB', 'GrupC', 'GrupD', 'GrupF'],
        )

        analysis_prompt_criteria = {
            "EX1_CRITERIA": ("- C1: Constructor (weight: 0)\n"
            "- C2: Destructor (weight: 0)\n"
            "- C3: isEmpty (weight: 0.25)\n"
            "- C4: isFull (weight: 0.25)\n"
            "- C5: getFront (weight: 0.25)\n"
            "- C6: enqueue (weight: 0.5)\n"
            "- C7: dequeue (weight: 0.5)\n"
            "- C8: print (weight: 0.25)\n"),
            "EX2_CRITERIA": ()

        }
        analysis_prompt_template = (
            "You are a university-level programming instructor evaluating code submitted by a student in an undergraduate computer science course.\n"
            "Please analyze the code in a friendly, constructive, and pedagogical tone. Focus on the implementation and correctness of specific queue operations.\n"
            "Do not comment on or deduct points for the use of raw pointers versus smart pointers — students are just beginning to learn C++.\n"
            "Also, ignore the language used in comments and documentation — do not evaluate spelling, grammar, or language choice in comments or string literals.\n\n"
            "After the analysis, assign a final score from 0 to 100, based on the weighted average of the following criteria:\n\n"
            "- C1: Constructor (weight: 0)\n"
            "- C2: Destructor (weight: 0)\n"
            "- C3: isEmpty (weight: 0.25)\n"
            "- C4: isFull (weight: 0.25)\n"
            "- C5: getFront (weight: 0.25)\n"
            "- C6: enqueue (weight: 0.5)\n"
            "- C7: dequeue (weight: 0.5)\n"
            "- C8: print (weight: 0.25)\n\n"
            "Return the results as a JSON object with the following fields:\n"
            "- 'feedback': A written summary of the evaluation in Catalan, directed to the student.\n"
            "- 'score': A numeric value (0–100) representing the overall quality of the code.\n"
            "- 'criteria': A list of objects, each representing one evaluation criterion. Each object must include:\n"
            "    - 'id': A unique identifier for the criterion (e.g., 'C1')\n"
            "    - 'description': A brief description of the criterion (e.g., 'enqueue method')\n"
            "    - 'weight': The weight assigned to this criterion (as listed above)\n"
            "    - 'score': The score (from 0 to 100) given for this criterion\n"
            "    - 'justification': A short explanation of the score, including concrete examples from the submitted code "
            "(e.g., 'La funció `enqueue` gestiona bé la cua buida, però no comprova si hi ha prou memòria').\n\n"
            "The code to evaluate is:\n\n"
        )

        #submissions = SubmissionSet.load_submissions('./_data/ed/pr2/out/submissions')
        submissions = SubmissionSet.load_submissions('./_data/ed/pr2/out/groups/GrupB')
        tester = teaching_lib.code_tester.CodeActivityTester(
            submissions,
            'teaching_utils.teaching_lib.code_tester.CSubmissionTest',
            options={
                "max_time": 240,
                "perform_analysis": True,
                "code_extraction_max_char": -1,
                #"analysis_model": "codellama:70b",
                #"analysis_model": "codellama:34b",
                #"analysis_model": "codellama",
                #"analysis_engine": "ollama",
                "analysis_model": "gpt-4-turbo",
                "analysis_engine": "openai",
                "analysis_custom_prompt": {
                    analysis_prompt_template,
                },
                "data_path": "./_data/ed/pr2/data",
                "host_tmp_basepath": "./_data/ed/pr2/tmp",
                "remove_tmp": False,
                "multi_project": True,
                "multi_project_structure": "directory",
                "multi_project_module_regex": {
                    'Exercici1': '1',
                    'Exercici2': '2',
                    'Exercici3': '3',
                }

            },
        )
        #tester.run_tests(start=0, limit=3, cache_file='./_data/ed/pr2/out/cache_all_groups.pkl')
        tester.run_tests(start=1, limit=3)
        #tester.run_tests()
        #tester.run_tests(cache_file='./_data/ed/pr2/out/cache_all_groups.pkl')
        tester.export_results('./_data/ed/pr2/out/report.csv',
                              override=True,
                              format='csv',
                              remove_groups=['2024_364301_Q2_M1', '2024_364301_Q2_M2']
                              )

