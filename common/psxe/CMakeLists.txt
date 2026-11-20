# psxe: the book's mini engine. Use it from a project's CMakeLists.txt:
#   add_subdirectory(psxe)
#   target_link_libraries(game PRIVATE psxe)
# The executable already links the SDK libraries (psxgpu, psxapi...), so the library only
# borrows the SDK's compiler flags (the `psn00bsdk` target).
add_library(psxe STATIC src/display.c src/ot.c src/gfx.c src/input.c)
target_include_directories(psxe PUBLIC include)
target_link_libraries(psxe PRIVATE psn00bsdk)
