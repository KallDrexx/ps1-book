# Reader-facing build for an armips project. Copy to <chapter>/starter/Makefile.
# Stages the sources next to a copy of the book's common/ directory (so that
# `.include "common/psxexe.inc"` works wherever the project lives), then runs armips.
NAME      ?= main
BOOK_ROOT ?= $(or $(PS1BOOK_ROOT),$(shell d="$(CURDIR)"; while [ "$$d" != / ] && [ ! -f "$$d/Summary.md" ]; do d="$$(dirname "$$d")"; done; echo "$$d"))
ARMIPS    ?= $(or $(shell command -v armips),$(BOOK_ROOT)/.toolchain/bin/armips)
STAGE     := build/stage

all: build/$(NAME).ps-exe
build/$(NAME).ps-exe: $(wildcard *.s *.inc *.bin)
	$(RM) -r $(STAGE)
	mkdir -p $(STAGE)
	cp $(filter-out build Makefile,$(wildcard *)) $(STAGE)/
	cp -r $(BOOK_ROOT)/common $(STAGE)/common
	cd $(STAGE) && $(ARMIPS) $(NAME).s -sym $(NAME).sym
	cp $(STAGE)/$(NAME).ps-exe $(STAGE)/$(NAME).sym build/
run: all
	$(BOOK_ROOT)/.toolchain/bin/pcsx-redux -exe build/$(NAME).ps-exe -run -fastboot
clean:
	$(RM) -r build
.PHONY: all run clean
