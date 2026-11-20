cmake_minimum_required(VERSION 3.21)

project(
	ch34
	LANGUAGES C
	VERSION   1.0.0
)

add_subdirectory(psxe)

psn00bsdk_add_executable(game GPREL main.c game.c object.c cull.c scene.c camera.c render.c track.c track_render.c title.c cdrom.c tim.c tpk.c shp.c)
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

# The whole asset set of the book comes from its generators: `make assets` runs mkassets.py into <build>/assets.
# The disc takes the files iso.xml lists from there: LOGO.TIM, PROPS.TPK, PYLON/ARCH/TOWER.SHP, SCENE.BIN, TRACK.TRK.
set(ASSETS ${CMAKE_CURRENT_BINARY_DIR}/assets)
set(ASSET_FILES ${ASSETS}/LOGO.TIM ${ASSETS}/PROPS.TPK ${ASSETS}/PYLON.SHP ${ASSETS}/ARCH.SHP ${ASSETS}/TOWER.SHP ${ASSETS}/SCENE.BIN ${ASSETS}/TRACK.TRK)
add_custom_command(
	OUTPUT  ${ASSET_FILES}
	COMMAND ${CMAKE_COMMAND} -E make_directory ${ASSETS}
	COMMAND ${PYTHON} ${BOOK_ROOT}/tools/assets/mkassets.py ${ASSETS}
	COMMENT "Generating the book's assets (tools/assets/mkassets.py)"
	VERBATIM
)
add_custom_target(assets DEPENDS ${ASSET_FILES})

# --- the disc image: hoverline.bin + hoverline.cue -----------------------------------------------
psn00bsdk_add_cd_image(
	iso hoverline iso.xml
	DEPENDS game assets system.cnf
)
