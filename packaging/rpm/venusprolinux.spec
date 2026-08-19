%{!?venus_version:%global venus_version 0.3.0}
%global app_id com.github.es00bac.venusprolinux

Name:           venusprolinux
Version:        %{venus_version}
Release:        1%{?dist}
Summary:        Configuration utility for UtechSmart Venus MMO mice

License:        MIT
URL:            https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

# Fedora package names, verified against the Fedora repositories. The
# python3-hidapi package supplies the imported `hid` extension module.
Requires:       python3 >= 3.10
Requires:       python3-hidapi
Requires:       python3-pyqt6

%description
Configure supported UtechSmart Venus MMO mice on Linux. Features include
button remapping, hardware macros, RGB lighting, DPI profiles, polling rate,
and battery monitoring.

%prep
%autosetup

%build

%install
install -d \
    %{buildroot}%{_bindir} \
    %{buildroot}%{_datadir}/%{name} \
    %{buildroot}%{_datadir}/applications \
    %{buildroot}%{_datadir}/icons/hicolor/1024x1024/apps \
    %{buildroot}%{_metainfodir} \
    %{buildroot}%{_udevrulesdir}

install -m644 \
    venus_gui.py venus_protocol.py holtek_protocol.py device_driver.py \
    staging_manager.py transaction_controller.py mouseimg.png icon.png \
    %{buildroot}%{_datadir}/%{name}/
install -m755 packaging/linux/venusprolinux \
    %{buildroot}%{_bindir}/venusprolinux
install -m644 packaging/linux/%{app_id}.desktop \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -m644 icon.png \
    %{buildroot}%{_datadir}/icons/hicolor/1024x1024/apps/%{app_id}.png
install -m644 %{app_id}.appdata.xml \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
install -m644 packaging/linux/99-venus-pro.rules \
    %{buildroot}%{_udevrulesdir}/99-venus-pro.rules

%files
%license LICENSE
%doc README.md PROTOCOL.md docs/MACRO_EDITOR.md
%{_bindir}/venusprolinux
%{_datadir}/%{name}/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/1024x1024/apps/%{app_id}.png
%{_metainfodir}/%{app_id}.metainfo.xml
%{_udevrulesdir}/99-venus-pro.rules

%changelog
* Wed Aug 19 2026 Es00bac <es00bac@github.com> - 0.3.0-1
- Add controller-aware configuration, expanded macros, and release packaging.
