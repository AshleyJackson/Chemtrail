# Installing the image in VirtualBox

This is the first end-to-end check of the image as a *machine*: Anaconda starts,
a human installs it, and the installed system boots. It is not a desktop test —
the image built today carries the platform (NVIDIA module, session libraries,
greenboot) and no desktop environment.

## 1. Build the ISO

```bash
bash ci/build-iso.sh
```

It prints the ISO path and its SHA-256. The path is
`build/iso/bootiso/install.iso`; the script finds the file rather than assuming,
so trust what it prints.

On a Windows host there is no `bash`, so the script runs in a container against
the host engine (Docker Desktop), which is what it was written for:

```powershell
docker run --rm -v "${PWD}:/w" -w /w `
  -v /var/run/docker.sock:/var/run/docker.sock `
  -e HOME=/tmp/client -e DOCKER_CONFIG=/tmp/client/.docker `
  quay.io/fedora/fedora-bootc:45 bash -c `
  'mkdir -p /tmp/client && dnf -y -q install docker-cli >/dev/null && RUNTIME=docker bash ci/build-iso.sh'
```

Three things it does that are not obvious, each learned by failing first:

- **The builder cannot read the engine's storage.** It needs a containers/storage
  holding the image, so the script pushes to a throwaway registry and copies the
  image in with `skopeo`. Nothing touches `/var/lib/docker`.
- **It needs the host cgroup namespace.** Without `--cgroupns=host`, nested podman
  inside the builder dies on the `pids` controller.
- **Fedora 45 keeps its repositories in `/usr/share/dnf5/repos.d`**, which osbuild
  does not read. The Containerfile copies them into `/etc/yum.repos.d`; without
  that the build stops at `NoReposError`.

## 2. Create the VM

VirtualBox cannot run a bootc image in BIOS mode. The firmware flag is not
optional: without EFI the installer never starts.

```powershell
$vbox  = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
$iso   = "C:\Users\ashley\projects\ashleyjackson\AI_OS\build\iso\bootiso\install.iso"
$vm    = "AI_OS"
$disks = "C:\Users\ashley\VMs\AI_OS"

New-Item -ItemType Directory -Force -Path $disks | Out-Null

& $vbox createvm --name $vm --ostype Fedora_64 --register
& $vbox createmedium disk --filename "$disks\disk.vdi" --size 40960 --format VDI

& $vbox modifyvm $vm `
  --memory 8192 --cpus 4 --firmware efi `
  --graphicscontroller vmsvga --vram 128 `
  --nic1 nat --audio-driver none `
  --uart1 0x3F8 4 --uartmode1 file "$disks\serial.log"

& $vbox storagectl $vm --name SATA --add sata --controller IntelAhci --portcount 2
& $vbox storageattach $vm --storagectl SATA --port 0 --device 0 `
  --type dvddrive --medium $iso
& $vbox storageattach $vm --storagectl SATA --port 1 --device 0 `
  --type hdd --medium "$disks\disk.vdi"
```

Memory and disk are deliberately generous. The installed system carries the
kernel from the day the image was built, and a smaller disk leaves no room for
the second deployment that rollback needs.

## 3. Install

```powershell
& $vbox startvm $vm
```

Anaconda comes up in the VirtualBox window. Create a user first: the installer
will not ask again later, and a system with no account cannot be logged into once
it boots. Then accept the defaults for storage (the installer wipes the 40 GB
disk) and begin the installation.

Expect the payload step to be slow. The installer writes the whole container image
from the ISO to the disk, several gigabytes of it, and in VirtualBox that runs at
a few megabytes per second; it can take tens of minutes. The progress bar is
honest about it.

Notes:

- **Secure Boot stays off.** VirtualBox's EFI does not enforce it by default, and
  the MOK enrolment path in [fedora-bootc.md](../architecture/fedora-bootc.md) §5
  is not implemented yet. Nothing in this image needs the key.
- **There is no NVIDIA GPU here.** `nvidia.ko` ships in the deployment and is
  never loaded, which is exactly the case the greenboot checks were written for:
  the required check only asserts the module is present on disk, and the wanted
  check exits clean when no NVIDIA device exists.

## 4. What success looks like

After the reboot into the installed system:

```bash
bootc status                 # the booted digest matches what the ISO carried
cat /usr/lib/aios/build-id   # the build identity baked at image time
systemctl is-system-running  # "running" or "degraded"; degraded needs a reason
systemctl --failed           # empty, or explained
journalctl -b -u greenboot-healthcheck --no-pager
```

A working install reaches multi-user, reports its own build id, and does not roll
back. A boot that reaches `greenboot` and fails its required check is a failed
install from our point of view, not a VirtualBox quirk.

## 5. When it fails

The serial log is the useful artefact, and it is captured even when the window is
closed:

```powershell
Get-Content "$disks\serial.log" -Tail 80
```

- **No bootable medium / firmware shell:** the VM was created without
  `--firmware efi`, or the ISO is not attached on port 0.
- **Anaconda starts, installation fails:** read the payload error; the image is
  pulled from the ISO, so a payload error means the ISO is incomplete, not that
  the network is down.
- **Installed system boots to emergency shell:** check the serial log for the
  failed unit before changing anything; `bootc status` from the emergency shell
  confirms which deployment booted.

## 6. Tear down

```powershell
& $vbox unregistervm $vm --delete
```
