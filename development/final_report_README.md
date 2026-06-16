# Final report web

Visor local amb `Streamlit` per navegar pels informes generats a:

`_data/sd/26/pr2/out/results/<group>/<student_key>/Results.md`
`_data/sd/26/pr2/out/results/<group>/<student_key>/Diff.md`

## Executar

Dependències via Poetry:

```bash
poetry install
```

Opcional (millor autoreload de Streamlit en local):

```bash
poetry install --with dev
```

Executa el report:

```bash
poetry run streamlit run development/final_report.py
```

Per defecte l'app apunta a:

`_data/sd/26/pr2/out/results`

Si vols usar una altra carpeta, canvia-la des del panell lateral.

## Llançar des de `sd.py`

`development/sd.py` inclou `launch_streamlit_final_report(...)`.

Activa el flag:

- `launch_final_report_web = True`

Quan acabi de generar els `Results.md`/`Diff.md`, obrirà la web de Streamlit amb la carpeta de resultats preconfigurada.

