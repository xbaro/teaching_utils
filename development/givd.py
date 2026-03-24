import logging
from typing import AnyStr

from teaching_utils import teaching_lib

logger = logging.getLogger(__name__)


def print_repo_stats(base: str, groups: str|list[str]|None = None, min_group: int = 1, max_group: int = 20,
                     clone: bool = False, force: bool = False, local_path: str|None = None) -> None:

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


if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)

    print_repo_stats('GiVD-2025/p1-tracertoy-', ['a', 'b', 'c', 'f'], 1, 20, True, force=False,
                     local_path='./_data/givd/2526/pr1/repositories')
    #extract_form_stats()
