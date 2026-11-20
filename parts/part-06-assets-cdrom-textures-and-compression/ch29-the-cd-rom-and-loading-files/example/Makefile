# Reader-facing wrapper around the CMake build. `make` builds the disc image, `make run` boots it in PCSX-Redux.
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
SDK       ?= $(BOOK_ROOT)/.toolchain/opt/psn00bsdk

all:
	cmake -S . -B build -G Ninja -Wno-dev -DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake -DCMAKE_BUILD_TYPE=Release
	cmake --build build
run: all
	$(BOOK_ROOT)/.toolchain/bin/pcsx-redux -iso build/hoverline.cue -stdout -run -fastboot
clean:
	$(RM) -r build
.PHONY: all run clean
