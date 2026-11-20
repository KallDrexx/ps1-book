cmake_minimum_required(VERSION 3.21)

project(
	ch18_example
	LANGUAGES C ASM
	VERSION   1.0.0
)

psn00bsdk_add_executable(game GPREL main.c expand.c callback.s)
