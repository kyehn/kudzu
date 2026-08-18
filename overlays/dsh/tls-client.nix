# 预编译 tls-client (bogdanfinn) 共享库,提供 opencode 模拟所需的自定义
# ClientHello (JA3/JA4)。node-tls-client 在构建时注入该库路径(OPENCODE_TLS_LIBRARY),
# 运行时零下载、完全可复现。
{
  lib,
  fetchurl,
  stdenv,
}:

let
  version = "1.15.1";
  asset =
    {
      x86_64-linux = {
        name = "tls-client-linux-ubuntu-amd64-${version}.so";
        hash = "sha256-45PoZgYOI4vDZQn4Uyk86/Wvgoau3lmBRGJpPvtgOx4=";
      };
      aarch64-linux = {
        name = "tls-client-linux-arm64-${version}.so";
        hash = "sha256-BIt1xPsImKMGIoGY1UXuzjmn1TSCAEh/A5X73EFo/jk=";
      };
    }
    .${stdenv.hostPlatform.system}
    or (throw "dsh: unsupported platform ${stdenv.hostPlatform.system} (tls-client has no prebuilt shared library)");
in
fetchurl {
  url = "https://github.com/bogdanfinn/tls-client/releases/download/v${version}/${asset.name}";
  hash = asset.hash;
  meta.license = lib.licenses.bsd3;
}