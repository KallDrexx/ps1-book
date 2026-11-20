cmake_minimum_required(VERSION 3.21)

project(
	ch30
	LANGUAGES C
	VERSION   1.0.0
)

add_subdirectory(psxe)

psn00bsdk_add_executable(game GPREL main.c cdrom.c tim.c)
target_link_libraries(game PRIVATE psxe)

# --- assets: generated into <build>/assets, never committed --------------------------------------
# The book root holds tools/assets (found through $PS1BOOK_ROOT, or by walking up to Summary.md).
set(BOOK_ROOT "$ENV{PS1BOOK_ROOT}")
if(NOT BOOK_ROOT)
	set(_dir "${CMAKE_CURRENT_SOURCE_DIR}")
	while(NOT EXISTS "${_dir}/Summary.md" AND NOT _dir STREQUAL "/")
		cmake_path(GET _dir PARENT_PATH _dir)
	endwhile()
	set(BOOK_ROOT "${_dir}")
endif()
if(EXISTS "$ENV{PS1BOOK_TOOLCHAIN}/venv/bin/python")
	set(PYTHON "$ENV{PS1BOOK_TOOLCHAIN}/venv/bin/python")
elseif(EXISTS "${BOOK_ROOT}/.toolchain/venv/bin/python")
	set(PYTHON "${BOOK_ROOT}/.toolchain/venv/bin/python")
else()
	find_program(PYTHON python3 REQUIRED)
endif()

add_custom_command(
	OUTPUT  ${CMAKE_CURRENT_BINARY_DIR}/assets/CRATE.TIM ${CMAKE_CURRENT_BINARY_DIR}/assets/PANEL.TIM
	        ${CMAKE_CURRENT_BINARY_DIR}/assets/LOGO.TIM
	COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/assets
	COMMAND ${PYTHON} ${BOOK_ROOT}/tools/assets/mkassets.py ${CMAKE_CURRENT_BINARY_DIR}/assets
	COMMENT "Generating CRATE.TIM, PANEL.TIM, LOGO.TIM (tools/assets/mkassets.py)"
	VERBATIM
)
add_custom_target(
	assets DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/assets/CRATE.TIM ${CMAKE_CURRENT_BINARY_DIR}/assets/PANEL.TIM
	               ${CMAKE_CURRENT_BINARY_DIR}/assets/LOGO.TIM
)

# --- the disc image: hoverline.bin + hoverline.cue -----------------------------------------------
psn00bsdk_add_cd_image(
	iso hoverline iso.xml
	DEPENDS game assets system.cnf
)
