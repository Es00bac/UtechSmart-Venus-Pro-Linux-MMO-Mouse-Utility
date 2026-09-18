# Copyright 2026 QindaQt contributors
# Distributed under the terms of the GNU General Public License v2

EAPI=8

PYTHON_COMPAT=( python3_{12..14} )

# AGENT-NOTE: like the other first-party overlay packages this pins a commit
# of the local development checkout. Upstream lives on GitHub (HOMEPAGE) but
# the QindaTK interface has not been published there yet; once it is, replace
# git-r3 with a SRC_URI archive of the tag. The bare repository comes first,
# then either machine's working tree: git-r3 takes the first URI that exists.
inherit desktop python-single-r1 udev xdg git-r3

DESCRIPTION="Configuration utility for the UtechSmart Venus Pro MMO mouse (Qt Widgets and QindaTK interfaces)"
HOMEPAGE="https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility"
EGIT_REPO_URI="file:///home/cabewse/git/QindaVenusPro.git
	file:///home/cabewse/work_SPaC3/QindaVenusPro
	file:///home/cabewse/work_space/QindaVenusPro"
# AGENT-NOTE: an immutable pin, not a branch - a package built twice must be
# the same package. Bump it together with the version.
EGIT_COMMIT="4e3eeabbc9b490f00d7b884bcccf31d110f5a7ff"

LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64"
IUSE="+qindatk test usb +widgets"
# At least one interface must be installed for the launcher to start.
REQUIRED_USE="${PYTHON_REQUIRED_USE} || ( qindatk widgets )"
RESTRICT="!test? ( test )"

APP_ID="com.github.es00bac.venusprolinux"

# The Widgets interface needs pyqt6[widgets]; the QindaTK one needs the
# QtQml/QtQuick bindings (pyqt6[qml,quick]) plus the QindaTK QML module and
# takes the tray icon from QtWidgets when that binding is present. The
# python-hidapi binding supplies the `hid` module both interfaces open the
# mouse with; pyusb only backs the optional "reclaim device" action.
RDEPEND="
	${PYTHON_DEPS}
	$(python_gen_cond_dep '
		dev-python/hidapi[${PYTHON_USEDEP}]
		dev-python/pyqt6[gui,${PYTHON_USEDEP}]
		qindatk? ( dev-python/pyqt6[qml,quick,${PYTHON_USEDEP}] )
		widgets? ( dev-python/pyqt6[widgets,${PYTHON_USEDEP}] )
		usb? ( dev-python/pyusb[${PYTHON_USEDEP}] )
	')
	qindatk? (
		>=dev-libs/qindatk-0.1.0
		>=dev-qt/qtdeclarative-6.8:6
	)
	virtual/udev
"
DEPEND="${RDEPEND}"
BDEPEND="
	test? ( ${RDEPEND} )
"

src_test() {
	# Everything here is hardware-safe and headless; the GUI suites render
	# offscreen with the software renderer and write settings under ${T}.
	local -x QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software HOME="${T}"
	local tests=(
		tests.test_areson_protocol_offline tests.test_holtek_protocol_offline
		tests.test_protocol tests.test_rgb tests.test_staging
		tests.test_atomic_controller tests.test_error_recovery
		tests.test_macro_draft tests.test_session
	)
	use widgets && tests+=( tests.test_battery_led_gui tests.test_macro_editor )
	use qindatk && tests+=( tests.test_qml_ui )
	"${EPYTHON}" -m unittest "${tests[@]}" || die "offline test suites failed"
}

src_install() {
	local app="/usr/share/${PN}"
	insinto "${app}"
	# Modules both interfaces share.
	doins venus_protocol.py holtek_protocol.py device_driver.py \
		staging_manager.py transaction_controller.py venus_keys.py \
		venus_session.py venus_macro_draft.py mouseimg.png icon.png
	use widgets && doins venus_gui.py
	if use qindatk; then
		doins venus_qml.py venus_qml_backend.py venus_qml_models.py
		doins -r qml
	fi
	python_optimize "${ED}${app}"

	# The launcher runs the modules with the interpreter they were byte-
	# compiled for and picks the QindaTK interface when it is installed.
	sed -e "s|python3}|${EPYTHON}}|" packaging/linux/venusprolinux \
		> "${T}/venusprolinux" || die
	dobin "${T}/venusprolinux"

	domenu "packaging/linux/${APP_ID}.desktop"
	local size
	for size in 48 64 128 256 512; do
		newicon -s "${size}" "packaging/linux/icons/${size}.png" "${APP_ID}.png"
	done
	insinto /usr/share/metainfo
	newins "${APP_ID}.appdata.xml" "${APP_ID}.metainfo.xml"

	# The reviewed rule: uaccess ACLs on the hidraw and USB nodes of the
	# three supported VID:PIDs, mode 0660 as the fallback.
	udev_dorules packaging/linux/99-venus-pro.rules

	dodoc README.md PROTOCOL.md docs/MACRO_EDITOR.md docs/QINDATK_UI.md
}

pkg_postinst() {
	xdg_pkg_postinst
	udev_reload
	elog "Unplug and reconnect the Venus mouse or its receiver once so the"
	elog "udev uaccess ACL from 99-venus-pro.rules applies to your session."
	if use qindatk && use widgets; then
		elog "'venusprolinux' starts the QindaTK interface; 'venusprolinux --widgets'"
		elog "starts the Qt Widgets one (both are desktop actions of the launcher)."
	fi
}

pkg_postrm() {
	xdg_pkg_postrm
	udev_reload
}
