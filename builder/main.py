# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import socket
import sys
from os.path import isfile, join

from SCons.Script import (COMMAND_LINE_TARGETS, AlwaysBuild, Builder, Default,
                          DefaultEnvironment)

import click

#
# Helpers
#


def _get_board_f_flash(env):
    frequency = env.subst("$BOARD_F_FLASH")
    frequency = str(frequency).replace("L", "")
    return str(int(int(frequency) / 1000000)) + "m"


def _get_board_flash_mode(env):
    mode = env.subst("$BOARD_FLASH_MODE")
    if mode == "qio":
        return "dio"
    elif mode == "qout":
        return "dout"
    return mode


def _parse_size(value):
    if isinstance(value, int):
        return value
    elif value.isdigit():
        return int(value)
    elif value.startswith("0x"):
        return int(value, 16)
    elif value[-1].upper() in ("K", "M"):
        base = 1024 if value[-1].upper() == "K" else 1024 * 1024
        return int(value[:-1]) * base
    return value


def _parse_partitions(env):
    partitions_csv = env.subst("$PARTITIONS_TABLE_CSV")
    if not isfile(partitions_csv):
        sys.stderr.write("Could not find the file %s with partitions "
                         "table.\n" % partitions_csv)
        env.Exit(1)
        return

    result = []
    next_offset = 0
    with open(partitions_csv) as fp:
        for line in fp.readlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = [t.strip() for t in line.split(",")]
            if len(tokens) < 5:
                continue
            partition = {
                "name": tokens[0],
                "type": tokens[1],
                "subtype": tokens[2],
                "offset": tokens[3] or next_offset,
                "size": tokens[4],
                "flags": tokens[5] if len(tokens) > 5 else None
            }
            result.append(partition)
            next_offset = (_parse_size(partition['offset']) +
                           _parse_size(partition['size']))
    return result


def _update_max_upload_size(env):
    if not env.get("PARTITIONS_TABLE_CSV"):
        return
    sizes = [
        _parse_size(p['size']) for p in _parse_partitions(env)
        if p['type'] in ("0", "app")
    ]
    if sizes:
        env.BoardConfig().update("upload.maximum_size", max(sizes))


def _to_unix_slashes(path):
    return path.replace('\\', '/')

#
# SPIFFS helpers
#

def fetch_spiffs_size(env):
    spiffs = None
    for p in _parse_partitions(env):
        if p['type'] == "data" and p['subtype'] == "spiffs":
            spiffs = p
    if not spiffs:
        sys.stderr.write(
            env.subst("Could not find the `spiffs` section in the partitions "
                      "table $PARTITIONS_TABLE_CSV\n"))
        env.Exit(1)
        return
    env["SPIFFS_START"] = _parse_size(spiffs['offset'])
    env["SPIFFS_SIZE"] = _parse_size(spiffs['size'])
    env["SPIFFS_PAGE"] = int("0x100", 16)
    env["SPIFFS_BLOCK"] = int("0x1000", 16)

#
# OTA DATA helpers
#

def fetch_ota_data(env):
    otadata = None
    for p in _parse_partitions(env):
        if p['type'] == "data" and p['subtype'] == "ota":
            otadata = p
    if not otadata:
        sys.stderr.write(
            env.subst("Could not find the `OTADATA section in the partitions "
                      "table $PARTITIONS_TABLE_CSV\n"))
        env.Exit(1)
        return
    env["OTADATA_XSTART"] = hex(_parse_size(otadata['offset']))
    env["OTADATA_XSIZE"] = hex(_parse_size(otadata['size']))
#    env["OTADATA_XSTART"] = otadata['offset']
#    env["OTADATA_XSIZE"] = otadata['size']

def __fetch_spiffs_size(target, source, env):
    fetch_spiffs_size(env)
    return (target, source)

env = DefaultEnvironment()
platform = env.PioPlatform()

#def my_progress_function(node, *args, **kw):
#    print('Evaluating node %s' % node)
#Progress(my_progress_function, interval=5)

import sys
class ProgressCounter(object):
    count = 0
    def __call__(self, node, *args, **kw):
        self.count += 1
#        sys.stderr.write('Evaluated %s nodes\r' % self.count)
        print('Evaluated %s nodes\r' % self.count)

Progress(ProgressCounter(), interval=100)

#env.Decider('timestamp-newer')

env.Replace(
    __get_board_f_flash=_get_board_f_flash,
    __get_board_flash_mode=_get_board_flash_mode,

    AR="xtensa-lx106-elf-ar",
    AS="xtensa-lx106-elf-as",
    CC="xtensa-lx106-elf-gcc",
    CXX="xtensa-lx106-elf-g++",
    GDB="xtensa-lx106-elf-gdb",
#    OBJCOPY=join(platform.get_package_dir("tool-esptoolpy") or "", "esptool.py"),
#    OBJCOPY=join(platform.get_package_dir("framework-esp8266-rtos-sdk-master"), "components", "esptool_py", "esptool", "esptool.py"),
    OBJCOPY="xtensa-lx106-elf-objcopy",
    ESPTOOL=join("$FRAMEWORK_DIR", "components", "esptool_py", "esptool", "esptool.py"),
    RANLIB="xtensa-lx106-elf-ranlib",
    SIZETOOL="xtensa-lx106-elf-size",

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.irom0\.text|\.text|\.data|\.rodata|)\s+([0-9]+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.rodata|\.bss)\s+([0-9]+).*", 
#    SIZEPROGREGEXP=r"^(?:\.iram0\.text|\.iram0\.vectors|\.dram0\.data|\.flash\.text|\.flash\.rodata|)\s+([0-9]+).*",
#    SIZEDATAREGEXP=r"^(?:\.dram0\.data|\.dram0\.bss|\.noinit)\s+([0-9]+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD="$SIZETOOL -B -d $SOURCES",

    ERASEFLAGS=[
        "--chip", "esp8266",
        "--port", '"$UPLOAD_PORT"'
    ],
    ERASECMD='"$PYTHONEXE" "$ESPTOOL" $ERASEFLAGS erase_flash',

    MKSPIFFSTOOL="mkspiffs_${PIOPLATFORM}_${PIOFRAMEWORK}",
    PROGSUFFIX=".elf"
)

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

env.Append(
    # copy CCFLAGS to ASFLAGS (-x assembler-with-cpp mode)
    ASFLAGS=env.get("CCFLAGS", [])[:],

    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$PYTHONEXE" "$ESPTOOL"',
                "--chip", "esp8266",
                "elf2image",
                "--version", "3",
                "--flash_mode", "$BOARD_FLASH_MODE",
                "--flash_freq", "${__get_board_f_flash(__env__)}",
                "--flash_size", env.BoardConfig().get("upload.flash_size", "4MB"),
#                "--flash_size", env.BoardConfig().get("upload.flash_size", "detect"),
                "--output", "$TARGET",
                "$SOURCES"
            ]), "Building $TARGET"),
            suffix=".bin"
        ),
        DataToBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$MKSPIFFSTOOL"',
                "-c", "$SOURCES",
                "-p", "$SPIFFS_PAGE",
                "-b", "$SPIFFS_BLOCK",
                "-s", "$SPIFFS_SIZE",
                "$TARGET"
            ]), "Building SPIFFS image from '$SOURCES' directory to $TARGET"),
            emitter=__fetch_spiffs_size,
            source_factory=env.Dir,
            suffix=".bin"
        )
    )
)

if not env.get("PIOFRAMEWORK"):
    env.SConscript("frameworks/_bare.py", exports="env")

#
# Target: Build executable and linkable firmware or SPIFFS image
#

target_elf = env.BuildProgram()
if "nobuild" in COMMAND_LINE_TARGETS:
    if set(["uploadfs", "uploadfsota"]) & set(COMMAND_LINE_TARGETS):
        fetch_spiffs_size(env)
        target_firm = join("$BUILD_DIR", "spiffs.bin")
    else:
        target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
else:
    if set(["buildfs", "uploadfs", "uploadfsota"]) & set(COMMAND_LINE_TARGETS):
        target_firm = env.DataToBin(
            join("$BUILD_DIR", "spiffs"), "$PROJECTDATA_DIR")
        AlwaysBuild(target_firm)
        AlwaysBuild(env.Alias("buildfs", target_firm))
    else:
        target_firm = env.ElfToBin(
            join("$BUILD_DIR", "${PROGNAME}"), target_elf)

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

# update max upload size based on CSV file
if env.get("PIOMAINPROG"):
    env.AddPreAction(
        "checkprogsize",
        env.VerboseAction(
            lambda source, target, env: _update_max_upload_size(env),
            "Retrieving maximum program size $SOURCES"))
# remove after PIO Core 3.6 release
elif set(["checkprogsize", "upload"]) & set(COMMAND_LINE_TARGETS):
    _update_max_upload_size(env)

#
# Target: Print binary size
#

target_size = env.Alias("size", target_elf,
                        env.VerboseAction("$SIZEPRINTCMD",
                                          "Calculating size $SOURCE"))
AlwaysBuild(target_size)

#
# Target: Upload firmware or SPIFFS image
#

upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = env.BoardConfig().get("debug.tools", {})
upload_actions = []

if upload_protocol == "esptool":
    env.Replace(
        UPLOADER="$ESPTOOL",
#        UPLOADEROTA=join(
#            platform.get_package_dir("tool-espotapy") or "", "espota.py"),
        UPLOADERFLAGS=[
            "--chip", "esp8266",
            "--port", '"$UPLOAD_PORT"',
            "--baud", "$UPLOAD_SPEED",
            "--before", env['SDKCONFIG'].get('CONFIG_ESPTOOLPY_BEFORE', "default_reset"),
            "--after", env['SDKCONFIG'].get('CONFIG_ESPTOOLPY_AFTER', "hard_reset"),
            "write_flash", "--compress" if 'CONFIG_ESPTOOLPY_COMPRESSED' in env['SDKCONFIG'] else "",
            "--flash_mode", "${__get_board_flash_mode(__env__)}",
            "--flash_freq", "${__get_board_f_flash(__env__)}",
            "--flash_size", "detect"
#            "--flash_size", "${__get_flash_size(__env__)}"
        ],
        UPLOADEROTAFLAGS=[
            "--debug", "--progress", "-i", "$UPLOAD_PORT", "-p", "3232",
            "$UPLOAD_FLAGS"
        ],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS 0x10000 "$SOURCE"',
        UPLOADOTACMD='"$PYTHONEXE" "$UPLOADEROTA" $UPLOADEROTAFLAGS -f "$SOURCE"',
    )
    for image in env.get("FLASH_EXTRA_IMAGES", []):
        env.Append(UPLOADERFLAGS=[image[0], image[1]])

    if "_uploadfs" in COMMAND_LINE_TARGETS:
        env.Replace(
            UPLOADERFLAGS=[
                "--chip", "esp8266",
                "--port", '"$UPLOAD_PORT"',
                "--baud", "$UPLOAD_SPEED",
                "--before", "default_reset",
                "--after", "hard_reset",
                "write_flash", "-z",
                "--flash_mode", "$BOARD_FLASH_MODE",
                "--flash_size", "detect",
                "$SPIFFS_START"
            ],
            UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS $SOURCE',
        )
        env.Append(UPLOADEROTAFLAGS=["-s"])

    # Handle uploading via OTA
    ota_port = None
    if env.get("UPLOAD_PORT"):
        try:
            ota_port = socket.gethostbyname(env.get("UPLOAD_PORT"))
        except socket.error:
            pass
    if ota_port:
        env.Replace(UPLOADCMD="$UPLOADOTACMD")
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, click.style("Looking for upload port...",fg="green")),
        env.VerboseAction("$UPLOADCMD", click.style("Uploading $SOURCE", fg="green")),
    ]
    if 'CONFIG_PARTITION_TABLE_TWO_OTA' in env['SDKCONFIG']:
        fetch_ota_data(env)
        env.Append(ERASEFLAGS=[
            "--baud", "$UPLOAD_SPEED",
            "--after", "no_reset",
            "erase_region",
            "$OTADATA_XSTART", "$OTADATA_XSIZE",
           ],
        )
        upload_actions.insert(1, env.VerboseAction('"$PYTHONEXE" "$ESPTOOL" $ERASEFLAGS', click.style("Erase OTA DATA $OTADATA_XSTART $OTADATA_XSIZE", fg="green")))

elif upload_protocol == "httptool":
    print(platform.packages)
    uploader_dir = platform.get_package_dir("tool-curl-for-win") or ""
    print("HTTP", uploader_dir)
    uploader_url = env['SDKCONFIG']["CUSTOM_UPLOAD_HOST"]+env['SDKCONFIG']["CUSTOM_UPLOAD_URL"]+"?"+env['SDKCONFIG'].get("CUSTOM_UPLOAD_PARAM","")

    env.Replace(
        CUSTOM_UPLOAD_USER=env['SDKCONFIG']["CUSTOM_UPLOAD_USER"],
        CUSTOM_UPLOAD_PASS=env['SDKCONFIG']["CUSTOM_UPLOAD_PASS"],
        CUSTOM_UPLOAD_URL=uploader_url,
        CURL=join(uploader_dir, "bin", "curl.exe"),
        UPLOADER="$CURL",
        UPLOADERFLAGS=[
            "--digest",
            "-u", "$CUSTOM_UPLOAD_USER:$CUSTOM_UPLOAD_PASS",
            "--data-binary",
            '@"$PROJECT_DIR\\$SOURCE"',
            "$CUSTOM_UPLOAD_URL",
            "-k",
        ],
        UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS',
    )
    upload_actions = [
        env.VerboseAction("$UPLOADCMD", click.style("$UPLOADCMD Uploading $SOURCE $UPLOAD_URL", fg="green")),
    ]
#    print(env.Dump())
elif upload_protocol in debug_tools:
    openocd_dir = platform.get_package_dir("tool-openocd-esp32") or ""
    uploader_flags = ["-s", _to_unix_slashes(openocd_dir)]
    uploader_flags.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    uploader_flags.extend(["-c", 'program_esp32 {{$SOURCE}} 0x10000 verify'])
    for image in env.get("FLASH_EXTRA_IMAGES", []):
        uploader_flags.extend(
            ["-c", 'program_esp32 {{%s}} %s verify' % (
                _to_unix_slashes(image[1]), image[0])])
    uploader_flags.extend(["-c", "reset run; shutdown"])
    for i, item in enumerate(uploader_flags):
        if "$PACKAGE_DIR" in item:
            uploader_flags[i] = item.replace(
                "$PACKAGE_DIR", _to_unix_slashes(openocd_dir))

    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=uploader_flags,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias(["upload", "uploadfs"], target_firm, upload_actions))

#
# Target: Erase Flash
#

AlwaysBuild(
    env.Alias("erase", None, [
        env.VerboseAction(env.AutodetectUploadPort,
                          "Looking for serial port..."),
        env.VerboseAction("$ERASECMD", "Ready for erasing")
    ]))

#
# Default targets
#

Default([target_buildprog, target_size])
