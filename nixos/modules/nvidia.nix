{
  inputs,
  lib,
  ...
}:

let
  nvidiaDriver = false;
  primeEnable = false && nvidiaDriver;
in
{
  imports = lib.optionals (!nvidiaDriver) [
    inputs.nixos-hardware.nixosModules.common-gpu-nvidia-disable
  ];
  services.xserver.videoDrivers = lib.optionals nvidiaDriver [ "nvidia" ];
  hardware.nvidia = lib.optionalAttrs nvidiaDriver {
    open = true;
    modesetting.enable = true;
    nvidiaSettings = false;
    powerManagement = {
      enable = true;
      finegrained = primeEnable;
    };
    prime = lib.optionalAttrs primeEnable {
      amdgpuBusId = "PCI:5:0:0";
      nvidiaBusId = "PCI:1:0:0";
      offload = {
        enable = true;
        enableOffloadCmd = true;
      };
    };
  };
}
