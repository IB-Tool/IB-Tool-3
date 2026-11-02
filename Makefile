#/***************************************************************************
# IBTool
#
# Toolset for the delineation of settlements on the basis
# of building footprints
#							 -------------------
#		begin				: 2024-12-18
#		git sha				: $Format:%H$
#		copyright			: (C) 2024 by Oliver Harig
#		email				: ottmar.hittzfeld@web.de
# ***************************************************************************/
#
#/***************************************************************************
# *																		 *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or	 *
# *   (at your option) any later version.								   *
# *																		 *
# ***************************************************************************/

# Development tasks only. The release ZIP is built exclusively with
#   python scripts/create_release_zip.py
# (see ai/core/release-conventions.md). The former Plugin Builder targets
# (compile, deploy, zip, package, upload, ...) packaged a wrong file layout
# and were removed.

# Translation file basenames (space separated). scripts/compile-strings.sh and
# update-strings.sh build the path as i18n/$(LOCALE).ts, so this must be the
# .ts file's basename, not just the ISO code (the plugin's translator loads
# i18n/IBTool_<locale>.qm).
LOCALES = IBTool_de

# Name of the lrelease binary on your system. If you have trouble compiling the
# translations, you may have to specify the full path to lrelease.
LRELEASE = lrelease


.PHONY: default test transup transcompile transclean pylint pep8
default:
	@echo "Targets: test, transup, transcompile, transclean, pylint, pep8"
	@echo "Release ZIP: python scripts/create_release_zip.py"

test:
	python -m pytest test/ -v

transup:
	@echo
	@echo "------------------------------------------------"
	@echo "Updating translation files with any new strings."
	@echo "------------------------------------------------"
	@chmod +x scripts/update-strings.sh
	@scripts/update-strings.sh $(LOCALES)

transcompile:
	@echo
	@echo "----------------------------------------"
	@echo "Compiled translation files to .qm files."
	@echo "----------------------------------------"
	@chmod +x scripts/compile-strings.sh
	@scripts/compile-strings.sh $(LRELEASE) $(LOCALES)

transclean:
	@echo
	@echo "------------------------------------"
	@echo "Removing compiled translation files."
	@echo "------------------------------------"
	rm -f i18n/*.qm

pylint:
	@echo
	@echo "-----------------"
	@echo "Pylint violations"
	@echo "-----------------"
	@pylint --reports=n --rcfile=.pylintrc . || true
	@echo
	@echo "----------------------"
	@echo "If you get a 'no module named qgis.core' error, try sourcing"
	@echo "the helper script we have provided first then run make pylint."
	@echo "e.g. source scripts/run-env-linux.sh <path to qgis install>; make pylint"
	@echo "----------------------"


# Run style checking with flake8, using the same config (.flake8) as CI
# (.github/workflows/qgis-plugin-ci.yml), so a local pass here means CI's
# "Flake8 (style)" step will pass too.
pep8:
	@echo
	@echo "-----------"
	@echo "Flake8 issues"
	@echo "-----------"
	flake8 .
