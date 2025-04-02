import sys
import re
import requests
import webbrowser
import shutil
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

            update_button = QPushButton("Update")
            if mod.get("files") and len(mod["files"]) > 0:
                zip_filename = mod["files"][0].get("filename", "unbekannt.zip")
            else:
                zip_filename = "unbekannt.zip"

            update_button.setProperty("zip_filename", zip_filename)
            update_button.setProperty("display_name", mod["name"])  # Modanzeige zur leichteren Identifizierung
            update_button.clicked.connect(lambda checked, btn=update_button: self.handle_update(btn))

            self.table.setCellWidget(row_index, 5, update_button)

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
                    mod_name = self.table.item(row, 0).text()
                    matched_mod = next((m for m in mods if m["name"] == mod_name), None)

                    if matched_mod and matched_mod.get("files") and len(matched_mod["files"]) > 0:
                        zip_filename = matched_mod["files"][0].get("filename", "unbekannt.zip")
                    else:
                        zip_filename = "unbekannt.zip"

                    update_button = QPushButton("⬆️ Update")
                    update_button.setProperty("zip_filename", zip_filename)  # wichtige neue Zeile!
                    update_button.clicked.connect(lambda checked, btn=update_button: self.handle_update(btn))
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

    def update_mod(self, zip_filename, filename_without_zip):
        print(f"Starte Update für Datei '{zip_filename}' mit interner Bezeichnung '{filename_without_zip}'")

        # URL festlegen
        download_url = f"https://modwerkstatt.com/download/{zip_filename}"
        print(f"⬇️ Lade Datei herunter: {download_url}")

        # Temporärer Download der ZIP-Datei
        temp_dir = tempfile.mkdtemp()
        zip_filepath = os.path.join(temp_dir, zip_filename)
        success = False

        try:
            response = requests.get(download_url)
            response.raise_for_status()

            if not zip_filepath.endswith(".zip"):
                zip_filepath += ".zip"

            with open(zip_filepath, 'wb') as file:
                file.write(response.content)
            print(f"📦 Datei heruntergeladen -> {zip_filepath}")

            # Alten Mod-Ordner sauber löschen
            mod_folder_path = os.path.join(get_mod_folder_from_settings(), filename_without_zip)
            if os.path.exists(mod_folder_path):
                print(f"⚠️ Lösche alten Mod-Ordner {mod_folder_path}...")
                shutil.rmtree(mod_folder_path)

            # Neuen Mod entpacken
            os.makedirs(mod_folder_path, exist_ok=True)
            temp_unzip_folder = os.path.join(temp_dir, "unpacked_mod")
            shutil.unpack_archive(zip_filepath, temp_unzip_folder)

            # Prüfen, ob zusätzlicher Unterordner vorhanden ist
            extracted_items = os.listdir(temp_unzip_folder)

            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_unzip_folder, extracted_items[0])):
                # Zusätzlicher Ordner gefunden – dessen Inhalt nach oben verschieben!
                inner_folder_path = os.path.join(temp_unzip_folder, extracted_items[0])
                for item in os.listdir(inner_folder_path):
                    item_full_path = os.path.join(inner_folder_path, item)
                    shutil.move(item_full_path, mod_folder_path)
                print("✅ Zusätzlicher Unterordner erkannt – Inhalt erfolgreich verschoben.")
            else:
                # Kein zusätzlicher Ordner – alles normal verschieben
                for item in extracted_items:
                    item_full_path = os.path.join(temp_unzip_folder, item)
                    shutil.move(item_full_path, mod_folder_path)
                print("✅ Kein zusätzlicher Unterordner gefunden – Inhalt direkt entpackt.")

            success = True
            print(f"✅ Mod erfolgreich aktualisiert nach {mod_folder_path}")

        except Exception as e:
            print(f"⚠️ Fehler beim Update '{zip_filename}': {e}")
            success = False

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return success

    def handle_update(self, update_button):
        zip_filename = update_button.property("zip_filename")
        display_name = update_button.property("display_name") or "Unbekannter Mod"
        filename_without_zip = zip_filename.replace('.zip', '')

        print(f"🔄 Starte Update für Mod: {display_name} ➡️ Dateiname: {zip_filename}")

        success = self.update_mod(zip_filename, filename_without_zip)
        if success:
            print(f"🎉 Update abgeschlossen für: {display_name}")

            current_row = self.table.indexAt(update_button.pos()).row()
            remote_version = self.table.item(current_row, 2).text().strip()
            self.table.item(current_row, 1).setText(remote_version)

            self.table.setCellWidget(current_row, 5, None)

            from PyQt5.QtCore import Qt
            sort_item = QTableWidgetItem("")
            sort_item.setData(Qt.UserRole, 0)
            sort_item.setTextAlignment(Qt.AlignCenter)
            sort_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(current_row, 5, sort_item)
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