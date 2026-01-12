Name:           venusprolinux
Version:        1.0.0
Release:        1%{?dist}
Summary:        Linux configuration utility for UtechSmart Venus Pro MMO mouse

License:        MIT
URL:            https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3 >= 3.8
Requires:       python3-hidapi
Requires:       python3-qt6
Recommends:     python3-evdev

%description
A professional configuration utility for the UtechSmart Venus Pro MMO
gaming mouse on Linux. Features button remapping, macro editor, RGB
lighting control, DPI profiles, and polling rate adjustment.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/venusprolinux
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
mkdir -p %{buildroot}/usr/share/doc/%{name}

install -m 755 venus_gui.py %{buildroot}/usr/share/venusprolinux/
install -m 644 venus_protocol.py %{buildroot}/usr/share/venusprolinux/
install -m 644 staging_manager.py %{buildroot}/usr/share/venusprolinux/
install -m 644 transaction_controller.py %{buildroot}/usr/share/venusprolinux/
install -m 644 mouseimg.png %{buildroot}/usr/share/venusprolinux/

install -m 644 icon.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/venusprolinux.png
install -m 644 venusprolinux.desktop %{buildroot}/usr/share/applications/

install -m 644 README.md %{buildroot}/usr/share/doc/%{name}/
install -m 644 PROTOCOL.md %{buildroot}/usr/share/doc/%{name}/
install -m 644 LICENSE %{buildroot}/usr/share/doc/%{name}/

cat > %{buildroot}/usr/bin/venusprolinux << 'EOF'
#!/usr/bin/env python3
import os
import sys
os.execv(sys.executable, [sys.executable, "/usr/share/venusprolinux/venus_gui.py"] + sys.argv[1:])
EOF
chmod 755 %{buildroot}/usr/bin/venusprolinux

%files
/usr/bin/venusprolinux
/usr/share/venusprolinux/
/usr/share/applications/venusprolinux.desktop
/usr/share/icons/hicolor/512x512/apps/venusprolinux.png
%doc /usr/share/doc/%{name}/

%post
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

%changelog
* Sun Jan 11 2026 Es00bac <es00bac@github.com> - 1.0.0-1
- Initial release
