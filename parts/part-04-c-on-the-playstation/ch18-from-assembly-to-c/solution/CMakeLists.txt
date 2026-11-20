cmake_minimum_required(VERSION 3.21)

project(
	ch18
	LANGUAGES C ASM
	VERSION   1.0.0
)

# One executable: C sources and the assembly routine are compiled separately
# (gcc for .c, gas via gcc for .s) and linked together.
psn00bsdk_add_executable(game GPREL main.c expand.c rgb555.s)
