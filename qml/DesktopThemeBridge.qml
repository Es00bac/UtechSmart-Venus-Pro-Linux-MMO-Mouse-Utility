// SPDX-License-Identifier: MIT
import QtQuick
import QindaTK.QindaQt

// Loaded lazily by Main.qml: on the QindaQt desktop this feeds the desktop's
// QST-1 tokens into QindaTK's theme; elsewhere the import fails and the
// Loader simply reports an error while the app keeps its built-in preset.
QindaQtTheme {}
