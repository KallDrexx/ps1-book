cmake_minimum_required(VERSION 3.21)

project(
	ch21
	LANGUAGES C
	VERSION   1.0.0
)

# TODO (README 7.3): add_subdirectory(psxe), build `game` from main.c only, link psxe.
psn00bsdk_add_executable(game GPREL main.c)
