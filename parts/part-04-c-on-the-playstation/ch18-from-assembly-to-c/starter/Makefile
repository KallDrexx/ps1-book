# Reader-facing wrapper around the CMake build. `make` builds, `make run` starts PCSX-Redux.
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
SDK       ?= $(BOOK_ROOT)/.toolchain/opt/psn00bsdk
CC        := $(SDK)/bin/mipsel-none-elf-gcc
# The flags the SDK uses (see lib/libpsn00b/cmake/libpsn00b.cmake), enough to compile one file to assembly.
ASMFLAGS  := -ffreestanding -march=r3000 -msoft-float -fno-pic -mno-abicalls

all:
	cmake -S . -B build -G Ninja -Wno-dev -DCMAKE_TOOLCHAIN_FILE=$(SDK)/lib/libpsn00b/cmake/sdk.cmake -DCMAKE_BUILD_TYPE=Release
	cmake --build build
run: all
	$(BOOK_ROOT)/.toolchain/bin/pcsx-redux -exe build/game.exe -run -fastboot
# `make asm` writes expand.O0.s and expand.O2.s: the same function, unoptimised and optimised.
asm:
	$(CC) -O0 -S $(ASMFLAGS) expand.c -o expand.O0.s
	$(CC) -O2 -S $(ASMFLAGS) expand.c -o expand.O2.s
clean:
	$(RM) -r build expand.O0.s expand.O2.s
.PHONY: all run clean asm
