# Reader-facing build for the three Bug Hunt programs: bug1, bug2, bug3.
# Stages the sources next to a copy of the book's common/ directory (so that
# `.include "common/psxexe.inc"` works wherever the project lives), then runs armips once per program.
#   make                 build all three
#   make run1 (run2...)  build one and open it in PCSX-Redux with the debugger on
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
ARMIPS    ?= $(or $(shell command -v armips),$(BOOK_ROOT)/.toolchain/bin/armips)
REDUX     ?= $(BOOK_ROOT)/.toolchain/bin/pcsx-redux
PROGS     := bug1 bug2 bug3
STAGE     := build/stage

all: $(PROGS:%=build/%.ps-exe)
build/%.ps-exe: %.s $(wildcard *.inc)
	mkdir -p build
	$(RM) -r $(STAGE)
	mkdir -p $(STAGE)
	cp $(filter-out build Makefile,$(wildcard *)) $(STAGE)/
	cp -r $(BOOK_ROOT)/common $(STAGE)/common
	cd $(STAGE) && $(ARMIPS) $*.s -sym $*.sym
	cp $(STAGE)/$*.ps-exe $(STAGE)/$*.sym build/
run%: build/bug%.ps-exe
	$(REDUX) -exe build/bug$*.ps-exe -run -fastboot -interpreter -debugger
clean:
	$(RM) -r build
.PHONY: all clean
