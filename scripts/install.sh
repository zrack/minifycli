#!/bin/sh
set -eu

if ! command -v cargo >/dev/null 2>&1; then
    printf '%s\n' 'Rust and Cargo are required. Install them from https://www.rust-lang.org/tools/install' >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
install_root=${MINI_INSTALL_ROOT:-"$HOME/.local"}

cargo install --path "$project_root" --locked --root "$install_root"
printf '\nInstalled mini in %s/bin\n' "$install_root"
printf 'Add %s/bin to your PATH if it is not already present.\n' "$install_root"
