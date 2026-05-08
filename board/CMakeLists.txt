cmake_minimum_required(VERSION 3.16)

project(remote_vkm_receiver LANGUAGES CXX)

add_executable(remote-vkm-receiver
    src/main.cpp
)

target_compile_features(remote-vkm-receiver PRIVATE cxx_std_17)
target_compile_options(remote-vkm-receiver PRIVATE -Wall -Wextra -Wpedantic)
