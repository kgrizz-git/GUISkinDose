@ECHO OFF
cd %~dp0
python -m sphinx.ext.apidoc -o docs/source src/guiskindose
python -m sphinx -M clean docs/source docs/build
python -m sphinx -b html docs/source docs/build/html
