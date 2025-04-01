from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtGui import QFont, QColor, QPalette


class ToastNotification(QWidget):
    def __init__(self, text, parent=None, duration=3000):
        super().__init__(parent)

        self.setAttribute(Qt.WA_DeleteOnClose)  # automatisch löschen
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)  # kein Fensterrahmen / immer oben
        self.duration = duration

        # Stil definieren:
        self.label = QLabel(text, self)
        font = QFont("Segoe UI", 10, QFont.Bold)
        self.label.setFont(font)
        layout = QHBoxLayout(self)
        layout.addWidget(self.label)

        # Hintergrundfarbe setzen
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#44c767"))  # Grünliche Hintergrundfarbe
        palette.setColor(QPalette.WindowText, Qt.white)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def showEvent(self, event):
        super().showEvent(event)

        # Positionieren (oben-rechts im Parent für Auffälligkeit)
        parent = self.parent()
        if parent:
            geo = parent.geometry()
            self.adjustSize()
            self.move(geo.topRight() - self.rect().topRight() + QPoint(-20, 20))  # Randabstand

        # Einblend-Animation:
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(500)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutBack)
        self.animation.start()

        # Timer zum automatischen Schließen
        QTimer.singleShot(self.duration, self.close)