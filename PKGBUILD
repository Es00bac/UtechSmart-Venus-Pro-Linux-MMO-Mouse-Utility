pkgname=venusprolinux
pkgver=1.0.0
pkgrel=1
pkgdesc="Linux configuration utility for the UtechSmart Venus Pro MMO mouse"
arch=('any')
url="https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility"
license=('MIT')
depends=('python' 'python-hidapi' 'python-pyqt6')
optdepends=('python-evdev: software macro playback' 'python-pyusb: magic unlock helper')
provides=('venusprolinux')
conflicts=('venusprolinux')

package() {
  cd "${srcdir}/VenusProLinux"
  install -Dm755 venus_gui.py "${pkgdir}/usr/share/venusprolinux/venus_gui.py"
  install -Dm644 venus_protocol.py "${pkgdir}/usr/share/venusprolinux/venus_protocol.py"
  install -Dm644 staging_manager.py "${pkgdir}/usr/share/venusprolinux/staging_manager.py"
  install -Dm644 transaction_controller.py "${pkgdir}/usr/share/venusprolinux/transaction_controller.py"
  install -Dm644 mouseimg.png "${pkgdir}/usr/share/venusprolinux/mouseimg.png"
  install -Dm644 PROTOCOL.md "${pkgdir}/usr/share/doc/venusprolinux/PROTOCOL.md"
  install -Dm644 README.md "${pkgdir}/usr/share/doc/venusprolinux/README.md"

  # Install icon
  install -Dm644 icon.png "${pkgdir}/usr/share/icons/hicolor/512x512/apps/venusprolinux.png"

  # Install desktop entry
  install -Dm644 venusprolinux.desktop "${pkgdir}/usr/share/applications/venusprolinux.desktop"

  install -Dm755 /dev/stdin "${pkgdir}/usr/bin/venusprolinux" <<'EOF'
#!/usr/bin/env python3
import os
import sys

os.execv(sys.executable, [sys.executable, "/usr/share/venusprolinux/venus_gui.py"] + sys.argv[1:])
EOF
}
