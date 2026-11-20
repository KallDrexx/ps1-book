cmake_minimum_required(VERSION 3.21)

project(
	ch28
	LANGUAGES C
	VERSION   1.0.0
)

add_subdirectory(psxe)

psn00bsdk_add_executable(game GPREL main.c)
target_link_libraries(game PRIVATE psxe)
