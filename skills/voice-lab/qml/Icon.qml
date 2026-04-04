import QtQuick
import "."

// SVG icon component with size control.
// Icons are white by default — use opacity for dimming.
// Usage: Icon { source: "icons/play.svg"; size: 20; opacity: 0.6 }
Image {
    id: icon
    property int size: 20

    width: size
    height: size
    sourceSize: Qt.size(size, size)
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
}
