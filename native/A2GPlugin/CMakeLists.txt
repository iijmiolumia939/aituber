cmake_minimum_required(VERSION 3.20)
cmake_policy(SET CMP0177 NEW)
project(A2GPlugin VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Build as DLL ─────────────────────────────────────────────────────────────
add_library(A2GPlugin SHARED
    A2GPlugin.cpp
)

target_include_directories(A2GPlugin PRIVATE .)

# ── Compiler flags ───────────────────────────────────────────────────────────
if(MSVC)
    # /MT      = static CRT (no separate vcruntime DLL needed next to Unity plugin)
    # /O2      = optimise for speed
    # /W4      = high warning level
    # /utf-8   = source and execution charset = UTF-8 (silences C4819)
    target_compile_options(A2GPlugin PRIVATE
        $<$<CONFIG:Release>:/MT /O2 /W4 /utf-8>
        $<$<CONFIG:Debug>:/MTd /Od /W4 /Zi /utf-8>
    )
    # Strip the lib-prefix on Windows (standard behaviour)
    set_target_properties(A2GPlugin PROPERTIES
        WINDOWS_EXPORT_ALL_SYMBOLS OFF
    )
endif()

# ── Post-build: copy DLL into Unity Plugins folder ───────────────────────────
# Resolve the Unity Plugins path relative to this CMakeLists.txt location:
#   native/A2GPlugin/  →  ../../AITuber/Assets/Plugins/x86_64/
set(UNITY_PLUGINS_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/../../AITuber/Assets/Plugins/x86_64")

add_custom_command(TARGET A2GPlugin POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "${UNITY_PLUGINS_DIR}"
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:A2GPlugin>"
        "${UNITY_PLUGINS_DIR}/A2GPlugin.dll"
    COMMENT "Copied A2GPlugin.dll -> Assets/Plugins/x86_64/"
)

# ── Optional: install target ──────────────────────────────────────────────────
install(TARGETS A2GPlugin
    RUNTIME DESTINATION "${UNITY_PLUGINS_DIR}"
)
install(FILES A2GPlugin.h
    DESTINATION "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
