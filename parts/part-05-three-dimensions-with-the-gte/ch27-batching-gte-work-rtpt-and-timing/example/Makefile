# Reader-facing wrapper around the CMake build. `make` builds, `make run` starts PCSX-Redux.
# `-interpreter`: the cycle counts this chapter quotes are those of the interpreter (the dynarec counts cycles differently).
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
SDK       ?= $(BOOK_ROOT)/.toolchain/opt/psn00bsdk

all:
	cmake -S . -B build -G Ninja -Wno-dev -DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake -DCMAKE_BUILD_TYPE=Release
	cmake --build build
run: all
	$(BOOK_ROOT)/.toolchain/bin/pcsx-redux -exe build/game.exe -run -fastboot -interpreter -stdout
clean:
	$(RM) -r build
.PHONY: all run clean
