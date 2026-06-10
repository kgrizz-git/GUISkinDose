# External library references

_Index of authoritative documentation for major MyPySkinDose dependencies. Expand before the next major dependency review._

| Library | Role in MyPySkinDose | Documentation |
|---------|----------------------|---------------|
| [pydicom](https://pypi.org/project/pydicom/) | DICOM RDSR parsing | [User guide](https://pydicom.github.io/pydicom/stable/) · [Tag dictionary](https://dicom.innolitics.com/) |
| [NiceGUI](https://pypi.org/project/nicegui/) | Web/desktop GUI (`[gui]` extra) | [Documentation](https://nicegui.io/documentation) · [User simulation testing](https://nicegui.io/documentation/section_testing) |
| [Plotly](https://pypi.org/project/plotly/) | 3D geometry and dose-map plots | [Python API](https://plotly.com/python/) · [Mesh3d](https://plotly.com/python/3d-mesh/) |
| [pandas](https://pypi.org/project/pandas/) | Normalized event DataFrame contract | [User guide](https://pandas.pydata.org/docs/user_guide/index.html) |
| [numpy-stl](https://pypi.org/project/numpy-stl/) | Human phantom meshes | [API](https://numpy-stl.readthedocs.io/) |

**Harness note:** Optional `LLMS.txt` or per-library cheat sheets can live in this directory when a dependency upgrade needs focused agent context. Until then, link here from `AGENTS.md` only when adding new integration surfaces.
