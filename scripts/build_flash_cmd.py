#!/usr/bin/env python3
"""
Generate a spd_dump command line to flash a Spreadtrum PAC firmware
using the classic BSL protocol (compatible with old FDLs).
"""
import os
import re
import sys
import subprocess
import xml.etree.ElementTree as ET

# === EDIT THESE PATHS TO MATCH YOUR SETUP ===
PAC = "/path/to/firmware.pac"
XML = "/path/to/extracted_pac/s9863a1h10_go.xml"
OUT_DIR = "/path/to/extracted_pac"
FDL1 = "/path/to/exploit/fdl1-dl.bin"
FDL2 = "/path/to/exploit/fdl2-dl.bin"
UNPAC = "/path/to/ilya_sprd/unpac/unpac"
SPD_DUMP = "/path/to/spreadtrum_flash/spd_dump"

# These are chip-specific constants for SC9863A. Do not change unless you
# know what you're doing.
FDL1_ADDR = "0x5000"
FDL2_ADDR = "0x9efffe00"
EXPLOIT_ADDR = "0x4ee8"

WRITE_TYPES = {"CODE2", "YAFFS_IMG2", "UBOOT_LOADER2", "MasterImage"}
ERASE_TYPES = {"EraseFlash2"}
# Skip these partitions to preserve device-unique data
SKIP_PARTITIONS = {"prodnv", "l_fixnv1_a", "l_fixnv1_b", "l_fixnv2_a", "l_fixnv2_b"}
# Partitions already successfully written (resume mode)
ALREADY_WRITTEN = {
    "splloader", "vbmeta_a", "vbmeta_system_a", "vbmeta_system_ext_a",
    "vbmeta_vendor_a", "vbmeta_product_a", "vbmeta_odm_a",
    "l_modem_a", "l_deltanv_a", "l_ldsp_a", "l_gdsp_a",
    "pm_sys_a", "boot_a",
    "vendor_boot_a", "init_boot_a", "dtbo_a",
    "cache", "blackbox", "tranfs", "userdata",
}
# Partitions already erased (resume mode)
ALREADY_ERASED = {"uboot_log", "tkv_a"}
# Defer these partitions to a separate script (too big / unstable in main batch)
DEFER_PARTITIONS = {"super"}

def get_pac_file_map():
    """Build map: file_id -> file_name from PAC contents."""
    result = subprocess.run([UNPAC, "list", PAC], capture_output=True, text=True, check=True)
    mapping = {}
    for line in result.stdout.splitlines():
        # line: type = 0x101, size = 0xd164, offset = 0x1c3bc, id = "FDL", name = "fdl1-sign.bin"
        m = re.search(r'id\s*=\s*"([^"]+)".*name\s*=\s*"([^"]+)"', line)
        if m:
            mapping[m.group(1)] = m.group(2)
    return mapping

def extract_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"[+] Extracting PAC to {OUT_DIR} ...", flush=True)
    r = subprocess.run([UNPAC, "-d", OUT_DIR, "extract", PAC],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr); sys.exit(1)
    print(f"[+] Done. Extracted {len(os.listdir(OUT_DIR))} files")

def parse_xml_files():
    """Return list of (order, file_id, type, partition_name) in XML sequence."""
    tree = ET.parse(XML)
    root = tree.getroot()
    files = []
    for i, f in enumerate(root.iter("File")):
        fid = (f.findtext("ID") or "").strip()
        ftype = (f.findtext("Type") or "").strip()
        block = f.find("Block")
        part = block.get("id") if block is not None else None
        if fid and ftype:
            files.append((i, fid, ftype, part))
    return files

def main():
    extract_all()
    pac_files = get_pac_file_map()
    print(f"[+] PAC contains {len(pac_files)} entries")

    xml_files = parse_xml_files()
    print(f"[+] XML has {len(xml_files)} File entries")

    # Build the command sequence
    cmd = [
        SPD_DUMP,
        "--wait", "300",
        "--verbose", "0",
        "--kick",                        # route boot_diag -> cali_diag -> dl_diag
        "keep_charge", "1",
        "exec_addr", EXPLOIT_ADDR,       # CVE-2022-38694 trigger (SC9863A)
        "fdl", FDL1, FDL1_ADDR,          # unlocked FDL1 (itel-dl)
        "fdl", FDL2, FDL2_ADDR,          # unlocked FDL2 (itel-dl)
        "exec",
        "disable_transcode",
        "skip_confirm", "1",
        "repartition", XML,
    ]

    ops_write = 0
    ops_erase = 0
    skipped = []
    for order, fid, ftype, part in xml_files:
        if ftype in ("FDL", "NAND_FDL"):
            continue
        if part in SKIP_PARTITIONS:
            skipped.append(f"{fid} ({ftype}) -> {part}: preserve device-unique data")
            continue
        if part in ALREADY_WRITTEN or part in ALREADY_ERASED:
            skipped.append(f"{fid} ({ftype}) -> {part}: already done (resume)")
            continue
        if part in DEFER_PARTITIONS:
            skipped.append(f"{fid} ({ftype}) -> {part}: deferred to separate script")
            continue
        if ftype in ERASE_TYPES and part:
            cmd += ["erase_part", part]
            ops_erase += 1
            continue
        if ftype in WRITE_TYPES and part:
            pac_name = pac_files.get(fid)
            if not pac_name:
                skipped.append(f"{fid} ({ftype}): no PAC file")
                continue
            file_path = os.path.join(OUT_DIR, pac_name)
            if not os.path.exists(file_path):
                skipped.append(f"{fid} ({ftype}): missing {pac_name}")
                continue
            cmd += ["write_part", part, file_path]
            ops_write += 1
            continue
        skipped.append(f"{fid} ({ftype}) part={part}: unhandled")

    cmd += ["set_active", "a", "power_off"]

    print(f"[+] writes : {ops_write}")
    print(f"[+] erases : {ops_erase}")
    print(f"[+] skipped: {len(skipped)}")
    for s in skipped:
        print(f"    - {s}")

    out_file = "/tmp/flash_cmd.sh"
    with open(out_file, "w") as f:
        f.write("#!/bin/bash\n")
        f.write("set -e\n")
        # Quote each arg
        quoted = []
        for a in cmd:
            if " " in a or '"' in a:
                a = '"' + a.replace('"', '\\"') + '"'
            quoted.append(a)
        f.write(" \\\n    ".join(quoted) + "\n")
    os.chmod(out_file, 0o755)
    print(f"[+] Command written to {out_file}")
    print(f"[+] Review it with: cat {out_file}")

if __name__ == "__main__":
    main()
