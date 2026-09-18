import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

// PersisOS login — "violet night".
// Wallpaper dimmed behind one frosted card: logo, username, password.
// A thin orchid underline glows under whichever field has focus.
Rectangle {
    id: root
    color: "#141317"

    readonly property color brand: "#9738ba"
    readonly property color glow: "#b25ae8"
    readonly property color ink: "#f4eff8"

    // SDDM reads this from theme.conf.
    property string background: config.background || ""

    Image {
        anchors.fill: parent
        source: root.background
        fillMode: Image.PreserveAspectCrop
        smooth: true

        // Dim layer so the card always reads clearly.
        Rectangle {
            anchors.fill: parent
            color: "#0d0c11"
            opacity: 0.55
        }
    }

    // ---- login card --------------------------------------------------------
    Rectangle {
        id: card
        anchors.centerIn: parent
        width: 340
        height: content.implicitHeight + 96
        radius: 20
        color: "#1b171f"
        opacity: 0.92
        border.color: root.brand
        border.width: 1

        ColumnLayout {
            id: content
            anchors.centerIn: parent
            width: parent.width - 56
            spacing: 16

            Image {
                source: "/usr/share/icons/hicolor/scalable/apps/persisos.svg"
                sourceSize.width: 84
                sourceSize.height: 84
                Layout.alignment: Qt.AlignHCenter
                smooth: true
            }

            Text {
                text: "PersisOS"
                color: root.ink
                font.pointSize: 17
                font.letterSpacing: 5
                Layout.alignment: Qt.AlignHCenter
            }

            // subtle divider
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: "#ffffff"
                opacity: 0.08
            }

            Text {
                text: sddm.hostName
                color: root.ink
                opacity: 0.5
                font.pointSize: 10
                elide: Text.ElideRight
                Layout.alignment: Qt.AlignHCenter
                visible: sddm.hostName !== ""
            }

            ColumnLayout {
                spacing: 4
                Layout.fillWidth: true

                Text {
                    text: "User"
                    color: root.ink
                    opacity: 0.55
                    font.pointSize: 9
                    font.letterSpacing: 1
                }
                PersisField {
                    id: userField
                    Layout.fillWidth: true
                    text: sddm.lastUser
                    onAccepted: passwordField.forceActiveFocus()
                }
            }

            ColumnLayout {
                spacing: 4
                Layout.fillWidth: true

                Text {
                    text: "Password"
                    color: root.ink
                    opacity: 0.55
                    font.pointSize: 9
                    font.letterSpacing: 1
                }
                PersisField {
                    id: passwordField
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    onAccepted: root.tryLogin()
                    onTextEdited: hint.text = ""
                }
            }

            Text {
                id: hint
                text: ""
                color: root.glow
                font.pointSize: 9
                Layout.alignment: Qt.AlignHCenter
                visible: text !== ""
            }

            ComboBox {
                id: sessionSelector
                model: sessionModel
                textRole: "name"
                currentIndex: sddm.lastSession
                Layout.fillWidth: true
                implicitHeight: 34

                contentItem: Text {
                    text: sessionSelector.displayText
                    color: root.ink
                    opacity: 0.6
                    font.pointSize: 9
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    elide: Text.ElideRight
                }
                background: Rectangle {
                    radius: 8
                    color: "#241e2b"
                    border.color: "#3a3142"
                    border.width: 1
                }
            }

            Button {
                id: loginButton
                text: "Log in"
                Layout.fillWidth: true
                hoverEnabled: true

                contentItem: Text {
                    text: loginButton.text
                    color: "#ffffff"
                    font.pointSize: 11
                    font.letterSpacing: 1
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 10
                    color: loginButton.hovered ? Qt.lighter(root.brand, 1.15) : root.brand
                }
                onClicked: root.tryLogin()
            }
        }
    }

    // ---- power buttons -----------------------------------------------------
    Row {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 24
        spacing: 12

        PowerButton { label: "Restart"; mode: "reboot" }
        PowerButton { label: "Shut down"; mode: "poweroff" }
    }

    Text {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 24
        text: "PersisOS"
        color: root.ink
        opacity: 0.35
        font.pointSize: 10
        font.letterSpacing: 3
    }

    function tryLogin() {
        if (userField.text === "") {
            hint.text = "Enter your username"
            return
        }
        sddm.login(userField.text, passwordField.text, sessionSelector.currentIndex)
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            hint.text = "Wrong password"
            passwordField.selectAll()
        }
    }

    Component.onCompleted: {
        if (sddm.lastUser !== "") {
            passwordField.forceActiveFocus()
        } else {
            userField.forceActiveFocus()
        }
    }

    // ---- small components ---------------------------------------------------
    component PersisField: TextField {
        id: field
        color: root.ink
        font.pointSize: 11
        selectByMouse: true
        background: Rectangle {
            radius: 8
            color: "#241e2b"
            border.color: field.activeFocus ? root.glow : "#3a3142"
            border.width: 1

            // animated accent underline
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                width: field.activeFocus ? parent.width - 16 : 0
                height: 2
                radius: 1
                color: root.glow
                Behavior on width {
                    NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
                }
            }
        }
    }

    component PowerButton: AbstractButton {
        id: powerButton
        property string label
        property string mode
        hoverEnabled: true

        contentItem: Text {
            text: powerButton.label
            color: powerButton.hovered ? root.glow : root.ink
            opacity: powerButton.hovered ? 1 : 0.55
            font.pointSize: 10
        }
        onClicked: mode === "reboot" ? sddm.reboot() : sddm.powerOff()
    }
}
