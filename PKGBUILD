# Maintainer: Es00bac <cabewse at gmail dot com>

pkgname=venusprolinux-git
pkgver=0.2.1.r7.g2b67745
pkgrel=1
pkgdesc="Linux configuration and battery utility for UtechSmart Venus mice"
arch=('any')
url="https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility"
license=('MIT')
depends=('python' 'python-hidapi' 'python-pyqt6')
makedepends=('git')
optdepends=('python-pyusb: USB-bus diagnostics and recovery')
provides=('venusprolinux')
conflicts=('venusprolinux')
install=venusprolinux.install
source=('venusprolinux::git+https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility.git')
sha256sums=('SKIP')

pkgver() {
    cd "$srcdir/venusprolinux"
    git describe --long --tags --always | sed -E 's/^v//;s/([^-]*-g)/r\1/;s/-/./g'
}

package() {
    cd "$srcdir/venusprolinux"

    install -d "$pkgdir/usr/share/venusprolinux"
    install -m644 venus_gui.py venus_protocol.py holtek_protocol.py \
        device_driver.py staging_manager.py transaction_controller.py \
        mouseimg.png icon.png "$pkgdir/usr/share/venusprolinux/"

    install -Dm755 packaging/linux/venusprolinux \
        "$pkgdir/usr/bin/venusprolinux"
    install -Dm644 packaging/linux/venusprolinux.desktop \
        "$pkgdir/usr/share/applications/venusprolinux.desktop"
    install -Dm644 com.github.es00bac.venusprolinux.appdata.xml \
        "$pkgdir/usr/share/metainfo/com.github.es00bac.venusprolinux.appdata.xml"
    install -Dm644 icon.png \
        "$pkgdir/usr/share/icons/hicolor/512x512/apps/venusprolinux.png"
    install -Dm644 packaging/linux/99-venus-pro.rules \
        "$pkgdir/usr/lib/udev/rules.d/99-venus-pro.rules"
    install -Dm644 LICENSE \
        "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
