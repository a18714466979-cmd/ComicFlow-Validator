#!/usr/bin/env bash
# Build and stage the offline FFmpeg used by the desktop installers.
set -euo pipefail

if [[ $# != 4 || "$1" != --target || "$3" != --output ]]; then
    printf 'Usage: %s --target {macos|windows-x64|linux} --output DIRECTORY\n' "$0" >&2
    exit 2
fi

script="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
target="$2"
mkdir -p "$(dirname "$4")"
output="$(cd "$(dirname "$4")" && pwd)/$(basename "$4")"
if [[ -e "$output" || -L "$output" ]]; then
    printf 'FFmpeg output already exists: %s\n' "$output" >&2
    exit 2
fi

executable=ffmpeg
platform_flags=(--enable-static --disable-shared)
linker_flags=
case "$target" in
    macos)
        [[ "$(uname -s)" == Darwin ]]
        export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"
        ;;
    windows-x64)
        command -v x86_64-w64-mingw32-gcc >/dev/null
        executable=ffmpeg.exe
        linker_flags=" -static-libgcc"
        platform_flags+=(--enable-cross-compile --target-os=mingw32 --arch=x86_64
                         --cross-prefix=x86_64-w64-mingw32- --disable-pthreads)
        ;;
    linux)
        [[ "$(uname -s)" == Linux ]]
        ;;
    *)
        printf 'Unknown FFmpeg target: %s\n' "$target" >&2
        exit 2
        ;;
esac

ffmpeg_version=7.1.5
zlib_version=1.3.2
ffmpeg_archive="ffmpeg-$ffmpeg_version.tar.xz"
zlib_archive="zlib-$zlib_version.tar.gz"
ffmpeg_url="https://ffmpeg.org/releases/$ffmpeg_archive"
zlib_url="https://zlib.net/fossils/$zlib_archive"
jobs="$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu)"
build="$(mktemp -d)"
trap 'rm -rf -- "$build"' EXIT
cd "$build"

download() {
    local url="$1" path="$2" digest="$3"
    if [[ -f "$(dirname "$script")/$path" ]]; then
        cp "$(dirname "$script")/$path" "$path"
    else
        curl --fail --silent --show-error --location --retry 3 \
            --proto '=https' --proto-redir '=https' --output "$path" "$url"
    fi
    printf '%s  %s\n' "$digest" "$path" | shasum -a 256 -c
}

download "$ffmpeg_url" "$ffmpeg_archive" de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f
download "$zlib_url" "$zlib_archive" bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
tar -xf "$ffmpeg_archive"
tar -xf "$zlib_archive"
ffmpeg="$build/ffmpeg-$ffmpeg_version"
zlib="$build/zlib-$zlib_version"

# Build only the static zlib library, required by the PNG preview encoder.
(
    cd "$zlib"
    if [[ "$target" == windows-x64 ]]; then
        make -j "$jobs" -f win32/Makefile.gcc PREFIX=x86_64-w64-mingw32- libz.a
    else
        ./configure --static
        make -j "$jobs" libz.a
    fi
)

# Input decoders remain enabled for older AVI, MOV and ASF codecs. The app
# uses only local files and pipes, and FFmpeg only writes preview frames.
(
    cd "$ffmpeg"
    ./configure \
        --disable-autodetect --disable-network --disable-gpl --disable-version3 --disable-nonfree \
        --disable-debug --disable-doc --disable-ffplay --disable-ffprobe --disable-avdevice \
        --disable-x86asm --enable-zlib \
        --disable-demuxers --enable-demuxer=mov,matroska,avi,asf,mpegts,mpegps,mpegvideo,flv,m4v \
        --disable-protocols --enable-protocol=file,pipe \
        --disable-encoders --enable-encoder=png,rawvideo,wrapped_avframe \
        --disable-muxers --enable-muxer=image2pipe,null,rawvideo \
        --disable-filters --enable-filter=showinfo,scale,setsar,select,fps,format \
        "--extra-cflags=-I$zlib" "--extra-ldflags=-L$zlib$linker_flags" \
        "${platform_flags[@]}"
    grep -qx '#define CONFIG_ZLIB 1' config.h
    grep -qx '#define CONFIG_GPL 0' config.h
    grep -qx '#define CONFIG_NONFREE 0' config.h
    grep -qx '#define CONFIG_VERSION3 0' config.h
    make -j "$jobs" "$executable"
)

stage="$build/stage"
source_dir="$stage/ffmpeg-source"
mkdir -p "$source_dir"
install -m 755 "$ffmpeg/$executable" "$stage/$executable"
cp "$ffmpeg_archive" "$zlib_archive" "$script" "$source_dir/"
cp "$ffmpeg/COPYING.LGPLv2.1" "$source_dir/FFmpeg-COPYING.LGPLv2.1"
cp "$ffmpeg/LICENSE.md" "$source_dir/FFmpeg-LICENSE.md"
cp "$zlib/LICENSE" "$source_dir/zlib-LICENSE"
cat > "$source_dir/NOTICE.txt" <<EOF
This distribution includes FFmpeg $ffmpeg_version as a separate executable
to read and preview local video files.

FFmpeg is distributed under the GNU Lesser General Public License,
version 2.1 or later. This build disables GPL components, version-3-only
components and nonfree components. It links zlib $zlib_version statically.
The zlib copyright and license are included.

The unmodified source archives and the script used to build the executable
are supplied in this directory. Both upstream archives are also available at:
$ffmpeg_url
$zlib_url

Rebuild with: bash build-ffmpeg.sh --target $target --output ffmpeg-runtime
EOF
mv "$stage" "$output"
printf 'Built %s with corresponding source and licenses at %s\n' "$executable" "$output"
