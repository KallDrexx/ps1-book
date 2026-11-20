# Chapter 11 answers

Run the book's `example/` program (it is meant to crash) and fill in the lines below.
Keep each `key: value` on one line.

exception_code: 4
bad_address: 0x8001003E
faulting_instruction: lw
explanation: lw needs an address that is a multiple of 4 but bytes+2 is not, so the R3000 raises an address error (AdEL) instead of loading; use lwr and lwl for data at unaligned addresses.
