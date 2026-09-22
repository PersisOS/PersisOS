import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    anchors.fill: parent
    color: "transparent"

    Column {
        anchors.centerIn: parent
        spacing: 16

        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            running: true
            width: 48
            height: 48
        }

        // Static label
        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Installing system, please wait...")
            font.pixelSize: 18
            font.weight: Font.DemiBold
            opacity: 0.85
        }
    }
}
