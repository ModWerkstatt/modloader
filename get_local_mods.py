import re
import os
from PyQt5.QtCore import QSettings


def get_mod_folder_from_settings():
    settings = QSettings("MeinProgramm", "ModLoader")
    return settings.value("mod_folder_path", "")


def read_minor_version(mod_lua_path):
    minor_version_pattern = re.compile(r'minorVersion\s*=\s*(\d+)', re.IGNORECASE)
    with open(mod_lua_path, "r", encoding="utf-8") as file:
        for line in file:
            minor_match = minor_version_pattern.search(line)
            if minor_match:
                return int(minor_match.group(1))
    return None


def get_mods_versions(mods_folder):
    mods_version_list = []

    if not os.path.exists(mods_folder):
        print("Mods-Ordner existiert nicht!")
        return mods_version_list

    for mod_dir in os.listdir(mods_folder):
        mod_path = os.path.join(mods_folder, mod_dir)
        mod_lua_path = os.path.join(mod_path, 'mod.lua')

        if os.path.isdir(mod_path) and os.path.exists(mod_lua_path):
            major_version_match = re.search(r'(\d+)$', mod_dir)
            major_version = int(major_version_match.group(1)) if major_version_match else None

            minor_version = read_minor_version(mod_lua_path)

            if major_version is not None and minor_version is not None:
                full_version = f"{major_version}.{minor_version}"
                mods_version_list.append({
                    "modOrdner": mod_dir,
                    "version": full_version
                })
    return mods_version_list


if __name__ == "__main__":
    mods_folder_path = get_mod_folder_from_settings()

    if mods_folder_path:
        mods_version_list = get_mods_versions(mods_folder_path)

        print("Gescannten Ordner und Versionen:")
        for mod in mods_version_list:
            print(f"- {mod['modOrdner']} (Version: {mod['version']})")
    else:
        print("Kein Mods-Pfad in den Einstellungen gesetzt. Bitte erst einstellen.")