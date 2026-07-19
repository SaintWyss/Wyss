#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "uso: $0 USER EDGE_USER HOME_GROUP REPOSITORY WORKING_DIRECTORY CONFIG_SOURCE DATA_DIRECTORY" >&2
  exit 2
}

[[ $# -eq 7 ]] || usage
wyss_user=$1
edge_user=$2
home_group=$3
repository=$4
working_directory=$5
config_source=$6
data_directory=$7

for path in "$repository" "$working_directory" "$config_source" "$data_directory"; do
  [[ $path = /* ]] || { echo "todas las rutas deben ser absolutas" >&2; exit 2; }
done
id "$wyss_user" >/dev/null
id "$edge_user" >/dev/null
getent group "$home_group" >/dev/null
[[ -x "$repository/.venv/bin/wyss" && -f "$config_source" && -d "$data_directory" ]] || {
  echo "repositorio, configuración o datos no están listos" >&2
  exit 2
}

owner_group=$(id -gn "$wyss_user")
owner_home=$(getent passwd "$wyss_user" | cut -d: -f6)
config_dir="$owner_home/.config/wyss"
config_path="$config_dir/config.toml"
template="$repository/deploy/systemd/wyss.service.in"
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT

sed \
  -e "s|@WYSS_USER@|$wyss_user|g" \
  -e "s|@EDGE_USER@|$edge_user|g" \
  -e "s|@HOME_GROUP@|$home_group|g" \
  -e "s|@OWNER_GROUP@|$owner_group|g" \
  -e "s|@REPOSITORY@|$repository|g" \
  -e "s|@WORKING_DIRECTORY@|$working_directory|g" \
  -e "s|@CONFIG_PATH@|$config_path|g" \
  -e "s|@DATA_DIRECTORY@|$data_directory|g" \
  "$template" >"$temporary"

sudo install -d -m 0700 -o "$wyss_user" -g "$owner_group" "$config_dir"
sudo install -m 0600 -o "$wyss_user" -g "$owner_group" "$config_source" "$config_path"
sudo install -m 0644 -o root -g root "$temporary" /etc/systemd/system/wyss.service
sudo systemctl daemon-reload
sudo systemctl enable wyss.service

echo "servicio instalado; iniciar con: sudo systemctl start wyss.service"
