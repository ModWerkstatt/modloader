import sys
import re
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem, QMessageBox, QFileDialog, QAction, QLabel)
from PyQt5.QtCore import Qt, QSettings, QTimer
from datetime import datetime
from toast_notification import ToastNotification
from get_local_mods import get_mods_versions, get_mod_folder_from_settings

APP_VERSION = "0.0.1"

class ModViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ModWerkstatt Mod Loader")
        self.setGeometry(100, 100, 800, 600)

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

        ## Lokale Daten schnell nutzbar als Dictionary vorbereiten
        local_dict = {}
        for mod_loc in mods_local:
            foldername, major_version = split_foldername_version(mod_loc["modOrdner"])
            local_dict[foldername] = mod_loc["version"]  # z.B. version = "1.2"

        ## JSON durchlaufen und vergleichen!
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
                # Ein Match wurde gefunden.
                local_version = local_dict[foldername_json]

                combined.append({
                    "name": mod_name,
                    "remote_version": remote_version,
                    "local_version": local_version,
                    "created": mod_entry.get("timecreated", 0),
                    "changed": mod_entry.get("timechanged", 0),
                })

        return combined

    def populate_mod_table(self, combined_mods):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(combined_mods))
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Lokale Version", "Remote Version", "Erstellt am", "Zuletzt geändert"])

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

        print("Aktuelle lokale Mods:")
        for mod_info in mods_list:
            print(mod_info["modOrdner"], mod_info["version"])

def split_foldername_version(folder_fullname):
    # Regex Muster um _Zahlen (Version) hinten abzutrennen
    match = re.match(r"(.+?)_(\d+)$", folder_fullname)
    if match:
        # (Basisname, Major-Version)
        return match.group(1), int(match.group(2))
    else:
        return folder_fullname, None  # kein Match / keine Zahl hinten

def main():
    app = QApplication(sys.argv)
    viewer = ModViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()