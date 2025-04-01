import sys
import re
import requests
import webbrowser
import zipfile
import os
import tempfile
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem, QMessageBox, QFileDialog, QAction, QLabel)
from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5 import QtWidgets, QtGui
from datetime import datetime
from packaging.version import parse as parse_version
from toast_notification import ToastNotification
from get_local_mods import get_mods_versions, get_mod_folder_from_settings

APP_VERSION = "0.0.1"

class ModViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModWerkstatt Mod Loader")
        self.setGeometry(100, 100, 900, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Hinzufügen eines Menüpunktes für Einstellungen
        select_mod_folder_action = QAction("Mod-Ordner auswählen", self)
        select_mod_folder_action.triggered.connect(self.select_mod_folder)

        # Menü und Menüeintrag erstellen
        menu = self.menuBar().addMenu("Einstellungen")
        menu.addAction(select_mod_folder_action)

        self.repo_changed_label = QLabel("Zuletzt geändert: Unbekannt")
        self.repo_changed_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.repo_changed_label)

        self.load_button = QPushButton("Auffrischen")
        self.load_button.clicked.connect(self.load_json)
        layout.addWidget(self.load_button)

        # Tabelle zur besseren Darstellung aller MODs
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Version", "Erstellt am", "Zuletzt geändert"])
        layout.addWidget(self.table)

        # Statusbar korrekt einfügen
        self.statusBar().showMessage("Bereit.")
        self.version_label = QLabel(f"Version {APP_VERSION}")
        self.statusBar().addPermanentWidget(self.version_label)
        self.show_mod_folder_in_statusbar()

        # Update available?
        self.notify_if_update_available()

        # Automatisches initiales Laden der JSON-Daten beim Start
        self.load_json()

        # Lokale MODs beim Start einmal laden
        self.load_local_mods_into_gui()

    def load_json(self):
        url = "https://modwerkstatt.com/tpfmm"
        try:
            response = requests.get(url)
            response.raise_for_status()
            json_data = response.json()

            mods_json = json_data["mods"]

            mod_folder = get_mod_folder_from_settings()
            mods_local = get_mods_versions(mod_folder) if mod_folder else []

            combined_mods = self.get_combined_mod_list(mods_json, mods_local)
            self.populate_mod_table(combined_mods)

            # Status, Toast etc., wie gehabt
            jetzt = datetime.now().strftime('%H:%M:%S')
            self.statusBar().showMessage(f"Daten wurden um {jetzt} erfolgreich aktualisiert.", 5000)
            toast = ToastNotification("✅ Daten erfolgreich aktualisiert.", self, 3000)
            toast.show()

            # nach 5 sec Mod-Ordner wieder anzeigen:
            QTimer.singleShot(5000, self.show_mod_folder_in_statusbar)

        except requests.RequestException as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Laden der Daten:\n{e}")
        except KeyError as e:
            QMessageBox.critical(self, "Fehler", f"Datenfeld fehlt in JSON:\n{e}")

    def get_combined_mod_list(self, mods_json, mods_local):
        combined = []

        # Lokale Daten vorbereiten
        local_dict = {}
        for mod_loc in mods_local:
            foldername, major_version = split_foldername_version(mod_loc["modOrdner"])
            local_dict[foldername] = mod_loc["version"]  # z.B. version = "1.2"

        # JSON-Daten durchlaufen und vergleichen!
        for mod_entry in mods_json:
            remote_version = mod_entry.get("version", "N/A")
            mod_name = mod_entry.get("name", "N/A")

            # files könnte mehrere haben, aber laut Beispiel ist es [0]
            try:
                folder_fullname = mod_entry["files"][0]["foldername"]
                foldername_json, _ = split_foldername_version(folder_fullname)
            except (IndexError, KeyError):
                continue

            if foldername_json in local_dict:
                local_version = local_dict[foldername_json]

                # statt manuellem Neubau hier den original JSON-Eintrag kopieren
                # und wichtige lokale Versionsinfo ergänzen
                mod_copy = mod_entry.copy()  # Erstelle Kopie des JSON-Mod-Entrys
                mod_copy["local_version"] = local_version
                mod_copy["remote_version"] = remote_version
                mod_copy["created"] = mod_entry.get("timecreated", 0)
                mod_copy["changed"] = mod_entry.get("timechanged", 0)

                combined.append(mod_copy)  # Diese Kopie enthält nun definitiv das "files"-Feld!

        return combined

    def populate_mod_table(self, combined_mods):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(combined_mods))
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Name", "Lokale Version", "Neueste Version", "Veröffentlicht", "Geändert", "Aktion"])

        for row_index, mod in enumerate(combined_mods):
            created_date = datetime.fromtimestamp(mod["created"]).strftime('%Y-%m-%d %H:%M:%S') if mod["created"] else 'N/A'
            changed_date = datetime.fromtimestamp(mod["changed"]).strftime('%Y-%m-%d %H:%M:%S') if mod["changed"] else ''

            self.table.setItem(row_index, 0, QTableWidgetItem(mod["name"]))
            self.table.setItem(row_index, 1, QTableWidgetItem(mod["local_version"]))
            self.table.setItem(row_index, 2, QTableWidgetItem(mod["remote_version"]))
            self.table.setItem(row_index, 3, QTableWidgetItem(created_date))
            self.table.setItem(row_index, 4, QTableWidgetItem(changed_date))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
        self.highlight_update_rows(combined_mods)

    def select_mod_folder(self):
        # Bisher gespeicherten Pfad laden und anzeigen
        current_folder = get_mod_folder_from_settings() or ""

        folder = QFileDialog.getExistingDirectory(self, "Mod-Ordner auswählen", current_folder)
        if folder:
            settings = QSettings("MeinProgramm", "ModLoader")
            settings.setValue("mod_folder_path", folder)

            toast = ToastNotification("✅ Mod-Ordner gespeichert.", self, 3000)
            toast.show()

            # Statusbar aktualisieren
            self.show_mod_folder_in_statusbar()

            # Lokale Mods erneut laden (optional):
            self.load_local_mods_into_gui()

    def show_mod_folder_in_statusbar(self):
        mod_folder = get_mod_folder_from_settings()
        if mod_folder:
            self.statusBar().showMessage(f"Aktueller Mod-Pfad: {mod_folder}")
        else:
            self.statusBar().showMessage("Mod-Ordner nicht gesetzt! Bitte festlegen unter Einstellungen.")

    def load_local_mods_into_gui(self):
        mod_folder = get_mod_folder_from_settings()

        if not mod_folder:
            QMessageBox.warning(self, "Keine Einstellungen", "Bitte zuerst einen Mod-Ordner auswählen (Einstellungen ➜ Mod-Ordner auswählen)")
            return

            mods_list = get_mods_versions(mod_folder)

        # print("Aktuelle lokale Mods:")
        # for mod_info in mods_list:
        #     print(mod_info["modOrdner"], mod_info["version"])

    def notify_if_update_available(self):
        is_update, latest_version, download_url = check_for_update(APP_VERSION)
        if is_update:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("🟢 Update verfügbar!")
            msg.setText(f"Eine neue Version ist verfügbar: {latest_version}\n\n"
                        f"Aktuelle installierte Version: {APP_VERSION}\n\n"
                        f"Möchtest du die neue Version herunterladen?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            user_choice = msg.exec()

            if user_choice == QMessageBox.Yes:
                # Nutzer zu GitHub Release Seite senden
                webbrowser.open(download_url)

    def highlight_update_rows(self, mods):
        row_count = self.table.rowCount()

        for row in range(row_count):
            local_item = self.table.item(row, 1)  # Lokale Versionsspalte
            remote_item = self.table.item(row, 2)  # Remote Versionsspalte

            if local_item and remote_item:
                local_version_text = local_item.text().strip()
                remote_version_text = remote_item.text().strip()

                if not remote_version_text:
                    remote_version_text = "0.0"

                try:
                    local_version = parse_version(local_version_text)
                    remote_version = parse_version(remote_version_text)
                except Exception as e:
                    print(f"⚠️ Fehler beim Parsen Version '{local_version_text}'/'{remote_version_text}': {e}")
                    continue

                if remote_version > local_version:
                    # echtes Update vorhanden
                    update_button = QPushButton("⬆️ Update")
                    update_button.clicked.connect(lambda checked, row=row: self.handle_update(row))
                    self.table.setCellWidget(row, 5, update_button)
                    sort_item = QTableWidgetItem("1")
                    sort_item.setData(Qt.UserRole, 1)  # Für besseres Sortieren
                    sort_item.setTextAlignment(Qt.AlignCenter)
                    sort_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.table.setItem(row, 5, sort_item)
                else:
                    # kein Update nötig, ggf. Knopf entfernen oder Zeile löschen
                    self.table.setCellWidget(row, 5, None)

                    sort_item = QTableWidgetItem("")
                    sort_item.setData(Qt.UserRole, 0)
                    sort_item.setTextAlignment(Qt.AlignCenter)
                    sort_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.table.setItem(row, 5, sort_item)

    def update_mod(self, filename):
        # Dynamisch Mods-Ordner aus Einstellungen laden:
        mods_ordner = get_mod_folder_from_settings()

        # Prüfen, ob Mods-Ordner gesetzt wurde:
        if not mods_ordner or not os.path.isdir(mods_ordner):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "⚠️ Fehler", "Bitte lege zuerst einen Mods-Ordner in den Einstellungen fest.")
            return False

        download_url = f"https://modwerkstatt.com/download/{filename}"

        print(f"⬇️ Lade Datei herunter: {download_url}")

        # Temporäre Datei anlegen und Download starten
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                local_zip_path = os.path.join(temp_dir, f"{filename}.zip")

                with requests.get(download_url, stream=True) as response:
                    response.raise_for_status()
                    with open(local_zip_path, "wb") as zip_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                zip_file.write(chunk)

                print(f"📦 Datei heruntergeladen -> {local_zip_path}")

                # Ziel-Ordner vorbereiten:
                zielordner = os.path.join(mods_ordner, filename)

                # Alten Ordner löschen falls nötig (ACHTUNG: dauerhaftes Löschen!)
                if os.path.exists(zielordner):
                    import shutil
                    print(f"⚠️ Lösche alten Mod-Ordner {zielordner}...")
                    shutil.rmtree(zielordner)

                os.makedirs(zielordner, exist_ok=True)

                # ZIP-Inhalt in Ordner entpacken:
                with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(zielordner)

                print(f"✅ Mod '{filename}' erfolgreich im Ordner '{zielordner}' installiert.")

            return True

        except Exception as e:
            print(f"⚠️ Fehler beim Update '{filename}': {e}")
            return False

    def handle_update(self, row):
        display_name = self.table.item(row, 0).text()
        zip_filename = self.table.item(row, 3).text().strip()  # 🔴 Hier anpassen auf richtige Spalte!

        # Filename OHNE .zip um Ordnerstruktur sauber zu halten:
        filename_without_zip = zip_filename.replace('.zip', '')

        print(f"🔄 Starte Update für Mod: {display_name} ➡️ Dateiname: {zip_filename}")

        success = self.update_mod(zip_filename, filename_without_zip)
        if success:
            print(f"🎉 Update abgeschlossen für: {display_name}")

            remote_version = self.table.item(row, 2).text().strip()
            self.table.item(row, 1).setText(remote_version)

            # Update-Button entfernen
            self.table.setCellWidget(row, 5, None)

            # Sortierung aktualisieren
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QTableWidgetItem
            sort_item = QTableWidgetItem("0")
            sort_item.setData(Qt.UserRole, 0)
            sort_item.setTextAlignment(Qt.AlignCenter)
            sort_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(row, 5, sort_item)

        else:
            print(f"❌ Update fehlgeschlagen für: {display_name}")


def split_foldername_version(folder_fullname):
    # Regex Muster um _Zahlen (Version) hinten abzutrennen
    match = re.match(r"(.+?)_(\d+)$", folder_fullname)
    if match:
        # (Basisname, Major-Version)
        return match.group(1), int(match.group(2))
    else:
        return folder_fullname, None  # kein Match / keine Zahl hinten

def get_latest_github_version():
    url = "https://api.github.com/repos/ModWerkstatt/modloader/releases/latest"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Fehler werfen, wenn Status nicht 200 ist
        latest_release = response.json()
        latest_tag = latest_release["tag_name"]
        print(f"GitHub aktuellste Release-Version: {latest_tag}")
        return latest_release["tag_name"], latest_release["html_url"]  # Version & Download-Link
    except requests.RequestException:
        return None, None  # bei einem Problem (Netzwerk/Fehler) nichts tun

def check_for_update(current_version):
    latest_version, latest_url = get_latest_github_version()
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        return True, latest_version, latest_url  # neue Version vorhanden
    return False, latest_version, None  # kein Update verfügbar


def main():
    app = QApplication(sys.argv)
    viewer = ModViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()