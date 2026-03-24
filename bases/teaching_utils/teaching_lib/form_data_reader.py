import math
import pandas as pd
import numpy as np

class FormDataReader:
    def __init__(self, data_path: str, config: dict = None):
        """
        Reader for form data results
        """
        self._config = {}
        if config is not None:
            self._config.update(config)

        self._data = FormDataReader.read_file(data_path)

        # Fix group information if needed
        if config is not None and 'fix_callback' in config:
            self._data = config['fix_callback'](self._data)

        self._group_data = FormDataReader.get_groups_data(self._data)
        self._group_data_fixed = FormDataReader.fix_groups_data(self._group_data)
        self._results_data = FormDataReader.compute_results_data(self._group_data_fixed)
        self._final_data = FormDataReader.extract_data(self._results_data)


    @property
    def data(self):
        return self._data

    @property
    def group_data(self):
        return self._group_data

    @property
    def group_data_fixed(self):
        return self._group_data_fixed

    def to_excel(self, path: str):
        self._final_data.to_excel(path)

    @staticmethod
    def levenshteinDistance(a, b):
        A = a.upper()
        B = b.upper()
        N, M = len(A), len(B)
        # Create an array of size NxM
        dp = [[0 for i in range(M + 1)] for j in range(N + 1)]

        # Base Case: When N = 0
        for j in range(M + 1):
            dp[0][j] = j
        # Base Case: When M = 0
        for i in range(N + 1):
            dp[i][0] = i
        # Transitions
        for i in range(1, N + 1):
            for j in range(1, M + 1):
                if A[i - 1] == B[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(
                        dp[i - 1][j],  # Insertion
                        dp[i][j - 1],  # Deletion
                        dp[i - 1][j - 1]  # Replacement
                    )

        return dp[N][M]

    # Defining main function
    @staticmethod
    def read_file(file: str) -> pd.DataFrame:
        raw_data = pd.read_excel(file, header=0)
        return raw_data

    @staticmethod
    def get_groups_data(data: pd.DataFrame):
        sorted_data = data.sort_values(['Equip', 'COGNOMS', 'NOM'])
        sorted_data['NomComplert'] = sorted_data['COGNOMS'] + ', ' + sorted_data['NOM']
        group_ids = sorted_data['Equip'].unique()

        groups = {}
        for gr in group_ids:
            if gr not in groups:
                groups[gr] = {
                    'status': 0,  # OK
                    'errors': [],
                    'members': {},
                    'comments': {},
                    'evaluation': {}
                }
            data_gr = sorted_data.loc[(sorted_data['Equip'] == gr)]
            members = data_gr['NomComplert'].unique()
            for id, member in enumerate(members):
                member_row = data_gr.loc[data_gr['NomComplert'] == member]
                groups[gr]['members'][member] = {
                    'nom': member_row['NOM'].values[0],
                    'cognoms': member_row['COGNOMS'].values[0],
                    'niub': member_row['NIUB'].values[0],
                    'm_id': id,
                    'self_eval': member_row.values[0][5:10],
                    'obs_globals': member_row.values[0][17],
                    'reflexions_globals': member_row.values[0][18],
                    'others_eval': {},
                    'others_eval_err': []
                }
                for i in range(1):
                    #eval_data = data_gr.loc[data_gr['NomComplert'] == member].values[0][13 + (4 * i):16 + (4 * i)]
                    eval_data = np.concat((data_gr.loc[data_gr['NomComplert'] == member].values[0][13:14], np.array([-1]), data_gr.loc[data_gr['NomComplert'] == member].values[0][14:16]))
                    if not isinstance(eval_data[0], str) or not isinstance(eval_data[1], str):
                        break
                    if eval_data[0].strip() in ['--', 'Nan', '.', '']:
                        break
                    nom_complert = eval_data[0] + ', ' + eval_data[1]
                    m_id = -1
                    m_dist = math.inf
                    for m in range(len(members)):
                        if members[m] == member:
                            # Skip with same user
                            continue
                        dist = FormDataReader.levenshteinDistance(nom_complert, members[m])
                        # print(f'dist {nom_complert} <-> {members[m]} ==> {dist}')
                        if dist < m_dist:
                            m_dist = dist
                            m_id = m
                    if m_id > -1:
                        if members[m_id] in groups[gr]['members'][member]['others_eval']:
                            if groups[gr]['members'][member]['others_eval'][members[m_id]]['m_dist'] > m_dist:
                                groups[gr]['errors'].append(
                                    f"ERROR: Duplicated member matching. Replaced {groups[gr]['members'][member]['others_eval'][members[m_id]]}[name = {groups[gr]['members'][member]['others_eval'][members[m_id]]['src_name']}] by {nom_complert}"
                                )
                                groups[gr]['members'][member]['others_eval_err'].append(
                                    groups[gr]['members'][member]['others_eval'][members[m_id]])
                                groups[gr]['members'][member]['others_eval'][members[m_id]] = {
                                    'm_id': id,
                                    'm_dist': m_dist,
                                    'src_name': nom_complert,
                                    'dst_name': members[m_id],
                                    'eval': eval_data[2:6],
                                    'comments': eval_data[6]
                                }
                            else:
                                groups[gr]['errors'].append(
                                    f"ERROR: Duplicated member matching. Skipped {nom_complert} for {groups[gr]['members'][member]['others_eval'][members[m_id]]}[name = {groups[gr]['members'][member]['others_eval'][members[m_id]]['src_name']}]"
                                )
                                groups[gr]['members'][member]['others_eval_err'].append({
                                    'm_id': id,
                                    'm_dist': m_dist,
                                    'src_name': nom_complert,
                                    'dst_name': members[m_id],
                                    'eval': eval_data[2:6],
                                    'comments': eval_data[6]
                                })
                            print(f'ERROR in group {gr}')
                            groups[gr]['status'] = 2  # ERROR
                        else:
                            groups[gr]['members'][member]['others_eval'][members[m_id]] = {
                                'm_id': id,
                                'm_dist': m_dist,
                                'src_name': nom_complert,
                                'dst_name': members[m_id],
                                'eval': eval_data[2:6],
                                'comments': eval_data[6]
                            }

        return groups

    @staticmethod
    def fix_groups_data(data):
        for gr in data:
            if data[gr]['status'] == 0:
                continue
            valid = True
            for member in data[gr]['members']:
                if len(data[gr]['members'][member]['others_eval_err']) == 0:
                    continue
                if len(data[gr]['members'][member]['others_eval_err']) == 1:
                    found_members = set(data[gr]['members'][member]['others_eval'].keys())
                    missing_members = set(data[gr]['members'].keys()) - found_members - {member}
                    if len(missing_members) == 1:
                        data[gr]['members'][member]['others_eval'][list(missing_members)[0]] = \
                        data[gr]['members'][member]['others_eval_err'][0]
                else:
                    valid = False
            if valid and data[gr]['status'] == 2:
                data[gr]['status'] = 1  # WARNING

        return data

    def print_stats(self):
        valid_gr = 0
        error_gr = 0
        fixed_gr = 0
        members = [0, 0, 0, 0, 0, 0, 0]

        data = self._group_data_fixed

        for gr in data:
            members[len(data[gr]['members'].keys())] += 1
            if data[gr]['status'] == 0:
                valid_gr += 1
            elif data[gr]['status'] == 1:
                fixed_gr += 1
            else:
                error_gr += 1

        print(f'Total groups: {len(data.keys())}')
        print(f'Teams per status: {valid_gr} Valid, {fixed_gr} Fixed, {error_gr} Error')
        print(
            f'Teams per #members: 0m [{members[0]}], 1m [{members[1]}], 2m [{members[2]}], 3m [{members[3]}], 4m [{members[4]}], 5m [{members[5]}], 6m [{members[6]}]')

    @staticmethod
    def compute_results_data(data):

        for gr in data:
            data[gr]['evaluation'] = {
                'learners': list(data[gr]['members'].keys()),
                'results': {}
            }
            for member in data[gr]['evaluation']['learners']:
                data[gr]['evaluation']['results'][member] = {
                    'funcionament_global': data[gr]['members'][member]['self_eval'][0],
                    'participacio_activa': data[gr]['members'][member]['self_eval'][2],
                    'q1': [None, None, None, None, None, None],  # Aporto Idees
                    'q2': [None, None, None, None, None, None],  # Realitzo la meva part de la pràctica
                    'q3': [None, None, None, None, None, None],  # Ajudo a la resta de l'equip
                    'q4': [None, None, None, None, None, None],  # Nota global participació
                    'q1_m': None,
                    'q2_m': None,
                    'q3_m': None,
                    'q4_m': None,
                    'q1_s': data[gr]['members'][member]['self_eval'][1],
                    'q2_s': data[gr]['members'][member]['self_eval'][3],
                    'q3_s': data[gr]['members'][member]['self_eval'][4],
                    'q4_s': data[gr]['members'][member]['self_eval'][5],
                    'comments': {},
                    'summary': {}
                }
                m_id = data[gr]['members'][member]['m_id']
                data[gr]['evaluation']['results'][member]['q1'][m_id] = data[gr]['members'][member]['self_eval'][1]
                data[gr]['evaluation']['results'][member]['q2'][m_id] = data[gr]['members'][member]['self_eval'][3]
                data[gr]['evaluation']['results'][member]['q3'][m_id] = data[gr]['members'][member]['self_eval'][4]
                data[gr]['evaluation']['results'][member]['q4'][m_id] = data[gr]['members'][member]['self_eval'][5]

            for member in data[gr]['evaluation']['learners']:
                m_id = data[gr]['members'][member]['m_id']
                for ref_member in data[gr]['members'][member]['others_eval']:
                    evals = data[gr]['members'][member]['others_eval'][ref_member]['eval']
                    data[gr]['evaluation']['results'][ref_member]['q1'][m_id] = evals[0]
                    data[gr]['evaluation']['results'][ref_member]['q2'][m_id] = evals[1]
                    data[gr]['evaluation']['results'][ref_member]['q3'][m_id] = evals[2]
                    data[gr]['evaluation']['results'][ref_member]['q4'][m_id] = evals[3]
                    comments = data[gr]['members'][member]['others_eval'][ref_member]['comments']
                    if isinstance(comments, str):
                        data[gr]['evaluation']['results'][ref_member]['comments'][member] = comments

            for member in data[gr]['evaluation']['learners']:
                for q_id in range(4):
                    q = data[gr]['evaluation']['results'][member][f'q{q_id + 1}']
                    q_s = data[gr]['evaluation']['results'][member][f'q{q_id + 1}_s']
                    vals = [v for v in q if v is not None]
                    data[gr]['evaluation']['results'][member][f'q{q_id + 1}_m'] = (sum(vals) - q_s) / (len(vals) - 1)

                data[gr]['evaluation']['results'][member]['summary'] = None
                auto_comment = []
                diff_qs = [
                    data[gr]['evaluation']['results'][member][f'q{i}_s'] - data[gr]['evaluation']['results'][member][
                        f'q{i}_m']
                    for i in [1, 2, 3, 4]]

                if sum(x > 2 for x in diff_qs) > 2:
                    auto_comment.append(
                        "Els teus companys t'avaluen molt per sota de la teva percepció en alguns punts.")
                elif sum(x > 1 for x in diff_qs) > 2:
                    auto_comment.append(
                        "Els teus companys t'avaluen lleugerament per sota de la teva percepció en alguns punts.")

                if sum(x < -2 for x in diff_qs) > 2:
                    auto_comment.append(
                        "Els teus companys t'avaluen molt per sobre de la teva percepció en alguns punts.")
                elif sum(x < -1 for x in diff_qs) > 2:
                    auto_comment.append(
                        "Els teus companys t'avaluen lleugerament per sobre de la teva percepció en alguns punts.")

                if len(auto_comment) > 0:
                    data[gr]['evaluation']['results'][member]['summary'] = '\n'.join(auto_comment)

        return data

    @staticmethod
    def extract_data(data) -> pd.DataFrame:
        cols = ['Estudiant', 'Grup', 'Status', 'Funcionament Global', 'Participació Activa', 'Q1 Auto', 'Q1 Companys',
                'Q2 Auto', 'Q2 Companys', 'Q3 Auto', 'Q3 Companys', 'Q4 Auto', 'Q4 Companys', 'Summary']
        learners_data = {}
        for gr in data:
            for learner in data[gr]['evaluation']['learners']:
                learner_eval_data = data[gr]['evaluation']['results'][learner]
                learners_data[learner] = [
                    learner,
                    gr,
                    data[gr]['status'],
                    learner_eval_data['funcionament_global'],
                    learner_eval_data['participacio_activa'],
                    learner_eval_data['q1_s'],
                    learner_eval_data['q1_m'],
                    learner_eval_data['q2_s'],
                    learner_eval_data['q2_m'],
                    learner_eval_data['q3_s'],
                    learner_eval_data['q3_m'],
                    learner_eval_data['q4_s'],
                    learner_eval_data['q4_m'],
                    learner_eval_data['summary'],
                ]

        return pd.DataFrame.from_dict(learners_data, orient='index', columns=cols)

    def export_group(self, file_out, group_filter=None):

        data = self._group_data_fixed

        with open(file_out, 'w') as f_out:
            for gr in data:
                if group_filter is not None and not gr.upper().startswith(group_filter):
                    continue
                f_out.write(f'# Grup {gr.upper()}\n')
                f_out.write('\n-----------------------------\n\n')
                for learner in data[gr]['evaluation']['learners']:
                    learner_eval_data = data[gr]['evaluation']['results'][learner]
                    f_out.write(f'## {learner}\n')
                    f_out.write(str([
                        learner,
                        gr,
                        data[gr]['status'],
                        learner_eval_data['funcionament_global'],
                        learner_eval_data['participacio_activa'],
                        learner_eval_data['q1_s'],
                        learner_eval_data['q1_m'],
                        learner_eval_data['q2_s'],
                        learner_eval_data['q2_m'],
                        learner_eval_data['q3_s'],
                        learner_eval_data['q3_m'],
                        learner_eval_data['q4_s'],
                        learner_eval_data['q4_m']
                    ]) + '\n')
                    f_out.write('\n### Avaluacions\n\n')
                    f_out.write(
                        f"Q1 - Aportació Idees: T'has valorat amb un {learner_eval_data['q1_s']} i els teus companys d'equip amb un {learner_eval_data['q1_m']:.1f}.\n")
                    f_out.write(
                        f"Q2 - Realització tasques assignades: T'has valorat amb un {learner_eval_data['q2_s']} i els teus companys d'equip amb un {learner_eval_data['q2_m']:.1f}.\n")
                    f_out.write(
                        f"Q3 - Ajuda a la resta de l'equip: T'has valorat amb un {learner_eval_data['q3_s']} i els teus companys d'equip amb un {learner_eval_data['q3_m']:.1f}.\n")
                    f_out.write(
                        f"Q4 - Nota global participació: T'has valorat amb un {learner_eval_data['q4_s']} i els teus companys d'equip amb un {learner_eval_data['q4_m']:.1f}.\n")

                    f_out.write('\n\n### Comentaris\n\n')
                    for c in learner_eval_data['comments']:
                        f_out.write(f"* {learner_eval_data['comments'][c]}\n")

                    f_out.write('\n-----------------------------\n\n')
                f_out.write('\n-----------------------------\n\n')

