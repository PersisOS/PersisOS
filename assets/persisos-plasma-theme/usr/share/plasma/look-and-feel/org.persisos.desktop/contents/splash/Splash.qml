import QtQuick 2.15

// PersisOS splash — "violet night".
// A single quiet composition: the logo rises out of a soft glow while a thin
// accent line underneath fills in step with the real session startup stages.
Rectangle {
    id: root
    color: "#141317"

    // ksplashqml increments this as it passes each well-known startup stage.
    property int stage
    readonly property int totalStages: 6

    readonly property color brand: "#9738ba"
    readonly property color glow: "#b25ae8"
    readonly property color ink: "#f4eff8"

    onStageChanged: {
        if (stage === 1) {
            intro.start()
        }
    }

    // Soft radial glow behind the logo, built from translucent circles so no
    // graphical-effects import is needed.
    Item {
        anchors.centerIn: logo
        width: 460
        height: 460

        Rectangle {
            anchors.centerIn: parent
            width: 440
            height: 440
            radius: 220
            color: root.brand
            opacity: 0.08
        }
        Rectangle {
            anchors.centerIn: parent
            width: 300
            height: 300
            radius: 150
            color: root.glow
            opacity: 0.07
        }

        // The glow breathes very slowly; barely visible, but keeps the
        // screen from feeling like a frozen frame.
        SequentialAnimation on opacity {
            loops: Animation.Infinite
            NumberAnimation { to: 0.75; duration: 3200; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 3200; easing.type: Easing.InOutSine }
        }
    }

    Item {
        id: logoSlot
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -26
        width: 168
        height: 168

        Image {
            id: logo
            source: "/usr/share/icons/hicolor/scalable/apps/persisos.svg"
            sourceSize.width: 168
            sourceSize.height: 168
            width: 168
            height: 168
            y: 18
            opacity: 0
            smooth: true

            ParallelAnimation {
                id: intro
                NumberAnimation {
                    target: logo
                    property: "opacity"
                    from: 0
                    to: 1
                    duration: 700
                    easing.type: Easing.OutQuad
                }
                NumberAnimation {
                    target: logo
                    property: "y"
                    from: 18
                    to: 0
                    duration: 700
                    easing.type: Easing.OutCubic
                }
                NumberAnimation {
                    target: wordmark
                    property: "opacity"
                    from: 0
                    to: 1
                    duration: 900
                    easing.type: Easing.OutQuad
                }
            }
        }
    }

    Text {
        id: wordmark
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: logo.bottom
        anchors.topMargin: 28
        text: "PersisOS"
        color: root.ink
        font.pointSize: 22
        font.letterSpacing: 6
        opacity: 0
    }

    // Thin progress line, tied to actual startup stages.
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: wordmark.bottom
        anchors.topMargin: 22
        width: 220
        height: 2

        Rectangle {
            anchors.fill: parent
            radius: 1
            color: "#ffffff"
            opacity: 0.12
        }
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            height: parent.height
            radius: 1
            width: parent.width * Math.min(1, root.stage / root.totalStages)
            color: root.glow
            Behavior on width {
                NumberAnimation { duration: 400; easing.type: Easing.OutCubic }
            }
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.verticalCenter
        anchors.topMargin: 130
        text: "Starting session"
        color: root.ink
        opacity: 0.45
        font.pointSize: 11
        font.letterSpacing: 2

        SequentialAnimation on opacity {
            loops: Animation.Infinite
            NumberAnimation { to: 0.18; duration: 1400; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.45; duration: 1400; easing.type: Easing.InOutSine }
        }
    }

    // Fade the whole splash out once the session signals its last stage.
    NumberAnimation {
        target: root
        property: "opacity"
        to: 0
        duration: 250
        running: root.stage >= root.totalStages
    }
}
