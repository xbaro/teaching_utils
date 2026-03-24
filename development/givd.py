import logging
from teaching_utils import teaching_lib

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':

    # logging.basicConfig(filename='myapp.log', level=logging.INFO)
    # logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)
    #logging.basicConfig(level=logging.CRITICAL)

    group = 'f'
    repositories = teaching_lib.repository.CodeRepositorySet(export_path=f'./_data/GiVD2526/pr1/{group}/repositories')
    #repositories.load_repositories('GiVD2023/p2-zbtoy-b', 1, 9)
    #repositories.load_repositories('GiVD-2024/p1-pathtracingtoy-a', 1, 14)
    repositories.load_repositories(f'GiVD-2025/p1-tracertoy-{group}', 4, 20)

    #repositories.clone_all(export_path=f'./_data/GiVD2526/pr1/{group}/repositories', force=False)

    # repositories.export_files('./_data/export_shaders/', 'resources/GPUshaders', 'glsl')

    repositories.print_stats()

