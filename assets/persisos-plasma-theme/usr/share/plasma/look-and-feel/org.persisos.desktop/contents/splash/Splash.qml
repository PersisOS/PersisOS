import QtQuick 2.15

Rectangle {
    id: root
    color: "#15121b"
    opacity: 1

    property int stage
    readonly property int totalStages: 6
    readonly property color accent: "#b773d4"
    readonly property color foreground: "#f7f3fa"

    onStageChanged: {
        if (stage === 1)
            intro.start()
        if (stage >= totalStages)
            fadeOut.start()
    }

    Rectangle {
        id: ambientGlow
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.56, 560)
        height: width
        radius: width / 2
        color: "#8739a5"
        opacity: 0.08
        scale: 0.88

        SequentialAnimation on scale {
            running: root.stage < root.totalStages
            loops: Animation.Infinite
            NumberAnimation { to: 1.02; duration: 4800; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.88; duration: 4800; easing.type: Easing.InOutSine }
        }
    }

    Column {
        id: brandBlock
        anchors.centerIn: parent
        spacing: 20
        opacity: 0

        Image {
            id: logo
            anchors.horizontalCenter: parent.horizontalCenter
            source: "/usr/share/icons/hicolor/scalable/apps/persisos.svg"
            sourceSize.width: 116
            sourceSize.height: 116
            width: 116
            height: 116
            smooth: true
            scale: 0.92
            transformOrigin: Item.Center
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "PersisOS"
            color: root.foreground
            font.family: "Inter"
            font.pointSize: 25
            font.weight: Font.DemiBold
            font.letterSpacing: 1.2
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 68
            height: 3
            radius: 2
            color: root.accent
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Preparing your desktop"
            color: "#c8bfce"
            font.family: "Inter"
            font.pointSize: 11
        }

        Item {
            width: 240
            height: 4

            Rectangle {
                anchors.fill: parent
                radius: 2
                color: "#ffffff"
                opacity: 0.14
            }
            Rectangle {
                width: parent.width * Math.max(0.04, Math.min(1, root.stage / root.totalStages))
                height: parent.height
                radius: 2
                color: root.accent
                Behavior on width {
                    NumberAnimation { duration: 450; easing.type: Easing.OutCubic }
                }
            }
        }
    }

    ParallelAnimation {
        id: intro
        NumberAnimation {
            target: brandBlock
            property: "opacity"
            to: 1
            duration: 650
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: logo
            property: "scale"
            to: 1
            duration: 800
            easing.type: Easing.OutBack
        }
    }

    NumberAnimation {
        id: fadeOut
        target: root
        property: "opacity"
        to: 0
        duration: 350
        easing.type: Easing.OutCubic
    }

    Component.onCompleted: {
        if (stage >= 1)
            intro.start()
    }
}
