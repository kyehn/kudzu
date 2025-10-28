set -l mode (gsettings get org.gnome.system.proxy mode | string trim -c "'")
if test "$mode" != manual
    return
end

set -l hosts (gsettings get org.gnome.system.proxy ignore-hosts | string trim -c "[]'" | string replace -a "', '" ",")
if test -n "$hosts"
    set -gx no_proxy $hosts
    set -gx NO_PROXY $hosts
end

set -l http_host (gsettings get org.gnome.system.proxy.http host | string trim -c "'")
set -l http_port (gsettings get org.gnome.system.proxy.http port)
if test -n "$http_host"
    set -gx http_proxy "http://$http_host:$http_port"
    set -gx HTTP_PROXY "http://$http_host:$http_port"
end

set -l https_host (gsettings get org.gnome.system.proxy.https host | string trim -c "'")
set -l https_port (gsettings get org.gnome.system.proxy.https port)
if test -n "$https_host"
    set -gx https_proxy "https://$https_host:$https_port"
    set -gx HTTPS_PROXY "https://$https_host:$https_port"
end

set -l ftp_host (gsettings get org.gnome.system.proxy.ftp host | string trim -c "'")
set -l ftp_port (gsettings get org.gnome.system.proxy.ftp port)
if test -n "$ftp_host"
    set -gx ftp_proxy "ftp://$ftp_host:$ftp_port"
    set -gx FTP_PROXY "ftp://$ftp_host:$ftp_port"
end

set -l socks_host (gsettings get org.gnome.system.proxy.socks host | string trim -c "'")
set -l socks_port (gsettings get org.gnome.system.proxy.socks port)
if test -n "$socks_host"
    set -gx all_proxy "socks5://$socks_host:$socks_port"
    set -gx ALL_PROXY "socks5://$socks_host:$socks_port"
end
