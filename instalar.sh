#!/bin/sh
# Instalación desde un clon, con el mismo instalador que usa el ZIP.
set -eu
src=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec sh "$src/packaging/portable/instalar.sh" "$@"
