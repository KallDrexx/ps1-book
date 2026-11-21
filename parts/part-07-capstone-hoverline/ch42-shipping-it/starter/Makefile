# Reader-facing wrapper around the CMake build.
#   make          the development disc: build/hoverline.cue (debug keys and readout on)
#   make run      boots it in PCSX-Redux
#   make release  the shippable disc and its papers in release/ (README 5)
#   make clean
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
SDK       ?= $(BOOK_ROOT)/.toolchain/opt/psn00bsdk
PYTHON    ?= $(or $(PS1BOOK_PYTHON),python3)
CMAKE_COMMON = -G Ninja -Wno-dev -DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake -DCMAKE_BUILD_TYPE=Release

all:
	cmake -S . -B build $(CMAKE_COMMON)
	cmake --build build
run: all
	$(BOOK_ROOT)/.toolchain/bin/pcsx-redux -iso build/hoverline.cue -run -fastboot
# TODO (README 5.1-5.5): the release. This placeholder builds a disc and copies it; it is not reproducible, pins no tool, and leaves out
# the manifest, the checksums and the papers.
release:
	cmake -S . -B build-release $(CMAKE_COMMON) -DHOVERLINE_RELEASE=ON
	cmake --build build-release
	mkdir -p release
	cp build-release/hoverline.bin build-release/hoverline.cue release/
	cp build-release/game.elf release/hoverline.elf
clean:
	$(RM) -r build build-release release
.PHONY: all run release clean
