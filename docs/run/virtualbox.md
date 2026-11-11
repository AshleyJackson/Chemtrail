# Installing the image in VirtualBox

This is the first end-to-end check of the image as a *machine*: Anaconda starts,
a human installs it, and the installed system boots. It is not a desktop test —
the image built today carries the platform (NVIDIA module, session libraries,
greenboot) and no desktop environment.

Two paths are documented here. Sections 1–6 record how the image was first
installed from an ISO we build; that path is history now, kept because it
recorded three failures that shaped the builder. **The install path going forward
is the network install in section 7** (ADR-0020): Fedora's own netinst media plus
a kickstart that pulls the image from GHCR. No ISO carrying the payload is built
or published. §7.0 builds the whole thing into one bootable file; §7.1–§7.3 do the
same by hand, which is what to reach for when something goes wrong.

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

## 7. Network install (ADR-0020)

The install medium is Fedora's netinst ISO — we build nothing and host only a
few-KB kickstart that tells Anaconda to pull the image from GHCR with its `bootc`
command. The kickstart lives in this repository as `install/aios-netinst.ks` and
pins, by digest, the first image CI published (commit 9219567). Note that every
new commit builds a new image, so this file lags HEAD until it is re-rendered —
that rendering is what promotion does per channel (ADR-0020 follow-up), not
something to do by hand for each test.

### 7.0 Build the one-file medium

There is a shortcut that removes every manual step below: bake the kickstart into
Fedora's installer image and boot the result.

```bash
bash ci/build-netboot-iso.sh
```

It prints the ISO path, its size, and its SHA-256. The output is
`build/netboot/aios-netboot-x86_64.iso`, and it is Fedora's netinstall media plus
one file, so it stays within a few megabytes of Fedora's own download.

What it does, and why each part is there:

- **Fetches Fedora's netinst ISO and verifies it** against the published
  `Fedora-Server-45-1.4-x86_64-CHECKSUM`. The base installer is Fedora's, so it is
  checked rather than trusted.
- **Embeds `install/aios-netinst.ks`** with `mkksiso`, which also rewrites the boot
  entries to `inst.ks=hd:LABEL=<iso's volume id>:/aios-netinst.ks`. The kernel
  arguments are inside the EFI boot image, which is why this needs `losetup` and
  `mkefiboot`: an unprivileged container cannot rebuild it, so run the script with
  `--privileged` when running it in a container.
- **Proves the result** is an ISO9660 image (`CD001` at offset 32769) with the
  kickstart actually inside it, rather than trusting the tool's exit status.

The kickstart pins a digest, so this medium installs exactly one image. Rebuild it
after a new image is published, or point it at a different digest by editing the
`bootc --source-imgref` line first.

Boot it in the VM from section 2 — port 0 holds this ISO instead of ours — and the
install runs unattended: the kickstart supplies storage, locale, and the
deployment. There is nothing to answer.

### 7.1 Get the media

- **Fedora Server 45 netinst ISO** (~1.2 GiB) from Fedora's own download page,
  https://fedoraproject.org/server/download — the "Network Install" image for
  x86_64 (the file is `Fedora-Server-netinst-x86_64-45-*.iso` under
  `download.fedoraproject.org/pub/fedora/linux/releases/`). It is published and
  mirrored by Fedora; it costs this project no storage and no releases.
- **The kickstart**, served over HTTP. For a one-off test no hosting decision is
  needed:

  ```
  inst.ks=https://raw.githubusercontent.com/AshleyJackson/Chemtrail/master/install/aios-netinst.ks
  ```

  One file per install, so the rate limits that make raw.githubusercontent.com a
  poor fit for *update resolution* do not matter here. Local serving is in 7.3.

### 7.2 Create the VM

Same as section 2, with two differences:

- Attach the **Fedora netinst ISO** on port 0 instead of our ISO.
- The installer must reach both the internet (it pulls the image) and the
  kickstart URL. Plain NAT reaches the internet but not the host; a NAT network
  reaches both:

  ```powershell
  & $vbox natnetwork add --netname AI_OS-net --network 192.168.56.0/24
  & $vbox modifyvm $vm --nic1 natnetwork --nat-network1 AI_OS-net
  ```

  (VirtualBox 7.x: the subcommand is `natnetwork add`, and a NIC set to
  `natnetwork` must name its network with `--nat-networkN` or it uses the
  default.) The host gets an address in that subnet; `ipconfig` shows it if you
  serve the kickstart locally.

### 7.3 Install with inst.ks=

Boot the VM from the netinst ISO. At the GRUB menu press `e`, append to the end
of the `linux` line:

```
 inst.ks=https://raw.githubusercontent.com/AshleyJackson/Chemtrail/master/install/aios-netinst.ks
```

and boot with Ctrl+X. Anaconda fetches the kickstart and pre-fills everything it
contains — storage (it wipes the disk), locale, and the `bootc` deployment — so
the install is confirm-and-begin rather than a form to fill in. To serve the file
locally instead of from GitHub:

```powershell
# on the host, from the repository root; any static file server works
python -m http.server 8080
```

and use `inst.ks=http://<host-ip-in-192.168.56.0/24>:8080/install/aios-netinst.ks`.

Expect the deployment step to be slow in a different way than the ISO path: the
image is pulled from GHCR over the VM's network, several gigabytes of it. The
progress bar is honest about it.

### 7.4 What success looks like / when it fails

Sections 4 and 5 apply unchanged — `bootc status` on the installed system must
show the digest the kickstart named. Two failure modes are specific to this path:

- **Anaconda cannot fetch the kickstart:** wrong URL, or a network mode that
  cannot reach the host (plain NAT). The error names the URL it tried.
- **The `bootc` step fails with a registry error:** the image is not published
  yet, or GHCR does not serve it anonymously — both are pipeline problems, not
  installer problems. Check that the build workflow has completed and that the
  digest in the kickstart matches what GHCR serves.
