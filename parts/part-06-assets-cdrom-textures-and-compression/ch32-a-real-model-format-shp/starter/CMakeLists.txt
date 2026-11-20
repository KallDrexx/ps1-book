cmake_minimum_required(VERSION 3.21)

project(
	ch32
	LANGUAGES C
	VERSION   1.0.0
)

add_subdirectory(psxe)

psn00bsdk_add_executable(game GPREL main.c cdrom.c tim.c tpk.c shp.c)
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

# SHIP.SHP (the model) and SHIP.TPK (its three textures) come from the book's generators: `make assets`.
set(ASSETS ${CMAKE_CURRENT_BINARY_DIR}/assets)
add_custom_command(
	OUTPUT  ${ASSETS}/SHIP.SHP ${ASSETS}/SHIP.TPK
	COMMAND ${CMAKE_COMMAND} -E make_directory ${ASSETS}
	COMMAND ${PYTHON} ${BOOK_ROOT}/tools/assets/mkassets.py ${ASSETS}
	COMMENT "Generating SHIP.SHP and SHIP.TPK (tools/assets/mkassets.py)"
	VERBATIM
)
add_custom_target(assets DEPENDS ${ASSETS}/SHIP.SHP ${ASSETS}/SHIP.TPK)

# --- the disc image: hoverline.bin + hoverline.cue -----------------------------------------------
psn00bsdk_add_cd_image(
	iso hoverline iso.xml
	DEPENDS game assets system.cnf
)
