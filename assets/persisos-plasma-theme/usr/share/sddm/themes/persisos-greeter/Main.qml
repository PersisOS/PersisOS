import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    width: 1600
    height: 900

    readonly property color ink: "#f7f4fb"
    readonly property color muted: "#c2bbcc"
    readonly property color accent: "#bd73df"
    property string message: ""
    property real welcomeIntroOffset: 24

    Image {
        anchors.fill: parent
        source: config.background
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#10101730" }
            GradientStop { position: 0.48; color: "#10101788" }
            GradientStop { position: 1.0; color: "#101017e8" }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#111018"
        opacity: 0.16
    }

    Column {
        id: welcome
        anchors.left: parent.left
        anchors.leftMargin: Math.max(48, root.width * 0.105)
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(480, root.width * 0.38)
        spacing: 18
        opacity: 0
        anchors.verticalCenterOffset: root.welcomeIntroOffset

        Image {
            source: "/usr/share/icons/hicolor/scalable/apps/persisos.svg"
            sourceSize.width: 72
            sourceSize.height: 72
            width: 72
            height: 72
            smooth: true
        }

        Text {
            text: "Welcome to"
            color: root.muted
            font.family: "Inter"
            font.pixelSize: 20
        }

        Text {
            text: "PersisOS"
            color: root.ink
            font.family: "Inter"
            font.pixelSize: Math.min(64, root.width * 0.052)
            font.weight: Font.DemiBold
        }

        Rectangle {
            width: 56
            height: 3
            radius: 2
            color: root.accent
        }

        Text {
            width: parent.width
            text: "A calm, capable desktop, ready when you are."
            color: root.muted
            font.family: "Inter"
            font.pixelSize: 17
            wrapMode: Text.WordWrap
        }

        Behavior on opacity {
            NumberAnimation { duration: 650; easing.type: Easing.OutCubic }
        }
        Behavior on welcomeIntroOffset {
            NumberAnimation { duration: 650; easing.type: Easing.OutCubic }
        }
    }

    Rectangle {
        id: loginCard
        width: Math.min(390, root.width * 0.34)
        height: form.implicitHeight + 72
        anchors.right: parent.right
        anchors.rightMargin: Math.max(48, root.width * 0.12)
        anchors.verticalCenter: parent.verticalCenter
        radius: 22
        color: "#201d28"
        border.width: 1
        border.color: "#ffffff20"
        opacity: 0
        scale: 0.97

        Column {
            id: form
            anchors.fill: parent
            anchors.margins: 34
            spacing: 14

            Text {
                text: "Sign in"
                color: root.ink
                font.family: "Inter"
                font.pixelSize: 26
                font.weight: Font.DemiBold
            }

            Text {
                text: "Continue to your PersisOS session"
                color: root.muted
                font.family: "Inter"
                font.pixelSize: 13
            }

            TextField {
                id: username
                width: parent.width
                height: 48
                text: userModel.lastUser
                placeholderText: "Username"
                font.family: "Inter"
                font.pixelSize: 15
                color: root.ink
                leftPadding: 14
                background: Rectangle {
                    radius: 10
                    color: "#302b39"
                    border.color: username.activeFocus ? root.accent : "#ffffff20"
                }
                onAccepted: password.forceActiveFocus()
            }

            TextField {
                id: password
                width: parent.width
                height: 48
                placeholderText: "Password"
                echoMode: TextInput.Password
                font.family: "Inter"
                font.pixelSize: 15
                color: root.ink
                leftPadding: 14
                background: Rectangle {
                    radius: 10
                    color: "#302b39"
                    border.color: password.activeFocus ? root.accent : "#ffffff20"
                }
                onAccepted: root.login()
            }

            ComboBox {
                id: session
                width: parent.width
                height: 44
                model: sessionModel
                textRole: "name"
                currentIndex: sessionModel.lastIndex
                font.family: "Inter"
                font.pixelSize: 14
                contentItem: Text {
                    leftPadding: 12
                    text: session.displayText
                    color: root.ink
                    font: session.font
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                background: Rectangle {
                    radius: 10
                    color: "#302b39"
                    border.color: session.activeFocus ? root.accent : "#ffffff20"
                }
            }

            Text {
                width: parent.width
                text: root.message
                color: "#ffb4ab"
                font.family: "Inter"
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                visible: text.length > 0
            }

            Button {
                width: parent.width
                height: 48
                text: "Sign in"
                font.family: "Inter"
                font.pixelSize: 15
                font.weight: Font.DemiBold
                contentItem: Text {
                    text: parent.text
                    color: "#ffffff"
                    font: parent.font
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 10
                    color: parent.down ? "#8d4daf" : "#a65dc9"
                    Behavior on color { ColorAnimation { duration: 140 } }
                }
                onClicked: root.login()
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                Button {
                    text: "Restart"
                    enabled: sddm.canReboot
                    onClicked: sddm.reboot()
                    background: Rectangle { color: "transparent" }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? root.muted : "#77717e"
                        font.family: "Inter"
                        font.pixelSize: 12
                    }
                }
                Button {
                    text: "Shut down"
                    enabled: sddm.canPowerOff
                    onClicked: sddm.powerOff()
                    background: Rectangle { color: "transparent" }
                    contentItem: Text {
                        text: parent.text
                        color: parent.enabled ? root.muted : "#77717e"
                        font.family: "Inter"
                        font.pixelSize: 12
                    }
                }
            }
        }

        Behavior on opacity {
            NumberAnimation { duration: 650; easing.type: Easing.OutCubic }
        }
        Behavior on scale {
            NumberAnimation { duration: 650; easing.type: Easing.OutBack }
        }
    }

    function login() {
        if (username.text.trim().length === 0) {
            root.message = "Enter your username to continue."
            username.forceActiveFocus()
            return
        }
        root.message = ""
        sddm.login(username.text, password.text, session.currentIndex)
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            root.message = "That password did not work. Please try again."
            password.clear()
            password.forceActiveFocus()
        }
    }

    Component.onCompleted: {
        welcome.opacity = 1
        root.welcomeIntroOffset = 0
        loginCard.opacity = 1
        loginCard.scale = 1
        if (username.text.length > 0)
            password.forceActiveFocus()
        else
            username.forceActiveFocus()
    }
}
