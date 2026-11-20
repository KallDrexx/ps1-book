cmake_minimum_required(VERSION 3.21)

project(
	ch18
	LANGUAGES C ASM
	VERSION   1.0.0
)

# TODO: add rgb555.s to this list so the assembly routine is assembled and linked.
psn00bsdk_add_executable(game GPREL main.c expand.c)
