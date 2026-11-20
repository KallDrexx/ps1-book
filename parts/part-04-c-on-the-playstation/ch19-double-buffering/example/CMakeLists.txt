cmake_minimum_required(VERSION 3.21)

project(
	ch19_example
	LANGUAGES C
	VERSION   1.0.0
)

psn00bsdk_add_executable(game GPREL main.c display.c)
