cmake_minimum_required(VERSION 3.21)

project(
	ch27_example
	LANGUAGES C
	VERSION   1.0.0
)

# The book's engine library, straight from the reference copy.
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../../../../common/psxe psxe)

psn00bsdk_add_executable(game GPREL main.c)
target_link_libraries(game PRIVATE psxe)
