from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget, QSpinBox, QDoubleSpinBox


def button(text, callback):
    b = QPushButton(text)
    b.clicked.connect(callback)
    return b


def row(*widgets):
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    for child in widgets:
        layout.addWidget(child)
    return w


def spin(value, maximum=100000, minimum=0, floating=False):
    s = QDoubleSpinBox() if floating else QSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    return s
